from pathlib import Path
import sqlite3

import pytest

from test_evidence_reader import seed_evidence
from test_research_evidence import research_job
from mi_boti.repositories.database import Database
from mi_boti.repositories.research import begin_run
from mi_boti.repositories.research_integrity import verify_research_integrity
from mi_boti.storage.backup import create_verified_copy, restore_verified_copy
from mi_boti.jobs.discovery import recover_interrupted_work
from mi_boti.jobs.research import claim
from mi_boti.domain.errors import StorageError
from mi_boti.storage.paths import prepare_data_root


def test_research_backup_restore_preserves_evidence_and_interrupts_pending_work(database, tmp_path):
    identifier, _ = seed_evidence(database)
    original = tuple(database.connection.execute("SELECT * FROM evidence WHERE id=?", (identifier,)).fetchone())
    business = original[1]
    active_job, token = research_job(database, business)
    active_run = begin_run(database, active_job, token)
    queued_job, _ = research_job(database, business)
    database.connection.execute("UPDATE jobs SET state='QUEUED',lease_token=NULL,lease_expires_at=NULL WHERE id=?", (queued_job,))
    backup = create_verified_copy(database.connection, tmp_path / "backups", minimum_mib=1)
    assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with sqlite3.connect(backup.path) as snapshot:
        assert snapshot.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    target = tmp_path / "new-data"; target.mkdir()
    restored = target / "mi_boti.sqlite3"
    restore_verified_copy(backup, restored, expected_guild="123456789012345678", supported_version=1)
    assert not list(target.glob("*.partial*"))
    assert prepare_data_root(target, minimum_mib=1) == target.resolve()
    with Database(restored) as db:
        assert db.migrate(minimum_disk_mib=1) == 1
        recover_interrupted_work(db)
        assert tuple(db.connection.execute("SELECT * FROM evidence WHERE id=?", (identifier,)).fetchone()) == original
        assert db.connection.execute("SELECT state FROM research_runs WHERE id=?", (active_run,)).fetchone()[0] == "INTERRUPTED"
        for job in (active_job, queued_job):
            assert db.connection.execute("SELECT state FROM jobs WHERE id=?", (job,)).fetchone()[0] == "INTERRUPTED"
            assert claim(db, job) is None
        assert verify_research_integrity(db.connection)["excerpt_hashes"] == 1
        assert not db.connection.execute("PRAGMA foreign_key_check").fetchall()


@pytest.mark.parametrize("damage", ["excerpt", "business", "job", "no-evidence"])
def test_backup_rejects_semantically_corrupt_research_even_when_foreign_keys_pass(database, tmp_path, damage):
    identifier, _ = seed_evidence(database)
    row = database.connection.execute("SELECT business_id,research_run_id FROM evidence WHERE id=?", (identifier,)).fetchone()
    if damage == "excerpt":
        database.connection.execute("UPDATE evidence SET extracted_fact=extracted_fact||'tampered' WHERE id=?", (identifier,))
    if damage == "business":
        from conftest import business
        other = business(database.connection)
        database.connection.execute("UPDATE evidence SET business_id=? WHERE id=?", (other, identifier))
    if damage == "job":
        database.connection.execute("UPDATE jobs SET kind='DISCOVER' WHERE id=(SELECT job_id FROM research_runs WHERE id=?)", (row[1],))
    if damage == "no-evidence":
        database.connection.execute("DELETE FROM evidence WHERE id=?", (identifier,))
    assert not database.connection.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(StorageError):
        create_verified_copy(database.connection, tmp_path / "backups", minimum_mib=1)
    assert not list((tmp_path / "backups").glob("*.sqlite3"))
