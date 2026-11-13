"""OS-held exclusive deployment lock; stale files are never proof of ownership."""

import os
from pathlib import Path

from .paths import reject_links
from ..domain.errors import LockError


class DeploymentLock:
    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self):
        if self._file is not None:
            raise LockError("Deployment lock is already held by this instance.")
        reject_links(self.path)
        handle = self.path.open("a+b")
        try:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise LockError("Another process holds this application's data directory.") from None
        self._file = handle
        return self

    def release(self):
        if self._file is None:
            return
        handle, self._file = self._file, None
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()
