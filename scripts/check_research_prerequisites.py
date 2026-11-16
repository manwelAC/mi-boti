"""Read-only Phase 4a checkpoint. No Discord, DNS, website or provider calls."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from mi_boti.domain.errors import AppError
from mi_boti.repositories.research_integrity import verify_research_integrity
from mi_boti.repositories.database import read_migrations
from mi_boti.storage.paths import reject_links


def inspect_database(path):
    reject_links(Path(path))
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        checks = {
            "sqlite_quick_check": connection.execute("PRAGMA quick_check").fetchall() == [("ok",)],
            "foreign_keys": not connection.execute("PRAGMA foreign_key_check").fetchall(),
        }
        expected = [(m.version, m.checksum) for m in read_migrations()]
        checks["migration_history"] = connection.execute("SELECT version,checksum FROM schema_migrations ORDER BY version").fetchall() == expected
        checks["schema_version"] = connection.execute("PRAGMA user_version").fetchone()[0] == len(expected)
        integrity = verify_research_integrity(connection)
        checks["research_integrity"] = True
        config = connection.execute("SELECT setup_state,settings_json FROM guild_config WHERE id='guild'").fetchone()
        checks["setup_ready"] = bool(config and config[0] == "READY")
        records = json.loads(config[1]).get("research_access", {}) if config else {}
        if not isinstance(records, dict): raise ValueError("Invalid review registry.")
        valid = 0
        for record in records.values():
            try:
                value = record["review"]["expires_at"]
                if not isinstance(value, str): raise ValueError("Invalid review expiry.")
                expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if expiry.tzinfo and expiry > datetime.now(timezone.utc): valid += 1
            except (KeyError, ValueError, TypeError):
                pass
        return {"mode": "read_only", "local_checkpoint_passed": all(checks.values()), "checks": checks,
                **integrity, "unexpired_review_records": valid,
                "unfinished_research_jobs": connection.execute("SELECT count(*) FROM jobs WHERE kind='RESEARCH' AND state IN ('QUEUED','RUNNING','RETRY_WAIT')").fetchone()[0],
                "full_phase4a_accepted": False,
                "limitations": ["Local records do not prove current Discord permissions, site access permission, HTTP compatibility or live delivery."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/mi_boti.sqlite3")
    options = parser.parse_args(argv)
    try:
        result = inspect_database(options.database)
    except (sqlite3.Error, AppError, ValueError, TypeError):
        result = {"mode": "read_only", "local_checkpoint_passed": False, "full_phase4a_accepted": False,
                  "error": "Research checkpoint could not verify the database; inspect its schema, provenance and excerpt integrity."}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["local_checkpoint_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
