"""The readiness checker must not confuse local records with live acceptance."""

import asyncio
import runpy
import sqlite3
from pathlib import Path

import pytest

from mi_boti.config import load_settings
from mi_boti.repositories.async_database import AsyncDatabase
from mi_boti.services.setup import SetupService
from fakes_discord import FakePort

inspect_database = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/check_phase2_prerequisites.py"))["inspect_database"]


def test_missing_database_is_not_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        inspect_database(missing)
    assert not missing.exists()


def test_local_checkpoint_does_not_accept_unconfigured_state(database):
    result = inspect_database(database.path)
    assert not result["local_checkpoint_passed"]
    assert not result["full_phase2_accepted"]


def test_ready_checkpoint_is_read_only_and_detects_missing_mapping(database, configured):
    async def setup():
        settings = load_settings(configured[0])
        db = AsyncDatabase(database.path)
        try:
            port = FakePort(settings)
            service = SetupService(db, port, settings)
            actor = port.members[settings.owner_ids[0]]
            preview = await service.preview(actor)
            plan = await service.claim(actor, preview["id"], preview["hash"])
            assert "completed" in await service.apply(plan, actor)
        finally:
            await db.close()
    asyncio.run(setup())
    before = list(database.connection.iterdump())
    result = inspect_database(database.path)
    assert result["local_checkpoint_passed"]
    assert not result["full_phase2_accepted"]
    assert result["counts"]["discord_resources"] == 17
    assert list(database.connection.iterdump()) == before
    database.connection.execute("DELETE FROM command_channels WHERE command_key='usage'")
    result = inspect_database(database.path)
    assert not result["checks"]["command_channels"]
    assert not result["local_checkpoint_passed"]
