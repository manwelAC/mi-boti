from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest

from conftest import job
from mi_boti.domain.campaigns import CampaignError, DiscoveryLifecycleError
from mi_boti.domain.registry import RegistryError
from mi_boti.domain.values import utc_now
from mi_boti.repositories.campaigns import (
    begin_discovery_attempt,
    create_campaign,
    edit_campaign,
    finish_discovery_query,
    get_active_campaign,
    get_campaign,
    list_campaigns,
    plan_unexhausted_queries,
    queue_discovery_query,
    set_active_campaign,
)
from mi_boti.repositories.registry import link_parent_business, resolve, resolve_identity_review


def sample_config(**overrides):
    base = {
        "schema_version": 1,
        "target_categories": ["restaurant", "cafe"],
        "geography": {
            "country_code": "PH",
            "locality": "Quezon City",
            "cells": [
                {"cell_id": "qc-1", "bbox": [14.648, 121.047, 14.653, 121.055]},
                {"cell_id": "qc-2", "bbox": [14.653, 121.055, 14.657, 121.061]},
            ],
        },
        "exclusions": ["fast food"],
        "provider_id": None,
        "service_description": "Custom ordering and loyalty systems",
    }
    base.update(overrides)
    return base


def leased_discover_job(db, *, hunt_id=None):
    c = db.connection
    job_id = job(c, hunt=hunt_id)
    token = str(uuid4())
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    c.execute(
        "UPDATE jobs SET state='RUNNING', lease_token=?, lease_expires_at=? WHERE id=?",
        (token, expiry, job_id),
    )
    return job_id, token


def observation(source_id="node/10", **overrides):
    raw = {
        "name": "Quezon Cafe",
        "source_namespace": "osm",
        "source_id": source_id,
        "source_url": "https://www.openstreetmap.org/" + source_id,
        "observed_at": utc_now(),
        "policy_version": "osm-v1",
        "attribution": "OSM contributors",
        "address": {
            "country": "PH",
            "city": "Quezon City",
            "street": "Katipunan Ave",
            "house_number": "10",
        },
    }
    raw.update(overrides)
    return raw


def test_campaign_versioning_preserves_history_and_archiving_clears_active_selection(database):
    c = database.connection
    now = utc_now()
    c.execute("INSERT INTO guild_config VALUES ('guild','123456789012345678','READY',1,'{}',?)", (now,))
    created = create_campaign(database, "223456789012345678", "QC Food & Beverage", sample_config())
    assert created.current_version == 1
    assert created.state == "ACTIVE"
    set_active_campaign(database, "223456789012345678", created.id)
    assert get_active_campaign(database).id == created.id

    # Stale expected_version fails closed without mutating.
    with pytest.raises(CampaignError, match="version changed"):
        edit_campaign(
            database,
            "223456789012345678",
            created.id,
            expected_version=2,
            name="Should Not Apply",
        )

    # Editing config creates version 2 while keeping version 1 immutable.
    updated_cfg = sample_config(target_categories=["cafe"])
    v2 = edit_campaign(
        database,
        "223456789012345678",
        created.id,
        expected_version=1,
        name="QC Cafes Only",
        config=updated_cfg,
    )
    assert v2.current_version == 2
    assert v2.name == "QC Cafes Only"
    assert get_campaign(database, created.id, version=1).config["target_categories"] == ["cafe", "restaurant"]
    assert get_campaign(database, created.id, version=2).config["target_categories"] == ["cafe"]

    # Archiving clears active_campaign_id in guild_config and rejects subsequent non-archive edits.
    archived = edit_campaign(
        database,
        "223456789012345678",
        created.id,
        expected_version=2,
        archive=True,
    )
    assert archived.state == "ARCHIVED"
    assert get_active_campaign(database) is None
    with pytest.raises(CampaignError, match="ACTIVE"):
        set_active_campaign(database, "223456789012345678", created.id)
    with pytest.raises(CampaignError, match="Archived"):
        edit_campaign(
            database,
            "223456789012345678",
            created.id,
            expected_version=2,
            name="Reopen attempt",
        )
    listed = list_campaigns(database, include_archived=False)
    assert listed["total"] == 0
    assert list_campaigns(database, include_archived=True)["total"] == 1


def test_query_and_coverage_lifecycle_distinguishes_fresh_exhausted_and_partial(database):
    camp = create_campaign(database, "223456789012345678", "QC Coverage", sample_config())
    job_id, token = leased_discover_job(database)
    planned = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    assert [p.geographic_cell for p in planned] == ["qc-1", "qc-2"]

    # Cell 1: partial response never claims complete coverage; remains planned on next check.
    q1 = queue_discovery_query(database, job_id, token, camp.id, planned[0])
    begin_discovery_attempt(database, q1, token, max_attempts=3, max_requests_per_day=10, max_job_requests=5)
    resolve(database, q1, observation("node/1"), token)
    finish_discovery_query(database, q1, token, outcome="PARTIAL", result_count=1)

    still_planned = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    assert [p.geographic_cell for p in still_planned] == ["qc-1", "qc-2"]

    # Cell 1 retry: succeeds completely -> coverage becomes FRESH and is skipped within TTL.
    q1_full = queue_discovery_query(database, job_id, token, camp.id, planned[0])
    begin_discovery_attempt(database, q1_full, token, max_attempts=3, max_requests_per_day=10, max_job_requests=5)
    resolve(database, q1_full, observation("node/1"), token)
    finish_discovery_query(database, q1_full, token, outcome="SUCCEEDED", result_count=1)

    after_q1 = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    assert [p.geographic_cell for p in after_q1] == ["qc-2"]

    # Cell 2: empty result -> coverage becomes EXHAUSTED and is also skipped within TTL.
    q2 = queue_discovery_query(database, job_id, token, camp.id, planned[1])
    begin_discovery_attempt(database, q2, token, max_attempts=3, max_requests_per_day=10, max_job_requests=5)
    finish_discovery_query(database, q2, token, outcome="SUCCEEDED", result_count=0, exhausted_cell=True)

    none_left = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    assert none_left == ()

    # After 31 days (past 30-day TTL), cells become eligible again.
    future = (datetime.now(timezone.utc) + timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    expired_plan = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10, now=future)
    assert [p.geographic_cell for p in expired_plan] == ["qc-1", "qc-2"]


def test_discovery_request_budgets_enforce_attempt_job_and_daily_caps(database):
    camp = create_campaign(database, "223456789012345678", "QC Budgets", sample_config())
    job_id, token = leased_discover_job(database)
    planned = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=5)
    q1 = queue_discovery_query(database, job_id, token, camp.id, planned[0])

    begin_discovery_attempt(database, q1, token, max_attempts=2, max_requests_per_day=3, max_job_requests=2)
    begin_discovery_attempt(database, q1, token, max_attempts=2, max_requests_per_day=3, max_job_requests=2)
    # 3rd attempt on same query exceeds max_attempts=2.
    with pytest.raises(DiscoveryLifecycleError, match="attempt cap"):
        begin_discovery_attempt(database, q1, token, max_attempts=2, max_requests_per_day=3, max_job_requests=5)

    # Another query on the same job hits max_job_requests=2.
    q2 = queue_discovery_query(database, job_id, token, camp.id, planned[1])
    with pytest.raises(DiscoveryLifecycleError, match="Job discovery-request budget"):
        begin_discovery_attempt(database, q2, token, max_attempts=2, max_requests_per_day=10, max_job_requests=2)

    # A second job on the same UTC day hits max_requests_per_day=2.
    job2, token2 = leased_discover_job(database)
    q3 = queue_discovery_query(database, job2, token2, camp.id, planned[1])
    with pytest.raises(DiscoveryLifecycleError, match="daily request budget"):
        begin_discovery_attempt(database, q3, token2, max_attempts=2, max_requests_per_day=2, max_job_requests=5)


def test_identity_review_resolution_updates_reused_candidates_without_quota_credit(database):
    camp = create_campaign(database, "223456789012345678", "QC Reviews", sample_config())
    job_id, token = leased_discover_job(database)
    planned = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    q1 = queue_discovery_query(database, job_id, token, camp.id, planned[0])
    begin_discovery_attempt(database, q1, token)
    first = resolve(database, q1, observation("node/1", website="https://shared.example"), token)
    assert first.state == "NEW"

    # Ambiguous candidate sharing website domain across two queries.
    ambig_obs = observation("way/99", website="https://shared.example")
    held1 = resolve(database, q1, ambig_obs, token)
    q2 = queue_discovery_query(database, job_id, token, camp.id, planned[1])
    begin_discovery_attempt(database, q2, token)
    held2 = resolve(database, q2, dict(ambig_obs, observed_at=utc_now()), token)
    assert held1.state == held2.state == "AMBIGUOUS"
    assert held1.review_id == held2.review_id

    # Stale revision on LINK_EXISTING fails closed.
    with pytest.raises(RegistryError, match="revision changed"):
        resolve_identity_review(
            database,
            held1.review_id,
            "223456789012345678",
            action="LINK_EXISTING",
            target_business_id=first.business_id,
            expected_business_revision=99,
            rationale="Confirmed same cafe polygon and node.",
        )

    resolved = resolve_identity_review(
        database,
        held1.review_id,
        "223456789012345678",
        action="LINK_EXISTING",
        target_business_id=first.business_id,
        expected_business_revision=1,
        rationale="Confirmed OSM way/99 is the building polygon for node/1.",
    )
    assert resolved.state == "RESOLVED_EXISTING"
    assert resolved.business_id == first.business_id

    # Both candidates that shared the open review are now RESOLVED_EXISTING.
    states = database.connection.execute(
        "SELECT state, business_id FROM candidates WHERE id IN (?, ?)",
        (held1.candidate_id, held2.candidate_id),
    ).fetchall()
    assert all(r["state"] == "RESOLVED_EXISTING" and r["business_id"] == first.business_id for r in states)
    # Second source strong claim is now attached to the linked business.
    q3 = queue_discovery_query(database, job_id, token, camp.id, planned[0])
    begin_discovery_attempt(database, q3, token)
    repeat = resolve(database, q3, ambig_obs, token)
    assert repeat.state == "EXISTING" and repeat.business_id == first.business_id
    # Zero leads, scores or hunt credits created.
    for table in ("leads", "scores", "hunt_credits", "research_runs"):
        assert database.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_identity_review_create_new_and_parent_hierarchy_cycle_prevention(database):
    camp = create_campaign(database, "223456789012345678", "QC Branches", sample_config())
    job_id, token = leased_discover_job(database)
    planned = plan_unexhausted_queries(database, camp.id, policy_version="osm-v1", limit=10)
    q1 = queue_discovery_query(database, job_id, token, camp.id, planned[0])
    begin_discovery_attempt(database, q1, token)

    hq = resolve(database, q1, observation("node/100", website="https://chain.example"), token)
    branch_cand = resolve(
        database,
        q1,
        observation(
            "node/101",
            website="https://chain.example",
            address={"country": "PH", "city": "Quezon City", "street": "Timog Ave", "house_number": "22"},
        ),
        token,
    )
    assert branch_cand.state == "AMBIGUOUS"

    branch = resolve_identity_review(
        database,
        branch_cand.review_id,
        "223456789012345678",
        action="CREATE_NEW",
        entity_kind="BRANCH",
        parent_id=hq.business_id,
        rationale="Distinct Timog Ave branch of the same brand.",
    )
    assert branch.state == "RESOLVED_NEW" and branch.business_id != hq.business_id
    branch_row = database.connection.execute("SELECT * FROM businesses WHERE id=?", (branch.business_id,)).fetchone()
    assert branch_row["parent_id"] == hq.business_id
    assert branch_row["entity_kind"] == "BRANCH"

    # Self-parent and cycle attempts are rejected.
    with pytest.raises(RegistryError, match="own parent"):
        link_parent_business(
            database,
            hq.business_id,
            hq.business_id,
            "223456789012345678",
            expected_revision=1,
            rationale="Invalid self parent.",
        )
    with pytest.raises(RegistryError, match="cycle"):
        link_parent_business(
            database,
            hq.business_id,
            branch.business_id,
            "223456789012345678",
            expected_revision=1,
            rationale="Invalid cycle.",
        )
