"""Offline diagnostics and explicit Discord gateway startup."""

import argparse
import json
import sys
import sqlite3
import asyncio

from .config import load_settings
from .domain.errors import AppError
from .runtime import initialize


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mi Boti local diagnostics and Discord startup; never starts hunting.")
    parser.add_argument(
        "command",
        choices=("check-config", "init-db", "run", "import-ph-extract", "verify-ph-extract"),
    )
    parser.add_argument(
        "--pbf-file",
        default=None,
        help="Optional local .osm.pbf file path for import-ph-extract (otherwise downloads from configured Geofabrik URL).",
    )
    options = parser.parse_args(argv)
    try:
        settings = load_settings()
        if options.command == "check-config":
            print(json.dumps(settings.safe_summary(), sort_keys=True))
        elif options.command == "init-db":
            with initialize(settings):
                print(json.dumps({"database": "initialized", "schema_version": 1,
                                  "discord_connected": False, "ai_enabled": False, "hunting_enabled": False}))
        elif options.command == "import-ph-extract":
            from pathlib import Path
            from .discovery.overpass import SourcePolicyError
            from .discovery.philippines_extract import (
                download_and_import_philippines_extract,
                import_pbf_to_snapshot,
            )
            from .storage.paths import prepare_data_root
            ext_policy = settings.sources.get("philippines_extract")
            if not ext_policy:
                raise SourcePolicyError("Configure [sources.philippines_extract] in config.toml before running import-ph-extract.")
            root = prepare_data_root(settings.data_dir, minimum_mib=settings.values["runtime.minimum_disk_free_mib"])
            if options.pbf_file:
                import time
                policy_timeout = float(ext_policy.get("timeout_seconds", 60))
                manifest = import_pbf_to_snapshot(
                    Path(options.pbf_file).resolve(),
                    root,
                    policy=ext_policy,
                    provider_url=str(ext_policy.get("endpoint", "")),
                    minimum_disk_mib=settings.values["runtime.minimum_disk_free_mib"],
                    deadline_monotonic=time.monotonic() + max(policy_timeout, 1.0),
                    isolate_process=True,
                )
            else:
                manifest = download_and_import_philippines_extract(
                    root,
                    policy=ext_policy,
                    minimum_disk_mib=settings.values["runtime.minimum_disk_free_mib"],
                )
            print(json.dumps({
                "snapshot_id": manifest.snapshot_id,
                "snapshot_observed_at": manifest.snapshot_observed_at,
                "pbf_sha256": manifest.pbf_sha256,
                "snapshot_db_sha256": manifest.snapshot_db_sha256,
                "counts": dict(manifest.counts),
                "incomplete_snapshot": manifest.incomplete_snapshot,
            }, sort_keys=True))
        elif options.command == "verify-ph-extract":
            from .discovery.philippines_extract import verify_local_snapshot
            manifest = verify_local_snapshot(settings.data_dir)
            print(json.dumps({
                "snapshot_id": manifest.snapshot_id,
                "snapshot_observed_at": manifest.snapshot_observed_at,
                "pbf_sha256": manifest.pbf_sha256,
                "snapshot_db_sha256": manifest.snapshot_db_sha256,
                "counts": dict(manifest.counts),
                "incomplete_snapshot": manifest.incomplete_snapshot,
                "verified": True,
            }, sort_keys=True))
        else:
            settings.require_identity(token=True)
            from .discord_app.bot import run_bot
            with initialize(settings) as database:
                asyncio.run(run_bot(settings, database.path))
        return 0
    except AppError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("STORAGE_ERROR: Check local storage permissions and available disk space.", file=sys.stderr)
        return 2
    except sqlite3.Error:
        print("DATABASE_ERROR: Database validation failed; stop and inspect the local database or backup.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
