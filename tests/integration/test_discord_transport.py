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


def test_campaign_commands_and_active_campaign_config_enforce_channel_and_versions(database, configured):
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            campaigns_ch = current["mappings"]["campaign.create"]
            config_ch = current["mappings"]["config"]

            # Create campaign in the mapped campaigns channel.
            create_ix = Interaction(replace(actor, channel_id=campaigns_ch))
            await client.operation(
                create_ix,
                "campaign.create",
                options_dict={"name": "QC Restaurants", "locality": "Quezon City"},
            )
            assert "Saved **QC Restaurants**" in create_ix.sent[-1]["content"]
            camp_id = await db.call(lambda d: d.connection.execute("SELECT id FROM campaigns").fetchone()[0])

            # List campaigns.
            list_ix = Interaction(replace(actor, channel_id=campaigns_ch))
            await client.operation(list_ix, "campaign.list", options_dict={"page": 1})
            assert camp_id in list_ix.sent[-1]["content"]

            # Set active_campaign_id via /config set in bot-settings channel.
            set_ix = Interaction(replace(actor, channel_id=config_ch))
            await client.operation(
                set_ix,
                "config",
                action_name="set",
                key="active_campaign_id",
                value=camp_id,
            )
            assert camp_id in set_ix.sent[-1]["content"]

            # Edit campaign to version 2, then archive.
            edit_ix = Interaction(replace(actor, channel_id=campaigns_ch))
            await client.operation(
                edit_ix,
                "campaign.edit",
                options_dict={
                    "campaign_id": camp_id,
                    "expected_version": 1,
                    "categories": "cafe",
                    "archive": True,
                },
            )
            assert "v2, ARCHIVED" in edit_ix.sent[-1]["content"]
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_discover_command_enqueues_and_runs_background_worker_with_approved_source(database, configured):
    from mi_boti.discovery.overpass import ATTRIBUTION, DiscoveryBatch

    class FakeSource:
        source_namespace = "osm"
        policy_version = "overpass-2026-11"

        def discover(self, planned, *, max_elements):
            return DiscoveryBatch(
                (
                    {
                        "name": "Dynamic QC Bistro",
                        "source_namespace": "osm",
                        "source_id": "node/9001",
                        "source_url": "https://www.openstreetmap.org/node/9001",
                        "observed_at": "2026-11-14T00:00:00.000000Z",
                        "policy_version": "overpass-2026-11",
                        "attribution": ATTRIBUTION,
                        "address": {
                            "country": "PH",
                            "city": "Quezon City",
                            "street": "Maginhawa St",
                            "house_number": "12",
                        },
                    },
                ),
                False,
                (),
            )

    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            campaigns_ch = current["mappings"]["campaign.create"]
            discover_ch = current["mappings"]["discover"]

            # Create an active campaign first.
            create_ix = Interaction(replace(actor, channel_id=campaigns_ch))
            await client.operation(
                create_ix,
                "campaign.create",
                options_dict={"name": "QC Live Test", "locality": "Quezon City"},
            )
            camp_id = await db.call(lambda d: d.connection.execute("SELECT id FROM campaigns").fetchone()[0])

            # Without an enabled source adapter, /discover fails closed without creating a job.
            denied_ix = Interaction(replace(actor, channel_id=discover_ch))
            await client.operation(
                denied_ix,
                "discover",
                options_dict={"campaign_id": camp_id, "limit": 10},
            )
            assert "[sources.philippines_extract]" in denied_ix.sent[-1]["content"]
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM jobs").fetchone()[0]) == 0

            # With an enabled source adapter, /discover enqueues and runs in background.
            client.discovery_source_factory = lambda: FakeSource()
            run_ix = Interaction(replace(actor, channel_id=discover_ch))
            await client.operation(
                run_ix,
                "discover",
                options_dict={"campaign_id": camp_id, "limit": 10},
            )
            await asyncio.gather(*tuple(client.tasks))
            assert any("finished with state `SUCCEEDED`" in msg["content"] for msg in run_ix.sent)
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]) == 1
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_discover_worker_does_not_block_async_database_and_revalidates_roles_and_mappings_live(database, configured):
    """Verify AsyncDatabase remains responsive during slow network discovery and mid-run role/channel revocation stops cell 2."""
    import threading
    from mi_boti.discovery.overpass import ATTRIBUTION, DiscoveryBatch
    from mi_boti.domain.discord import ActorContext

    async def run():
        db, port, client, owner_actor = await initialized(database, configured)
        fetch_started = threading.Event()
        release_fetch = threading.Event()
        try:
            current = await db.call(repository.state)
            campaigns_ch = current["mappings"]["campaign.create"]
            discover_ch = current["mappings"]["discover"]
            config_ch = current["mappings"]["config"]

            # Configure operator role 444 via confirmed setup so channel overwrites match.
            set_role_ix = Interaction(replace(owner_actor, channel_id=config_ch))
            await client.operation(set_role_ix, "config", action_name="set", key="operator_role_ids", value="444")
            plan_row = await db.call(
                lambda d: dict(
                    d.connection.execute("SELECT * FROM setup_plans WHERE state='PREVIEW' ORDER BY created_at DESC LIMIT 1").fetchone()
                )
            )
            confirm_ix = Interaction(replace(owner_actor, channel_id=config_ch))
            await client.confirm_setup(confirm_ix, plan_row["id"], plan_row["plan_hash"])
            await asyncio.gather(*tuple(client.tasks))

            # Create a 2-cell campaign.
            create_ix = Interaction(replace(owner_actor, channel_id=campaigns_ch))
            await client.operation(
                create_ix,
                "campaign.create",
                options_dict={
                    "name": "Two Cell Auth Campaign",
                    "locality": "Quezon City",
                    "bbox": "14.648,121.047,14.657,121.061",
                },
            )
            camp_id = await db.call(lambda d: d.connection.execute("SELECT id FROM campaigns").fetchone()[0])
            # Update campaign to have 2 explicit cells so the worker runs 2 fetches.
            from mi_boti.repositories.campaigns import edit_campaign
            await db.call(
                lambda d: edit_campaign(
                    d,
                    owner_actor.user_id,
                    camp_id,
                    expected_version=1,
                    config={
                        "schema_version": 1,
                        "target_categories": ["restaurant", "cafe"],
                        "geography": {
                            "country_code": "PH",
                            "locality": "Quezon City",
                            "cells": [
                                {"cell_id": "c1", "bbox": [14.648, 121.047, 14.652, 121.054]},
                                {"cell_id": "c2", "bbox": [14.652, 121.054, 14.657, 121.061]},
                            ],
                        },
                        "exclusions": [],
                        "provider_id": None,
                        "service_description": "Two cells",
                    },
                )
            )

            operator = replace(
                owner_actor,
                channel_id=discover_ch,
                user_id="777777777777777777",
                role_ids=frozenset({"444"}),
                administrator=False,
            )
            port.members[operator.user_id] = operator

            calls = []

            class BlockingSource:
                source_namespace = "osm"
                policy_version = "overpass-2026-11"

                def discover(self, planned, *, max_elements, **_):
                    calls.append(planned.geographic_cell)
                    if len(calls) == 1:
                        fetch_started.set()
                        release_fetch.wait(timeout=5.0)
                    return DiscoveryBatch(
                        (
                            {
                                "name": f"Cafe {planned.geographic_cell}",
                                "source_namespace": "osm",
                                "source_id": f"node/{len(calls)}",
                                "source_url": f"https://www.openstreetmap.org/node/{len(calls)}",
                                "observed_at": "2026-11-14T00:00:00.000000Z",
                                "policy_version": "overpass-2026-11",
                                "attribution": ATTRIBUTION,
                                "address": {"country": "PH", "city": "Quezon City"},
                            },
                        ),
                        False,
                        (),
                    )

            client.discovery_source_factory = lambda: BlockingSource()
            op_ix = Interaction(operator)
            await client.operation(
                op_ix,
                "discover",
                options_dict={"campaign_id": camp_id, "limit": 10},
            )

            # Wait until cell 1 network fetch is in flight on the background thread.
            while not fetch_started.is_set():
                await asyncio.sleep(0.01)

            # Prove AsyncDatabase is NOT blocked while the network request is in flight!
            db_probe = await asyncio.wait_for(
                db.call(lambda d: d.connection.execute("SELECT 1").fetchone()[0]),
                timeout=0.5,
            )
            assert db_probe == 1

            # Revoke the operator's role while cell 1 is in flight; cell 1 pre-commit revalidation must interrupt!
            port.members[operator.user_id] = replace(operator, role_ids=frozenset())
            release_fetch.set()
            await asyncio.gather(*tuple(client.tasks))
            assert calls == ["c1"]
            assert any("finished with state `INTERRUPTED` (`AUTHORIZATION_LOST`)" in msg["content"] for msg in op_ix.sent)
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]) == 0
        finally:
            release_fetch.set()
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


def test_guide_command_and_persistent_button_are_private_and_create_no_jobs(database, configured):
    async def run():
        db,port,client,actor=await initialized(database,configured)
        try:
            current=await db.call(repository.state)
            guide_actor=replace(actor,channel_id=current["mappings"]["guide"])
            calls=list(port.calls)
            interaction=Interaction(guide_actor)
            await client.operation(interaction,"guide")
            assert interaction.sent[-1]["embed"].title=="Mi Boti · your tool guide"
            panel=current["panels"]["guide"]
            button_interaction=Interaction(guide_actor)
            button_interaction.message=SimpleNamespace(id=int(panel["message_id"]))
            await client.panel_action(button_interaction,"guide",panel["id"],panel["revision"])
            assert button_interaction.sent[-1]["embed"].title=="Mi Boti · your tool guide"
            assert await db.call(lambda d:d.connection.execute("SELECT count(*) FROM jobs").fetchone()[0])==0
            assert port.calls==calls
            denied=Interaction(actor)
            await client.operation(denied,"guide")
            assert 'Use <#' in denied.sent[-1]["content"]
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
