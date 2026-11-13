"""Explicit transactions, immutable migration checksums and guild binding."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
import sqlite3
import threading

from ..domain.errors import DatabaseError, MigrationError
from ..domain.values import snowflake, utc_now
from ..storage.backup import create_verified_copy
from ..storage.paths import reject_links


@dataclass(frozen=True)
class Migration:
    version: int
    sql: str
    checksum: str


def read_migrations(directory: Path | None = None) -> tuple[Migration, ...]:
    resource = directory if directory is not None else files("mi_boti").joinpath("migrations")
    try:
        manifest = json.loads(resource.joinpath("manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, list) or not manifest:
            raise ValueError
        result = []
        for expected, entry in enumerate(manifest, start=1):
            if set(entry) != {"version", "file", "sha256"} or type(entry["version"]) is not int or entry["version"] != expected:
                raise ValueError
            if not re.fullmatch(rf"{expected:04d}_[a-z_]+\.sql", entry["file"]):
                raise ValueError
            raw = resource.joinpath(entry["file"]).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != entry["sha256"]:
                raise ValueError
            result.append(Migration(expected, raw.decode("utf-8"), digest))
        sql_names = {p.name for p in resource.iterdir() if p.name.endswith(".sql")}
        if sql_names != {entry["file"] for entry in manifest}:
            raise ValueError
        return tuple(result)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        raise MigrationError("Migration manifest or SQL checksum is invalid.") from None


def _statements(sql: str):
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip() and not all(line.strip().startswith("--") for line in pending.splitlines() if line.strip()):
        raise MigrationError("Migration contains an incomplete SQL statement.")


class Database:
    def __init__(self, path: Path, *, busy_timeout_ms: int = 5000):
        reject_links(path)
        self.path = path
        self._write_lock = threading.RLock()
        try:
            self.connection = sqlite3.connect(path, isolation_level=None, timeout=busy_timeout_ms / 1000)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            if self.connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError
        except sqlite3.Error:
            if hasattr(self, "connection"):
                self.connection.close()
            raise DatabaseError("Cannot open a valid application database.") from None

    @contextmanager
    def transaction(self):
        with self._write_lock:
            if self.connection.in_transaction:
                raise DatabaseError("Nested write transactions are not supported.")
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                yield self.connection
                self.connection.execute("COMMIT")
            except BaseException:
                if self.connection.in_transaction:
                    self.connection.execute("ROLLBACK")
                raise

    def migrate(self, *, directory: Path | None = None, minimum_disk_mib: int = 500) -> int:
        migrations = read_migrations(directory)
        with self._write_lock:
            names = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if names and "schema_migrations" not in names:
                raise MigrationError("Existing database has no recognized migration history.")
            rows = self.connection.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall() if names else []
            if len(rows) > len(migrations) or self.connection.execute("PRAGMA user_version").fetchone()[0] > len(migrations):
                raise MigrationError("Database schema is newer than this application.")
            for expected, row in enumerate(rows, start=1):
                if row[0] != expected or row[1] != migrations[expected - 1].checksum:
                    raise MigrationError("Applied migration history or checksum does not match.")
            if self.connection.execute("PRAGMA user_version").fetchone()[0] != len(rows):
                raise MigrationError("Database schema version and migration ledger disagree.")
            if self.connection.execute("PRAGMA foreign_key_check").fetchall():
                raise MigrationError("Existing database has foreign-key violations.")
            pending = migrations[len(rows):]
            if pending and rows:
                create_verified_copy(self.connection, self.path.parent / "backups", minimum_mib=minimum_disk_mib)
            for migration in pending:
                try:
                    with self.transaction() as connection:
                        for statement in _statements(migration.sql):
                            bare = re.sub(r"(?m)^\s*--[^\n]*", "", statement).lstrip()
                            if not re.match(r"(?i)(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE)\b", bare):
                                raise MigrationError("Migration contains a prohibited transaction or pragma command.")
                            connection.execute(statement)
                        connection.execute("INSERT INTO schema_migrations(version,checksum,applied_at) VALUES (?,?,?)",
                                           (migration.version, migration.checksum, utc_now()))
                        if connection.execute("PRAGMA foreign_key_check").fetchall():
                            raise MigrationError("Migration produced foreign-key violations.")
                        connection.execute(f"PRAGMA user_version={migration.version}")
                except sqlite3.Error:
                    raise MigrationError("Migration failed; its changes were rolled back.") from None
            return len(migrations)

    def bind_guild(self, guild_id: str) -> None:
        snowflake(guild_id)
        with self.transaction() as connection:
            row = connection.execute("SELECT guild_id FROM deployment WHERE id=1").fetchone()
            if row and row[0] != guild_id:
                raise DatabaseError("Database is bound to another Discord guild.")
            if not row:
                connection.execute("INSERT INTO deployment(id,guild_id,created_at) VALUES (1,?,?)", (guild_id, utc_now()))

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
