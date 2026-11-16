"""A consistent, validated SQLite copy. Expanded artifact manifests come later."""

from dataclasses import dataclass
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from ..domain.errors import StorageError
from .paths import reject_links, ensure_disk_space


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    sha256: str
    size_bytes: int
    schema_version: int
    guild_id: str | None


def _read_only(path: Path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None)


def _seal_copy(connection):
    """Publish a standalone copy, without a WAL sidecar dependency."""
    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint and checkpoint[0] != 0:
        raise StorageError("Could not checkpoint the temporary database copy.")
    if connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() != "delete":
        raise StorageError("Could not finalize a standalone database copy.")


def _remove_temporary_database(path):
    # Only our generated temporary filename and its exact SQLite companions.
    for suffix in ("", "-wal", "-shm", "-journal"):
        item = Path(str(path) + suffix)
        reject_links(item)
        item.unlink(missing_ok=True)


def verify_copy(path: Path, *, expected_sha256: str | None = None, expected_guild: str | None = None) -> BackupInfo:
    reject_links(path)
    try:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise StorageError("Backup checksum does not match.")
        with closing(_read_only(path)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise StorageError("Backup database integrity check failed.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise StorageError("Backup foreign-key check failed.")
            from ..repositories.research_integrity import verify_research_integrity
            verify_research_integrity(connection)
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            has_binding = connection.execute("SELECT 1 FROM sqlite_master WHERE name='deployment' AND type='table'").fetchone()
            row = connection.execute("SELECT guild_id FROM deployment WHERE id=1").fetchone() if has_binding else None
            guild = row[0] if row else None
            if expected_guild is not None and guild != expected_guild:
                raise StorageError("Backup belongs to a different or unbound deployment.")
        return BackupInfo(path, digest, path.stat().st_size, version, guild)
    except (OSError, sqlite3.Error):
        raise StorageError("Cannot verify a readable, consistent SQLite backup.") from None


def create_verified_copy(source: sqlite3.Connection, directory: Path, *, minimum_mib: int = 500, timeout_seconds: int = 30) -> BackupInfo:
    if source.in_transaction:
        raise StorageError("Commit or roll back active writes before backing up this connection.")
    reject_links(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ensure_disk_space(directory, minimum_mib)
    identifier = uuid4().hex
    temporary = directory / (identifier + ".partial")
    final = directory / (identifier + ".sqlite3")
    deadline = time.monotonic() + timeout_seconds

    def progress(*_):
        if time.monotonic() >= deadline:
            raise StorageError("Backup exceeded its execution deadline.")

    try:
        with closing(sqlite3.connect(temporary, isolation_level=None)) as destination:
            source.backup(destination, pages=128, progress=progress, sleep=0.01)
            _seal_copy(destination)
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        verify_copy(temporary)
        os.replace(temporary, final)
        return verify_copy(final)
    except (OSError, sqlite3.Error):
        raise StorageError("Could not create a verified database copy.") from None
    finally:
        _remove_temporary_database(temporary)


def restore_verified_copy(info: BackupInfo, destination: Path, *, expected_guild: str, supported_version: int) -> None:
    """Owner maintenance primitive: destination must be a new file, never live DB."""
    reject_links(destination)
    if destination.exists() or not destination.parent.is_dir():
        raise StorageError("Restore requires a new database file in an existing private data directory.")
    verified = verify_copy(info.path, expected_sha256=info.sha256, expected_guild=expected_guild)
    if verified.schema_version != supported_version:
        raise StorageError("Backup schema requires explicit migration compatibility review.")
    temporary = destination.with_name(uuid4().hex + ".partial")
    try:
        with closing(_read_only(info.path)) as source, closing(sqlite3.connect(temporary)) as output:
            source.backup(output)
            _seal_copy(output)
        verify_copy(temporary, expected_guild=expected_guild)
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        # Same-directory atomic, no-clobber publication on NTFS/POSIX filesystems.
        # Fail closed on a filesystem without hard-link support.
        os.link(temporary, destination)
    except (OSError, sqlite3.Error):
        raise StorageError("Could not restore into the new data directory.") from None
    finally:
        _remove_temporary_database(temporary)
