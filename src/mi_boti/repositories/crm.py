"""Transactional manual CRM core. Runtime/Discord integration is unreleased."""

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from ..domain import crm
from ..domain.values import snowflake, utc_now
from ..domain.errors import AppError
from ..domain.campaigns import parse_utc
from ..domain.registry import domain as registry_domain, phone as registry_phone
from ..research.collector import safe_url
from .research_integrity import verify_excerpt


EMAIL = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"


def _contact_url(value):
    try: return safe_url(value)
    except AppError:
        raise crm.CrmError("Contact URL/domain must be a permitted public HTTP/HTTPS reference.") from None


def _contact_value(kind, value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2048 or any(ord(char) < 32 for char in value):
        raise crm.CrmError("Contact value must be bounded public contact text without control characters.")
    value = value.strip()
    if kind == "EMAIL":
        if len(value) > 320 or not re.fullmatch(EMAIL, value): raise crm.CrmError("Use a literal publicly displayed email address.")
        local, host = value.rsplit("@", 1)
        if local.startswith(".") or local.endswith(".") or ".." in local: raise crm.CrmError("Email address format is unsupported.")
        _contact_url("https://" + host)
        normalized = local + "@" + host.casefold()
    elif kind == "PHONE":
        digits = "".join(char for char in value if char.isascii() and char.isdigit())
        if not re.fullmatch(r"\+?[0-9() .-]+", value) or not 7 <= len(digits) <= 15:
            raise crm.CrmError("Use the published phone number without a guessed country code or extension.")
        normalized = ("+" if value.startswith("+") else "") + digits
    elif kind == "WEBSITE":
        url, host = _contact_url(value)
        parts = urlsplit(url)
        normalized = urlunsplit((parts.scheme, f"[{host}]" if ":" in host else host, parts.path, parts.query, ""))
    else:
        raise crm.CrmError("Contact kind must be EMAIL, PHONE or WEBSITE.")
    return value, normalized


def _contact_plan(c, business_id, kind, value, evidence_id, rationale, expected_revision=None):
    business = c.execute("SELECT * FROM businesses WHERE id=?", (crm.identifier(business_id),)).fetchone()
    if not business: raise crm.CrmError("Business not found in this deployment.")
    if expected_revision is not None and business["revision"] != crm.revision(expected_revision):
        raise crm.CrmError("Business revision changed; reopen the contact review.")
    _identity(c, business["id"])
    evidence_id = _evidence(c, business["id"], [evidence_id])[0]
    evidence = c.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    value, normalized = _contact_value(kind, value)
    fact = evidence["extracted_fact"]
    if kind == "EMAIL":
        local, host = normalized.rsplit("@", 1)
        # Match only the requested literal route; never run the broad address
        # grammar repeatedly across arbitrary page text.
        pattern = r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~@-])" + re.escape(local) + "@(?ai:" + re.escape(host) + r")(?![\w@-]|\.[A-Za-z0-9])"
        matches = [normalized] if re.search(pattern, fact) else []
    elif kind == "PHONE":
        matches = []
        for match in re.finditer(r"(?<![\w+])\+?[0-9][0-9() .-]{5,38}[0-9](?!\w)", fact):
            try: matches.append(_contact_value(kind, match.group())[1])
            except crm.CrmError: pass
    else:
        matches = []
        candidates = [evidence["source_url"]] + re.findall(r"https?://[^\s<>\"']+", fact)
        for candidate in candidates:
            if not candidate: continue
            try: matches.append(_contact_value(kind, candidate)[1])
            except AppError: pass
    if normalized not in matches:
        raise crm.CrmError("The selected evidence does not explicitly show this contact route. Do not guess or infer contact details.")
    if c.execute("SELECT 1 FROM business_contacts WHERE business_id=? AND kind=? AND normalized_value=?", (business["id"], kind, normalized)).fetchone():
        raise crm.CrmError("This contact route is already recorded; inspect its existing source history.")
    return {"business_id": business["id"], "business_name": business["name"], "expected_revision": business["revision"],
            "address_json": business["address_json"],
            "kind": kind, "value": value, "normalized_value": normalized, "evidence_id": evidence_id,
            "source_url": evidence["source_url"], "source_identifier": evidence["source_identifier"], "observed_at": evidence["observed_at"], "rationale": crm.text(rationale)}


def contact_preview(db, business_id, *, kind, value, evidence_id, rationale, _guard=None):
    with db.transaction() as c:
        if _guard: _guard(c)
        return _contact_plan(c, business_id, kind, value, evidence_id, rationale)


def record_contact(db, business_id, actor_id, *, expected_revision, kind, value, evidence_id, rationale, _guard=None):
    actor, now = snowflake(actor_id), utc_now()
    expected_revision = crm.revision(expected_revision)
    with db.transaction() as c:
        if _guard: _guard(c)
        plan = _contact_plan(c, business_id, kind, value, evidence_id, rationale, expected_revision)
        contact_id = str(uuid4())
        c.execute("INSERT INTO business_contacts VALUES (?,?,?,?,?,?,?)", (contact_id, plan["business_id"], kind, plan["value"], plan["normalized_value"], plan["evidence_id"], now))
        identifier = None
        if kind == "EMAIL": identifier = ("EMAIL", "published", plan["normalized_value"])
        if kind == "WEBSITE" and (host := registry_domain(plan["value"])): identifier = ("DOMAIN", "hostname", host)
        if kind == "PHONE":
            country = c.execute("SELECT country_code FROM businesses WHERE id=?", (plan["business_id"],)).fetchone()[0]
            if number := registry_phone(plan["value"], country): identifier = ("PHONE", number[0], number[1])
        if identifier:
            c.execute("INSERT OR IGNORE INTO business_identifiers VALUES (?,?,?,?,?,'SUPPORTING',?)", (str(uuid4()), plan["business_id"], *identifier, now))
        c.execute("UPDATE businesses SET revision=revision+1,updated_at=? WHERE id=?", (now, plan["business_id"]))
        payload = {"contact_id": contact_id, "kind": kind, "evidence_id": plan["evidence_id"], "rationale": plan["rationale"]}
        c.execute("INSERT INTO business_events VALUES (?,?,?,?,?,?)", (str(uuid4()), plan["business_id"], actor, "crm.contact_recorded", json.dumps(payload), now))
        c.execute("INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid4()), str(uuid4()), actor, "crm.contact_recorded", "business", plan["business_id"], "SUCCESS", json.dumps(payload), now))
        return dict(c.execute("SELECT * FROM business_contacts WHERE id=?", (contact_id,)).fetchone())


def qualification_preview(db, business_id, *, evidence_ids, rationale, _guard=None):
    business_id = crm.identifier(business_id)
    with db.transaction() as c:
        if _guard: _guard(c)
        business = c.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        if not business: raise crm.CrmError("Business not found in this deployment.")
        _identity(c, business_id)
        if c.execute("SELECT 1 FROM leads WHERE business_id=?", (business_id,)).fetchone(): raise crm.CrmError("This business already has a CRM lead.")
        selected = _evidence(c, business_id, evidence_ids)
        sources = [dict(c.execute("SELECT id,source_url,source_identifier,observed_at,confidence FROM evidence WHERE id=?", (value,)).fetchone()) for value in selected]
        return {"business_id": business_id, "business_name": business["name"], "expected_revision": business["revision"],
                "address_json": business["address_json"], "disposition": business["disposition"],
                "evidence_ids": selected, "sources": sources, "rationale": crm.text(rationale)}


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


def _transition_plan(c, lead_id, *, expected_revision, target_stage, note=None, attestation=None,
                     reviewed_evidence_ids=None, contact_id=None, due_at=None):
    now = utc_now()
    expected_revision = crm.revision(expected_revision)
    note = crm.text(note, required=False)
    lead = _lead(c, lead_id, expected_revision)
    source = lead["stage"]
    if not isinstance(target_stage, str) or target_stage not in crm.TRANSITIONS[source]:
        raise crm.CrmError("This pipeline transition is not allowed.")
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
    elif reviewed_evidence_ids is not None or contact_id is not None:
        raise crm.CrmError("Contact/evidence review arguments belong only to READY transitions.")
    if target_stage == "CONTACTED":
        payload["manual_contact_attestation"] = crm.text(attestation)
    elif attestation is not None:
        raise crm.CrmError("A contact attestation belongs only to CONTACTED transitions.")
    if target_stage == "FOLLOW_UP":
        payload["due_at"] = crm.due_time(due_at, now)
    elif due_at is not None:
        raise crm.CrmError("A due time is accepted only when moving to FOLLOW_UP.")
    return lead, payload


def transition_preview(db, lead_id, *, _guard=None, **options):
    lead_id = crm.identifier(lead_id)
    with db.transaction() as c:
        if _guard: _guard(c)
        lead, payload = _transition_plan(c, lead_id, **options)
        business = c.execute("SELECT name,address_json FROM businesses WHERE id=?", (lead["business_id"],)).fetchone()
        contact = dict(c.execute("SELECT c.*,e.source_url,e.observed_at FROM business_contacts c JOIN evidence e ON e.id=c.evidence_id WHERE c.id=?", (payload["contact_id"],)).fetchone()) if payload.get("contact_id") else None
        return {"lead_id": lead_id, "business_id": lead["business_id"], "business_name": business[0], "address_json": business[1], "expected_revision": lead["revision"], "proposal": payload, "contact": contact}


def transition(db, lead_id, actor_id, *, expected_revision, target_stage, note=None, attestation=None,
               reviewed_evidence_ids=None, contact_id=None, due_at=None, _guard=None):
    lead_id, actor, now = crm.identifier(lead_id), snowflake(actor_id), utc_now()
    with db.transaction() as c:
        if _guard: _guard(c)
        lead, payload = _transition_plan(c, lead_id, expected_revision=expected_revision, target_stage=target_stage,
                                        note=note, attestation=attestation, reviewed_evidence_ids=reviewed_evidence_ids,
                                        contact_id=contact_id, due_at=due_at)
        if target_stage == "FOLLOW_UP":
            followup = str(uuid4())
            c.execute("INSERT INTO followups VALUES (?,?,?,?,'PENDING',?,1,?,NULL)", (followup, lead_id, payload["due_at"], payload["note"], actor, now))
            payload["followup_id"] = followup
        c.execute("UPDATE leads SET stage=?,revision=revision+1,updated_at=? WHERE id=?", (target_stage, now, lead_id))
        _event(c, lead_id, actor, "STAGE_CHANGED", payload, now)
        return dict(c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())


def add_note(db, lead_id, actor_id, *, expected_revision, body, supersedes_id=None, _guard=None):
    lead_id = crm.identifier(lead_id)
    supersedes_id = crm.identifier(supersedes_id) if supersedes_id is not None else None
    actor, body, now = snowflake(actor_id), crm.text(body), utc_now()
    expected_revision = crm.revision(expected_revision)
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
    lead["contacts"] = [dict(row) for row in db.connection.execute("SELECT c.*,e.observed_at,e.source_url FROM business_contacts c JOIN evidence e ON e.id=c.evidence_id WHERE c.business_id=? ORDER BY c.created_at,c.id LIMIT 10", (lead["business_id"],))]
    return lead


def get_note(db, lead_id, note_id):
    lead_id, note_id = crm.identifier(lead_id), crm.identifier(note_id)
    _lead(db.connection, lead_id)
    row = db.connection.execute("SELECT * FROM lead_notes WHERE id=? AND lead_id=?", (note_id, lead_id)).fetchone()
    if not row: raise crm.CrmError("Note not found on this lead.")
    return dict(row)


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
