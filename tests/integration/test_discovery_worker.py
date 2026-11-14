from datetime import datetime, timedelta, timezone
import json

import pytest

from mi_boti.discovery.overpass import ATTRIBUTION, DiscoveryBatch
from mi_boti.domain.errors import AppError
from mi_boti.domain.values import utc_now
from mi_boti.jobs.discovery import (
    JobSchedulerError,
    claim_discover_job,
    enqueue_manual_discovery,
    execute_manual_discovery_job,
    heartbeat_job_lease,
    recover_interrupted_work,
    request_job_cancellation,
)
from mi_boti.repositories.campaigns import create_campaign


class SourceFailure(AppError):
    code = "SOURCE_UNAVAILABLE"


class FakeDiscoverySource:
    source_namespace = "osm"
    policy_version = "osm-v1"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def discover(self, planned, *, max_elements):
        self.calls.append((planned.geographic_cell, max_elements))
        item = self.responses.pop(0) if self.responses else DiscoveryBatch((), False, ())
        if isinstance(item, Exception):
            raise item
        return item


def ready_guild_and_campaign(db):
    now = utc_now()
    db.connection.execute(
        "INSERT INTO guild_config VALUES ('guild','123456789012345678','READY',1,'{}',?)",
        (now,),
    )
    config = {
        "schema_version": 1,
        "target_categories": ["restaurant", "cafe"],
        "geography": {
            "country_code": "PH",
            "locality": "Quezon City",
            "cells": [
                {"cell_id": "qc-a", "bbox": [14.648, 121.047, 14.653, 121.055]},
                {"cell_id": "qc-b", "bbox": [14.653, 121.055, 14.657, 121.061]},
            ],
        },
        "exclusions": [],
        "provider_id": None,
        "service_description": "Restaurant and cafe ordering software",
    }
    return create_campaign(db, "223456789012345678", "QC Discovery Campaign", config)


def obs(source_id="node/1", name="Test Cafe", **extra):
    raw = {
        "name": name,
        "source_namespace": "osm",
        "source_id": source_id,
        "source_url": "https://www.openstreetmap.org/" + source_id,
        "observed_at": utc_now(),
        "policy_version": "osm-v1",
        "attribution": ATTRIBUTION,
        "address": {
            "country": "PH",
            "city": "Quezon City",
            "street": "Main St",
            "house_number": "1",
        },
    }
    raw.update(extra)
    return raw


def test_idempotent_enqueue_and_bounded_worker_execution_with_fake_source(database):
    camp = ready_guild_and_campaign(database)
    j1 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:interaction:1",
        campaign_id=camp.id,
        limit=3,
    )
    j2 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:interaction:1",
        campaign_id=camp.id,
        limit=3,
    )
    assert j1["id"] == j2["id"]
    assert database.connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1

    claimed = claim_discover_job(database)
    assert claimed is not None and claimed.id == j1["id"] and claimed.state == "RUNNING"
    renewed = heartbeat_job_lease(database, claimed.id, claimed.lease_token, lease_seconds=60)
    assert renewed.lease_expires_at >= claimed.lease_expires_at

    fake_source = FakeDiscoverySource(
        [
            DiscoveryBatch((obs("node/1", "Alpha Cafe"), obs("node/2", "Beta Restaurant")), False, ()),
            DiscoveryBatch((obs("node/1", "Alpha Cafe"), obs("node/3", "")), False, ()),
        ]
    )
    finished = execute_manual_discovery_job(database, renewed, fake_source)
    assert finished["state"] == "SUCCEEDED"
    progress = json.loads(finished["progress_json"])
    assert progress["phase"] == "COMPLETED"
    assert progress["discovery_requests"] == 2
    assert progress["seen"] == 3  # Capped by limit=3 across both cells!
    assert progress["new"] == 2
    assert progress["existing"] == 1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 2
    assert database.connection.execute("SELECT count(*) FROM coverage_cells WHERE state='FRESH'").fetchone()[0] == 2
    for table in ("research_runs", "scores", "leads", "hunt_credits", "ai_executions"):
        assert database.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_lost_authorization_before_dispatch_interrupts_job_without_calling_source(database):
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:auth-lost",
        campaign_id=camp.id,
        limit=10,
    )
    claimed = claim_discover_job(database, enqueued["id"])
    fake_source = FakeDiscoverySource([DiscoveryBatch((obs("node/1"),), False, ())])
    result = execute_manual_discovery_job(
        database,
        claimed,
        fake_source,
        authorize_dispatch=lambda _: False,
    )
    assert result["state"] == "INTERRUPTED"
    assert result["error_code"] == "AUTHORIZATION_LOST"
    assert fake_source.calls == []
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0


def test_cancellation_mid_flight_stops_remaining_queries_and_marks_cancelled(database):
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:cancel-mid",
        campaign_id=camp.id,
        limit=10,
    )
    claimed = claim_discover_job(database, enqueued["id"])

    class CancellingSource(FakeDiscoverySource):
        def discover(self, planned, *, max_elements):
            request_job_cancellation(database, claimed.id, "223456789012345678")
            return super().discover(planned, max_elements=max_elements)

    source = CancellingSource([DiscoveryBatch((obs("node/10"),), False, ())])
    result = execute_manual_discovery_job(database, claimed, source)
    assert result["state"] == "CANCELLED"
    assert result["error_code"] == "OPERATOR_CANCELLED"
    assert len(source.calls) == 1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0
    q_state = database.connection.execute("SELECT state FROM discovery_queries").fetchone()[0]
    assert q_state == "CANCELLED"


def test_source_failure_records_failed_query_and_job_without_partial_business_writes(database):
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:source-fail",
        campaign_id=camp.id,
    )
    claimed = claim_discover_job(database, enqueued["id"])
    source = FakeDiscoverySource(
        [
            SourceFailure("Attempt 1 timed out."),
            SourceFailure("Attempt 2 timed out."),
            SourceFailure("Attempt 3 timed out."),
        ]
    )
    result = execute_manual_discovery_job(database, claimed, source, max_attempts_per_query=3)
    assert result["state"] == "FAILED"
    assert result["error_code"] == "SOURCE_UNAVAILABLE"
    q_row = database.connection.execute("SELECT state, attempts, error_code FROM discovery_queries").fetchone()
    assert q_row["state"] == "FAILED" and q_row["attempts"] == 3 and q_row["error_code"] == "SOURCE_UNAVAILABLE"


def test_transient_source_failure_recovers_on_bounded_retry_and_counts_attempts(database):
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:source-retry-ok",
        campaign_id=camp.id,
    )
    claimed = claim_discover_job(database, enqueued["id"])
    source = FakeDiscoverySource(
        [
            SourceFailure("Transient 504 on cell 1."),
            DiscoveryBatch((obs("node/55", "Recovered Cafe"),), False, ()),
            DiscoveryBatch((), False, ()),
        ]
    )
    result = execute_manual_discovery_job(database, claimed, source, max_attempts_per_query=3)
    assert result["state"] == "SUCCEEDED"
    prog = json.loads(result["progress_json"])
    assert prog["discovery_requests"] == 3
    assert prog["new"] == 1


def test_startup_recovery_marks_running_hunts_and_jobs_interrupted_and_bounds_crash_charge(database):
    camp = ready_guild_and_campaign(database)
    t0 = "2026-11-14T00:00:00.000000Z"
    lease_end = "2026-11-14T00:00:30.000000Z"
    restart_time = "2026-11-14T02:00:00.000000Z"  # 2 hours later offline!
    with database.transaction() as c:
        c.execute(
            "INSERT INTO hunts VALUES ('hunt-1',?,1,'{}','disabled','223456789012345678',25,0,'RUNNING',NULL,'{}',5000,?,?,?,?,?,1)",
            (camp.id, t0, lease_end, t0, t0, t0),
        )
        c.execute(
            "INSERT INTO jobs VALUES ('job-run','DISCOVER','{}','idemp-1','hunt-1',NULL,'223456789012345678','RUNNING',1,3,'{}','tok-1',?,0,NULL,?,?,NULL)",
            (lease_end, t0, t0),
        )
        c.execute(
            "INSERT INTO jobs VALUES ('job-hunt-queued','DISCOVER','{}','idemp-2','hunt-1',NULL,'223456789012345678','QUEUED',0,3,'{}',NULL,NULL,0,NULL,?,?,NULL)",
            (t0, t0),
        )
    summary = recover_interrupted_work(database, now=restart_time)
    assert summary == {"interrupted_hunts": 1, "interrupted_jobs": 2}
    hunt_row = database.connection.execute("SELECT * FROM hunts WHERE id='hunt-1'").fetchone()
    assert hunt_row["state"] == "INTERRUPTED"
    assert hunt_row["stop_reason"] == "RESTART_INTERRUPTION"
    # 5000ms prior + at most 30000ms reserved lease = 35000ms (never 2 hours).
    assert hunt_row["active_milliseconds"] == 35000
    assert hunt_row["active_checkpoint_at"] is None
    assert hunt_row["active_lease_expires_at"] is None
    assert hunt_row["max_observed_at"] == restart_time
    states = [
        r[0]
        for r in database.connection.execute("SELECT state FROM jobs ORDER BY id").fetchall()
    ]
    assert states == ["INTERRUPTED", "INTERRUPTED"]
    # Interrupted jobs cannot be claimed automatically on startup.
    assert claim_discover_job(database, now=restart_time) is None


def test_revoking_authorization_after_fetch_one_prevents_fetch_two_and_interrupts_job(database):
    """Regression for Blocker 3: revoking authorization after fetch one must block fetch two and settle INTERRUPTED."""
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:revoke-after-cell-1",
        campaign_id=camp.id,
        limit=10,
    )
    claimed = claim_discover_job(database, enqueued["id"])
    authorized = [True]

    class RevokingAfterCellOneSource(FakeDiscoverySource):
        def discover(self, planned, *, max_elements):
            batch = super().discover(planned, max_elements=max_elements)
            return batch

    source = RevokingAfterCellOneSource(
        [
            DiscoveryBatch((obs("node/1", "First Cell Cafe"),), False, ()),
            DiscoveryBatch((obs("node/2", "Second Cell Cafe"),), False, ()),
        ]
    )

    auth_checks = [0]

    def fresh_auth(_payload):
        auth_checks[0] += 1
        # Allow initial check, cell 1 pre-dispatch, and cell 1 pre-commit; revoke before cell 2!
        if len(source.calls) >= 1 and auth_checks[0] >= 4:
            authorized[0] = False
        return authorized[0]

    result = execute_manual_discovery_job(
        database,
        claimed,
        source,
        authorize_dispatch=fresh_auth,
    )
    assert result["state"] == "INTERRUPTED"
    assert result["error_code"] == "AUTHORIZATION_LOST"
    assert len(source.calls) == 1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 1


def test_revoking_authorization_during_fetch_prevents_result_commit_and_retry(database):
    """Verify authorization lost during an in-flight request or before retry blocks both commit and retry."""
    camp = ready_guild_and_campaign(database)
    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:revoke-before-retry",
        campaign_id=camp.id,
        limit=10,
    )
    claimed = claim_discover_job(database, enqueued["id"])
    authorized = [True]

    class FailingThenRevokingSource(FakeDiscoverySource):
        def discover(self, planned, *, max_elements):
            authorized[0] = False
            return super().discover(planned, max_elements=max_elements)

    source = FailingThenRevokingSource(
        [
            SourceFailure("Transient failure on attempt 1"),
            DiscoveryBatch((obs("node/99", "Should Not Be Fetched"),), False, ()),
        ]
    )
    result = execute_manual_discovery_job(
        database,
        claimed,
        source,
        authorize_dispatch=lambda _: authorized[0],
        max_attempts_per_query=3,
    )
    assert result["state"] == "INTERRUPTED"
    assert result["error_code"] == "AUTHORIZATION_LOST"
    assert len(source.calls) == 1
    q_row = database.connection.execute("SELECT state, attempts FROM discovery_queries").fetchone()
    assert q_row["state"] == "FAILED" and q_row["attempts"] == 1


def test_long_fetch_renews_lease_via_periodic_heartbeat_and_never_leaves_job_running(database):
    """Regression for Blocker 4: a 31-second simulated fetch renews the 30-second lease via heartbeats and finishes SUCCEEDED."""
    camp = ready_guild_and_campaign(database)
    t_now = [datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)]

    def fake_clock():
        return t_now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:long-fetch-31s",
        campaign_id=camp.id,
        limit=1,
        now=fake_clock(),
    )
    claimed = claim_discover_job(database, enqueued["id"], lease_seconds=30, now=fake_clock())

    class SlowThirtyOneSecondSource:
        source_namespace = "osm"
        policy_version = "osm-v1"

        def discover(self, planned, *, max_elements, on_wait_tick=None, **_):
            # Advance simulated wall-clock 31 seconds in 10s steps, firing heartbeat tick each step.
            for step in (10, 10, 11):
                t_now[0] += timedelta(seconds=step)
                if on_wait_tick is not None:
                    on_wait_tick()
            return DiscoveryBatch((obs("node/31", "Heartbeated Cafe", observed_at=fake_clock()),), False, ())

    result = execute_manual_discovery_job(
        database,
        claimed,
        SlowThirtyOneSecondSource(),
        lease_seconds=30,
        heartbeat_seconds=0.02,
        clock=fake_clock,
    )
    assert result["state"] == "SUCCEEDED"
    assert database.connection.execute("SELECT count(*) FROM jobs WHERE state='RUNNING'").fetchone()[0] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 1


def test_expired_lease_or_exception_settles_job_and_query_instead_of_leaving_running(database):
    """If a fetch stalls without heartbeats past the 30s lease, the worker settles INTERRUPTED (never leaves RUNNING)."""
    camp = ready_guild_and_campaign(database)
    t_now = [datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)]

    def fake_clock():
        return t_now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    enqueued = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:unheartbeated-stall",
        campaign_id=camp.id,
        limit=5,
        now=fake_clock(),
    )
    claimed = claim_discover_job(database, enqueued["id"], lease_seconds=30, now=fake_clock())

    class StalledSourceWithoutTick:
        source_namespace = "osm"
        policy_version = "osm-v1"

        def discover(self, planned, *, max_elements):
            # Advance clock 31s in a single jump before background thread can renew.
            t_now[0] += timedelta(seconds=31)
            return DiscoveryBatch((obs("node/77", "Stale Cafe", observed_at=fake_clock()),), False, ())

    result = execute_manual_discovery_job(
        database,
        claimed,
        StalledSourceWithoutTick(),
        lease_seconds=30,
        heartbeat_seconds=10.0,
        clock=fake_clock,
    )
    assert result["state"] == "INTERRUPTED"
    assert database.connection.execute("SELECT count(*) FROM jobs WHERE state='RUNNING'").fetchone()[0] == 0
    assert database.connection.execute("SELECT count(*) FROM discovery_queries WHERE state='RUNNING'").fetchone()[0] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0


def test_synchronous_heartbeat_runs_on_connection_owner_thread_without_manual_on_wait_tick(database):
    """Regression for Issue 1: actual periodic heartbeat fires on the connection owner thread without calling on_wait_tick, with zero unhandled thread exceptions."""
    import threading
    import time

    thread_exceptions = []
    old_hook = threading.excepthook

    def _hook(args):
        thread_exceptions.append(args)
        old_hook(args)

    threading.excepthook = _hook
    try:
        camp = ready_guild_and_campaign(database)
        t_now = [datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)]
        t_lock = threading.Lock()

        def fake_clock():
            with t_lock:
                return t_now[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        enqueued = enqueue_manual_discovery(
            database,
            actor_id="223456789012345678",
            guild_id="123456789012345678",
            channel_id="323456789012345678",
            idempotency_key="discover:owner-thread-hb",
            campaign_id=camp.id,
            limit=1,
            now=fake_clock(),
        )
        claimed = claim_discover_job(database, enqueued["id"], lease_seconds=30, now=fake_clock())

        class SourceWithoutWaitTick:
            source_namespace = "osm"
            policy_version = "osm-v1"

            def discover(self, planned, *, max_elements):
                # Do NOT accept or call on_wait_tick! Advance simulated wall clock 31s across real sleeps
                # so the owner thread's periodic heartbeat loop must renew the 30s lease on its own.
                for step in (10, 10, 11):
                    time.sleep(0.06)
                    with t_lock:
                        t_now[0] += timedelta(seconds=step)
                time.sleep(0.06)
                return DiscoveryBatch((obs("node/88", "Owner Thread HB Cafe", observed_at=fake_clock()),), False, ())

        result = execute_manual_discovery_job(
            database,
            claimed,
            SourceWithoutWaitTick(),
            lease_seconds=30,
            heartbeat_seconds=0.02,
            clock=fake_clock,
        )
        assert thread_exceptions == []
        assert result["state"] == "SUCCEEDED"
        assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 1
    finally:
        threading.excepthook = old_hook


def test_stalled_headers_slow_stream_and_late_response_terminate_timely_and_settle_failed(database):
    """Regression for Issue 2: stalled headers, slow streams, and late responses are bounded by the attempt deadline, abort in-flight work, and settle jobs/queries FAILED."""
    import asyncio
    import threading
    import time
    from mi_boti.jobs.discovery import execute_manual_discovery_job_async
    from mi_boti.repositories.async_database import AsyncDatabase

    camp = ready_guild_and_campaign(database)

    # Case A: Synchronous worker with a source that stalls past request_timeout_seconds (0.15s)
    # unless register_abort unblocks it.
    enq_stalled = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:stalled-header",
        campaign_id=camp.id,
        limit=1,
    )
    claimed_stalled = claim_discover_job(database, enq_stalled["id"])
    aborted = threading.Event()

    class StalledHeaderSource:
        source_namespace = "osm"
        policy_version = "osm-v1"

        def discover(self, planned, *, max_elements, register_abort=None, **_):
            if register_abort is not None:
                register_abort(aborted.set)
            # Would block for 10 seconds if deadline + abort didn't fire!
            aborted.wait(timeout=10.0)
            return DiscoveryBatch((obs("node/901", "Never Committed"),), False, ())

    t0 = time.monotonic()
    res_stalled = execute_manual_discovery_job(
        database,
        claimed_stalled,
        StalledHeaderSource(),
        request_timeout_seconds=0.12,
        max_attempts_per_query=1,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 1.5
    assert aborted.is_set()
    assert res_stalled["state"] == "FAILED"
    assert res_stalled["error_code"] == "SOURCE_UNAVAILABLE"
    q_stalled = database.connection.execute(
        "SELECT state, error_code FROM discovery_queries WHERE job_id=?",
        (claimed_stalled.id,),
    ).fetchone()
    assert q_stalled["state"] == "FAILED" and q_stalled["error_code"] == "SOURCE_UNAVAILABLE"
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0

    # Case B: Late response arriving after monotonic deadline in async worker is rejected and settled FAILED.
    async def run_async_late():
        async_db = AsyncDatabase(database.path)
        try:
            enq_late = await async_db.call(
                lambda db: enqueue_manual_discovery(
                    db,
                    actor_id="223456789012345678",
                    guild_id="123456789012345678",
                    channel_id="323456789012345678",
                    idempotency_key="discover:async-late-response",
                    campaign_id=camp.id,
                    limit=1,
                )
            )
            claimed_late = await async_db.call(lambda db: claim_discover_job(db, enq_late["id"]))
            fake_mono = [100.0]

            class LateReturningSource:
                source_namespace = "osm"
                policy_version = "osm-v1"

                def discover(self, planned, *, max_elements, **_):
                    # Advance monotonic clock past the 5.0s request_timeout_seconds before returning!
                    fake_mono[0] += 6.0
                    return DiscoveryBatch((obs("node/902", "Late Cafe"),), False, ())

            res_late = await execute_manual_discovery_job_async(
                async_db,
                claimed_late,
                LateReturningSource(),
                request_timeout_seconds=5.0,
                max_attempts_per_query=1,
                monotonic=lambda: fake_mono[0],
            )
            assert res_late["state"] == "FAILED"
            assert res_late["error_code"] == "SOURCE_UNAVAILABLE"
            q_late = await async_db.call(
                lambda db: dict(
                    db.connection.execute(
                        "SELECT state, error_code FROM discovery_queries WHERE job_id=?",
                        (claimed_late.id,),
                    ).fetchone()
                )
            )
            assert q_late["state"] == "FAILED" and q_late["error_code"] == "SOURCE_UNAVAILABLE"
            assert await async_db.call(lambda db: db.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]) == 0
        finally:
            await async_db.close()

    asyncio.run(run_async_late())


def test_stalled_dns_resolver_in_discovery_job_bounds_workers_blocks_retries_and_uses_stricter_timeout(database):
    """Regression: when OverpassDiscoveryAdapter's resolver blocks without cooperating with register_abort:
    1. Effective attempt timeout uses min(request_timeout_seconds, policy['timeout_seconds']).
    2. Worker count never exceeds 1 across retries and subsequent jobs while DNS remains wedged.
    3. Shutdown reports drained=False while wedged (never falsely claiming termination) and drained=True once released.
    """
    import asyncio
    import httpx
    import threading
    import time
    from uuid import uuid4
    from mi_boti.discovery.overpass import OverpassDiscoveryAdapter, SourceCancelledError
    from mi_boti.discovery.planner import QuerySpec
    from mi_boti.domain.campaigns import PlannedCellQuery
    from mi_boti.jobs.discovery import (
        _effective_attempt_timeout,
        active_discovery_worker_count,
        execute_manual_discovery_job_async,
        shutdown_discovery_workers,
    )
    from mi_boti.repositories.async_database import AsyncDatabase

    camp = ready_guild_and_campaign(database)
    source_key = "test-wedged-dns:" + uuid4().hex

    release_dns = threading.Event()
    entered_dns = threading.Event()
    resolver_calls = [0]

    def uncooperative_resolver(*_, **__):
        resolver_calls[0] += 1
        entered_dns.set()
        # Ignores register_abort completely!
        release_dns.wait()  # The test's finally block releases this uncooperative resolver.
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    policy = {
        "enabled": True,
        "endpoint": "https://overpass-api.de/api/interpreter",
        "allowed_hosts": ("overpass-api.de",),
        "policy_version": "overpass-2026-11",
        "review_expires_at": "2027-06-01T00:00:00Z",
        "user_agent": "MiBoti/0.1 (+https://example.invalid; contact=ops@example.invalid)",
        "min_interval_seconds": 10,
        "max_concurrency": 1,
        "timeout_seconds": 20,
        "max_response_bytes": 1048576,
        "allowed_tags": ("cafe", "restaurant"),
    }
    adapter = OverpassDiscoveryAdapter(
        policy,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})
        ),
        resolver=uncooperative_resolver,
        rate_limit_key=source_key,
    )

    # Verify stricter timeout selection in both directions:
    assert _effective_attempt_timeout(adapter, 0.12) == 0.12
    adapter_strict_policy = OverpassDiscoveryAdapter(
        {**policy, "timeout_seconds": 2},
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})
        ),
        resolver=uncooperative_resolver,
        rate_limit_key=source_key,
    )
    assert _effective_attempt_timeout(adapter_strict_policy, 20.0) == 2.0

    enq1 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:wedged-dns-sync",
        campaign_id=camp.id,
        limit=1,
    )
    claimed1 = claim_discover_job(database, enq1["id"])

    # Establish the wedged resolver explicitly instead of hoping the OS schedules
    # both source/DNS threads inside a 100 ms attempt budget under the full suite.
    # Cancelling the probe must return promptly, leaving the uncooperative DNS
    # thread tracked; subsequent jobs must refuse admission without spawning more.
    probe_cancel = threading.Event()
    probe_errors = []
    planned_probe = PlannedCellQuery(
        "qc-dns-probe",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 1, 1, adapter.policy_version),
    )

    def start_resolver_probe():
        try:
            adapter.discover(
                planned_probe,
                max_elements=1,
                is_cancelled=probe_cancel.is_set,
                deadline_monotonic=time.monotonic() + 2.0,
            )
        except BaseException as error:
            probe_errors.append(error)

    probe_thread = threading.Thread(target=start_resolver_probe, daemon=True)
    probe_thread.start()

    try:
        assert entered_dns.wait(timeout=2.0), "Resolver did not start within the probe deadline."
        probe_cancel.set()
        probe_thread.join(timeout=1.0)
        assert not probe_thread.is_alive(), "Cancelled probe did not return promptly."
        assert len(probe_errors) == 1 and isinstance(probe_errors[0], SourceCancelledError)
        t0 = time.monotonic()
        # Policy timeout is 20s, explicit request_timeout_seconds is 0.10s; stricter 0.10s must govern!
        res1 = execute_manual_discovery_job(
            database,
            claimed1,
            adapter,
            request_timeout_seconds=0.10,
            max_attempts_per_query=3,
        )
        elapsed1 = time.monotonic() - t0
        assert elapsed1 < 1.5
        assert entered_dns.is_set()
        assert res1["state"] == "FAILED"
        assert res1["error_code"] == "SOURCE_UNAVAILABLE"

        # All 3 retry attempts executed, but attempts 2 and 3 were blocked from spawning a new resolver thread!
        q1 = database.connection.execute(
            "SELECT state, attempts, error_code FROM discovery_queries WHERE job_id=?",
            (claimed1.id,),
        ).fetchone()
        assert q1["state"] == "FAILED"
        assert q1["attempts"] == 3
        assert resolver_calls[0] == 1
        assert active_discovery_worker_count(source_key=source_key) == 1

        # A second job submitted while the resolver is still wedged must also fail fast without spawning threads.
        async def run_second_job_while_wedged():
            async_db = AsyncDatabase(database.path)
            try:
                enq2 = await async_db.call(
                    lambda db: enqueue_manual_discovery(
                        db,
                        actor_id="223456789012345678",
                        guild_id="123456789012345678",
                        channel_id="323456789012345678",
                        idempotency_key="discover:wedged-dns-async-2",
                        campaign_id=camp.id,
                        limit=1,
                    )
                )
                claimed2 = await async_db.call(lambda db: claim_discover_job(db, enq2["id"]))
                res2 = await execute_manual_discovery_job_async(
                    async_db,
                    claimed2,
                    adapter,
                    request_timeout_seconds=0.10,
                    max_attempts_per_query=2,
                )
                assert res2["state"] == "FAILED"
                assert res2["error_code"] == "SOURCE_UNAVAILABLE"
            finally:
                await async_db.close()

        asyncio.run(run_second_job_while_wedged())
        assert resolver_calls[0] == 1
        assert active_discovery_worker_count(source_key=source_key) == 1

        # Shutdown check while resolver is still blocked must honestly report drained=False, remaining=1.
        shut_blocked = shutdown_discovery_workers(timeout=0.03, source_key=source_key)
        assert shut_blocked == {"drained": False, "remaining": 1}
    finally:
        probe_cancel.set()
        release_dns.set()
        probe_thread.join(timeout=1.0)

    shut_drained = shutdown_discovery_workers(timeout=1.0, source_key=source_key)
    assert shut_drained == {"drained": True, "remaining": 0}
    assert active_discovery_worker_count(source_key=source_key) == 0
