import asyncio
from dataclasses import replace

import pytest

from test_discord_transport import initialized, Interaction
from test_campaigns_and_reviews import sample_config, leased_discover_job, observation
from mi_boti.repositories import discord as repository
from mi_boti.repositories.campaigns import create_campaign, plan_unexhausted_queries, queue_discovery_query, begin_discovery_attempt
from mi_boti.repositories.registry import resolve
from mi_boti.discord_app.identity import lead, read_record, card


def seed(db):
    camp = create_campaign(db, "223456789012345678", "Review UI", sample_config())
    job, token = leased_discover_job(db)
    query = queue_discovery_query(db, job, token, camp.id, plan_unexhausted_queries(db, camp.id, policy_version="osm-v1")[0])
    begin_discovery_attempt(db, query, token)
    first = resolve(db, query, observation("node/1", website="https://shared.example"), token)
    held = resolve(db, query, observation("way/99", website="https://shared.example"), token)
    assert held.review_id
    return first.business_id, held.review_id


@pytest.mark.parametrize("case", ["link", "separate", "concurrent", "stale", "actor", "expired", "wrong-channel", "permissions", "invalid-rationale"])
def test_review_preview_and_fresh_confirmation(database, configured, case):
    business, review = seed(database)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["lead"])
            interaction = Interaction(actor)
            await lead(client, interaction, identifier=review, action="separate" if case == "separate" else "link",
                       target=None if case == "separate" else business,
                       rationale="" if case == "invalid-rationale" else "Compared the original source identity.")
            state = lambda d: d.connection.execute("SELECT state FROM identity_reviews WHERE id=?", (review,)).fetchone()[0]
            assert await db.call(state) == "OPEN"
            if case == "invalid-rationale":
                assert "view" not in interaction.sent[-1]
                return
            view = interaction.sent[-1]["view"]
            if case == "stale":
                await db.call(lambda d: d.connection.execute("UPDATE businesses SET revision=revision+1 WHERE id=?", (business,)))
            if case == "expired": view.expires = 0
            if case == "actor": actor = replace(actor, user_id="999")
            if case == "wrong-channel": actor = replace(actor, channel_id="900")
            if case == "permissions": port.members.pop(actor.user_id)
            confirm = Interaction(actor)
            if case == "concurrent":
                other = Interaction(actor)
                await asyncio.gather(view.confirm(confirm), view.confirm(other))
                assert sum("Identity resolved:" in i.sent[-1]["content"] for i in (confirm, other)) == 1
            else:
                await view.confirm(confirm)
            assert await db.call(state) == ("RESOLVED" if case in {"link", "separate", "concurrent"} else "OPEN")
            if case in {"link", "separate", "concurrent"}:
                replay = Interaction(actor)
                await view.confirm(replay)
                assert "already used" in replay.sent[-1]["content"]
            for table in ("leads", "scores", "hunt_credits", "research_runs"):
                assert await db.call(lambda d: d.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]) == 0
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_queue_and_records_are_bounded_and_sanitized(database):
    business, review = seed(database)
    queue = read_record(database)
    assert len(queue["rows"]) == 1
    assert not read_record(database, page=2)["rows"]
    assert read_record(database, business)["kind"] == "business"
    embed = card(read_record(database, review))
    assert len(embed) <= 6000
    untrusted = read_record(database, business)
    untrusted["name"] = "@everyone **fake score**"
    assert "@everyone" not in card(untrusted).description
    with pytest.raises(Exception, match="UUID"):
        read_record(database, "not-a-uuid")
    with pytest.raises(Exception, match="positive"):
        read_record(database, page=0)
