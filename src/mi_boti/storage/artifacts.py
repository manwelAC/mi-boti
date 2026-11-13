"""Generated artifact paths, atomic file writes and immutable content hashes."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from ..domain.errors import StorageError
from ..domain.values import utc_now
from .paths import confined, ensure_disk_space


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    relative_path: str
    sha256: str
    size_bytes: int


class ArtifactStore:
    def __init__(self, root: Path, database, *, minimum_disk_mib: int = 500, retention_days=None):
        self.root, self.database, self.minimum_disk_mib = root, database, minimum_disk_mib
        self.retention_days = dict(retention_days or {"RESEARCH": 30, "EXPORT": 7, "VERIFICATION": 30})
        if any(type(days) is not int or days <= 0 for days in self.retention_days.values()):
            raise StorageError("Artifact retention must use positive day limits.")

    def put(self, content: bytes, *, media_type: str = "text/plain", retention_class="RESEARCH", expires_at: str | None = None) -> ArtifactRef:
        if not isinstance(content, bytes) or len(content) > 2097152:
            raise StorageError("Artifact must be bytes within the 2 MiB storage limit.")
        if media_type not in {"text/plain", "text/csv", "application/json"}:
            raise StorageError("Artifact media type is not supported.")
        if retention_class not in self.retention_days:
            raise StorageError("Unknown artifact retention class.")
        if expires_at is None:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=self.retention_days[retention_class])).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            try:
                parsed_expiry = datetime.strptime(expires_at, "%Y-%m-%dT%H:%M:%S.%fZ")
                if parsed_expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != expires_at:
                    raise ValueError
            except (TypeError, ValueError):
                raise StorageError("Artifact expiry must be a canonical UTC timestamp.") from None
        ensure_disk_space(self.root, self.minimum_disk_mib, len(content))
        identifier = str(uuid4())
        relative = f"artifacts/{identifier}/{uuid4().hex}.txt"
        target = confined(self.root, relative)
        temporary = target.with_suffix(".partial")
        target.parent.mkdir(mode=0o700)
        digest = hashlib.sha256(content).hexdigest()
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO artifacts(id,relative_path,sha256,bytes,media_type,created_at,expires_at,state) VALUES (?,?,?,?,?,?,?,'PRESENT')",
                    (identifier, relative, digest, len(content), media_type, utc_now(), expires_at),
                )
            return ArtifactRef(identifier, relative, digest, len(content))
        except OSError:
            raise StorageError("Could not write the artifact safely.") from None
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, artifact_id: str) -> bytes:
        row = self.database.connection.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if row is None or row["state"] != "PRESENT":
            raise StorageError("Artifact is not available.")
        path = confined(self.root, row["relative_path"])
        try:
            if path.stat().st_size > 2097152:
                raise StorageError("Artifact exceeds its storage limit.")
            content = path.read_bytes()
        except FileNotFoundError:
            with self.database.transaction() as connection:
                connection.execute("UPDATE artifacts SET state='MISSING' WHERE id=?", (artifact_id,))
            raise StorageError("Artifact file is missing; provenance remains in the database.") from None
        except OSError:
            raise StorageError("Artifact file is not readable.") from None
        if len(content) != row["bytes"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
            raise StorageError("Artifact content failed integrity validation.")
        return content

    def cleanup_orphans(self, *, max_age_seconds: int = 86400, now: float | None = None, scan_limit: int = 1000) -> int:
        """Remove only old, generated, unreferenced files in a bounded scan."""
        if max_age_seconds <= 0 or scan_limit <= 0:
            raise StorageError("Orphan cleanup requires positive bounds.")
        cutoff = (time.time() if now is None else now) - max_age_seconds
        count = scanned = 0
        base = confined(self.root, "artifacts")
        for directory in base.iterdir():
            scanned += 1
            if scanned > scan_limit:
                break
            if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", directory.name):
                continue
            directory = confined(self.root, Path("artifacts") / directory.name)
            if not directory.is_dir():
                continue
            for file in directory.iterdir():
                scanned += 1
                if scanned > scan_limit:
                    return count
                if not re.fullmatch(r"[0-9a-f]{32}\.(?:partial|txt)", file.name):
                    continue
                relative = file.relative_to(self.root).as_posix()
                file = confined(self.root, relative)
                if not file.is_file() or file.stat().st_mtime >= cutoff:
                    continue
                referenced = self.database.connection.execute(
                    "SELECT 1 FROM artifacts WHERE relative_path=?", (relative,),
                ).fetchone()
                if referenced is None:
                    file.unlink()
                    count += 1
            if not any(directory.iterdir()):
                directory.rmdir()
        return count
