import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from test_identity_ui import seed
from test_discord_transport import initialized, Interaction
from mi_boti.discord_app.discovery_results import read_results, results_card, show_results
from mi_boti.repositories import discord as repository
from mi_boti.domain.registry import RegistryError


def test_persisted_results_and_page_bounds(database):
    seed(database)
    job = database.connection.execute("SELECT id FROM jobs WHERE kind='DISCOVER'").fetchone()[0]
    data = read_results(database, job)
    assert data["total"] == 2 and len(data["rows"]) == 2
    assert len(results_card(data)) <= 6000
    assert not read_results(database, job, 2)["rows"]
    with pytest.raises(RegistryError): read_results(database, job, 0)
    with pytest.raises(RegistryError): read_results(database, str(uuid4()))


@pytest.mark.parametrize("case", ["view", "wrong-channel", "other-actor", "revoked", "inspect", "expired"])
def test_private_results_recheck_policy_without_writes(database, configured, case):
    seed(database)
    job = database.connection.execute("SELECT id FROM jobs WHERE kind='DISCOVER'").fetchone()[0]
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["discover"])
            initial = Interaction(actor)
            await show_results(client, initial, job)
            view = initial.sent[-1]["view"]
            assert len(initial.sent[-1]["embed"].fields) == 2
            before = await db.call(lambda d: list(d.connection.execute("SELECT id,state FROM candidates")))
            if case == "wrong-channel": actor = replace(actor, channel_id="900")
            if case == "other-actor": actor = replace(actor, user_id="999")
            if case == "revoked": port.members.pop(actor.user_id)
            if case == "expired": view.expires = 0
            interaction = Interaction(actor)
            if case == "inspect":
                select = view.children[-1]
                select._values = [view.data["rows"][0]["id"]]
                await select.callback(interaction)
                assert "Source reference" in interaction.sent[-1]["embed"].fields[0].name
            else:
                await view.children[1].callback(interaction)
                if case != "view": assert "embed" not in interaction.sent[-1]
                else: assert "No saved observations" in interaction.sent[-1]["embed"].fields[0].value
            after = await db.call(lambda d: list(d.connection.execute("SELECT id,state FROM candidates")))
            assert [tuple(r) for r in before] == [tuple(r) for r in after]
            assert client.tasks == set()
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
