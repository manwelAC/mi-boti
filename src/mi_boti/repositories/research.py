"""Immutable provider-free evidence checkpoints under an owned RESEARCH lease."""

from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from ..domain.values import utc_now
from ..research.collector import ResearchError, safe_url


def _job(connection, job_id, lease_token, now):
    job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if (not job or job["kind"] != "RESEARCH" or job["state"] != "RUNNING" or job["cancel_requested"]
            or not lease_token or job["lease_token"] != lease_token or not job["lease_expires_at"]
            or job["lease_expires_at"] <= now or job["hunt_id"] is not None):
        raise ResearchError("Research checkpoint requires a current uncancelled manual RESEARCH lease.")
    payload = json.loads(job["payload_json"])
    if payload.get("refresh") is not True or payload.get("analyze", False) is not False:
        raise ResearchError("Manual collection requires explicit refresh and analyze:false.")
    business = connection.execute("SELECT id FROM businesses WHERE id=?", (payload.get("business_id"),)).fetchone()
    if not business:
        raise ResearchError("Research business does not exist.")
    if connection.execute("SELECT 1 FROM identity_reviews r,json_each(r.matches_json) m WHERE r.state='OPEN' AND m.value=?", (business[0],)).fetchone():
        raise ResearchError("Resolve the open identity review before research.")
    return job, payload


def begin_run(db, job_id, lease_token):
    now, run_id = utc_now(), str(uuid4())
    with db.transaction() as c:
        job, payload = _job(c, job_id, lease_token, now)
        existing = c.execute("SELECT id FROM research_runs WHERE job_id=?", (job_id,)).fetchone()
        if existing:
            raise ResearchError("This job already has a research run; explicit refresh needs a new job.")
        c.execute("INSERT INTO research_runs VALUES (?,?,?,'REFRESH','RUNNING',?,NULL,'[]')",
                  (run_id, payload["business_id"], job_id, now))
    return run_id


def finish_run(db, run_id, lease_token, collection):
    if collection.state not in {"SUCCEEDED", "PARTIAL", "FAILED"} or not 0 <= collection.requests <= 32 or len(collection.pages) > 5:
        raise ResearchError("Invalid research result envelope.")
    if (collection.state == "FAILED") == bool(collection.pages):
        raise ResearchError("Research outcome disagrees with available evidence.")
    now = utc_now()
    evidence_ids = []
    with db.transaction() as c:
        run = c.execute("SELECT * FROM research_runs WHERE id=? AND state='RUNNING'", (run_id,)).fetchone()
        if not run: raise ResearchError("Research run is absent or already settled.")
        job, payload = _job(c, run["job_id"], lease_token, now)
        if payload["business_id"] != run["business_id"]: raise ResearchError("Research run business changed.")
        for page in collection.pages:
            safe_url(page.source_url)
            safe_url(page.final_url)
            try:
                observed = datetime.strptime(page.observed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                if observed > datetime.now(timezone.utc): raise ValueError
            except ValueError:
                raise ResearchError("Evidence observation timestamp is invalid.") from None
            if (not page.excerpt.strip() or len(page.excerpt) > 20000 or not page.policy_version
                    or hashlib.sha256(page.excerpt.encode()).hexdigest() != page.excerpt_sha256):
                raise ResearchError("Evidence excerpt or hash is invalid.")
            identifier = str(uuid4())
            limitations = list(page.limitations) + ["Original URL: " + page.source_url, "Excerpt SHA-256: " + page.excerpt_sha256]
            c.execute("INSERT INTO evidence VALUES (?,?,?,NULL,?,NULL,?,?,0.5,?,NULL,?)",
                      (identifier, run["business_id"], run_id, page.final_url, page.observed_at,
                       "Public page excerpt (source assertion): " + page.excerpt, json.dumps(limitations), page.policy_version))
            evidence_ids.append(identifier)
        c.execute("UPDATE research_runs SET state=?,finished_at=?,limitations_json=? WHERE id=?",
                  (collection.state, now, json.dumps(collection.limitations), run_id))
        # Job settlement belongs to the scheduler, after this atomic checkpoint.
    return tuple(evidence_ids)
