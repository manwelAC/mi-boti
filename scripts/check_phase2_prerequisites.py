"""Read-only local Phase 2 checkpoint; never connects to Discord or reads tokens.

Run with the project environment: python scripts/check_phase2_prerequisites.py
Use --database PATH for a disposable test database. Live L01 checks stay separate.
"""

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from mi_boti.domain.discord import COMMAND_CHANNELS, OUTPUT_DESTINATIONS, PANELS, RESOURCES


def inspect_database(path):
    checks = {}
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        checks["sqlite_quick_check"] = [r[0] for r in connection.execute("PRAGMA quick_check")] == ["ok"]
        checks["foreign_keys"] = not list(connection.execute("PRAGMA foreign_key_check"))
        config = connection.execute("SELECT setup_state FROM guild_config WHERE id='guild'").fetchone()
        checks["setup_ready"] = config is not None and config[0] == "READY"
        resources = {r["resource_key"]: dict(r) for r in connection.execute("SELECT * FROM discord_resources")}
        checks["managed_resources"] = set(resources) == set(RESOURCES) and all(
            r["state"] == "ACTIVE" and r["discord_id"] and r["kind"] == RESOURCES[k].kind
            for k, r in resources.items())
        by_id = {r["id"]: r for r in resources.values()}
        checks["resource_parent_links"] = checks["managed_resources"] and all(
            r["parent_resource_id"] == (resources[RESOURCES[k].parent]["id"] if RESOURCES[k].parent else None)
            for k, r in resources.items())
        for table, column, expected in (("command_channels", "command_key", COMMAND_CHANNELS),
                                        ("output_destinations", "output_key", OUTPUT_DESTINATIONS)):
            mappings = list(connection.execute("SELECT * FROM " + table))
            checks[table] = {r[column] for r in mappings} == set(expected) and all(
                r["resource_id"] in by_id and by_id[r["resource_id"]]["kind"] == "TEXT"
                and by_id[r["resource_id"]]["state"] == "ACTIVE" for r in mappings)
        panels = list(connection.execute("SELECT * FROM panels"))
        checks["persistent_panel_records"] = {r["panel_key"] for r in panels} == set(PANELS) and all(
            r["state"] == "ACTIVE" and r["message_id"] and r["revision"] >= 1
            and PANELS[r["panel_key"]] in resources
            and r["resource_id"] == resources[PANELS[r["panel_key"]]]["id"] for r in panels)
        checks["no_unfinished_setup"] = not connection.execute(
            "SELECT 1 FROM setup_plans WHERE state IN ('CONFIRMED','APPLYING') LIMIT 1").fetchone()
        counts = {table: connection.execute("SELECT count(*) FROM " + table).fetchone()[0]
                  for table in ("discord_resources", "command_channels", "output_destinations", "panels", "jobs", "hunts")}
    return {"scope": "local persisted state only; no live Discord verification", "checks": checks,
            "counts": counts, "local_checkpoint_passed": all(checks.values()),
            "full_phase2_accepted": False,
            "live_checks_not_established_by_this_script": ["persistent button response after restart",
                "independent user/role denial", "rename/deletion recovery", "permission loss", "interaction defer timing"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/mi_boti.sqlite3"))
    args = parser.parse_args()
    try:
        result = inspect_database(args.database)
    except (sqlite3.Error, OSError):
        print(json.dumps({"local_checkpoint_passed": False, "error": "Cannot inspect an existing compatible database read-only."}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["local_checkpoint_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
