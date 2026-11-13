import asyncio
from dataclasses import replace
from types import SimpleNamespace

import discord
import pytest

from mi_boti.config import load_settings
from mi_boti.discord_app.bot import MiBotiClient
from mi_boti.discord_app.views import PanelView, SetupConfirmation
from mi_boti.domain.discord import ActorContext, COMMAND_CHANNELS
from mi_boti.repositories.async_database import AsyncDatabase
from mi_boti.repositories import discord as repository
from fakes_discord import FakePort


class Interaction:
    def __init__(self, actor, events=None):
        self.guild_id = int(actor.guild_id) if actor.guild_id else None
        self.channel_id = int(actor.channel_id) if actor.channel_id else None
        self.user = SimpleNamespace(id=int(actor.user_id))
        self.channel = object.__new__(discord.TextChannel)
        self.channel.id = self.channel_id
        self.message = None
        self.sent = []
        self.events = events if events is not None else []
        self.done = False
        async def defer(**options):
            assert options["ephemeral"] is True
            self.events.append("ack")
            self.done = True
        async def send(content=None, **options):
            assert self.done
            assert options["ephemeral"] is True
            assert not options["allowed_mentions"].everyone
            self.sent.append({"content": content, **options})
        self.response = SimpleNamespace(is_done=lambda: self.done, defer=defer)
        self.followup = SimpleNamespace(send=send)


async def initialized(database, configured):
    settings = load_settings(configured[0])
    db = AsyncDatabase(database.path)
    port = FakePort(settings)
    client = MiBotiClient(settings, db, port_factory=lambda *_: port)
    await client._async_setup_hook()  # SDK local initialization only; no login.
    actor = port.members[settings.owner_ids[0]]
    preview = await client.setup_service.preview(actor)
    plan = await client.setup_service.claim(actor, preview["id"], preview["hash"])
    await client.setup_service.apply(plan, actor)
    return db, port, client, actor


def test_sdk_registers_all_command_keys_and_persistent_controls(database, configured):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            guild = discord.Object(id=int(client.settings.guild_id))
            keys = {c.qualified_name.replace(" ", ".") for c in client.tree.walk_commands(guild=guild) if isinstance(c, discord.app_commands.Command)}
            assert keys == set(COMMAND_CHANNELS)
            current = await db.call(repository.state)
            for key, panel in current["panels"].items():
                view = PanelView(client, key, panel["id"], panel["revision"], current)
                assert view.is_persistent()
                assert all(len(button.custom_id or "") <= 100 for button in view.children)
            pending = await client.setup_service.preview(actor)
            assert SetupConfirmation(client, pending["id"], pending["hash"]).is_persistent()
            calls = list(port.calls)
            await client.restore_views()
            assert port.calls == calls
            assert client.tasks == set()
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


@pytest.mark.parametrize("case", ["channel", "guild", "member", "thread", "permission", "missing-resource", "missing-panel"])
def test_transport_denials_are_private_and_only_append_a_denial_audit(database, configured, case):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["hunt.start"])
            if case == "channel": actor = replace(actor, channel_id="900")
            if case == "guild": actor = replace(actor, guild_id="999")
            if case == "member":
                actor = replace(actor, user_id="998")
                port.members[actor.user_id] = actor
            if case == "permission":
                actor = replace(actor, user_id="999", role_ids=frozenset())
                port.members[actor.user_id] = actor
            interaction = Interaction(actor)
            if case == "thread": interaction.channel = SimpleNamespace(id=actor.channel_id)
            if case == "missing-resource": del port.channels[current["resources"]["business-research"]["discord_id"]]
            if case == "missing-panel": port.messages.clear()
            before = await db.call(lambda d: [s for s in d.connection.iterdump() if not s.startswith('INSERT INTO "audit_events"')])
            audit_before = await db.call(lambda d: d.connection.execute("SELECT count(*) FROM audit_events").fetchone()[0])
            calls = list(port.calls)
            await client.operation(interaction, "hunt.start")
            assert interaction.sent
            assert "not implemented" not in interaction.sent[-1]["content"]
            assert await db.call(lambda d: [s for s in d.connection.iterdump() if not s.startswith('INSERT INTO "audit_events"')]) == before
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM audit_events").fetchone()[0]) == audit_before + 1
            assert port.calls == calls
            assert client.tasks == set()
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_acknowledgment_precedes_metadata_and_disabled_operations_have_no_effect(database, configured):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            events = []
            original = port.fresh_actor
            async def observed(*args):
                events.append("metadata")
                return await original(*args)
            port.fresh_actor = observed
            interaction = Interaction(replace(actor, channel_id=current["mappings"]["hunt.start"]), events)
            await client.operation(interaction, "hunt.start")
            assert events[:2] == ["ack", "metadata"]
            assert "no job" in interaction.sent[-1]["content"]
            assert database.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
            assert database.connection.execute("SELECT count(*) FROM hunts").fetchone()[0] == 0
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_mapping_and_operator_changes_require_preview_confirmation(database, configured):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            before = await db.call(repository.state)
            actor = replace(actor, channel_id=before["mappings"]["config"])
            interaction = Interaction(actor)
            await client.operation(interaction, "config", action_name="set", key="operator_role_ids", value="444")
            assert (await db.call(repository.state))["roles"] == frozenset()
            assert any("view" in reply for reply in interaction.sent)
            row = await db.call(lambda d: dict(d.connection.execute("SELECT * FROM setup_plans WHERE state='PREVIEW' ORDER BY created_at DESC LIMIT 1").fetchone()))
            confirm = Interaction(actor)
            await client.confirm_setup(confirm, row["id"], row["plan_hash"])
            await asyncio.gather(*tuple(client.tasks))
            assert (await db.call(repository.state))["roles"] == frozenset({"444"})
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_stale_panel_cannot_launch_setup_or_work(database, configured):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            panel = current["panels"]["settings"]
            interaction = Interaction(replace(actor, channel_id=current["mappings"]["setup"]))
            interaction.message = SimpleNamespace(id=int(panel["message_id"]))
            before = await db.call(lambda d: d.connection.execute("SELECT count(*) FROM setup_plans").fetchone()[0])
            await client.panel_action(interaction, "setup", panel["id"], panel["revision"] - 1)
            assert "stale" in interaction.sent[-1]["content"]
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM setup_plans").fetchone()[0]) == before
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_application_identity_mismatch_prevents_command_sync(database, configured):
    async def run():
        env = {**configured[0], "MI_BOTI_APPLICATION_ID": "123"}
        settings = load_settings(env)
        db = AsyncDatabase(database.path)
        client = MiBotiClient(settings, db, port_factory=lambda *_: FakePort(settings))
        await client._async_setup_hook()
        calls = []
        async def info(): return SimpleNamespace(id=999)
        async def sync(**_): calls.append("sync")
        client.application_info = info
        client.tree.sync = sync
        try:
            with pytest.raises(Exception, match="different application"):
                await client.setup_hook()
            assert calls == []
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


@pytest.mark.parametrize("mutation", [False, True])
@pytest.mark.parametrize("failure", ["timeout", "rate-limit"])
def test_sdk_transport_failures_are_bounded_and_mutations_remain_uncertain(mutation, failure):
    from mi_boti.discord_app.transport import DiscordPort
    from mi_boti.domain.discord import SetupError, UncertainOperation
    async def run():
        port = DiscordPort(None, None)
        async def failing():
            if failure == "rate-limit": raise discord.RateLimited(99)
            raise asyncio.TimeoutError
        with pytest.raises(UncertainOperation if mutation else SetupError) as captured:
            await port.api(failing(), mutation=mutation)
        if failure == "rate-limit":
            assert "Wait at least 99 seconds" in str(captured.value)
            assert "rate-limited" in str(captured.value)
    asyncio.run(run())


def test_sdk_bucket_allows_available_requests_in_long_reset_window(database, configured):
    # A 60-second reset window is not exhaustion when tokens remain. The SDK's
    # optional 30-second cap rejects even those available requests preemptively.
    from discord.http import Ratelimit
    async def run():
        settings = load_settings(configured[0])
        db = AsyncDatabase(database.path)
        client = MiBotiClient(settings, db, port_factory=lambda *_: FakePort(settings))
        try:
            old_bucket = Ratelimit(30.0)
            old_bucket.remaining = 5
            old_bucket.expires = asyncio.get_running_loop().time() + 60
            with pytest.raises(discord.RateLimited):
                await old_bucket.acquire()
            cap = client.http.max_ratelimit_timeout
            bucket = Ratelimit(cap)
            bucket.remaining = 5
            bucket.expires = asyncio.get_running_loop().time() + 60
            await asyncio.wait_for(bucket.acquire(), timeout=0.1)
            assert bucket.remaining == 4
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
