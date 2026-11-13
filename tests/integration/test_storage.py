from dataclasses import replace
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from conftest import business
from mi_boti.domain.errors import LockError, StorageError
from mi_boti.storage.artifacts import ArtifactStore
from mi_boti.storage.backup import create_verified_copy, verify_copy, restore_verified_copy
from mi_boti.storage.lock import DeploymentLock
from mi_boti.storage.paths import confined, prepare_data_root
from mi_boti.repositories.database import Database


def test_deployment_lock_is_exclusive_and_released_after_process_death(tmp_path):
    lockfile = tmp_path / "deployment.lock"
    script = "from pathlib import Path; from mi_boti.storage.lock import DeploymentLock; import sys; lock=DeploymentLock(Path(sys.argv[1])).acquire(); print('READY',flush=True); sys.stdin.read()"
    proc = subprocess.Popen([sys.executable, "-c", script, str(lockfile)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        with pytest.raises(LockError):
            DeploymentLock(lockfile).acquire()
    finally:
        proc.terminate()
        proc.communicate(timeout=10)
    with DeploymentLock(lockfile):
        pass


@pytest.mark.parametrize("relative", ["../outside", "nested/../../outside", "C:\\outside", "/outside", "bad\x00path"])
def test_traversal_is_rejected(tmp_path, relative):
    with pytest.raises(StorageError):
        confined(tmp_path, relative)


def test_real_junction_or_symlink_cannot_escape(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    junction = root / "escape"
    if os.name == "nt":
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True)
    else:
        junction.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(StorageError):
            confined(root, "escape/contact.txt")
        assert not (outside / "contact.txt").exists()
    finally:
        if os.name == "nt":
            junction.rmdir()
        else:
            junction.unlink()
    assert outside.is_dir()


def test_data_root_refuses_unrelated_files_and_checks_disk_floor(tmp_path, monkeypatch):
    root = tmp_path / "private-data"
    prepared = prepare_data_root(root, minimum_mib=1)
    assert (prepared / "logs").is_dir()
    (prepared / "unrelated.txt").write_text("preserve me")
    with pytest.raises(StorageError, match="unrelated"):
        prepare_data_root(root, minimum_mib=1)
    from mi_boti.storage import paths
    monkeypatch.setattr(paths.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 0})())
    with pytest.raises(StorageError, match="Insufficient"):
        paths.ensure_disk_space(root, 1)


def test_artifact_hash_missing_file_and_escape_protection(database, tmp_path):
    root = tmp_path / "artifact-data"
    (root / "artifacts").mkdir(parents=True)
    store = ArtifactStore(root, database, minimum_disk_mib=1)
    artifact = store.put(b"Observed public services", media_type="text/plain")
    row = database.connection.execute("SELECT expires_at FROM artifacts WHERE id=?", (artifact.id,)).fetchone()
    assert row[0] is not None
    assert store.read(artifact.id) == b"Observed public services"
    path = root / artifact.relative_path
    path.write_bytes(b"tampered")
    with pytest.raises(StorageError, match="integrity"):
        store.read(artifact.id)
    path.unlink()
    with pytest.raises(StorageError, match="missing"):
        store.read(artifact.id)
    assert database.connection.execute("SELECT state FROM artifacts WHERE id=?", (artifact.id,)).fetchone()[0] == "MISSING"
    database.connection.execute("UPDATE artifacts SET state='PRESENT',relative_path='../outside.txt' WHERE id=?", (artifact.id,))
    with pytest.raises(StorageError):
        store.read(artifact.id)


def test_verified_wal_copy_restore_and_tamper_rejection(database, tmp_path):
    with database.transaction() as c:
        company = business(c)
    backup = create_verified_copy(database.connection, tmp_path / "backups", minimum_mib=1)
    assert backup.schema_version == 1
    verified = verify_copy(backup.path, expected_sha256=backup.sha256, expected_guild="123456789012345678")
    with closing(sqlite3.connect(backup.path)) as c:
        assert c.execute("SELECT name FROM businesses WHERE id=?", (company,)).fetchone()[0] == "Fixture"
    restore = tmp_path / "restored.sqlite3"
    restore_verified_copy(verified, restore, expected_guild="123456789012345678", supported_version=1)
    with Database(restore) as recovered:
        assert recovered.migrate() == 1
        assert recovered.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 1
        assert recovered.connection.execute("SELECT count(*) FROM jobs WHERE state='RUNNING'").fetchone()[0] == 0
    with pytest.raises(StorageError, match="new database"):
        restore_verified_copy(verified, restore, expected_guild="123456789012345678", supported_version=1)
    with pytest.raises(StorageError):
        verify_copy(backup.path, expected_sha256="0" * 64)
    with pytest.raises(StorageError):
        verify_copy(backup.path, expected_guild="999")
    with pytest.raises(StorageError):
        restore_verified_copy(verified, tmp_path / "bad-version.sqlite3", expected_guild="123456789012345678", supported_version=2)


def test_snapshot_includes_committed_wal_and_excludes_uncommitted_changes(database, tmp_path):
    # A second connection can have an uncommitted write while the first performs
    # an online backup. The copy must capture only the committed snapshot.
    with database.transaction() as c:
        company = business(c)
    with Database(database.path) as other:
        other.connection.execute("BEGIN IMMEDIATE")
        other.connection.execute("UPDATE businesses SET name='uncommitted' WHERE id=?", (company,))
        try:
            backup = create_verified_copy(database.connection, tmp_path / "snapshot", minimum_mib=1)
        finally:
            other.connection.execute("ROLLBACK")
    with closing(sqlite3.connect(backup.path)) as c:
        assert c.execute("SELECT name FROM businesses WHERE id=?", (company,)).fetchone()[0] == "Fixture"


def test_backup_rejects_full_disk_without_creating_a_snapshot(database, tmp_path, monkeypatch):
    from mi_boti.storage import paths
    monkeypatch.setattr(paths.shutil, "disk_usage", lambda _: type("Usage", (), {"free": 0})())
    directory = tmp_path / "full-disk"
    with pytest.raises(StorageError):
        create_verified_copy(database.connection, directory, minimum_mib=1)
    assert not list(directory.glob("*.sqlite3"))


def test_failed_artifact_commit_leaves_an_old_orphan_that_can_be_cleaned(database, tmp_path, monkeypatch):
    from contextlib import contextmanager
    root = tmp_path / "orphan-data"
    (root / "artifacts").mkdir(parents=True)
    store = ArtifactStore(root, database, minimum_disk_mib=1)
    preserved = store.put(b"committed evidence")
    original_transaction = database.transaction

    @contextmanager
    def fail_commit():
        raise RuntimeError("simulated crash before metadata commit")
        yield

    monkeypatch.setattr(database, "transaction", fail_commit)
    with pytest.raises(RuntimeError):
        store.put(b"uncommitted orphan")
    monkeypatch.setattr(database, "transaction", original_transaction)
    files = list((root / "artifacts").glob("*/*.txt"))
    assert len(files) == 2
    for file in files:
        os.utime(file, (1, 1))
    assert store.cleanup_orphans(now=100000, max_age_seconds=86400) == 1
    assert store.read(preserved.id) == b"committed evidence"
    assert store.cleanup_orphans(now=100000, max_age_seconds=86400) == 0


def test_partial_artifact_write_does_not_publish_metadata(database, tmp_path, monkeypatch):
    root = tmp_path / "interrupted-data"
    (root / "artifacts").mkdir(parents=True)
    store = ArtifactStore(root, database, minimum_disk_mib=1)
    import mi_boti.storage.artifacts as artifacts
    monkeypatch.setattr(artifacts.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk fixture")))
    with pytest.raises(StorageError):
        store.put(b"interrupted")
    assert database.connection.execute("SELECT count(*) FROM artifacts").fetchone()[0] == 0
    assert list((root / "artifacts").glob("*/*.partial")) == []


def test_invalid_artifact_policy_is_rejected_before_writing(database, tmp_path):
    root = tmp_path / "policy-data"
    (root / "artifacts").mkdir(parents=True)
    store = ArtifactStore(root, database, minimum_disk_mib=1)
    for options in [{"retention_class": "UNKNOWN"}, {"expires_at": "bad"},
                    {"expires_at": "2026-11-14T00:00:00.1Z"}, {"media_type": "text/html"}]:
        with pytest.raises(StorageError):
            store.put(b"fixture", **options)
    assert list((root / "artifacts").iterdir()) == []


def test_backup_failure_never_replaces_a_verified_copy(database, tmp_path, monkeypatch):
    directory = tmp_path / "protected-backups"
    verified = create_verified_copy(database.connection, directory, minimum_mib=1)
    import mi_boti.storage.backup as module
    original = module.verify_copy
    monkeypatch.setattr(module, "verify_copy", lambda *_args, **_kwargs: (_ for _ in ()).throw(StorageError("invalid fixture")))
    with pytest.raises(StorageError):
        create_verified_copy(database.connection, directory, minimum_mib=1)
    assert len(list(directory.glob("*.sqlite3"))) == 1
    assert list(directory.glob("*.partial")) == []
    monkeypatch.setattr(module, "verify_copy", original)
    assert verify_copy(verified.path, expected_sha256=verified.sha256).sha256 == verified.sha256
    database.connection.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(StorageError, match="active writes"):
            create_verified_copy(database.connection, directory, minimum_mib=1)
    finally:
        database.connection.execute("ROLLBACK")
