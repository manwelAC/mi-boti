"""Explicit manual research admission and bounded async execution; no AI path."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import time
from uuid import uuid4

from ..domain.values import snowflake, utc_now
from ..research.collector import AccessReview, ResearchError
from ..repositories import research as evidence
from ..repositories import research_access as access
from ..repositories.discord import audit
from .discovery import heartbeat_job_lease


def enqueue(db, *, business_id, actor_id, guild_id, channel_id, idempotency_key, refresh, analyze=False):
    if analyze is not False: raise ResearchError("AI analysis is disabled. Retry with analyze:false.")
    if refresh is not True: raise ResearchError("Use refresh:true to authorize a new immutable research run.")
    actor_id, guild_id, channel_id = (snowflake(v) for v in (actor_id, guild_id, channel_id))
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 256:
        raise ResearchError("Research needs a valid interaction identity.")
    with db.transaction() as c:
        existing = c.execute("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            if existing["kind"] != "RESEARCH" or existing["business_id"] != business_id or existing["actor_id"] != actor_id:
                raise ResearchError("Interaction identity belongs to another operation.")
            return dict(existing)
        config = c.execute("SELECT guild_id,setup_state FROM guild_config WHERE id='guild'").fetchone()
        if not config or config[0] != guild_id or config[1] != "READY": raise ResearchError("Server configuration is not ready.")
        if not c.execute("SELECT 1 FROM businesses WHERE id=?", (business_id,)).fetchone(): raise ResearchError("Business not found.")
        policy = access.get_access(db, business_id)
        if c.execute("SELECT 1 FROM identity_reviews r,json_each(r.matches_json) m WHERE state='OPEN' AND m.value=?", (business_id,)).fetchone():
            raise ResearchError("Resolve the business identity review before research.")
        if c.execute("SELECT 1 FROM jobs WHERE kind='RESEARCH' AND business_id=? AND state IN ('QUEUED','RUNNING','RETRY_WAIT')", (business_id,)).fetchone():
            raise ResearchError("Research for this business is already queued or running.")
        if c.execute("SELECT count(*) FROM jobs WHERE state IN ('QUEUED','RUNNING','RETRY_WAIT')").fetchone()[0] >= 2:
            raise ResearchError("The background-job slots are busy; retry after current work finishes.")
        job_id, now = str(uuid4()), utc_now()
        payload = {"command_key": "research", "business_id": business_id, "actor_id": actor_id, "guild_id": guild_id,
                   "channel_id": channel_id, "refresh": True, "analyze": False, "policy_version": policy["review"]["policy_version"]}
        c.execute("INSERT INTO jobs(id,kind,payload_json,idempotency_key,business_id,actor_id,state,attempt,max_attempts,progress_json,cancel_requested,created_at,updated_at) "
                  "VALUES (?,'RESEARCH',?,?,?,?,'QUEUED',0,1,'{}',0,?,?)",
                  (job_id, json.dumps(payload), idempotency_key, business_id, actor_id, now, now))
        audit(c, actor_id, "research.enqueued", "SUCCESS", job_id, {"business_id": business_id})
        return dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def claim(db, job_id, *, lease_seconds=30, max_concurrency=2, max_age_seconds=3600):
    now = utc_now()
    with db.transaction() as c:
        job = c.execute("SELECT * FROM jobs WHERE id=? AND kind='RESEARCH' AND state='QUEUED'", (job_id,)).fetchone()
        if not job: return None
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))).total_seconds()
        if age < 0 or age > max_age_seconds or job["cancel_requested"]:
            c.execute("UPDATE jobs SET state=?,updated_at=?,error_code=? WHERE id=?", ("CANCELLED" if job["cancel_requested"] else "FAILED", now, "SAFETY_LIMIT", job_id))
            return None
        if c.execute("SELECT count(*) FROM jobs WHERE state='RUNNING'").fetchone()[0] >= max_concurrency:
            c.execute("UPDATE jobs SET state='FAILED',updated_at=?,error_code='WORKER_BUSY' WHERE id=?", (now, job_id))
            return None
        token = str(uuid4())
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        c.execute("UPDATE jobs SET state='RUNNING',attempt=1,lease_token=?,lease_expires_at=?,updated_at=? WHERE id=?", (token, expiry, now, job_id))
        return dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def current_access(db, job):
    evidence._job(db.connection, job["id"], job["lease_token"], utc_now())
    payload = json.loads(job["payload_json"])
    record = access.get_access(db, job["business_id"])
    if record["review"]["policy_version"] != payload["policy_version"]:
        raise ResearchError("Website-access review changed; start a new research operation.")
    return record


def settle_failure(db, job, state, code):
    with db.transaction() as c:
        owned = c.execute("SELECT state,lease_token FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if not owned or owned[0] != "RUNNING" or owned[1] != job["lease_token"]: return
        now = utc_now()
        c.execute("UPDATE research_runs SET state=?,finished_at=?,limitations_json=? WHERE job_id=? AND state='RUNNING'",
                  (state, now, json.dumps(["Collection stopped safely; inaccessible data remains unknown."]), job["id"]))
        c.execute("UPDATE jobs SET state=?,error_code=?,updated_at=?,lease_token=NULL,lease_expires_at=NULL WHERE id=?", (state, code, now, job["id"]))
        audit(c, job["actor_id"], "research.stopped", state, job["id"], {"code": code})


async def execute(db, job, collector, authorize, *, lease_seconds=30, heartbeat_seconds=10, max_pages=5, max_age_seconds=3600):
    payload = json.loads(job["payload_json"])
    async def check():
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"].replace("Z", "+00:00"))).total_seconds()
        if age < 0 or age >= max_age_seconds: raise ResearchError("Research job age limit reached.")
        if not await authorize(payload): raise ResearchError("Research authorization is no longer valid.")
        await db.call(lambda d: current_access(d, job))
        return True
    collection_task = None
    async def abort():
        if collection_task and not collection_task.done():
            collection_task.cancel()
            await asyncio.gather(collection_task, return_exceptions=True)
    try:
        await check()
        run_id = await db.call(lambda d: evidence.begin_run(d, job["id"], job["lease_token"]))
        record = await db.call(lambda d: current_access(d, job))
        collection_task = asyncio.create_task(collector.collect(record["url"], AccessReview(**record["review"]), max_pages=max_pages, authorize=check))
        last_check = time.monotonic()
        async with asyncio.timeout(min(max_age_seconds, 120)):
            while True:
                done, _ = await asyncio.wait({collection_task}, timeout=min(heartbeat_seconds, 1))
                await db.call(lambda d: current_access(d, job))
                if time.monotonic() - last_check >= heartbeat_seconds:
                    await check()
                    last_check = time.monotonic()
                if done: break
                await db.call(lambda d: heartbeat_job_lease(d, job["id"], job["lease_token"], lease_seconds=lease_seconds))
            result = collection_task.result()
            await check()
            await db.call(lambda d: evidence.finish_run(d, run_id, job["lease_token"], result, settle_job=True))
    except asyncio.CancelledError:
        await abort()
        await db.call(lambda d: settle_failure(d, job, "INTERRUPTED", "SHUTDOWN_INTERRUPTION"))
        raise
    except Exception:
        await abort()
        cancelled = await db.call(lambda d: d.connection.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job["id"],)).fetchone()[0])
        await db.call(lambda d: settle_failure(d, job, "CANCELLED" if cancelled else "FAILED", "OPERATOR_CANCELLED" if cancelled else "RESEARCH_BLOCKED"))
    finally:
        await abort()
    return await db.call(lambda d: dict(d.connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()))
