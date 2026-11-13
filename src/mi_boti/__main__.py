"""Offline configuration/database diagnostics, pending Phase 2 Discord startup."""

import argparse
import json
import sys
import sqlite3

from .config import load_settings
from .domain.errors import AppError
from .runtime import initialize


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Mi Boti foundation diagnostics; never starts hunting.")
    parser.add_argument("command", choices=("check-config", "init-db"))
    options = parser.parse_args(argv)
    try:
        settings = load_settings()
        if options.command == "check-config":
            print(json.dumps(settings.safe_summary(), sort_keys=True))
        else:
            with initialize(settings):
                print(json.dumps({"database": "initialized", "schema_version": 1,
                                  "discord_connected": False, "ai_enabled": False, "hunting_enabled": False}))
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


if __name__ == "__main__":
    raise SystemExit(main())
