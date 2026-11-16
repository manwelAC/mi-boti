import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from test_evidence_reader import seed_evidence
from test_discord_transport import initialized
from mi_boti.repositories import crm
from mi_boti.repositories import discord as discord_repo
from mi_boti.repositories.async_database import AsyncDatabase
from mi_boti.domain.crm import CrmError
from mi_boti.domain.values import utc_now
from mi_boti.services.crm import ManualCrmService


ACTOR = "223456789012345678"
EXPECTED_TRANSITIONS = {
    "NEW": {"REVIEWING", "ARCHIVED"},
    "REVIEWING": {"READY", "LOST", "ARCHIVED"},
    "READY": {"CONTACTED", "REVIEWING", "LOST", "ARCHIVED"},
    "CONTACTED": {"FOLLOW_UP", "WON", "LOST", "ARCHIVED"},
    "FOLLOW_UP": {"CONTACTED", "WON", "LOST", "ARCHIVED"},
    "WON": {"REVIEWING"}, "LOST": {"REVIEWING"}, "ARCHIVED": {"REVIEWING"},
}


def qualification(db):
    evidence, _ = seed_evidence(db)
    business = db.connection.execute("SELECT business_id FROM evidence WHERE id=?", (evidence,)).fetchone()[0]
    return business, evidence


def make_lead(db):
    business, evidence = qualification(db)
    lead = crm.qualify_manual(db, business, ACTOR, expected_revision=1, evidence_ids=[evidence], rationale="Human reviewed public services and fit.")
    contact = str(uuid4())
    db.connection.execute("INSERT INTO business_contacts VALUES (?,?,'WEBSITE','https://public.example/','https://public.example/',?,?)", (contact, business, evidence, utc_now()))
    return lead, evidence, contact


def test_manual_qualification_preserves_origin_and_creates_no_score_or_credit(database):
    business, evidence = qualification(database)
    before = dict(database.connection.execute("SELECT * FROM businesses WHERE id=?", (business,)).fetchone())
    lead = crm.qualify_manual(database, business, ACTOR, expected_revision=1, evidence_ids=[evidence], rationale="Evidence reviewed by operator.")
    assert lead["qualification_kind"] == "MANUAL" and lead["current_score_id"] is None and lead["stage"] == "NEW"
    after = dict(database.connection.execute("SELECT * FROM businesses WHERE id=?", (business,)).fetchone())
    assert after["disposition"] == "QUALIFIED" and after["revision"] == 2
    assert before["origin_job_id"] == after["origin_job_id"] and before["origin_hunt_id"] == after["origin_hunt_id"]
    for table in ("scores", "findings", "hunt_credits"):
        assert database.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    with pytest.raises(CrmError): crm.qualify_manual(database, business, ACTOR, expected_revision=2, evidence_ids=[evidence], rationale="Replay")
    assert database.connection.execute("SELECT count(*) FROM leads").fetchone()[0] == 1


@pytest.mark.parametrize("source", list(EXPECTED_TRANSITIONS))
@pytest.mark.parametrize("target", list(EXPECTED_TRANSITIONS))
def test_all_documented_pipeline_edges_and_rejected_edges_are_atomic(database, source, target):
    lead, evidence, contact = make_lead(database)
    database.connection.execute("UPDATE leads SET stage=? WHERE id=?", (source, lead["id"]))
    options = dict(expected_revision=1, target_stage=target, note="Reviewed outcome or reopening rationale.")
    if target == "READY": options.update(reviewed_evidence_ids=[evidence], contact_id=contact)
    if target == "CONTACTED": options["attestation"] = "I manually contacted this business outside Mi Boti."
    if target == "FOLLOW_UP": options["due_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    if target in EXPECTED_TRANSITIONS[source]:
        updated = crm.transition(database, lead["id"], ACTOR, **options)
        assert updated["stage"] == target and updated["revision"] == 2
        assert database.connection.execute("SELECT count(*) FROM followups").fetchone()[0] == int(target == "FOLLOW_UP")
    else:
        before = list(database.connection.iterdump())
        with pytest.raises(CrmError): crm.transition(database, lead["id"], ACTOR, **options)
        assert list(database.connection.iterdump()) == before


@pytest.mark.parametrize("case", ["foreign-evidence", "no-evidence", "stale", "blank", "duplicate-evidence", "tampered-evidence", "unknown-confidence", "future-evidence"])
def test_invalid_qualification_rolls_back(database, case):
    business, evidence = qualification(database)
    other, foreign = qualification(database)
    opts = dict(expected_revision=1, evidence_ids=[evidence], rationale="Reviewed evidence.")
    if case == "foreign-evidence": opts["evidence_ids"] = [foreign]
    if case == "no-evidence": opts["evidence_ids"] = []
    if case == "stale": opts["expected_revision"] = 99
    if case == "blank": opts["rationale"] = " "
    if case == "duplicate-evidence": opts["evidence_ids"] = [evidence, evidence]
    if case == "tampered-evidence": database.connection.execute("UPDATE evidence SET extracted_fact=extracted_fact||'tampered' WHERE id=?", (evidence,))
    if case == "unknown-confidence": database.connection.execute("UPDATE evidence SET confidence=0 WHERE id=?", (evidence,))
    if case == "future-evidence": database.connection.execute("UPDATE evidence SET observed_at='2099-01-01T00:00:00.000000Z' WHERE id=?", (evidence,))
    before = list(database.connection.iterdump())
    with pytest.raises(CrmError): crm.qualify_manual(database, business, ACTOR, **opts)
    assert list(database.connection.iterdump()) == before


@pytest.mark.parametrize("case", ["ready-contact", "ready-evidence", "contact-attestation", "followup-due", "followup-naive", "outcome-note", "reopen-note", "stale"])
def test_pipeline_prerequisites_reject_before_any_mutation(database, case):
    lead, evidence, contact = make_lead(database)
    source, target, options = "REVIEWING", "READY", dict(reviewed_evidence_ids=[evidence], contact_id=contact)
    if case == "ready-contact": options["contact_id"] = str(uuid4())
    if case == "ready-evidence": options["reviewed_evidence_ids"] = []
    if case == "contact-attestation": source, target, options = "READY", "CONTACTED", {}
    if case in {"followup-due", "followup-naive"}:
        source, target, options = "CONTACTED", "FOLLOW_UP", {}
        if case == "followup-naive": options["due_at"] = "2099-01-01T12:00:00"
    if case == "outcome-note": source, target, options = "CONTACTED", "WON", {}
    if case == "reopen-note": source, target, options = "ARCHIVED", "REVIEWING", {}
    database.connection.execute("UPDATE leads SET stage=? WHERE id=?", (source, lead["id"]))
    before = list(database.connection.iterdump())
    with pytest.raises(CrmError):
        crm.transition(database, lead["id"], ACTOR, expected_revision=99 if case == "stale" else 1, target_stage=target, **options)
    assert list(database.connection.iterdump()) == before


def test_concurrent_qualification_creates_only_one_lead(database):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from mi_boti.repositories.database import Database
    business, evidence = qualification(database)
    barrier = threading.Barrier(2)
    def attempt():
        with Database(database.path) as db:
            barrier.wait(timeout=5)
            try:
                return crm.qualify_manual(db, business, ACTOR, expected_revision=1, evidence_ids=[evidence], rationale="Concurrent named human review.")["id"]
            except CrmError:
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert database.connection.execute("SELECT count(*) FROM leads").fetchone()[0] == 1
    assert database.connection.execute("SELECT count(*) FROM lead_events WHERE kind='MANUAL_QUALIFIED'").fetchone()[0] == 1


def test_notes_are_append_only_and_stale_or_cross_lead_corrections_fail(database):
    lead, _, _ = make_lead(database)
    other, _, _ = make_lead(database)
    note = crm.add_note(database, lead["id"], ACTOR, expected_revision=1, body="Original @everyone text preserved.")
    correction = crm.add_note(database, lead["id"], ACTOR, expected_revision=2, body="Corrected observation.", supersedes_id=note["id"])
    assert note["body"] == database.connection.execute("SELECT body FROM lead_notes WHERE id=?", (note["id"],)).fetchone()[0]
    assert correction["supersedes_id"] == note["id"]
    with pytest.raises(CrmError): crm.add_note(database, lead["id"], ACTOR, expected_revision=2, body="Stale")
    with pytest.raises(CrmError): crm.add_note(database, other["id"], ACTOR, expected_revision=1, body="Wrong lead", supersedes_id=note["id"])
    assert crm.list_records(database, lead_id=lead["id"], kind="lead_notes")["total"] == 2


@pytest.mark.parametrize("case", ["allowed", "denied", "wrong-channel", "no-confirmation", "role-revoked"])
def test_service_checks_fresh_authorization_confirmation_and_transaction_policy(database, configured, case, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("Isolated manual CRM must not execute a provider, network fetch or outreach.")
    monkeypatch.setattr("subprocess.Popen", forbidden)
    monkeypatch.setattr("httpx.AsyncClient", forbidden)
    business, evidence = qualification(database)
    async def run():
        db, port, client, actor = await initialized(database, configured)
        try:
            state = await db.call(discord_repo.state)
            actor = replace(actor, channel_id=state["mappings"]["lead"])
            if case == "wrong-channel": actor = replace(actor, channel_id="900")
            if case == "role-revoked": actor = replace(actor, user_id="999", role_ids=frozenset({"444"}))
            calls = []
            async def authorize(command):
                calls.append(command)
                if case == "denied": raise CrmError("Current role denied.")
                return actor
            service = ManualCrmService(db, authorize, guild_id=client.settings.guild_id, owner_ids=client.settings.owner_ids)
            action = service.qualify_manual(business, confirmed=case != "no-confirmation", expected_revision=1, evidence_ids=[evidence], rationale="Explicit human review.")
            if case == "allowed":
                lead = await action
                assert (await service.get_lead(lead["id"]))["stage"] == "NEW"
            else:
                with pytest.raises(CrmError): await action
                assert await db.call(lambda d: d.connection.execute("SELECT count(*) FROM leads").fetchone()[0]) == 0
            assert calls and not client.tasks
        finally:
            await client.close()
            await db.close()
    asyncio.run(run())


def test_crm_stage_and_append_only_history_survive_backup_and_recovery(database, tmp_path):
    from mi_boti.storage.backup import create_verified_copy, restore_verified_copy
    from mi_boti.repositories.database import Database
    from mi_boti.jobs.discovery import recover_interrupted_work
    lead, evidence, contact = make_lead(database)
    lead = crm.transition(database, lead["id"].upper(), ACTOR, expected_revision=1, target_stage="REVIEWING")
    crm.add_note(database, lead["id"], ACTOR, expected_revision=2, body="Reviewed the published contact route.")
    lead = crm.transition(database, lead["id"], ACTOR, expected_revision=3, target_stage="READY", reviewed_evidence_ids=[evidence], contact_id=contact)
    backup = create_verified_copy(database.connection, tmp_path / "copies", minimum_mib=1)
    restored = tmp_path / "restored.sqlite3"
    restore_verified_copy(backup, restored, expected_guild="123456789012345678", supported_version=1)
    with Database(restored) as db:
        recover_interrupted_work(db)
        assert crm.get_lead(db, lead["id"])["stage"] == "READY"
        assert crm.get_lead(db, lead["id"])["revision"] == 4
        assert crm.list_records(db)["records"][0]["business_name"]
        assert crm.list_records(db, lead_id=lead["id"], kind="lead_notes")["total"] == 1
        assert crm.list_records(db, lead_id=lead["id"], kind="lead_events")["total"] == 4
        assert not db.connection.execute("PRAGMA foreign_key_check").fetchall()
