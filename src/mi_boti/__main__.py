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
    parser.add_argument("command", choices=("check-config", "init-db", "run"))
    options = parser.parse_args(argv)
    try:
        settings = load_settings()
        if options.command == "check-config":
            print(json.dumps(settings.safe_summary(), sort_keys=True))
        elif options.command == "init-db":
            with initialize(settings):
                print(json.dumps({"database": "initialized", "schema_version": 1,
                                  "discord_connected": False, "ai_enabled": False, "hunting_enabled": False}))
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
