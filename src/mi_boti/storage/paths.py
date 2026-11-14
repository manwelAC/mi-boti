"""Confined local paths and private data-root preparation."""

import csv
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess

from ..domain.errors import StorageError

DATA_CHILDREN = frozenset({
    "mi_boti.sqlite3", "mi_boti.sqlite3-wal", "mi_boti.sqlite3-shm", "mi_boti.sqlite3-journal",
    "deployment.lock", "artifacts", "backups", "datasets", "exports", "logs", "tmp", "verification",
})


def reject_links(path: Path) -> None:
    """Inspect the original absolute path before resolve can hide a junction."""
    absolute = Path(os.path.abspath(path))
    for part in (*reversed(absolute.parents), absolute):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise StorageError("Symbolic links and reparse points are not allowed in storage paths.")


def confined(root: Path, relative: str | Path) -> Path:
    value = Path(relative)
    if value.is_absolute() or value.drive or not value.parts or any(x in {"..", "."} for x in value.parts):
        raise StorageError("Expected a relative path inside the data directory.")
    # Backslashes and drive syntax must not become traversal on a different OS.
    if any(x in str(relative) for x in ("\x00", ":")) or ".." in str(relative).replace("\\", "/").split("/"):
        raise StorageError("Unsafe storage path.")
    reject_links(root)
    target = root / value
    reject_links(target)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        raise StorageError("Storage path escapes the data directory.") from None
    return target


def _restrict_permissions(root: Path) -> None:
    if os.name != "nt":
        root.chmod(0o700)
        return
    try:
        identity = subprocess.run(
            ["whoami.exe", "/user", "/fo", "csv", "/nh"], check=True,
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sid = next(csv.reader(io.StringIO(identity.stdout)))[1]
        if not sid.startswith("S-1-") or any(c not in "S-0123456789" for c in sid):
            raise ValueError
        subprocess.run(
            ["icacls.exe", str(root), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
            check=True, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, ValueError, IndexError, StopIteration, subprocess.SubprocessError):
        raise StorageError("Cannot restrict data-directory permissions to the service account and SYSTEM.") from None


def ensure_disk_space(root: Path, minimum_mib: int, additional_bytes: int = 0) -> None:
    if shutil.disk_usage(root).free < minimum_mib * 1024 * 1024 + additional_bytes:
        raise StorageError("Insufficient free disk space for safe storage work.")


def prepare_data_root(path: Path, *, minimum_mib: int = 500) -> Path:
    reject_links(path)
    absolute = path.resolve()
    if absolute in {Path(absolute.anchor), Path.home().resolve(), Path.cwd().resolve()}:
        raise StorageError("Use a dedicated application data directory.")
    if absolute.exists():
        if not absolute.is_dir() or any(p.name not in DATA_CHILDREN for p in absolute.iterdir()):
            raise StorageError("The selected data directory contains unrelated files.")
        for entry in absolute.iterdir():
            reject_links(entry)
    try:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
        _restrict_permissions(absolute)
        ensure_disk_space(absolute, minimum_mib)
        for folder in ("artifacts", "backups", "datasets", "exports", "logs", "tmp", "verification"):
            confined(absolute, folder).mkdir(exist_ok=True, mode=0o700)
        return absolute
    except OSError:
        raise StorageError("Cannot prepare writable private application storage.") from None
