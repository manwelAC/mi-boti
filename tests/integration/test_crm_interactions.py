import asyncio
from dataclasses import replace
import hashlib
from uuid import uuid4

import pytest

from conftest import business as make_business
from test_discord_transport import initialized, Interaction
from test_research_evidence import research_job
from mi_boti.domain.values import utc_now
from mi_boti.domain.crm import CrmError
from mi_boti.repositories import crm, discord as discord_repo
from mi_boti.repositories.research import begin_run, finish_run
from mi_boti.research.collector import PageObservation, Collection
from mi_boti.discord_app.crm import CrmInteractions


ACTOR = "223456789012345678"


def fixture(db, text=None):
    business = make_business(db.connection)
    job, token = research_job(db, business)
    run = begin_run(db, job, token)
    text = text or "Public contact: hello@public.example. Phone: +63 (2) 8123-4567. Website: https://public.example/contact."
    page = PageObservation("https://public.example/contact", "https://public.example/contact", utc_now(), text,
                           hashlib.sha256(text.encode()).hexdigest(), "review-v1", ("Literal public source assertion.",))
    evidence = finish_run(db, run, token, Collection("SUCCEEDED", (page,), 2, ()))[0]
    return business, evidence


@pytest.mark.parametrize("kind,value", [("EMAIL", "hello@public.example"), ("PHONE", "+63 (2) 8123-4567"), ("WEBSITE", "https://public.example/contact")])
def test_contact_capture_requires_literal_evidence_and_preserves_provenance(database, kind, value):
    business, evidence = fixture(database)
    before = list(database.connection.iterdump())
    plan = crm.contact_preview(database, business, kind=kind, value=value, evidence_id=evidence, rationale="Confirmed the published business contact.")
    assert before == list(database.connection.iterdump())
    contact = crm.record_contact(database, business, ACTOR, expected_revision=plan["expected_revision"], kind=kind, value=value, evidence_id=evidence, rationale=plan["rationale"])
    assert contact["evidence_id"] == evidence and contact["business_id"] == business
    assert database.connection.execute("SELECT strength FROM business_identifiers WHERE business_id=?", (business,)).fetchone()[0] == "SUPPORTING"
    assert database.connection.execute("SELECT count(*) FROM identity_claims").fetchone()[0] == 0
    assert database.connection.execute("SELECT revision FROM businesses WHERE id=?", (business,)).fetchone()[0] == 2
    with pytest.raises(CrmError, match="already recorded"):
        crm.record_contact(database, business, ACTOR, expected_revision=2, kind=kind, value=value, evidence_id=evidence, rationale="Duplicate route.")
    assert database.connection.execute("SELECT count(*) FROM business_contacts").fetchone()[0] == 1


@pytest.mark.parametrize("case", ["guessed-email", "guessed-phone", "guessed-website", "foreign-evidence", "stale", "missing-revision", "private-url", "local-case", "email-suffix", "email-prefix", "long-punctuation", "unicode-domain"])
def test_invalid_contact_never_writes(database, case):
    raw = "Public contact: other!hello@public.example" if case == "email-prefix" else "!" * 18000 if case == "long-punctuation" else None
    if case == "unicode-domain": raw = "Public contact: hello@publİc.example"
    business, evidence = fixture(database, raw)
    options = dict(expected_revision=1, kind="EMAIL", value="hello@public.example", evidence_id=evidence, rationale="Named evidence review.")
    if case == "guessed-email": options["value"] = "sales@public.example"
    if case == "guessed-phone": options.update(kind="PHONE", value="+639171234567")
    if case == "guessed-website": options.update(kind="WEBSITE", value="https://different.example/")
    if case == "foreign-evidence": options["evidence_id"] = fixture(database)[1]
    if case == "stale": options["expected_revision"] = 99
    if case == "missing-revision": options["expected_revision"] = None
    if case == "private-url": options.update(kind="WEBSITE", value="http://127.0.0.1/")
    if case == "local-case": options["value"] = "HELLO@public.example"
    if case == "email-suffix": options["value"] = "hello@public.example.evil"
    before = list(database.connection.iterdump())
    with pytest.raises(CrmError): crm.record_contact(database, business, ACTOR, **options)
    assert before == list(database.connection.iterdump())


@pytest.mark.parametrize("kind", ["contact", "qualification", "transition"])
@pytest.mark.parametrize("case", ["success", "cancel", "actor", "expired", "channel", "permission", "stale", "concurrent"])
def test_isolated_crm_previews_and_confirmations(database, configured, kind, case, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("CRM interaction must not fetch, execute AI or send outreach.")
    monkeypatch.setattr("httpx.AsyncClient", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    business, evidence = fixture(database)
    lead = crm.qualify_manual(database, business, ACTOR, expected_revision=1, evidence_ids=[evidence], rationale="Initial human review.") if kind == "transition" else None
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(discord_repo.state)
            actor = replace(actor, channel_id=current["mappings"]["pipeline" if kind == "transition" else "lead"])
            ui = CrmInteractions(client)
            preview = Interaction(actor)
            before = await db.call(lambda d: list(d.connection.iterdump()))
            if kind == "contact": await ui.preview_contact(preview, business, kind="EMAIL", value="hello@public.example", evidence_id=evidence, rationale="Reviewed business attribution.")
            elif kind == "qualification": await ui.preview_qualification(preview, business, evidence_ids=[evidence], rationale="Reviewed fit with published business facts.")
            else: await ui.preview_transition(preview, lead["id"], expected_revision=1, target_stage="REVIEWING")
            assert before == await db.call(lambda d: list(d.connection.iterdump()))
            assert len(preview.sent[-1]["embed"]) <= 6000
            view = preview.sent[-1]["view"]
            if case == "actor": actor = replace(actor, user_id="999")
            if case == "expired": view.expires = 0
            if case == "channel": actor = replace(actor, channel_id="900")
            if case == "permission": port.members.pop(actor.user_id)
            if case == "stale":
                await db.call(lambda d: d.connection.execute("UPDATE " + ("leads" if kind == "transition" else "businesses") + " SET revision=revision+1"))
            ix = Interaction(actor)
            if case == "cancel": await view.cancel(ix)
            elif case == "concurrent": await asyncio.gather(view.confirm(ix), view.confirm(Interaction(actor)))
            else: await view.confirm(ix)
            success = case in {"success", "concurrent"}
            if kind == "contact": assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM business_contacts").fetchone()[0]) == int(success)
            elif kind == "qualification": assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM leads").fetchone()[0]) == int(success)
            else: assert await db.call(lambda d: d.connection.execute("SELECT stage FROM leads").fetchone()[0]) == ("REVIEWING" if success else "NEW")
            if success:
                replay = Interaction(actor); await view.confirm(replay)
                assert "was used" in replay.sent[-1]["content"]
            for table in ("scores", "findings", "hunt_credits"):
                assert await db.call(lambda d: d.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]) == 0
            assert not client.tasks
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_isolated_contact_qualification_pipeline_and_notes_flow(database, configured):
    business, evidence = fixture(database)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(discord_repo.state)
            actor = replace(actor, channel_id=current["mappings"]["lead"])
            ui = CrmInteractions(client)
            contact_ix = Interaction(actor)
            await ui.preview_contact(contact_ix, business, kind="EMAIL", value="hello@public.example", evidence_id=evidence, rationale="Reviewed literal public contact and attribution.")
            await contact_ix.sent[-1]["view"].confirm(Interaction(actor))
            contact_id = await db.call(lambda d: d.connection.execute("SELECT id FROM business_contacts").fetchone()[0])
            qualification = Interaction(actor)
            await ui.preview_qualification(qualification, business, evidence_ids=[evidence], rationale="Reviewed public services and relevance.")
            await qualification.sent[-1]["view"].confirm(Interaction(actor))
            lead = await db.call(lambda d: dict(d.connection.execute("SELECT * FROM leads").fetchone()))
            for stage in ("REVIEWING", "READY"):
                preview = Interaction(actor)
                options = {"reviewed_evidence_ids": [evidence], "contact_id": contact_id} if stage == "READY" else {}
                await ui.preview_transition(preview, lead["id"], expected_revision=lead["revision"], target_stage=stage, **options)
                await preview.sent[-1]["view"].confirm(Interaction(actor))
                lead = await db.call(lambda d: dict(d.connection.execute("SELECT * FROM leads").fetchone()))
            body = "Reviewed @everyone **public facts**. " * 40
            await ui.add_note(Interaction(actor), lead["id"], expected_revision=lead["revision"], body=body)
            note = await db.call(lambda d: dict(d.connection.execute("SELECT * FROM lead_notes").fetchone()))
            for render in (lambda ix: ui.list_leads(ix), lambda ix: ui.detail(ix, lead["id"]),
                           lambda ix: ui.notes(ix, lead["id"]), lambda ix: ui.show_note(ix, lead["id"], note["id"])):
                ix = Interaction(actor)
                await render(ix)
                embed = ix.sent[-1]["embed"]
                assert len(embed) <= 6000
                assert all(len(field.value) <= 1024 for field in embed.fields)
                assert "@everyone" not in str(embed.to_dict())
            assert lead["stage"] == "READY" and note["body"] == body.strip()
            assert not client.tasks
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_long_review_text_is_readable_without_confirming_or_mutating(database, configured):
    business, evidence = fixture(database)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(discord_repo.state)
            actor = replace(actor, channel_id=current["mappings"]["lead"])
            ui = CrmInteractions(client)
            rationale = "Reviewed " + "A" * 1500
            ix = Interaction(actor)
            await ui.preview_qualification(ix, business, evidence_ids=[evidence], rationale=rationale)
            view = ix.sent[-1]["view"]
            before = await db.call(lambda d: list(d.connection.iterdump()))
            full = Interaction(actor)
            await view.read_full(full)
            assert full.sent[-1]["embed"].description == rationale
            assert not view.used
            assert before == await db.call(lambda d: list(d.connection.iterdump()))
            denied = Interaction(replace(actor, user_id="999"))
            await view.read_full(denied)
            assert "embed" not in denied.sent[-1]
            assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM leads").fetchone()[0]) == 0
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_shared_published_contact_stays_a_supporting_identifier_not_a_merge(database):
    first, evidence1 = fixture(database)
    second, evidence2 = fixture(database)
    for business, evidence in ((first, evidence1), (second, evidence2)):
        crm.record_contact(database, business, ACTOR, expected_revision=1, kind="EMAIL", value="hello@public.example", evidence_id=evidence, rationale="Explicit shared public route attribution reviewed.")
    assert database.connection.execute("SELECT count(DISTINCT business_id) FROM business_contacts").fetchone()[0] == 2
    assert database.connection.execute("SELECT count(*) FROM identity_claims").fetchone()[0] == 0
    assert database.connection.execute("SELECT count(*) FROM business_identifiers WHERE strength='SUPPORTING'").fetchone()[0] == 2


def test_source_url_path_is_preserved_exactly_in_contact_proof(database):
    business, evidence = fixture(database)
    exact = "https://public.example/contact."
    database.connection.execute("UPDATE evidence SET source_url=? WHERE id=?", (exact, evidence))
    contact = crm.record_contact(database, business, ACTOR, expected_revision=1, kind="WEBSITE", value=exact, evidence_id=evidence, rationale="Reviewed the exact observed source URL.")
    assert contact["value"] == exact and contact["normalized_value"] == exact


def test_visible_url_punctuation_is_not_silently_removed_to_guess_a_route(database):
    business, evidence = fixture(database, "Published website: https://other.example/contact.")
    with pytest.raises(CrmError, match="does not explicitly show"):
        crm.record_contact(database, business, ACTOR, expected_revision=1, kind="WEBSITE", value="https://other.example/contact", evidence_id=evidence, rationale="This guessed shortened path must not be accepted.")


def test_maximum_evidence_and_note_cards_fit_with_supplementary_unicode(database, configured):
    import json
    business, evidence = fixture(database)
    database.connection.execute("UPDATE businesses SET name=?,address_json=? WHERE id=?", ("🌱" * 1500, json.dumps({"city": "🌱" * 1000}), business))
    original = dict(database.connection.execute("SELECT * FROM evidence WHERE id=?", (evidence,)).fetchone())
    identifiers = [evidence]
    for index in range(9):
        row = original | {"id": str(uuid4()), "source_url": "https://public.example/" + "🌱" * 500 + str(index)}
        database.connection.execute("INSERT INTO evidence(" + ",".join(row) + ") VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))
        identifiers.append(row["id"])
    def units(value): return len(value.encode("utf-16-le")) // 2
    def check(embed):
        parts = [embed.title or "", embed.description or "", embed.footer.text or ""]
        for field in embed.fields:
            assert units(field.value) <= 1024
            parts.extend([field.name, field.value])
        assert sum(map(units, parts)) <= 6000
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            current = await db.call(discord_repo.state)
            actor = replace(actor, channel_id=current["mappings"]["lead"])
            ui = CrmInteractions(client)
            ix = Interaction(actor)
            await ui.preview_qualification(ix, business, evidence_ids=identifiers, rationale="🌱" * 2000)
            check(ix.sent[-1]["embed"])
            await ix.sent[-1]["view"].confirm(Interaction(actor))
            lead = await db.call(lambda d: dict(d.connection.execute("SELECT * FROM leads").fetchone()))
            for revision in range(1, 11):
                await db.call(lambda d, rev=revision: crm.add_note(d, lead["id"], ACTOR, expected_revision=rev, body="🌱" * 2000))
            notes = Interaction(actor)
            await ui.notes(notes, lead["id"])
            assert len(notes.sent[-1]["embed"].fields) == 10
            check(notes.sent[-1]["embed"])
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())
