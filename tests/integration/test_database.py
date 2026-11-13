import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from conftest import campaign, job, business, hunt
from mi_boti.domain.errors import DatabaseError, MigrationError
from mi_boti.domain.values import utc_now
from mi_boti.repositories.database import Database, read_migrations


def migration_directory(tmp_path):
    source = Path(__file__).parents[2] / "src/mi_boti/migrations"
    target = tmp_path / "migrations"
    shutil.copytree(source, target)
    return target


def append_migration(directory, sql):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    version = len(manifest) + 1
    name = f"{version:04d}_fixture.sql"
    raw = sql.encode()
    (directory / name).write_bytes(raw)
    manifest.append({"version": version, "file": name, "sha256": hashlib.sha256(raw).hexdigest()})
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_initial_migration_is_idempotent_with_all_documented_tables(database):
    before = list(database.connection.iterdump())
    assert database.migrate() == 1
    assert list(database.connection.iterdump()) == before
    tables = {r[0] for r in database.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert len(tables) == 41
    assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgrade_preserves_records_backs_up_and_failure_rolls_back(database, tmp_path):
    directory = migration_directory(tmp_path)
    with database.transaction() as c:
        identifier = business(c)
    append_migration(directory, "CREATE TABLE fixture_upgrade (id TEXT NOT NULL PRIMARY KEY) STRICT;\n")
    assert database.migrate(directory=directory, minimum_disk_mib=1) == 2
    assert database.connection.execute("SELECT name FROM businesses WHERE id=?", (identifier,)).fetchone()[0] == "Fixture"
    assert len(list((database.path.parent / "backups").glob("*.sqlite3"))) == 1
    append_migration(directory, "CREATE TABLE rolled_back (id TEXT);\nINSERT INTO nonexistent VALUES (1);\n")
    with pytest.raises(MigrationError, match="rolled back"):
        database.migrate(directory=directory, minimum_disk_mib=1)
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    assert database.connection.execute("SELECT name FROM sqlite_master WHERE name='rolled_back'").fetchone() is None
    assert database.connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2


def test_checksum_file_and_applied_history_tampering_rejected(database, tmp_path):
    directory = migration_directory(tmp_path)
    file = directory / "0001_initial.sql"
    file.write_text(file.read_text() + "\n-- tampered\n")
    with pytest.raises(MigrationError, match="checksum"):
        database.migrate(directory=directory)
    database.connection.execute("UPDATE schema_migrations SET checksum='tampered'")
    with pytest.raises(MigrationError, match="checksum"):
        database.migrate()


def test_newer_or_unrecognized_schema_is_not_reset(database, tmp_path):
    database.connection.execute("PRAGMA user_version=99")
    with pytest.raises(MigrationError, match="newer"):
        database.migrate()
    assert database.connection.execute("PRAGMA user_version").fetchone()[0] == 99
    with Database(tmp_path / "unknown.sqlite3") as unknown:
        unknown.connection.execute("CREATE TABLE private_fixture (value TEXT)")
        with pytest.raises(MigrationError, match="no recognized"):
            unknown.migrate()
        assert unknown.connection.execute("SELECT name FROM sqlite_master WHERE name='private_fixture'").fetchone()


def test_foreign_keys_not_null_enums_json_and_singleton_guild(database):
    c = database.connection
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO identity_claims VALUES ('x','missing',?)", (utc_now(),))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO command_channels VALUES (NULL,'missing',1)")
    with database.transaction() as tx:
        job_id = job(tx)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE jobs SET state='MADE_UP' WHERE id=?", (job_id,))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE jobs SET payload_json='broken-json' WHERE id=?", (job_id,))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE jobs SET payload_json='[]' WHERE id=?", (job_id,))
    with pytest.raises(DatabaseError, match="another"):
        database.bind_guild("999")
    assert c.execute("SELECT guild_id FROM deployment").fetchone()[0] == "123456789012345678"


def test_strong_claims_and_open_hunt_are_unique_across_connections(database):
    with database.transaction() as c:
        company = business(c)
        campaign_id = campaign(c)
        hunt(c, campaign_id)
        c.execute("INSERT INTO identity_claims VALUES ('source:osm:node:1',?,?)", (company, utc_now()))
    with Database(database.path, busy_timeout_ms=100) as second:
        with pytest.raises(sqlite3.IntegrityError):
            with second.transaction() as c:
                hunt(c, campaign_id)
        with pytest.raises(sqlite3.IntegrityError):
            second.connection.execute("INSERT INTO identity_claims VALUES ('source:osm:node:1',?,?)", (company, utc_now()))


def test_manual_lead_has_no_fabricated_score_and_origin_is_immutable(database):
    with database.transaction() as c:
        company = business(c)
        c.execute("INSERT INTO leads VALUES ('lead-fixture',?,NULL,'MANUAL','NEW',1,?,?)", (company, utc_now(), utc_now()))
    with pytest.raises(sqlite3.IntegrityError):
        database.connection.execute("UPDATE leads SET qualification_kind='AUTOMATIC' WHERE id='lead-fixture'")
    with pytest.raises(sqlite3.IntegrityError):
        database.connection.execute("UPDATE businesses SET origin_job_id='other' WHERE id=?", (company,))


def test_nested_transactions_and_partial_writes_are_rejected(database):
    with pytest.raises(DatabaseError):
        with database.transaction():
            with database.transaction():
                pass
    with pytest.raises(RuntimeError):
        with database.transaction() as c:
            c.execute("INSERT INTO audit_events VALUES ('a','c',NULL,'test','test',NULL,'ok','{}',?)", (utc_now(),))
            raise RuntimeError("fixture")
    assert database.connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
