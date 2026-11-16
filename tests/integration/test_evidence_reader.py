import asyncio
from dataclasses import replace

import pytest

from conftest import business as make_business
from test_research_evidence import research_job
from test_discord_transport import initialized, Interaction
from mi_boti.discord_app.evidence import read_page, evidence_card, show_evidence, EvidencePicker
from mi_boti.repositories import discord as repository
from mi_boti.repositories.research import begin_run, finish_run
from mi_boti.research.collector import PageObservation, Collection, ResearchError
from mi_boti.domain.values import utc_now
import hashlib


def seed_evidence(db):
    business = make_business(db.connection)
    job, token = research_job(db, business)
    run = begin_run(db, job, token)
    text = "Public service. @everyone **do not execute** " * 100
    page = PageObservation("https://public.example/", "https://public.example/", utc_now(), text,
                           hashlib.sha256(text.encode()).hexdigest(), "review-v1", ("Not independently verified.",))
    return finish_run(db, run, token, Collection("SUCCEEDED", (page,), 2, ()))[0], text


def test_full_excerpt_paging_preserves_all_saved_text(database):
    identifier, original = seed_evidence(database)
    first = read_page(database, identifier)
    pages = [read_page(database, identifier, n) for n in range(1, first["pages"] + 1)]
    assert "".join(page["text"] for page in pages).endswith(original)
    assert all(len(evidence_card(page)) <= 6000 for page in pages)
    assert all(len(evidence_card(page).description) <= 4096 for page in pages)
    assert all("@everyone" not in evidence_card(page).description for page in pages)
    with pytest.raises(ResearchError): read_page(database, identifier, first["pages"] + 1)


@pytest.mark.parametrize("case", ["page", "picker", "channel", "actor", "expired", "permission"])
def test_evidence_controls_recheck_policy_without_writes(database, configured, case):
    identifier, _ = seed_evidence(database)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(repository.state)
            actor = replace(actor, channel_id=current["mappings"]["research"])
            ix = Interaction(actor)
            await show_evidence(client, ix, identifier)
            view = ix.sent[-1]["view"]
            if case == "channel": actor = replace(actor, channel_id="900")
            if case == "actor": actor = replace(actor, user_id="999")
            if case == "expired": view.expires = 0
            if case == "permission": port.members.pop(actor.user_id)
            before = await db.call(lambda d: [tuple(r) for r in d.connection.execute("SELECT * FROM evidence")])
            next_ix = Interaction(actor)
            if case == "picker":
                picker = EvidencePicker(client, actor.user_id, [{"id": identifier, "observed_at": utc_now()}])
                picker.children[0]._values = [identifier]
                await picker.children[0].callback(next_ix)
            else:
                await view.children[1].callback(next_ix)
            assert ("embed" in next_ix.sent[-1]) == (case in {"page", "picker"})
            assert before == await db.call(lambda d: [tuple(r) for r in d.connection.execute("SELECT * FROM evidence")])
            assert not client.tasks
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
