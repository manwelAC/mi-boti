import asyncio
from dataclasses import replace
import json

import pytest

from mi_boti.config import load_settings
from mi_boti.domain.discord import RESOURCES, COMMAND_CHANNELS, OUTPUT_DESTINATIONS, SetupError
from mi_boti.repositories.async_database import AsyncDatabase
from mi_boti.repositories import discord as repository
from mi_boti.services.setup import SetupService
from fakes_discord import FakePort


async def rig(database, configured):
    settings = load_settings(configured[0])
    db = AsyncDatabase(database.path)
    port = FakePort(settings)
    service = SetupService(db, port, settings)
    actor = port.members[settings.owner_ids[0]]
    return db, port, service, actor


async def confirm(service, actor, preview):
    plan = await service.claim(actor, preview["id"], preview["hash"])
    return await service.apply(plan, actor)


def test_preview_confirm_and_repeat_are_idempotent(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            preview = await service.preview(actor)
            assert port.calls == []
            assert len(preview["actions"]) == 17
            assert "completed" in await confirm(service, actor, preview)
            first_ids = set(port.channels)
            current = await db.call(repository.state)
            assert current["config"]["setup_state"] == "READY"
            assert set(current["resources"]) == set(RESOURCES)
            assert set(current["mappings"]) == set(COMMAND_CHANNELS)
            assert set(current["outputs"]) == set(OUTPUT_DESTINATIONS)
            assert len(port.messages) == 5
            assert "900" in port.channels
            preview = await service.preview(actor)
            assert all(a["action"] == "KEEP" for a in preview["actions"])
            assert "completed" in await confirm(service, actor, preview)
            assert set(port.channels) == first_ids
            assert len(port.messages) == 5
            assert database.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
            assert database.connection.execute("SELECT count(*) FROM hunts").fetchone()[0] == 0
        finally: await db.close()
    asyncio.run(run())


@pytest.mark.parametrize("case", ["actor", "channel", "expiry", "snapshot", "configuration", "digest", "cancel", "roles", "bot_permissions"])
def test_invalid_or_cancelled_confirmation_has_no_remote_effect(database, configured, case):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            preview = await service.preview(actor)
            digest = preview["hash"]
            if case == "actor": actor = replace(actor, user_id="999", administrator=True)
            if case == "channel": actor = replace(actor, channel_id="999")
            if case == "expiry": await db.call(lambda d: d.connection.execute("UPDATE setup_plans SET expires_at='2000-01-01T00:00:00.000000Z'"))
            if case == "snapshot": port.channels["900"] = replace(port.channels["900"], name="changed")
            if case == "configuration": await db.call(lambda d: d.connection.execute("UPDATE guild_config SET revision=revision+1"))
            if case == "digest": digest = "forged"
            if case == "roles": actor = replace(actor, user_id="998", role_ids=frozenset({"444"}))
            if case == "bot_permissions": port.bot_permissions = frozenset()
            if case == "cancel":
                assert await service.claim(actor, preview["id"], digest, cancel=True) is None
            with pytest.raises(SetupError if case != "roles" else Exception):
                await service.claim(actor, preview["id"], digest)
            assert port.calls == []
        finally: await db.close()
    asyncio.run(run())


def test_deleted_resource_is_only_recreated_after_new_confirmation(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            await confirm(service, actor, await service.preview(actor))
            current = await db.call(repository.state)
            missing = current["resources"]["business-research"]["discord_id"]
            del port.channels[missing]
            count = len(port.calls)
            preview = await service.preview(actor)
            assert len(port.calls) == count
            assert any(a["key"] == "business-research" and a["action"] == "CREATE" for a in preview["actions"])
            assert "completed" in await confirm(service, actor, preview)
            assert missing not in port.channels
            assert len(port.channels) == 18
        finally: await db.close()
    asyncio.run(run())


def test_names_do_not_authorize_or_adopt_unrelated_resources(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            port.channels["900"] = replace(port.channels["900"], name="dashboard")
            preview = await service.preview(actor)
            dashboard = next(a for a in preview["actions"] if a["key"] == "dashboard")
            assert dashboard["action"] == "CREATE" and dashboard["name"] != "dashboard"
            assert "completed" in await confirm(service, actor, preview)
            assert port.channels["900"].name == "dashboard"
        finally: await db.close()
    asyncio.run(run())


def test_uncertain_creation_is_held_then_explicitly_adopted(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            port.failure_key, port.uncertain = "lead_hunting", True
            result = await confirm(service, actor, await service.preview(actor))
            assert "partial" in result
            created = next(c.id for c in port.channels.values() if c.name == "Lead Hunting")
            count = len(port.calls)
            preview = await service.preview(actor)
            assert preview["blockers"]
            with pytest.raises(SetupError): await service.claim(actor, preview["id"], preview["hash"])
            assert len(port.calls) == count
            port.failure_key = None
            preview = await service.preview(actor, adoptions={"lead_hunting": created})
            assert "completed" in await confirm(service, actor, preview)
            assert len([c for c in port.channels.values() if c.name == "Lead Hunting"]) == 1
        finally: await db.close()
    asyncio.run(run())


def test_restart_records_interruption_and_never_restarts_provisioning(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            preview = await service.preview(actor)
            await service.claim(actor, preview["id"], preview["hash"])
            await db.call(repository.recover_setup)
            assert port.calls == []
            row = await db.call(lambda d: d.connection.execute("SELECT state FROM setup_plans WHERE id=?", (preview["id"],)).fetchone()[0])
            assert row == "PARTIAL"
            assert "completed" in await confirm(service, actor, await service.preview(actor))
            await db.call(repository.recover_setup)
            assert (await db.call(repository.state))["config"]["setup_state"] == "READY"
        finally: await db.close()
    asyncio.run(run())


def test_permission_failure_retains_completed_resources_and_retries_only_after_approval(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            port.failure_key = "campaigns"
            assert "partial" in await confirm(service, actor, await service.preview(actor))
            saved = set(port.channels)
            assert len(saved) > 1
            port.failure_key = None
            preview = await service.preview(actor)
            assert set(port.channels) == saved
            assert "completed" in await confirm(service, actor, preview)
            assert saved <= set(port.channels)
        finally: await db.close()
    asyncio.run(run())


def test_replayed_confirmation_and_unconfirmed_apply_cannot_provision(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            preview = await service.preview(actor)
            with pytest.raises(SetupError): await service.apply(preview, actor)
            assert port.calls == []
            plan = await service.claim(actor, preview["id"], preview["hash"])
            with pytest.raises(SetupError): await service.claim(actor, preview["id"], preview["hash"])
            assert "completed" in await service.apply(plan, actor)
            count = len(port.calls)
            with pytest.raises(SetupError): await service.apply(plan, actor)
            assert len(port.calls) == count
        finally: await db.close()
    asyncio.run(run())


def test_unmanaged_children_block_category_adoption(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            from mi_boti.domain.discord import RemoteChannel, REQUIRED_BOT_PERMISSIONS
            port.channels["901"] = RemoteChannel("901", "Unrelated category", "CATEGORY", None, (), REQUIRED_BOT_PERMISSIONS)
            port.channels["900"] = replace(port.channels["900"], parent_id="901")
            preview = await service.preview(actor, adoptions={"system": "901"})
            assert any("unmanaged" in b for b in preview["blockers"])
            with pytest.raises(SetupError): await service.claim(actor, preview["id"], preview["hash"])
            assert port.calls == []
        finally: await db.close()
    asyncio.run(run())


def test_renamed_channels_keep_identity_and_deleted_panels_require_confirmed_repair(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            await confirm(service, actor, await service.preview(actor))
            current = await db.call(repository.state)
            channel_id = current["resources"]["bot-control"]["discord_id"]
            port.channels[channel_id] = replace(port.channels[channel_id], name="renamed-safe")
            port.messages.clear()
            count = len(port.calls)
            preview = await service.preview(actor)
            assert len(port.calls) == count
            assert next(a for a in preview["actions"] if a["key"] == "bot-control")["action"] == "KEEP"
            assert "completed" in await confirm(service, actor, preview)
            assert port.channels[channel_id].name == "renamed-safe"
            assert len(port.messages) == 5
        finally: await db.close()
    asyncio.run(run())


def test_administrator_losing_authorization_before_dispatch_cannot_provision(database, configured):
    async def run():
        db, port, service, owner = await rig(database, configured)
        try:
            admin = replace(owner, user_id="998", administrator=True)
            port.members[admin.user_id] = admin
            preview = await service.preview(admin)
            plan = await service.claim(admin, preview["id"], preview["hash"])
            port.members[admin.user_id] = replace(admin, administrator=False)
            assert "partial" in await service.apply(plan, admin)
            assert port.calls == []
        finally: await db.close()
    asyncio.run(run())


def test_concurrent_confirmations_admit_only_one_setup_job(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            one, two = await service.preview(actor), await service.preview(actor)
            results = await asyncio.gather(service.claim(actor, one["id"], one["hash"]),
                                           service.claim(actor, two["id"], two["hash"]), return_exceptions=True)
            accepted = [result for result in results if isinstance(result, dict)]
            assert len(accepted) == 1
            assert sum(isinstance(result, SetupError) for result in results) == 1
            assert "completed" in await service.apply(accepted[0], actor)
            assert len(port.channels) == 18 and len(port.messages) == 5
        finally: await db.close()
    asyncio.run(run())


def test_uncertain_panel_send_is_not_automatically_repeated(database, configured):
    async def run():
        db, port, service, actor = await rig(database, configured)
        try:
            port.failure_key = "panel.dashboard"
            assert "partial" in await confirm(service, actor, await service.preview(actor))
            count = len(port.calls)
            preview = await service.preview(actor)
            assert any("panel.dashboard" in blocker for blocker in preview["blockers"])
            with pytest.raises(SetupError): await service.claim(actor, preview["id"], preview["hash"])
            assert len(port.calls) == count
            # Operator inspected and removed the uncertain message before
            # explicitly proposing recreation. The service never guesses.
            port.messages.clear()
            port.failure_key = None
            preview = await service.preview(actor, recreate=("panel.dashboard",))
            assert "completed" in await confirm(service, actor, preview)
            assert len(port.messages) == 5
        finally: await db.close()
    asyncio.run(run())


def test_lost_authorization_after_channel_creation_blocks_panel_publication(database, configured):
    async def run():
        db, port, service, owner = await rig(database, configured)
        try:
            admin = replace(owner, user_id="998", administrator=True)
            port.members[admin.user_id] = admin
            original = port.provision
            async def provision(spec, *args):
                result = await original(spec, *args)
                if spec.key == "activity-logs":
                    port.members[admin.user_id] = replace(admin, administrator=False)
                return result
            port.provision = provision
            assert "partial" in await confirm(service, admin, await service.preview(admin))
            assert len(port.channels) == 18
            assert port.messages == {}
        finally: await db.close()
    asyncio.run(run())


def test_legacy_workspace_adds_guide_only_after_confirming_upgrade(database, configured):
    async def run():
        db,port,service,actor=await rig(database,configured)
        try:
            initial=await service.preview(actor)
            await confirm(service,actor,initial)
            before=await db.call(repository.state)
            guide=before["resources"]["guide"]
            def legacy(db):
                with db.transaction() as c:
                    c.execute("DELETE FROM panels WHERE panel_key='guide'")
                    c.execute("DELETE FROM command_channels WHERE command_key='guide'")
                    c.execute("DELETE FROM discord_resources WHERE resource_key='guide'")
            await db.call(legacy)
            port.channels.pop(guide["discord_id"])
            actor=replace(actor,channel_id=before["mappings"]["setup"])
            calls=list(port.calls)
            preview=await service.preview(actor)
            assert port.calls==calls
            creates=[a["key"] for a in preview["actions"] if a["action"]=='CREATE']
            assert creates==['guide']
            assert 'completed' in await confirm(service,actor,preview)
            after=await db.call(repository.state)
            assert all(after["resources"][k]["discord_id"]==v["discord_id"] for k,v in before["resources"].items() if k!='guide')
            assert after["mappings"]["guide"]==after["resources"]["guide"]["discord_id"]
            assert len(after["panels"])==5
        finally:
            await db.close()
    asyncio.run(run())
