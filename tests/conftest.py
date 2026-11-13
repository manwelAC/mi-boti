from pathlib import Path
from uuid import uuid4

import pytest

from mi_boti.config import load_settings
from mi_boti.domain.values import utc_now
from mi_boti.repositories.database import Database


def pytest_configure(config):
    # Do not depend on the machine-wide pytest temp root, which may belong to
    # another account/session. A fresh UUID target is never reused or removed.
    if config.option.basetemp is None:
        parent = Path(__file__).resolve().parents[1] / ".pytest_cache" / "mi_boti_runs"
        from mi_boti.storage.paths import reject_links
        reject_links(parent)
        parent.mkdir(parents=True, exist_ok=True)
        selected = parent / uuid4().hex
        if selected.exists() or selected.resolve().parent != parent.resolve():
            raise RuntimeError("Unsafe test temporary directory.")
        config.option.basetemp = str(selected)


@pytest.fixture
def configured(tmp_path):
    config = tmp_path / "settings.toml"
    config.write_text("", encoding="utf-8")
    env = {
        "MI_BOTI_CONFIG_FILE": str(config), "MI_BOTI_DATA_DIR": str(tmp_path / "data"),
        "MI_BOTI_GUILD_ID": "123456789012345678", "MI_BOTI_OWNER_IDS": "223456789012345678",
    }
    return env, config


@pytest.fixture
def database(tmp_path):
    with Database(tmp_path / "test.sqlite3") as db:
        db.migrate(minimum_disk_mib=1)
        db.bind_guild("123456789012345678")
        yield db


def campaign(connection):
    identifier = str(uuid4())
    now = utc_now()
    connection.execute(
        "INSERT INTO campaigns VALUES (?,?,?,1,?,?,?)",
        (identifier, "Fixture PH", "ACTIVE", "1", now, now),
    )
    connection.execute("INSERT INTO campaign_versions VALUES (?,1,'{}','1',?)", (identifier, now))
    return identifier


def job(connection, *, hunt=None, state="QUEUED"):
    identifier = str(uuid4())
    now = utc_now()
    connection.execute(
        "INSERT INTO jobs(id,kind,payload_json,idempotency_key,hunt_id,actor_id,state,attempt,max_attempts,progress_json,cancel_requested,created_at,updated_at) "
        "VALUES (?,'DISCOVER','{}',?,?, '1',?,0,3,'{}',0,?,?)",
        (identifier, identifier, hunt, state, now, now),
    )
    return identifier


def business(connection, *, hunt=None):
    origin = job(connection, hunt=hunt)
    identifier = str(uuid4())
    now = utc_now()
    connection.execute(
        "INSERT INTO businesses(id,name,normalized_name,entity_kind,disposition,origin_job_id,origin_hunt_id,created_at,updated_at,revision) "
        "VALUES (?,'Fixture','fixture','BUSINESS','PENDING',?,?,?, ?,1)",
        (identifier, origin, hunt, now, now),
    )
    return identifier


def hunt(connection, campaign_id, *, state="RUNNING"):
    identifier = str(uuid4())
    now = utc_now()
    connection.execute(
        "INSERT INTO hunts(id,campaign_id,campaign_version,snapshot_json,provider_id,initiated_by,quota,qualified_count,state,counters_json,active_milliseconds,max_observed_at,created_at,updated_at,revision) "
        "VALUES (?,?,1,'{}','disabled-fixture','1',25,0,?,'{}',0,?,?,?,1)",
        (identifier, campaign_id, state, now, now, now),
    )
    return identifier
