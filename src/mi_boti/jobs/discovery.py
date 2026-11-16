"""Bounded non-AI discovery job admission, leases, cancellation, worker and startup recovery.

Never starts or resumes autonomous hunting on startup, never uses paid or unapproved
discovery sources, and never invokes AI providers or awards hunt quota credits.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import inspect
import json
import threading
import time
from typing import Callable, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from ..discovery.overpass import (
    DiscoveryBatch,
    DiscoverySourceError,
    SourceCancelledError,
    active_resolver_worker_count,
    shutdown_resolver_workers,
)
from ..domain.campaigns import DiscoveryLifecycleError, PlannedCellQuery, parse_utc, validate_actor
from ..domain.errors import AppError
from ..domain.registry import encoded
from ..domain.values import snowflake, utc_now
from ..repositories.campaigns import (
    begin_discovery_attempt,
    finish_discovery_query,
    get_campaign,
    plan_unexhausted_queries,
    queue_discovery_query,
)
from ..repositories.database import Database
from ..repositories.registry import resolve


class JobSchedulerError(AppError):
    code = "JOB_SCHEDULER_INVALID"


class DiscoverySourcePort(Protocol):
    source_namespace: str
    policy_version: str

    def discover(self, planned: PlannedCellQuery, *, max_elements: int) -> DiscoveryBatch:
        ...


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    kind: str
    payload: dict
    idempotency_key: str
    hunt_id: str | None
    business_id: str | None
    actor_id: str
    state: str
    attempt: int
    max_attempts: int
    progress: dict
    lease_token: str
    lease_expires_at: str
    cancel_requested: bool
    created_at: str
    updated_at: str


def _future_utc(now_utc: str, seconds: int) -> str:
    return (parse_utc(now_utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row_to_claimed(row) -> ClaimedJob:
    return ClaimedJob(
        id=row["id"],
        kind=row["kind"],
        payload=json.loads(row["payload_json"]),
        idempotency_key=row["idempotency_key"],
        hunt_id=row["hunt_id"],
        business_id=row["business_id"],
        actor_id=row["actor_id"],
        state=row["state"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        progress=json.loads(row["progress_json"] or "{}"),
        lease_token=row["lease_token"],
        lease_expires_at=row["lease_expires_at"],
        cancel_requested=bool(row["cancel_requested"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def enqueue_manual_discovery(
    db,
    *,
    actor_id: str,
    guild_id: str,
    channel_id: str,
    idempotency_key: str,
    campaign_id: str,
    limit: int = 25,
    max_attempts: int = 3,
    now: str | None = None,
) -> dict:
    """Idempotently enqueue a standalone manual DISCOVER job (hunt_id=None)."""
    actor = validate_actor(actor_id)
    guild = snowflake(guild_id)
    channel = snowflake(channel_id)
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key.strip()) <= 256:
        raise JobSchedulerError("Idempotency key is required.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise JobSchedulerError("Manual discovery limit must be an integer between 1 and 100.")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise JobSchedulerError("Job max_attempts must be between 1 and 3.")
    stamp = now or utc_now()
    parse_utc(stamp)
    with db.transaction() as c:
        existing = c.execute("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            return dict(existing)
        cfg = c.execute("SELECT setup_state, revision, guild_id FROM guild_config WHERE id='guild'").fetchone()
        if not cfg or cfg["setup_state"] != "READY" or cfg["guild_id"] != guild:
            raise JobSchedulerError("Server configuration is not READY for discovery.")
        campaign_row = get_campaign(db, campaign_id)
        if campaign_row.state != "ACTIVE":
            raise JobSchedulerError("Manual discovery requires an ACTIVE campaign.")
        job_id = str(uuid4())
        payload = {
            "schema_version": 1,
            "command_key": "discover",
            "guild_id": guild,
            "channel_id": channel,
            "actor_id": actor,
            "campaign_id": campaign_id,
            "campaign_version": campaign_row.current_version,
            "config_revision": cfg["revision"],
            "options": {"limit": limit},
        }
        progress = {
            "phase": "QUEUED",
            "discovery_requests": 0,
            "seen": 0,
            "new": 0,
            "existing": 0,
            "ambiguous": 0,
            "invalid": 0,
        }
        c.execute(
            "INSERT INTO jobs(id,kind,payload_json,idempotency_key,hunt_id,business_id,actor_id,state,attempt,max_attempts,progress_json,lease_token,lease_expires_at,cancel_requested,next_attempt_at,created_at,updated_at,error_code) "
            "VALUES (?,'DISCOVER',?,?,NULL,NULL,?,'QUEUED',0,?,?,NULL,NULL,0,?,?,?,NULL)",
            (
                job_id,
                encoded(payload),
                idempotency_key,
                actor,
                max_attempts,
                encoded(progress),
                stamp,
                stamp,
                stamp,
            ),
        )
        c.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(uuid4()),
                actor,
                "job.enqueue_discover",
                "job",
                job_id,
                "SUCCESS",
                encoded({"campaign_id": campaign_id, "limit": limit}),
                stamp,
            ),
        )
        return dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def claim_discover_job(
    db,
    job_id: str | None = None,
    *,
    lease_seconds: int = 30,
    max_concurrency: int = 2,
    manual_max_age_seconds: int = 3600,
    now: str | None = None,
) -> ClaimedJob | None:
    """Atomically claim one eligible QUEUED or due RETRY_WAIT DISCOVER job."""
    if type(lease_seconds) is not int or lease_seconds < 5:
        raise JobSchedulerError("Lease duration must be at least 5 seconds.")
    if type(max_concurrency) is not int or not 1 <= max_concurrency <= 2:
        raise JobSchedulerError("Worker concurrency must be 1 or 2.")
    stamp = now or utc_now()
    parse_utc(stamp)
    with db.transaction() as c:
        running = c.execute("SELECT count(*) FROM jobs WHERE state='RUNNING'").fetchone()[0]
        if running >= max_concurrency:
            return None
        if job_id is not None:
            row = c.execute("SELECT * FROM jobs WHERE id=? AND kind='DISCOVER'", (job_id,)).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM jobs WHERE kind='DISCOVER' AND state IN ('QUEUED','RETRY_WAIT') "
                "AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY created_at ASC LIMIT 1",
                (stamp,),
            ).fetchone()
        if not row or row["state"] not in {"QUEUED", "RETRY_WAIT"}:
            return None
        if row["next_attempt_at"] and row["next_attempt_at"] > stamp:
            return None
        if row["cancel_requested"]:
            c.execute(
                "UPDATE jobs SET state='CANCELLED', lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code='OPERATOR_CANCELLED' WHERE id=?",
                (stamp, row["id"]),
            )
            return None
        age_seconds = (parse_utc(stamp) - parse_utc(row["created_at"])).total_seconds()
        if row["hunt_id"] is None and age_seconds > manual_max_age_seconds:
            c.execute(
                "UPDATE jobs SET state='FAILED', lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code='SAFETY_LIMIT' WHERE id=?",
                (stamp, row["id"]),
            )
            return None
        if row["attempt"] >= row["max_attempts"]:
            c.execute(
                "UPDATE jobs SET state='FAILED', lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code='RETRY_LIMIT_REACHED' WHERE id=?",
                (stamp, row["id"]),
            )
            return None
        token = str(uuid4())
        expiry = _future_utc(stamp, lease_seconds)
        c.execute(
            "UPDATE jobs SET state='RUNNING', attempt=attempt+1, lease_token=?, lease_expires_at=?, updated_at=?, error_code=NULL WHERE id=?",
            (token, expiry, stamp, row["id"]),
        )
        return _row_to_claimed(c.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())


def heartbeat_job_lease(
    db,
    job_id: str,
    lease_token: str,
    *,
    lease_seconds: int = 30,
    now: str | None = None,
) -> ClaimedJob:
    stamp = now or utc_now()
    expiry = _future_utc(stamp, lease_seconds)
    with db.transaction() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if (
            not row
            or row["state"] != "RUNNING"
            or not lease_token
            or row["lease_token"] != lease_token
            or not row["lease_expires_at"]
            or row["lease_expires_at"] <= stamp
        ):
            raise JobSchedulerError("Cannot renew an expired or unowned job lease.")
        c.execute(
            "UPDATE jobs SET lease_expires_at=?, updated_at=? WHERE id=?",
            (expiry, stamp, job_id),
        )
        return _row_to_claimed(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def request_job_cancellation(db, job_id: str, actor_id: str, *, now: str | None = None) -> dict:
    actor = validate_actor(actor_id)
    stamp = now or utc_now()
    parse_utc(stamp)
    with db.transaction() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise JobSchedulerError("Job was not found.")
        if row["state"] in {"QUEUED", "RETRY_WAIT"}:
            c.execute(
                "UPDATE jobs SET state='CANCELLED', cancel_requested=1, lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code='OPERATOR_CANCELLED' WHERE id=?",
                (stamp, job_id),
            )
        elif row["state"] == "RUNNING":
            c.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=?",
                (stamp, job_id),
            )
        c.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(uuid4()),
                actor,
                "job.cancel_request",
                "job",
                job_id,
                "SUCCESS",
                encoded({"prior_state": row["state"]}),
                stamp,
            ),
        )
        return dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def recover_interrupted_work(db, *, now: str | None = None) -> dict:
    """Startup reconciliation per doc 17: mark unfinished hunts/jobs INTERRUPTED.

    Charges at most the already-reserved active lease on running hunts, never the
    offline interval, and never starts or requeues autonomous work.
    """
    stamp = now or utc_now()
    current_dt = parse_utc(stamp)
    with db.transaction() as c:
        interrupted_hunts = 0
        for hunt in c.execute(
            "SELECT * FROM hunts WHERE state IN ('RUNNING','PAUSING','PAUSED','STOPPING')"
        ).fetchall():
            added_ms = 0
            if hunt["state"] in {"RUNNING", "PAUSING", "STOPPING"} and hunt["active_checkpoint_at"]:
                checkpoint_dt = parse_utc(hunt["active_checkpoint_at"])
                end_dt = current_dt
                if hunt["active_lease_expires_at"]:
                    lease_dt = parse_utc(hunt["active_lease_expires_at"])
                    if lease_dt < end_dt:
                        end_dt = lease_dt
                if end_dt > checkpoint_dt:
                    added_ms = min(30000, int((end_dt - checkpoint_dt).total_seconds() * 1000))
            max_obs = max(hunt["max_observed_at"], stamp)
            c.execute(
                "UPDATE hunts SET state='INTERRUPTED', stop_reason='RESTART_INTERRUPTION', "
                "active_milliseconds=active_milliseconds+?, active_checkpoint_at=NULL, active_lease_expires_at=NULL, "
                "max_observed_at=?, updated_at=?, revision=revision+1 WHERE id=?",
                (added_ms, max_obs, stamp, hunt["id"]),
            )
            interrupted_hunts += 1

        interrupted_jobs = c.execute(
            "UPDATE jobs SET state='INTERRUPTED', lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code='RESTART_INTERRUPTION' "
            "WHERE state='RUNNING' OR ((hunt_id IS NOT NULL OR kind='RESEARCH') AND state IN ('QUEUED','RETRY_WAIT'))",
            (stamp,),
        ).rowcount
        c.execute(
            "UPDATE discovery_queries SET state='FAILED', finished_at=?, error_code='RESTART_INTERRUPTION' WHERE state IN ('QUEUED','RUNNING')",
            (stamp,),
        )
        c.execute("UPDATE research_runs SET state='INTERRUPTED',finished_at=?,limitations_json=? WHERE state IN ('QUEUED','RUNNING')",
                  (stamp, json.dumps(["Research interrupted by restart; explicit refresh is required."])))
        return {"interrupted_hunts": interrupted_hunts, "interrupted_jobs": interrupted_jobs}


def _check_authorization(authorize_dispatch: Callable[[dict], bool] | None, payload: dict) -> bool:
    if authorize_dispatch is None:
        return True
    try:
        return bool(authorize_dispatch(dict(payload)))
    except Exception:
        return False


def _settle_job_and_queries(
    db,
    job_id: str,
    lease_token: str,
    *,
    job_state: str,
    error_code: str,
    query_id: str | None = None,
    query_state: str = "FAILED",
    now: str,
) -> dict:
    with db.transaction() as c:
        if query_id is not None:
            c.execute(
                "UPDATE discovery_queries SET state=?, finished_at=?, error_code=? WHERE id=? AND state IN ('QUEUED','RUNNING')",
                (query_state, now, error_code, query_id),
            )
        c.execute(
            "UPDATE discovery_queries SET state=?, finished_at=?, error_code=? WHERE job_id=? AND state IN ('QUEUED','RUNNING')",
            (query_state, now, error_code, job_id),
        )
        c.execute(
            "UPDATE jobs SET state=?, lease_token=NULL, lease_expires_at=NULL, updated_at=?, error_code=? "
            "WHERE id=? AND state='RUNNING' AND (lease_token=? OR lease_expires_at<=?)",
            (job_state, now, error_code, job_id, lease_token, now),
        )
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else {"id": job_id, "state": job_state, "error_code": error_code}


_SOURCE_WORKERS_GUARD = threading.Lock()
_ACTIVE_SOURCE_WORKERS: dict[str, set[threading.Thread]] = {}
_DETACHED_SOURCE_WORKERS: dict[str, set[threading.Thread]] = {}


def _source_worker_key(source_port: DiscoverySourcePort) -> str:
    rate_key = getattr(source_port, "_rate_key", None)
    if isinstance(rate_key, str) and rate_key:
        return rate_key
    policy = getattr(source_port, "policy", None)
    if isinstance(policy, dict) and "endpoint" in policy:
        host = (urlsplit(str(policy["endpoint"])).hostname or "").lower().rstrip(".")
        return f"{getattr(source_port, 'source_namespace', 'src')}:{host}"
    return f"{getattr(source_port, 'source_namespace', 'src')}:{id(source_port)}"


def active_discovery_worker_count(source_key: str | None = None) -> int:
    """Return the count of currently alive source/resolver worker threads."""
    with _SOURCE_WORKERS_GUARD:
        keys = [source_key] if source_key is not None else list(set(_ACTIVE_SOURCE_WORKERS) | set(_DETACHED_SOURCE_WORKERS))
        live_threads: set[threading.Thread] = set()
        for k in keys:
            act = {t for t in _ACTIVE_SOURCE_WORKERS.get(k, set()) if t.is_alive()}
            det = {t for t in _DETACHED_SOURCE_WORKERS.get(k, set()) if t.is_alive()}
            if act:
                _ACTIVE_SOURCE_WORKERS[k] = act
            else:
                _ACTIVE_SOURCE_WORKERS.pop(k, None)
            if det:
                _DETACHED_SOURCE_WORKERS[k] = det
            else:
                _DETACHED_SOURCE_WORKERS.pop(k, None)
            live_threads |= act | det
    return len(live_threads) + active_resolver_worker_count(rate_key=source_key)


def shutdown_discovery_workers(*, timeout: float = 1.0, source_key: str | None = None) -> dict[str, object]:
    """Wait up to timeout seconds for tracked discovery and DNS resolver threads to exit.

    Never claims termination when a worker remains detached/blocked; returns
    {"drained": bool, "remaining": int}.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _SOURCE_WORKERS_GUARD:
        keys = [source_key] if source_key is not None else list(set(_ACTIVE_SOURCE_WORKERS) | set(_DETACHED_SOURCE_WORKERS))
        threads: list[threading.Thread] = []
        for k in keys:
            threads.extend(t for t in _ACTIVE_SOURCE_WORKERS.get(k, set()) if t.is_alive())
            threads.extend(t for t in _DETACHED_SOURCE_WORKERS.get(k, set()) if t.is_alive())
    for t in threads:
        rem = max(0.0, deadline - time.monotonic())
        t.join(timeout=rem)
    rem_resolver = max(0.0, deadline - time.monotonic())
    shutdown_resolver_workers(timeout=rem_resolver, rate_key=source_key)
    remaining = active_discovery_worker_count(source_key=source_key)
    return {"drained": remaining == 0, "remaining": remaining}


def _acquire_source_worker_admission(source_port: DiscoverySourcePort) -> str:
    """Verify no prior timed-out/detached worker or DNS resolver thread is still wedged for this source."""
    key = _source_worker_key(source_port)
    rate_key = getattr(source_port, "_rate_key", None)
    if active_resolver_worker_count(rate_key=rate_key if isinstance(rate_key, str) else None) > 0:
        raise DiscoverySourceError(
            "Discovery source resolver is still occupied by an uncompleted timed-out DNS lookup."
        )
    with _SOURCE_WORKERS_GUARD:
        det = {t for t in _DETACHED_SOURCE_WORKERS.get(key, set()) if t.is_alive()}
        if det:
            _DETACHED_SOURCE_WORKERS[key] = det
            raise DiscoverySourceError(
                "Discovery source worker is still occupied by an uncompleted timed-out request."
            )
        _DETACHED_SOURCE_WORKERS.pop(key, None)
    return key


def _effective_attempt_timeout(source_port: DiscoverySourcePort, request_timeout_seconds: float) -> float:
    """Return the stricter (min) of explicit request_timeout_seconds and source policy timeout_seconds."""
    explicit_timeout = float(request_timeout_seconds)
    policy = getattr(source_port, "policy", None)
    if isinstance(policy, dict) and "timeout_seconds" in policy:
        effective = min(explicit_timeout, float(policy["timeout_seconds"]))
    else:
        effective = explicit_timeout
    return min(max(0.01, effective), 30.0)


def _invoke_source_discover(
    source_port: DiscoverySourcePort,
    cell_query: PlannedCellQuery,
    *,
    max_elements: int,
    on_wait_tick: Callable[[], None],
    is_cancelled: Callable[[], bool],
    deadline_monotonic: float,
    register_abort: Callable[[Callable[[], None]], None] | None = None,
    campaign_id: str | None = None,
) -> DiscoveryBatch:
    sig = inspect.signature(source_port.discover)
    kwargs: dict = {"max_elements": max_elements}
    params = sig.parameters
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if "on_wait_tick" in params or accepts_var_kw:
        kwargs["on_wait_tick"] = on_wait_tick
    if "is_cancelled" in params or accepts_var_kw:
        kwargs["is_cancelled"] = is_cancelled
    if "deadline_monotonic" in params or accepts_var_kw:
        kwargs["deadline_monotonic"] = deadline_monotonic
    if register_abort is not None and ("register_abort" in params or accepts_var_kw):
        kwargs["register_abort"] = register_abort
    if campaign_id is not None and ("campaign_id" in params or accepts_var_kw):
        kwargs["campaign_id"] = campaign_id
    return source_port.discover(cell_query, **kwargs)


def _acknowledge_source_checkpoint(
    source_port: DiscoverySourcePort,
    batch: DiscoveryBatch,
    *,
    now: str,
) -> None:
    token = getattr(batch, "checkpoint_token", None)
    if token is None:
        return
    ack_fn = getattr(source_port, "acknowledge_checkpoint", None)
    if callable(ack_fn):
        ack_fn(token, now=now)


def execute_manual_discovery_job(
    db,
    claimed: ClaimedJob,
    source_port: DiscoverySourcePort,
    *,
    authorize_dispatch: Callable[[dict], bool] | None = None,
    lease_seconds: int = 30,
    heartbeat_seconds: float | None = None,
    request_timeout_seconds: float = 20.0,
    max_job_requests: int = 20,
    max_requests_per_day: int = 100,
    max_attempts_per_query: int = 3,
    manual_max_age_seconds: int = 3600,
    coverage_ttl_seconds: int = 2592000,
    similarity_threshold: float = 0.85,
    clock: Callable[[], str] = utc_now,
    monotonic: Callable[[], float] = time.monotonic,
    on_before_cursor_ack: Callable[[dict], None] | None = None,
) -> dict:
    """Execute a claimed standalone manual DISCOVER job with owner-thread lease heartbeats and fresh auth."""
    current_query_id: str | None = None
    hb_interval = (
        float(heartbeat_seconds)
        if heartbeat_seconds is not None
        else max(0.05, min(10.0, float(lease_seconds) / 3.0))
    )
    per_attempt_timeout = _effective_attempt_timeout(source_port, request_timeout_seconds)

    try:
        now = clock()
        if not _check_authorization(authorize_dispatch, claimed.payload):
            return _settle_job_and_queries(
                db,
                claimed.id,
                claimed.lease_token,
                job_state="INTERRUPTED",
                error_code="AUTHORIZATION_LOST",
                now=now,
            )

        campaign_id = claimed.payload["campaign_id"]
        campaign_version = int(claimed.payload["campaign_version"])
        observation_limit = int(claimed.payload.get("options", {}).get("limit", 25))
        planned_cells = plan_unexhausted_queries(
            db,
            campaign_id,
            campaign_version=campaign_version,
            source=source_port.source_namespace,
            policy_version=source_port.policy_version,
            limit=observation_limit,
            coverage_ttl_seconds=coverage_ttl_seconds,
            now=now,
        )

        for planned in planned_cells:
            now = clock()
            row = db.connection.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone()
            if not row or row["state"] != "RUNNING" or row["lease_token"] != claimed.lease_token:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="LEASE_EXPIRED",
                    now=now,
                )
            if row["lease_expires_at"] <= now:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="LEASE_EXPIRED",
                    now=now,
                )
            if row["cancel_requested"]:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="CANCELLED",
                    error_code="OPERATOR_CANCELLED",
                    query_state="CANCELLED",
                    now=now,
                )
            age_elapsed = (parse_utc(now) - parse_utc(row["created_at"])).total_seconds()
            if age_elapsed > manual_max_age_seconds:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="FAILED",
                    error_code="SAFETY_LIMIT",
                    now=now,
                )

            # Revalidate authorization before every external query dispatch.
            if not _check_authorization(authorize_dispatch, claimed.payload):
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="AUTHORIZATION_LOST",
                    now=now,
                )

            # Renew lease before starting query.
            heartbeat_job_lease(
                db,
                claimed.id,
                claimed.lease_token,
                lease_seconds=lease_seconds,
                now=now,
            )

            progress = json.loads(row["progress_json"] or "{}")
            remaining_observations = observation_limit - int(progress.get("seen", 0))
            if remaining_observations <= 0:
                break
            per_query_cap = min(planned.spec.limit, remaining_observations)
            cell_query = PlannedCellQuery(
                geographic_cell=planned.geographic_cell,
                spec=type(planned.spec)(
                    bbox=planned.spec.bbox,
                    categories=planned.spec.categories,
                    limit=per_query_cap,
                    target_version=planned.spec.target_version,
                    policy_version=planned.spec.policy_version,
                ),
            )
            query_id = queue_discovery_query(
                db,
                claimed.id,
                claimed.lease_token,
                campaign_id,
                cell_query,
                source=source_port.source_namespace,
                now=now,
            )
            current_query_id = query_id
            try:
                begin_discovery_attempt(
                    db,
                    query_id,
                    claimed.lease_token,
                    max_attempts=max_attempts_per_query,
                    max_requests_per_day=max_requests_per_day,
                    max_job_requests=max_job_requests,
                    now=now,
                )
            except DiscoveryLifecycleError:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="FAILED",
                    error_code="SAFETY_LIMIT",
                    query_id=query_id,
                    query_state="FAILED",
                    now=now,
                )

            def _try_isolated_heartbeat() -> None:
                try:
                    with Database(db.path, busy_timeout_ms=5000) as hb_db:
                        heartbeat_job_lease(
                            hb_db,
                            claimed.id,
                            claimed.lease_token,
                            lease_seconds=lease_seconds,
                            now=clock(),
                        )
                except AppError:
                    pass

            batch = None
            while True:
                now = clock()
                rem_age = max(0.0, manual_max_age_seconds - (parse_utc(now) - parse_utc(row["created_at"])).total_seconds())
                job_deadline_m = monotonic() + rem_age
                attempt_deadline_m = min(job_deadline_m, monotonic() + per_attempt_timeout)

                cancel_flag = threading.Event()
                abort_callbacks: list[Callable[[], None]] = []
                abort_lock = threading.Lock()

                def _register_abort(cb: Callable[[], None]) -> None:
                    with abort_lock:
                        abort_callbacks.append(cb)

                def _trigger_abort() -> None:
                    cancel_flag.set()
                    with abort_lock:
                        cbs = list(abort_callbacks)
                    for cb in cbs:
                        try:
                            cb()
                        except Exception:
                            pass

                def _hb_thread_loop() -> None:
                    # Dedicated short-lived SQLite connection created and owned strictly by this thread.
                    try:
                        with Database(db.path, busy_timeout_ms=5000) as hb_db:
                            while not cancel_flag.wait(hb_interval):
                                if monotonic() >= attempt_deadline_m:
                                    _trigger_abort()
                                    break
                                r = hb_db.connection.execute(
                                    "SELECT state, cancel_requested, lease_token FROM jobs WHERE id=?",
                                    (claimed.id,),
                                ).fetchone()
                                if not r or r["state"] != "RUNNING" or r["lease_token"] != claimed.lease_token or r["cancel_requested"]:
                                    _trigger_abort()
                                    break
                                try:
                                    heartbeat_job_lease(
                                        hb_db,
                                        claimed.id,
                                        claimed.lease_token,
                                        lease_seconds=lease_seconds,
                                        now=clock(),
                                    )
                                except AppError:
                                    _trigger_abort()
                                    break
                    except AppError:
                        _trigger_abort()

                hb_thread = threading.Thread(
                    target=_hb_thread_loop,
                    name=f"mi-boti-hb-{claimed.id[:8]}",
                    daemon=True,
                )
                hb_thread.start()
                try:
                    source_key = _acquire_source_worker_admission(source_port)
                    if hasattr(source_port, "discover") and "register_abort" in inspect.signature(source_port.discover).parameters:
                        res_box: dict[str, object] = {}
                        done_evt = threading.Event()

                        def _src_worker() -> None:
                            cur = threading.current_thread()
                            try:
                                res_box["batch"] = _invoke_source_discover(
                                    source_port,
                                    cell_query,
                                    max_elements=per_query_cap,
                                    on_wait_tick=_try_isolated_heartbeat,
                                    is_cancelled=cancel_flag.is_set,
                                    deadline_monotonic=attempt_deadline_m,
                                    register_abort=_register_abort,
                                    campaign_id=campaign_id,
                                )
                            except BaseException as exc:
                                res_box["exc"] = exc
                            finally:
                                with _SOURCE_WORKERS_GUARD:
                                    act = _ACTIVE_SOURCE_WORKERS.get(source_key)
                                    if act is not None:
                                        act.discard(cur)
                                        if not act:
                                            _ACTIVE_SOURCE_WORKERS.pop(source_key, None)
                                    det = _DETACHED_SOURCE_WORKERS.get(source_key)
                                    if det is not None:
                                        det.discard(cur)
                                        if not det:
                                            _DETACHED_SOURCE_WORKERS.pop(source_key, None)
                                done_evt.set()

                        src_thread = threading.Thread(
                            target=_src_worker,
                            name=f"mi-boti-src-{claimed.id[:8]}",
                            daemon=True,
                        )
                        with _SOURCE_WORKERS_GUARD:
                            _ACTIVE_SOURCE_WORKERS.setdefault(source_key, set()).add(src_thread)
                        src_thread.start()
                        try:
                            while not done_evt.is_set():
                                now_m = monotonic()
                                if now_m >= attempt_deadline_m:
                                    _trigger_abort()
                                    raise DiscoverySourceError("Discovery source request exceeded total attempt deadline.")
                                r_chk = db.connection.execute(
                                    "SELECT state, cancel_requested, lease_token FROM jobs WHERE id=?",
                                    (claimed.id,),
                                ).fetchone()
                                if not r_chk or r_chk["state"] != "RUNNING" or r_chk["lease_token"] != claimed.lease_token or r_chk["cancel_requested"]:
                                    _trigger_abort()
                                    raise SourceCancelledError("Discovery request cancelled.")
                                wait_slice = min(hb_interval, max(0.005, attempt_deadline_m - now_m), 0.05)
                                done_evt.wait(timeout=wait_slice)
                            if "exc" in res_box:
                                raise res_box["exc"]  # type: ignore[misc]
                            batch = res_box["batch"]  # type: ignore[assignment]
                        finally:
                            _trigger_abort()
                            src_thread.join(timeout=0.05)
                            if src_thread.is_alive():
                                with _SOURCE_WORKERS_GUARD:
                                    _DETACHED_SOURCE_WORKERS.setdefault(source_key, set()).add(src_thread)
                    else:
                        batch = _invoke_source_discover(
                            source_port,
                            cell_query,
                            max_elements=per_query_cap,
                            on_wait_tick=_try_isolated_heartbeat,
                            is_cancelled=cancel_flag.is_set,
                            deadline_monotonic=attempt_deadline_m,
                            register_abort=_register_abort,
                            campaign_id=campaign_id,
                        )
                    if monotonic() > attempt_deadline_m:
                        raise DiscoverySourceError("Discovery source result arrived after total attempt deadline.")
                    break
                except AppError as err:
                    _trigger_abort()
                    now = clock()
                    r_canc = db.connection.execute(
                        "SELECT cancel_requested FROM jobs WHERE id=?",
                        (claimed.id,),
                    ).fetchone()
                    if err.code == "OPERATOR_CANCELLED" or (r_canc and r_canc["cancel_requested"]):
                        return _settle_job_and_queries(
                            db,
                            claimed.id,
                            claimed.lease_token,
                            job_state="CANCELLED",
                            error_code="OPERATOR_CANCELLED",
                            query_id=query_id,
                            query_state="CANCELLED",
                            now=now,
                        )
                    transient = err.code in {"SOURCE_UNAVAILABLE", "SOURCE_RATE_LIMIT"}
                    retry_after_sec = getattr(err, "retry_after_seconds", None)
                    rem_age_now = manual_max_age_seconds - (parse_utc(now) - parse_utc(row["created_at"])).total_seconds()
                    if retry_after_sec is not None and retry_after_sec > rem_age_now:
                        transient = False
                    q_row = db.connection.execute(
                        "SELECT attempts FROM discovery_queries WHERE id=?",
                        (query_id,),
                    ).fetchone()
                    can_retry = (
                        transient
                        and q_row is not None
                        and q_row["attempts"] < max_attempts_per_query
                        and rem_age_now > 0
                    )
                    if can_retry:
                        # Revalidate fresh authorization before every retry!
                        if not _check_authorization(authorize_dispatch, claimed.payload):
                            return _settle_job_and_queries(
                                db,
                                claimed.id,
                                claimed.lease_token,
                                job_state="INTERRUPTED",
                                error_code="AUTHORIZATION_LOST",
                                query_id=query_id,
                                query_state="FAILED",
                                now=now,
                            )
                        try:
                            heartbeat_job_lease(
                                db,
                                claimed.id,
                                claimed.lease_token,
                                lease_seconds=lease_seconds,
                                now=now,
                            )
                            begin_discovery_attempt(
                                db,
                                query_id,
                                claimed.lease_token,
                                max_attempts=max_attempts_per_query,
                                max_requests_per_day=max_requests_per_day,
                                max_job_requests=max_job_requests,
                                now=now,
                            )
                            continue
                        except (DiscoveryLifecycleError, JobSchedulerError):
                            pass
                    return _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="FAILED",
                        error_code=err.code,
                        query_id=query_id,
                        query_state="FAILED",
                        now=now,
                    )
                finally:
                    _trigger_abort()
                    hb_thread.join(timeout=2.0)

            now = clock()
            r_after = db.connection.execute(
                "SELECT state, cancel_requested, lease_token FROM jobs WHERE id=?",
                (claimed.id,),
            ).fetchone()
            if not r_after or r_after["state"] != "RUNNING" or r_after["lease_token"] != claimed.lease_token or r_after["cancel_requested"]:
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="CANCELLED" if (r_after and r_after["cancel_requested"]) else "INTERRUPTED",
                    error_code="OPERATOR_CANCELLED" if (r_after and r_after["cancel_requested"]) else "LEASE_EXPIRED",
                    query_id=query_id,
                    query_state="CANCELLED" if (r_after and r_after["cancel_requested"]) else "FAILED",
                    now=now,
                )
            # Revalidate authorization before committing query results.
            if not _check_authorization(authorize_dispatch, claimed.payload):
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="AUTHORIZATION_LOST",
                    query_id=query_id,
                    query_state="FAILED",
                    now=now,
                )

            heartbeat_job_lease(
                db,
                claimed.id,
                claimed.lease_token,
                lease_seconds=lease_seconds,
                now=now,
            )

            counts = {"seen": 0, "new": 0, "existing": 0, "ambiguous": 0, "invalid": 0}
            seen_candidates = set()
            for obs in batch.observations[:per_query_cap]:
                res = resolve(
                    db,
                    query_id,
                    obs,
                    claimed.lease_token,
                    now=now,
                    similarity_threshold=similarity_threshold,
                )
                if res.candidate_id in seen_candidates:
                    continue
                seen_candidates.add(res.candidate_id)
                counts["seen"] += 1
                counts[res.state.lower()] += 1

            finish_discovery_query(
                db,
                query_id,
                claimed.lease_token,
                outcome="PARTIAL" if batch.partial else "SUCCEEDED",
                result_count=counts["seen"],
                exhausted_cell=(not batch.partial and counts["seen"] == 0),
                now=now,
            )
            current_query_id = None
            with db.transaction() as c:
                current = c.execute(
                    "SELECT state, cancel_requested, lease_expires_at, progress_json FROM jobs WHERE id=? AND lease_token=?",
                    (claimed.id, claimed.lease_token),
                ).fetchone()
                if (
                    not current
                    or current["state"] != "RUNNING"
                    or current["lease_expires_at"] <= now
                    or current["cancel_requested"]
                ):
                    raise JobSchedulerError("Discovery worker lost its job lease before progress commit.")
                progress = json.loads(current["progress_json"] or "{}")
                for k, delta in counts.items():
                    progress[k] = int(progress.get(k, 0)) + delta
                progress["phase"] = "RUNNING"
                c.execute(
                    "UPDATE jobs SET progress_json=?, updated_at=? WHERE id=?",
                    (encoded(progress), now, claimed.id),
                )

            # Acknowledge durable source checkpoint ONLY after candidate/registry results and
            # query/job progress are durably committed in mi_boti.sqlite3 under valid authorization and lease ownership.
            if batch.checkpoint_token is not None:
                now = clock()
                r_ack = db.connection.execute(
                    "SELECT state, cancel_requested, lease_token, lease_expires_at FROM jobs WHERE id=?",
                    (claimed.id,),
                ).fetchone()
                if (
                    not r_ack
                    or r_ack["state"] != "RUNNING"
                    or r_ack["lease_token"] != claimed.lease_token
                    or r_ack["lease_expires_at"] <= now
                    or r_ack["cancel_requested"]
                ):
                    return _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="CANCELLED" if (r_ack and r_ack["cancel_requested"]) else "INTERRUPTED",
                        error_code="OPERATOR_CANCELLED" if (r_ack and r_ack["cancel_requested"]) else "LEASE_EXPIRED",
                        now=now,
                    )
                if not _check_authorization(authorize_dispatch, claimed.payload):
                    return _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="INTERRUPTED",
                        error_code="AUTHORIZATION_LOST",
                        now=now,
                    )
                if on_before_cursor_ack is not None:
                    on_before_cursor_ack(dict(batch.checkpoint_token))
                _acknowledge_source_checkpoint(source_port, batch, now=now)

        now = clock()
        if not _check_authorization(authorize_dispatch, claimed.payload):
            return _settle_job_and_queries(
                db,
                claimed.id,
                claimed.lease_token,
                job_state="INTERRUPTED",
                error_code="AUTHORIZATION_LOST",
                now=now,
            )
        with db.transaction() as c:
            current = c.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone()
            if (
                not current
                or current["state"] != "RUNNING"
                or current["lease_token"] != claimed.lease_token
                or current["lease_expires_at"] <= now
            ):
                return _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="LEASE_EXPIRED",
                    now=now,
                )
            progress = json.loads(current["progress_json"] or "{}")
            progress["phase"] = "COMPLETED"
            c.execute(
                "UPDATE jobs SET state='SUCCEEDED', progress_json=?, lease_token=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
                (encoded(progress), now, claimed.id),
            )
            return dict(c.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone())
    except BaseException as exc:
        now = clock()
        r_canc = db.connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (claimed.id,)).fetchone()
        if (r_canc and r_canc["cancel_requested"]) or (isinstance(exc, AppError) and exc.code == "OPERATOR_CANCELLED"):
            job_state = "CANCELLED"
            err_code = "OPERATOR_CANCELLED"
        else:
            err_code = exc.code if isinstance(exc, AppError) else "CRITICAL_ERROR"
            job_state = (
                "INTERRUPTED"
                if isinstance(exc, (DiscoveryLifecycleError, JobSchedulerError)) or err_code in {"LEASE_EXPIRED", "AUTHORIZATION_LOST"}
                else "FAILED"
            )
        return _settle_job_and_queries(
            db,
            claimed.id,
            claimed.lease_token,
            job_state=job_state,
            error_code=err_code,
            query_id=current_query_id,
            query_state="CANCELLED" if job_state == "CANCELLED" else "FAILED",
            now=now,
        )


async def execute_manual_discovery_job_async(
    async_db,
    claimed: ClaimedJob,
    source_port: DiscoverySourcePort,
    *,
    authorize_dispatch: Callable[[dict], object] | None = None,
    lease_seconds: int = 30,
    heartbeat_seconds: float | None = None,
    request_timeout_seconds: float = 20.0,
    max_job_requests: int = 20,
    max_requests_per_day: int = 100,
    max_attempts_per_query: int = 3,
    manual_max_age_seconds: int = 3600,
    coverage_ttl_seconds: int = 2592000,
    similarity_threshold: float = 0.85,
    clock: Callable[[], str] = utc_now,
    monotonic: Callable[[], float] = time.monotonic,
    on_before_cursor_ack: Callable[[dict], None] | None = None,
) -> dict:
    """Execute a claimed manual DISCOVER job asynchronously without blocking the SQLite executor."""
    current_query_id: str | None = None
    hb_interval = (
        float(heartbeat_seconds)
        if heartbeat_seconds is not None
        else max(0.05, min(10.0, float(lease_seconds) / 3.0))
    )
    per_attempt_timeout = _effective_attempt_timeout(source_port, request_timeout_seconds)

    async def _check_auth() -> bool:
        if authorize_dispatch is None:
            return True
        try:
            res = authorize_dispatch(dict(claimed.payload))
            if inspect.isawaitable(res):
                res = await res
            return bool(res)
        except Exception:
            return False

    try:
        now = clock()
        if not await _check_auth():
            return await async_db.call(
                lambda db: _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="AUTHORIZATION_LOST",
                    now=now,
                )
            )

        campaign_id = claimed.payload["campaign_id"]
        campaign_version = int(claimed.payload["campaign_version"])
        observation_limit = int(claimed.payload.get("options", {}).get("limit", 25))
        planned_cells = await async_db.call(
            lambda db: plan_unexhausted_queries(
                db,
                campaign_id,
                campaign_version=campaign_version,
                source=source_port.source_namespace,
                policy_version=source_port.policy_version,
                limit=observation_limit,
                coverage_ttl_seconds=coverage_ttl_seconds,
                now=now,
            )
        )

        for planned in planned_cells:
            now = clock()
            row = await async_db.call(
                lambda db: dict(r)
                if (r := db.connection.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone())
                else None
            )
            if (
                not row
                or row["state"] != "RUNNING"
                or row["lease_token"] != claimed.lease_token
                or row["lease_expires_at"] <= now
            ):
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="INTERRUPTED",
                        error_code="LEASE_EXPIRED",
                        now=now,
                    )
                )
            if row["cancel_requested"]:
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="CANCELLED",
                        error_code="OPERATOR_CANCELLED",
                        query_state="CANCELLED",
                        now=now,
                    )
                )
            if (parse_utc(now) - parse_utc(row["created_at"])).total_seconds() > manual_max_age_seconds:
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="FAILED",
                        error_code="SAFETY_LIMIT",
                        now=now,
                    )
                )

            if not await _check_auth():
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="INTERRUPTED",
                        error_code="AUTHORIZATION_LOST",
                        now=now,
                    )
                )

            await async_db.call(
                lambda db: heartbeat_job_lease(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    lease_seconds=lease_seconds,
                    now=now,
                )
            )

            progress = json.loads(row["progress_json"] or "{}")
            remaining_observations = observation_limit - int(progress.get("seen", 0))
            if remaining_observations <= 0:
                break
            per_query_cap = min(planned.spec.limit, remaining_observations)
            cell_query = PlannedCellQuery(
                geographic_cell=planned.geographic_cell,
                spec=type(planned.spec)(
                    bbox=planned.spec.bbox,
                    categories=planned.spec.categories,
                    limit=per_query_cap,
                    target_version=planned.spec.target_version,
                    policy_version=planned.spec.policy_version,
                ),
            )
            query_id = await async_db.call(
                lambda db: queue_discovery_query(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    campaign_id,
                    cell_query,
                    source=source_port.source_namespace,
                    now=now,
                )
            )
            current_query_id = query_id
            try:
                await async_db.call(
                    lambda db: begin_discovery_attempt(
                        db,
                        query_id,
                        claimed.lease_token,
                        max_attempts=max_attempts_per_query,
                        max_requests_per_day=max_requests_per_day,
                        max_job_requests=max_job_requests,
                        now=now,
                    )
                )
            except DiscoveryLifecycleError:
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="FAILED",
                        error_code="SAFETY_LIMIT",
                        query_id=query_id,
                        query_state="FAILED",
                        now=now,
                    )
                )

            batch = None
            while True:
                now = clock()
                rem_age = max(0.0, manual_max_age_seconds - (parse_utc(now) - parse_utc(row["created_at"])).total_seconds())
                job_deadline_m = monotonic() + rem_age
                attempt_deadline_m = min(job_deadline_m, monotonic() + per_attempt_timeout)

                cancel_flag = threading.Event()
                abort_callbacks: list[Callable[[], None]] = []
                abort_lock = threading.Lock()

                def _register_abort(cb: Callable[[], None]) -> None:
                    with abort_lock:
                        abort_callbacks.append(cb)

                def _trigger_abort() -> None:
                    cancel_flag.set()
                    with abort_lock:
                        cbs = list(abort_callbacks)
                    for cb in cbs:
                        try:
                            cb()
                        except Exception:
                            pass

                async def _async_hb_loop():
                    while not cancel_flag.is_set():
                        await asyncio.sleep(hb_interval)
                        if cancel_flag.is_set():
                            break
                        if monotonic() >= attempt_deadline_m:
                            _trigger_abort()
                            break
                        try:
                            def _hb_and_check(db):
                                r = db.connection.execute(
                                    "SELECT state, cancel_requested, lease_token FROM jobs WHERE id=?",
                                    (claimed.id,),
                                ).fetchone()
                                if not r or r["state"] != "RUNNING" or r["lease_token"] != claimed.lease_token or r["cancel_requested"]:
                                    return True
                                heartbeat_job_lease(
                                    db,
                                    claimed.id,
                                    claimed.lease_token,
                                    lease_seconds=lease_seconds,
                                    now=clock(),
                                )
                                return False
                            if await async_db.call(_hb_and_check):
                                _trigger_abort()
                                break
                        except AppError:
                            _trigger_abort()
                            break

                hb_task = asyncio.create_task(_async_hb_loop())
                loop = asyncio.get_running_loop()
                caught_err: AppError | None = None
                src_thread: threading.Thread | None = None
                source_key: str | None = None
                try:
                    source_key = _acquire_source_worker_admission(source_port)
                    fut = loop.create_future()

                    def _async_src_worker() -> None:
                        cur = threading.current_thread()
                        try:
                            res = _invoke_source_discover(
                                source_port,
                                cell_query,
                                max_elements=per_query_cap,
                                on_wait_tick=lambda: None,
                                is_cancelled=cancel_flag.is_set,
                                deadline_monotonic=attempt_deadline_m,
                                register_abort=_register_abort,
                                campaign_id=campaign_id,
                            )
                            if not loop.is_closed():
                                loop.call_soon_threadsafe(
                                    lambda r=res: fut.set_result(r) if not fut.done() else None
                                )
                        except BaseException as exc:
                            if not loop.is_closed():
                                loop.call_soon_threadsafe(
                                    lambda e=exc: fut.set_exception(e) if not fut.done() else None
                                )
                        finally:
                            with _SOURCE_WORKERS_GUARD:
                                if source_key is not None:
                                    act = _ACTIVE_SOURCE_WORKERS.get(source_key)
                                    if act is not None:
                                        act.discard(cur)
                                        if not act:
                                            _ACTIVE_SOURCE_WORKERS.pop(source_key, None)
                                    det = _DETACHED_SOURCE_WORKERS.get(source_key)
                                    if det is not None:
                                        det.discard(cur)
                                        if not det:
                                            _DETACHED_SOURCE_WORKERS.pop(source_key, None)

                    src_thread = threading.Thread(
                        target=_async_src_worker,
                        name=f"mi-boti-asrc-{claimed.id[:8]}",
                        daemon=True,
                    )
                    with _SOURCE_WORKERS_GUARD:
                        _ACTIVE_SOURCE_WORKERS.setdefault(source_key, set()).add(src_thread)
                    src_thread.start()

                    rem_wait = max(0.01, attempt_deadline_m - monotonic())
                    batch = await asyncio.wait_for(asyncio.shield(fut), timeout=rem_wait)
                    if monotonic() > attempt_deadline_m:
                        raise DiscoverySourceError("Discovery source result arrived after total attempt deadline.")
                    break
                except asyncio.TimeoutError:
                    _trigger_abort()
                    caught_err = DiscoverySourceError("Discovery source request timed out.")
                except asyncio.CancelledError:
                    _trigger_abort()
                    raise
                except AppError as err:
                    _trigger_abort()
                    caught_err = err
                finally:
                    _trigger_abort()
                    hb_task.cancel()
                    await asyncio.gather(hb_task, return_exceptions=True)
                    if src_thread is not None and source_key is not None:
                        src_thread.join(timeout=0.05)
                        if src_thread.is_alive():
                            with _SOURCE_WORKERS_GUARD:
                                _DETACHED_SOURCE_WORKERS.setdefault(source_key, set()).add(src_thread)

                if caught_err is not None:
                    now = clock()
                    is_canc = await async_db.call(
                        lambda db: bool(
                            (r := db.connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (claimed.id,)).fetchone())
                            and r["cancel_requested"]
                        )
                    )
                    if caught_err.code == "OPERATOR_CANCELLED" or is_canc:
                        return await async_db.call(
                            lambda db: _settle_job_and_queries(
                                db,
                                claimed.id,
                                claimed.lease_token,
                                job_state="CANCELLED",
                                error_code="OPERATOR_CANCELLED",
                                query_id=query_id,
                                query_state="CANCELLED",
                                now=now,
                            )
                        )
                    transient = caught_err.code in {"SOURCE_UNAVAILABLE", "SOURCE_RATE_LIMIT"}
                    retry_after_sec = getattr(caught_err, "retry_after_seconds", None)
                    rem_age_now = manual_max_age_seconds - (parse_utc(now) - parse_utc(row["created_at"])).total_seconds()
                    if retry_after_sec is not None and retry_after_sec > rem_age_now:
                        transient = False
                    attempts_used = await async_db.call(
                        lambda db: (
                            r["attempts"]
                            if (r := db.connection.execute("SELECT attempts FROM discovery_queries WHERE id=?", (query_id,)).fetchone())
                            else max_attempts_per_query
                        )
                    )
                    can_retry = transient and attempts_used < max_attempts_per_query and rem_age_now > 0
                    if can_retry:
                        if not await _check_auth():
                            return await async_db.call(
                                lambda db: _settle_job_and_queries(
                                    db,
                                    claimed.id,
                                    claimed.lease_token,
                                    job_state="INTERRUPTED",
                                    error_code="AUTHORIZATION_LOST",
                                    query_id=query_id,
                                    query_state="FAILED",
                                    now=now,
                                )
                            )
                        try:
                            await async_db.call(
                                lambda db: (
                                    heartbeat_job_lease(
                                        db,
                                        claimed.id,
                                        claimed.lease_token,
                                        lease_seconds=lease_seconds,
                                        now=now,
                                    ),
                                    begin_discovery_attempt(
                                        db,
                                        query_id,
                                        claimed.lease_token,
                                        max_attempts=max_attempts_per_query,
                                        max_requests_per_day=max_requests_per_day,
                                        max_job_requests=max_job_requests,
                                        now=now,
                                    ),
                                )
                            )
                            continue
                        except (DiscoveryLifecycleError, JobSchedulerError):
                            pass
                    return await async_db.call(
                        lambda db: _settle_job_and_queries(
                            db,
                            claimed.id,
                            claimed.lease_token,
                            job_state="FAILED",
                            error_code=caught_err.code,
                            query_id=query_id,
                            query_state="FAILED",
                            now=now,
                        )
                    )

            now = clock()
            is_canc = await async_db.call(
                lambda db: bool(
                    (r := db.connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (claimed.id,)).fetchone())
                    and r["cancel_requested"]
                )
            )
            if is_canc:
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="CANCELLED",
                        error_code="OPERATOR_CANCELLED",
                        query_id=query_id,
                        query_state="CANCELLED",
                        now=now,
                    )
                )
            if not await _check_auth():
                return await async_db.call(
                    lambda db: _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="INTERRUPTED",
                        error_code="AUTHORIZATION_LOST",
                        query_id=query_id,
                        query_state="FAILED",
                        now=now,
                    )
                )

            def _commit_batch(db):
                heartbeat_job_lease(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    lease_seconds=lease_seconds,
                    now=now,
                )
                counts = {"seen": 0, "new": 0, "existing": 0, "ambiguous": 0, "invalid": 0}
                seen_candidates = set()
                for obs in batch.observations[:per_query_cap]:
                    res = resolve(
                        db,
                        query_id,
                        obs,
                        claimed.lease_token,
                        now=now,
                        similarity_threshold=similarity_threshold,
                    )
                    if res.candidate_id in seen_candidates:
                        continue
                    seen_candidates.add(res.candidate_id)
                    counts["seen"] += 1
                    counts[res.state.lower()] += 1
                finish_discovery_query(
                    db,
                    query_id,
                    claimed.lease_token,
                    outcome="PARTIAL" if batch.partial else "SUCCEEDED",
                    result_count=counts["seen"],
                    exhausted_cell=(not batch.partial and counts["seen"] == 0),
                    now=now,
                )
                with db.transaction() as c:
                    current = c.execute(
                        "SELECT state, cancel_requested, lease_expires_at, progress_json FROM jobs WHERE id=? AND lease_token=?",
                        (claimed.id, claimed.lease_token),
                    ).fetchone()
                    if (
                        not current
                        or current["state"] != "RUNNING"
                        or current["lease_expires_at"] <= now
                        or current["cancel_requested"]
                    ):
                        raise JobSchedulerError("Discovery worker lost its job lease before progress commit.")
                    progress = json.loads(current["progress_json"] or "{}")
                    for k, delta in counts.items():
                        progress[k] = int(progress.get(k, 0)) + delta
                    progress["phase"] = "RUNNING"
                    c.execute(
                        "UPDATE jobs SET progress_json=?, updated_at=? WHERE id=?",
                        (encoded(progress), now, claimed.id),
                    )

            await async_db.call(_commit_batch)
            current_query_id = None

            if batch.checkpoint_token is not None:
                now = clock()
                ack_status = await async_db.call(
                    lambda db: dict(r)
                    if (
                        r := db.connection.execute(
                            "SELECT state, cancel_requested, lease_token, lease_expires_at FROM jobs WHERE id=?",
                            (claimed.id,),
                        ).fetchone()
                    )
                    else None
                )
                if (
                    not ack_status
                    or ack_status["state"] != "RUNNING"
                    or ack_status["lease_token"] != claimed.lease_token
                    or ack_status["lease_expires_at"] <= now
                    or ack_status["cancel_requested"]
                ):
                    return await async_db.call(
                        lambda db: _settle_job_and_queries(
                            db,
                            claimed.id,
                            claimed.lease_token,
                            job_state="CANCELLED" if (ack_status and ack_status["cancel_requested"]) else "INTERRUPTED",
                            error_code="OPERATOR_CANCELLED" if (ack_status and ack_status["cancel_requested"]) else "LEASE_EXPIRED",
                            now=now,
                        )
                    )
                if not await _check_auth():
                    return await async_db.call(
                        lambda db: _settle_job_and_queries(
                            db,
                            claimed.id,
                            claimed.lease_token,
                            job_state="INTERRUPTED",
                            error_code="AUTHORIZATION_LOST",
                            now=now,
                        )
                    )
                if on_before_cursor_ack is not None:
                    on_before_cursor_ack(dict(batch.checkpoint_token))
                await asyncio.to_thread(_acknowledge_source_checkpoint, source_port, batch, now=now)

        now = clock()
        if not await _check_auth():
            return await async_db.call(
                lambda db: _settle_job_and_queries(
                    db,
                    claimed.id,
                    claimed.lease_token,
                    job_state="INTERRUPTED",
                    error_code="AUTHORIZATION_LOST",
                    now=now,
                )
            )

        def _complete_job(db):
            with db.transaction() as c:
                current = c.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone()
                if (
                    not current
                    or current["state"] != "RUNNING"
                    or current["lease_token"] != claimed.lease_token
                    or current["lease_expires_at"] <= now
                ):
                    return _settle_job_and_queries(
                        db,
                        claimed.id,
                        claimed.lease_token,
                        job_state="INTERRUPTED",
                        error_code="LEASE_EXPIRED",
                        now=now,
                    )
                progress = json.loads(current["progress_json"] or "{}")
                progress["phase"] = "COMPLETED"
                c.execute(
                    "UPDATE jobs SET state='SUCCEEDED', progress_json=?, lease_token=NULL, lease_expires_at=NULL, updated_at=? WHERE id=?",
                    (encoded(progress), now, claimed.id),
                )
                return dict(c.execute("SELECT * FROM jobs WHERE id=?", (claimed.id,)).fetchone())

        return await async_db.call(_complete_job)
    except asyncio.CancelledError:
        now = clock()
        await async_db.call(
            lambda db: _settle_job_and_queries(
                db,
                claimed.id,
                claimed.lease_token,
                job_state="INTERRUPTED",
                error_code="RESTART_INTERRUPTION",
                query_id=current_query_id,
                query_state="FAILED",
                now=now,
            )
        )
        raise
    except BaseException as exc:
        now = clock()
        is_canc = await async_db.call(
            lambda db: bool(
                (r := db.connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (claimed.id,)).fetchone())
                and r["cancel_requested"]
            )
        )
        if is_canc or (isinstance(exc, AppError) and exc.code == "OPERATOR_CANCELLED"):
            job_state = "CANCELLED"
            err_code = "OPERATOR_CANCELLED"
        else:
            err_code = exc.code if isinstance(exc, AppError) else "CRITICAL_ERROR"
            job_state = (
                "INTERRUPTED"
                if isinstance(exc, (DiscoveryLifecycleError, JobSchedulerError)) or err_code in {"LEASE_EXPIRED", "AUTHORIZATION_LOST"}
                else "FAILED"
            )
        return await async_db.call(
            lambda db: _settle_job_and_queries(
                db,
                claimed.id,
                claimed.lease_token,
                job_state=job_state,
                error_code=err_code,
                query_id=current_query_id,
                query_state="CANCELLED" if job_state == "CANCELLED" else "FAILED",
                now=now,
            )
        )
