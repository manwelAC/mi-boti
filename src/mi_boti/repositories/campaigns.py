"""Transactional campaign versioning, query/coverage lifecycle and audit."""

from dataclasses import dataclass
import json
from uuid import uuid4

from ..discovery.planner import QuerySpec
from ..domain.campaigns import (
    CampaignError,
    DiscoveryLifecycleError,
    PlannedCellQuery,
    is_coverage_fresh,
    parse_utc,
    plan_campaign_queries,
    validate_actor,
    validate_campaign_config,
    validate_campaign_name,
)
from ..domain.registry import encoded
from ..domain.values import utc_now


@dataclass(frozen=True)
class CampaignRecord:
    id: str
    name: str
    state: str
    current_version: int
    config: dict
    created_by: str
    created_at: str
    updated_at: str


def _audit(connection, actor_id, action, entity_kind, entity_id, outcome, details=None, *, now=None):
    connection.execute(
        "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
        (
            str(uuid4()),
            str(uuid4()),
            actor_id,
            action,
            entity_kind,
            entity_id,
            outcome,
            encoded(details or {}),
            now or utc_now(),
        ),
    )


def _load_campaign(connection, campaign_id: str, *, version: int | None = None) -> CampaignRecord:
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise CampaignError("Campaign identifier is required.")
    row = connection.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if row is None:
        raise CampaignError("Campaign was not found in this deployment.")
    target_version = row["current_version"] if version is None else version
    if type(target_version) is not int or target_version < 1:
        raise CampaignError("Campaign version must be a positive integer.")
    ver = connection.execute(
        "SELECT config_json FROM campaign_versions WHERE campaign_id=? AND version=?",
        (campaign_id, target_version),
    ).fetchone()
    if ver is None:
        raise CampaignError("Requested campaign version was not found.")
    return CampaignRecord(
        id=row["id"],
        name=row["name"],
        state=row["state"],
        current_version=target_version,
        config=json.loads(ver["config_json"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def create_campaign(db, actor_id: str, name: str, config: dict, *, now: str | None = None) -> CampaignRecord:
    actor = validate_actor(actor_id)
    cleaned_name = validate_campaign_name(name)
    validated_config = validate_campaign_config(config)
    stamp = now or utc_now()
    parse_utc(stamp)
    campaign_id = str(uuid4())
    with db.transaction() as c:
        c.execute(
            "INSERT INTO campaigns VALUES (?,?, 'ACTIVE', 1, ?, ?, ?)",
            (campaign_id, cleaned_name, actor, stamp, stamp),
        )
        c.execute(
            "INSERT INTO campaign_versions VALUES (?, 1, ?, ?, ?)",
            (campaign_id, encoded(validated_config), actor, stamp),
        )
        _audit(
            c,
            actor,
            "campaign.create",
            "campaign",
            campaign_id,
            "SUCCESS",
            {"version": 1, "name": cleaned_name},
            now=stamp,
        )
        return _load_campaign(c, campaign_id)


def edit_campaign(
    db,
    actor_id: str,
    campaign_id: str,
    *,
    expected_version: int,
    name: str | None = None,
    config: dict | None = None,
    archive: bool = False,
    now: str | None = None,
) -> CampaignRecord:
    actor = validate_actor(actor_id)
    if type(expected_version) is not int or expected_version < 1:
        raise CampaignError("Expected campaign version must be a positive integer.")
    if type(archive) is not bool:
        raise CampaignError("Archive flag must be boolean.")
    if name is None and config is None and not archive:
        raise CampaignError("Provide a campaign name, configuration update or archive flag.")
    cleaned_name = validate_campaign_name(name) if name is not None else None
    validated_config = validate_campaign_config(config) if config is not None else None
    stamp = now or utc_now()
    parse_utc(stamp)
    with db.transaction() as c:
        current = _load_campaign(c, campaign_id)
        if current.current_version != expected_version:
            raise CampaignError("Campaign version changed; reload the current campaign before editing.")
        if current.state == "ARCHIVED" and not archive:
            raise CampaignError("Archived campaigns cannot be edited.")
        new_name = cleaned_name if cleaned_name is not None else current.name
        new_state = "ARCHIVED" if archive else current.state
        new_version = current.current_version
        if validated_config is not None and validated_config != current.config:
            new_version = current.current_version + 1
            c.execute(
                "INSERT INTO campaign_versions VALUES (?, ?, ?, ?, ?)",
                (campaign_id, new_version, encoded(validated_config), actor, stamp),
            )
        c.execute(
            "UPDATE campaigns SET name=?, state=?, current_version=?, updated_at=? WHERE id=?",
            (new_name, new_state, new_version, stamp, campaign_id),
        )
        if new_state == "ARCHIVED":
            row = c.execute("SELECT settings_json FROM guild_config WHERE id='guild'").fetchone()
            if row:
                settings = json.loads(row[0])
                if settings.get("active_campaign_id") == campaign_id:
                    settings["active_campaign_id"] = None
                    c.execute(
                        "UPDATE guild_config SET settings_json=?, revision=revision+1, updated_at=? WHERE id='guild'",
                        (encoded(settings), stamp),
                    )
        _audit(
            c,
            actor,
            "campaign.edit",
            "campaign",
            campaign_id,
            "SUCCESS",
            {"version": new_version, "state": new_state},
            now=stamp,
        )
        return _load_campaign(c, campaign_id)


def get_campaign(db, campaign_id: str, *, version: int | None = None) -> CampaignRecord:
    return _load_campaign(db.connection, campaign_id, version=version)


def list_campaigns(db, *, page: int = 1, page_size: int = 10, include_archived: bool = True) -> dict:
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 10:
        raise CampaignError("Pagination requires page >= 1 and page_size between 1 and 10.")
    c = db.connection
    where = "" if include_archived else "WHERE state='ACTIVE'"
    total = c.execute(f"SELECT count(*) FROM campaigns {where}").fetchone()[0]
    offset = (page - 1) * page_size
    rows = c.execute(
        f"SELECT id FROM campaigns {where} ORDER BY created_at DESC, id ASC LIMIT ? OFFSET ?",
        (page_size, offset),
    ).fetchall()
    items = [_load_campaign(c, row["id"]) for row in rows]
    return {"items": tuple(items), "page": page, "page_size": page_size, "total": total}


def set_active_campaign(db, actor_id: str, campaign_id: str | None, *, now: str | None = None) -> str | None:
    actor = validate_actor(actor_id)
    stamp = now or utc_now()
    parse_utc(stamp)
    with db.transaction() as c:
        row = c.execute("SELECT settings_json FROM guild_config WHERE id='guild'").fetchone()
        if row is None:
            raise CampaignError("Run /setup before selecting an active campaign.")
        if campaign_id is not None:
            record = _load_campaign(c, campaign_id)
            if record.state != "ACTIVE":
                raise CampaignError("Only an ACTIVE campaign can be selected as active.")
        settings = json.loads(row[0])
        settings["active_campaign_id"] = campaign_id
        c.execute(
            "UPDATE guild_config SET settings_json=?, revision=revision+1, updated_at=? WHERE id='guild'",
            (encoded(settings), stamp),
        )
        _audit(
            c,
            actor,
            "campaign.set_active",
            "campaign",
            campaign_id,
            "SUCCESS",
            {"active_campaign_id": campaign_id},
            now=stamp,
        )
        return campaign_id


def get_active_campaign(db) -> CampaignRecord | None:
    c = db.connection
    row = c.execute("SELECT settings_json FROM guild_config WHERE id='guild'").fetchone()
    if not row:
        return None
    campaign_id = json.loads(row[0]).get("active_campaign_id")
    if not campaign_id:
        return None
    record = _load_campaign(c, campaign_id)
    return record if record.state == "ACTIVE" else None


def _require_discover_lease(connection, job_id: str, lease_token: str, now: str):
    parse_utc(now)
    job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if (
        not job
        or job["kind"] != "DISCOVER"
        or job["state"] != "RUNNING"
        or not lease_token
        or job["lease_token"] != lease_token
        or not job["lease_expires_at"]
        or job["lease_expires_at"] <= now
        or job["cancel_requested"]
    ):
        raise DiscoveryLifecycleError("Discovery operation requires a current, uncancelled DISCOVER job lease.")
    if job["hunt_id"]:
        hunt = connection.execute("SELECT state, campaign_id FROM hunts WHERE id=?", (job["hunt_id"],)).fetchone()
        if not hunt or hunt["state"] != "RUNNING":
            raise DiscoveryLifecycleError("Associated hunt is not RUNNING.")
    return job


def plan_unexhausted_queries(
    db,
    campaign_id: str,
    *,
    campaign_version: int | None = None,
    source: str = "osm",
    policy_version: str,
    limit: int = 25,
    coverage_ttl_seconds: int = 2592000,
    now: str | None = None,
) -> tuple[PlannedCellQuery, ...]:
    stamp = now or utc_now()
    parse_utc(stamp)
    c = db.connection
    record = _load_campaign(c, campaign_id, version=campaign_version)
    rows = c.execute(
        "SELECT geographic_cell, query_hash, observed_at, state FROM coverage_cells WHERE campaign_id=? AND source=?",
        (campaign_id, source),
    ).fetchall()
    fresh_by_cell: dict[str, set[str]] = {}
    for row in rows:
        if row["state"] in {"FRESH", "EXHAUSTED"} and is_coverage_fresh(row["observed_at"], stamp, coverage_ttl_seconds):
            fresh_by_cell.setdefault(row["geographic_cell"], set()).add(row["query_hash"])
    return plan_campaign_queries(
        record.config,
        campaign_version=record.current_version,
        policy_version=policy_version,
        limit=limit,
        fresh_hashes_by_cell=fresh_by_cell,
    )


def queue_discovery_query(
    db,
    job_id: str,
    lease_token: str,
    campaign_id: str,
    planned: PlannedCellQuery,
    *,
    source: str = "osm",
    now: str | None = None,
) -> str:
    stamp = now or utc_now()
    if not isinstance(planned, PlannedCellQuery) or not isinstance(planned.spec, QuerySpec):
        raise DiscoveryLifecycleError("Expected a validated PlannedCellQuery.")
    if source != "osm":
        raise DiscoveryLifecycleError("Only the osm discovery source namespace is supported.")
    with db.transaction() as c:
        job = _require_discover_lease(c, job_id, lease_token, stamp)
        campaign_row = _load_campaign(c, campaign_id, version=planned.spec.target_version)
        if campaign_row.state != "ACTIVE" and job["hunt_id"] is None:
            raise DiscoveryLifecycleError("Manual discovery requires an ACTIVE campaign.")
        if job["hunt_id"]:
            hunt_row = c.execute("SELECT campaign_id FROM hunts WHERE id=?", (job["hunt_id"],)).fetchone()
            if not hunt_row or hunt_row["campaign_id"] != campaign_id:
                raise DiscoveryLifecycleError("Discovery query campaign disagrees with its hunt.")
        query_id = str(uuid4())
        c.execute(
            "INSERT INTO discovery_queries VALUES (?,?,?,?,?,?,?,?,?,'QUEUED',0,0,?,NULL,NULL)",
            (
                query_id,
                job_id,
                campaign_id,
                job["hunt_id"],
                source,
                planned.spec.fingerprint,
                planned.spec.policy_version,
                planned.geographic_cell,
                encoded(planned.spec.request()),
                stamp,
            ),
        )
        return query_id


def begin_discovery_attempt(
    db,
    query_id: str,
    lease_token: str,
    *,
    max_attempts: int = 3,
    max_requests_per_day: int = 100,
    max_job_requests: int = 20,
    now: str | None = None,
) -> dict:
    stamp = now or utc_now()
    if (
        type(max_attempts) is not int
        or not 1 <= max_attempts <= 3
        or type(max_requests_per_day) is not int
        or max_requests_per_day < 1
        or type(max_job_requests) is not int
        or max_job_requests < 1
    ):
        raise DiscoveryLifecycleError("Attempt and request budgets must be bounded positive integers.")
    with db.transaction() as c:
        query = c.execute("SELECT * FROM discovery_queries WHERE id=?", (query_id,)).fetchone()
        if not query:
            raise DiscoveryLifecycleError("Discovery query was not found.")
        job = _require_discover_lease(c, query["job_id"], lease_token, stamp)
        if query["state"] not in {"QUEUED", "RUNNING"}:
            raise DiscoveryLifecycleError("Discovery query is already terminal.")
        if query["attempts"] >= max_attempts:
            raise DiscoveryLifecycleError("Discovery query reached its maximum attempt cap.")
        day_prefix = stamp[:10]
        daily_used = c.execute(
            "SELECT COALESCE(SUM(attempts), 0) FROM discovery_queries WHERE source=? AND started_at LIKE ?",
            (query["source"], f"{day_prefix}%"),
        ).fetchone()[0]
        if daily_used >= max_requests_per_day:
            raise DiscoveryLifecycleError("Source daily request budget is exhausted.")
        progress = json.loads(job["progress_json"] or "{}")
        job_requests = int(progress.get("discovery_requests", 0))
        if job_requests >= max_job_requests:
            raise DiscoveryLifecycleError("Job discovery-request budget is exhausted.")
        progress["discovery_requests"] = job_requests + 1
        c.execute(
            "UPDATE jobs SET progress_json=?, updated_at=? WHERE id=?",
            (encoded(progress), stamp, job["id"]),
        )
        if job["hunt_id"]:
            hunt = c.execute("SELECT counters_json, snapshot_json FROM hunts WHERE id=?", (job["hunt_id"],)).fetchone()
            counters = json.loads(hunt["counters_json"] or "{}")
            snapshot = json.loads(hunt["snapshot_json"] or "{}")
            hunt_cap = int(snapshot.get("limits", {}).get("discovery_requests", max_job_requests))
            hunt_used = int(counters.get("discovery_requests", 0))
            if hunt_used >= hunt_cap:
                raise DiscoveryLifecycleError("Hunt discovery-request budget is exhausted.")
            counters["discovery_requests"] = hunt_used + 1
            c.execute(
                "UPDATE hunts SET counters_json=?, updated_at=?, revision=revision+1 WHERE id=?",
                (encoded(counters), stamp, job["hunt_id"]),
            )
        new_attempts = query["attempts"] + 1
        c.execute(
            "UPDATE discovery_queries SET state='RUNNING', attempts=?, error_code=NULL WHERE id=?",
            (new_attempts, query_id),
        )
        return dict(c.execute("SELECT * FROM discovery_queries WHERE id=?", (query_id,)).fetchone())


def finish_discovery_query(
    db,
    query_id: str,
    lease_token: str,
    *,
    outcome: str,
    result_count: int = 0,
    exhausted_cell: bool = False,
    error_code: str | None = None,
    now: str | None = None,
) -> dict:
    stamp = now or utc_now()
    if outcome not in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
        raise DiscoveryLifecycleError("Invalid discovery query terminal outcome.")
    if type(result_count) is not int or result_count < 0 or type(exhausted_cell) is not bool:
        raise DiscoveryLifecycleError("Invalid discovery result count or exhaustion flag.")
    if outcome in {"FAILED", "CANCELLED"} and not error_code:
        raise DiscoveryLifecycleError("Failed or cancelled queries require a safe error_code.")
    if outcome in {"SUCCEEDED", "PARTIAL"} and error_code is not None:
        raise DiscoveryLifecycleError("Successful or partial queries must not set error_code.")
    with db.transaction() as c:
        query = c.execute("SELECT * FROM discovery_queries WHERE id=?", (query_id,)).fetchone()
        if not query:
            raise DiscoveryLifecycleError("Discovery query was not found.")
        job = c.execute("SELECT * FROM jobs WHERE id=?", (query["job_id"],)).fetchone()
        if (
            not job
            or job["kind"] != "DISCOVER"
            or job["state"] != "RUNNING"
            or not lease_token
            or job["lease_token"] != lease_token
            or not job["lease_expires_at"]
            or job["lease_expires_at"] <= stamp
            or (outcome != "CANCELLED" and job["cancel_requested"])
        ):
            raise DiscoveryLifecycleError("Discovery query completion requires the active job lease.")
        if query["state"] != "RUNNING" or query["attempts"] < 1:
            raise DiscoveryLifecycleError("Discovery query must be RUNNING with at least one attempt before finishing.")
        observed_candidates = c.execute(
            "SELECT count(*) FROM candidates WHERE query_id=?",
            (query_id,),
        ).fetchone()[0]
        final_count = max(result_count, observed_candidates)
        c.execute(
            "UPDATE discovery_queries SET state=?, result_count=?, finished_at=?, error_code=? WHERE id=?",
            (outcome, final_count, stamp, error_code, query_id),
        )
        if outcome in {"SUCCEEDED", "PARTIAL"}:
            # Never claim complete coverage from partial results.
            coverage_state = "PARTIAL" if outcome == "PARTIAL" else ("EXHAUSTED" if exhausted_cell or final_count == 0 else "FRESH")
            c.execute(
                "INSERT INTO coverage_cells VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(campaign_id,source,geographic_cell,query_hash) DO UPDATE SET "
                "last_query_id=excluded.last_query_id, observed_at=excluded.observed_at, state=excluded.state",
                (
                    query["campaign_id"],
                    query["source"],
                    query["geographic_cell"],
                    query["query_hash"],
                    query_id,
                    stamp,
                    coverage_state,
                ),
            )
        return dict(c.execute("SELECT * FROM discovery_queries WHERE id=?", (query_id,)).fetchone())
