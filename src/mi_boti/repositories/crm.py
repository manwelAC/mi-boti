"""Transactional manual CRM core. Runtime/Discord integration is unreleased."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from ..domain import crm
from ..domain.values import snowflake, utc_now
from ..domain.errors import AppError
from ..domain.campaigns import parse_utc
from ..research.collector import safe_url
from .research_integrity import verify_excerpt


def _event(c, lead_id, actor, kind, payload, now):
    c.execute("INSERT INTO lead_events VALUES (?,?,?,?,?,?)", (str(uuid4()), lead_id, actor, kind, json.dumps(payload), now))
    c.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
              (str(uuid4()), str(uuid4()), actor, "crm." + kind.lower(), "lead", lead_id, "SUCCESS", json.dumps(payload), now))


def _identity(c, business_id):
    if c.execute("SELECT 1 FROM identity_reviews r,json_each(r.matches_json) m WHERE r.state='OPEN' AND m.value=?", (business_id,)).fetchone():
        raise crm.CrmError("Resolve the open business identity review before this CRM action.")


def _evidence(c, business_id, identifiers):
    identifiers = crm.evidence_ids(identifiers)
    for identifier in identifiers:
        row = c.execute("SELECT e.*,r.business_id AS run_business,r.state AS run_state FROM evidence e "
                        "LEFT JOIN research_runs r ON r.id=e.research_run_id WHERE e.id=?", (identifier,)).fetchone()
        if (not row or row["business_id"] != business_id or not row["extracted_fact"].strip()
                or row["confidence"] <= 0 or not (row["source_url"] or row["source_identifier"])
                or (row["research_run_id"] and (row["run_business"] != business_id or row["run_state"] not in {"SUCCEEDED", "PARTIAL"}))):
            raise crm.CrmError("Review usable, source-linked evidence belonging to this business.")
        if row["candidate_id"]:
            candidate = c.execute("SELECT business_id,state FROM candidates WHERE id=?", (row["candidate_id"],)).fetchone()
            if not candidate or candidate[0] != business_id or candidate[1] not in {"NEW", "EXISTING", "RESOLVED_NEW", "RESOLVED_EXISTING"}:
                raise crm.CrmError("Candidate evidence has unresolved or conflicting business provenance.")
        try:
            verify_excerpt(row["extracted_fact"], row["limitations_json"])
            if parse_utc(row["observed_at"]) > datetime.now(timezone.utc):
                raise crm.CrmError("Evidence observation time is in the future.")
            if row["source_url"]: safe_url(row["source_url"])
        except (AppError, ValueError):
            raise crm.CrmError("Selected evidence failed source, timestamp or excerpt-integrity validation.") from None
    return identifiers


def _lead(c, lead_id, expected_revision=None):
    row = c.execute("SELECT * FROM leads WHERE id=?", (crm.identifier(lead_id),)).fetchone()
    if not row: raise crm.CrmError("Lead not found in this deployment.")
    if expected_revision is not None and row["revision"] != crm.revision(expected_revision):
        raise crm.CrmError("Lead revision changed; reload before applying this action.")
    return row


def qualify_manual(db, business_id, actor_id, *, expected_revision, evidence_ids, rationale, _guard=None):
    business_id, actor = crm.identifier(business_id), snowflake(actor_id)
    rationale, expected_revision = crm.text(rationale), crm.revision(expected_revision)
    now, lead_id = utc_now(), str(uuid4())
    with db.transaction() as c:
        if _guard: _guard(c)
        business = c.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        if not business: raise crm.CrmError("Business not found in this deployment.")
        if business["revision"] != expected_revision: raise crm.CrmError("Business revision changed; reload before qualifying.")
        _identity(c, business_id)
        if c.execute("SELECT 1 FROM leads WHERE business_id=?", (business_id,)).fetchone():
            raise crm.CrmError("This business already has a CRM lead; reopen its existing record.")
        selected = _evidence(c, business_id, evidence_ids)
        c.execute("INSERT INTO leads VALUES (?,?,NULL,'MANUAL','NEW',1,?,?)", (lead_id, business_id, now, now))
        c.execute("UPDATE businesses SET disposition='QUALIFIED',revision=revision+1,updated_at=? WHERE id=?", (now, business_id))
        payload = {"evidence_ids": selected, "rationale": rationale, "qualification_kind": "MANUAL", "quota_credit": False}
        _event(c, lead_id, actor, "MANUAL_QUALIFIED", payload, now)
        c.execute("INSERT INTO business_events VALUES (?,?,?,?,?,?)", (str(uuid4()), business_id, actor, "crm.manual_qualified", json.dumps(payload | {"lead_id": lead_id}), now))
        return dict(c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())


def transition(db, lead_id, actor_id, *, expected_revision, target_stage, note=None, attestation=None,
               reviewed_evidence_ids=None, contact_id=None, due_at=None, _guard=None):
    lead_id = crm.identifier(lead_id)
    actor, now = snowflake(actor_id), utc_now()
    note = crm.text(note, required=False)
    with db.transaction() as c:
        if _guard: _guard(c)
        lead = _lead(c, lead_id, expected_revision)
        source = lead["stage"]
        if not isinstance(target_stage, str) or target_stage not in crm.TRANSITIONS[source]: raise crm.CrmError("This pipeline transition is not allowed.")
        if (target_stage in {"WON", "LOST"} or source in {"WON", "LOST", "ARCHIVED"}) and not note:
            raise crm.CrmError("Record a nonempty outcome or reopening rationale.")
        payload = {"from": source, "to": target_stage, "note": note}
        if target_stage == "READY":
            _identity(c, lead["business_id"])
            payload["evidence_ids"] = _evidence(c, lead["business_id"], reviewed_evidence_ids)
            contact = c.execute("SELECT * FROM business_contacts WHERE id=?", (crm.identifier(contact_id),)).fetchone()
            if not contact or contact["business_id"] != lead["business_id"] or not contact["value"].strip():
                raise crm.CrmError("READY requires an existing source-backed contact route for this business.")
            _evidence(c, lead["business_id"], [contact["evidence_id"]])
            payload["contact_id"] = contact["id"]
        if target_stage == "CONTACTED":
            payload["manual_contact_attestation"] = crm.text(attestation)
        if target_stage == "FOLLOW_UP":
            due = crm.due_time(due_at, now)
            followup = str(uuid4())
            c.execute("INSERT INTO followups VALUES (?,?,?,?,'PENDING',?,1,?,NULL)", (followup, lead_id, due, note, actor, now))
            payload.update(followup_id=followup, due_at=due)
        elif due_at is not None:
            raise crm.CrmError("A due time is accepted only when moving to FOLLOW_UP.")
        c.execute("UPDATE leads SET stage=?,revision=revision+1,updated_at=? WHERE id=?", (target_stage, now, lead_id))
        _event(c, lead_id, actor, "STAGE_CHANGED", payload, now)
        return dict(c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())


def add_note(db, lead_id, actor_id, *, expected_revision, body, supersedes_id=None, _guard=None):
    lead_id = crm.identifier(lead_id)
    supersedes_id = crm.identifier(supersedes_id) if supersedes_id is not None else None
    actor, body, now = snowflake(actor_id), crm.text(body), utc_now()
    with db.transaction() as c:
        if _guard: _guard(c)
        _lead(c, lead_id, expected_revision)
        if supersedes_id is not None:
            original = c.execute("SELECT lead_id FROM lead_notes WHERE id=?", (crm.identifier(supersedes_id),)).fetchone()
            if not original or original[0] != lead_id: raise crm.CrmError("A correction must reference a note on this lead.")
        note_id = str(uuid4())
        c.execute("INSERT INTO lead_notes VALUES (?,?,?,?,?,?)", (note_id, lead_id, actor, body, now, supersedes_id))
        c.execute("UPDATE leads SET revision=revision+1,updated_at=? WHERE id=?", (now, lead_id))
        _event(c, lead_id, actor, "NOTE_CORRECTED" if supersedes_id else "NOTE_ADDED", {"note_id": note_id, "supersedes_id": supersedes_id}, now)
        return dict(c.execute("SELECT * FROM lead_notes WHERE id=?", (note_id,)).fetchone())


def get_lead(db, lead_id):
    lead = dict(_lead(db.connection, lead_id))
    lead["business"] = dict(db.connection.execute("SELECT * FROM businesses WHERE id=?", (lead["business_id"],)).fetchone())
    return lead


def list_records(db, *, stage=None, lead_id=None, kind="leads", page=1):
    if type(page) is not int or page < 1: raise crm.CrmError("Page must be a positive integer.")
    if kind not in {"leads", "lead_notes", "lead_events"}: raise crm.CrmError("Unsupported CRM history kind.")
    where, args = "", []
    if kind == "leads":
        if stage is not None:
            if not isinstance(stage, str) or stage not in crm.TRANSITIONS: raise crm.CrmError("Unknown pipeline stage.")
            where, args = " WHERE stage=?", [stage]
    else:
        lead_id = crm.identifier(lead_id)
        _lead(db.connection, lead_id)
        where, args = " WHERE lead_id=?", [lead_id]
    total = db.connection.execute(f"SELECT count(*) FROM {kind}" + where, args).fetchone()[0]
    table = f"{kind} r" + (" JOIN businesses b ON b.id=r.business_id" if kind == "leads" else "")
    columns = "r.*,b.name AS business_name" if kind == "leads" else "r.*"
    rows = db.connection.execute(f"SELECT {columns} FROM {table}" + where + " ORDER BY r.created_at,r.id LIMIT 10 OFFSET ?", [*args, (page - 1) * 10]).fetchall()
    return {"total": total, "page": page, "records": [dict(row) for row in rows]}
