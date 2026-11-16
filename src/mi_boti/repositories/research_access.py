"""Versioned, named website-access reviews in the singleton's settings JSON."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from ..domain.values import snowflake, utc_now
from ..domain.campaigns import validate_rationale
from ..research.collector import AccessReview, ResearchError, safe_url
from .discord import audit


def get_access(db, business_id):
    row = db.connection.execute("SELECT settings_json,revision FROM guild_config WHERE id='guild'").fetchone()
    if not row: raise ResearchError("Server configuration is missing.")
    record = json.loads(row[0]).get("research_access", {}).get(business_id)
    if not record: raise ResearchError("No website-access review exists. Ask an administrator to use /research action:review.")
    review = AccessReview(**record["review"])
    review.validate(datetime.now(timezone.utc))
    safe_url(record["url"])
    return record


def prepare_access(db, business_id, actor_id, url, permission_url, rationale, *, ttl_seconds=604800):
    actor_id = snowflake(actor_id)
    if not db.connection.execute("SELECT 1 FROM businesses WHERE id=?", (business_id,)).fetchone():
        raise ResearchError("Business not found in this deployment.")
    url, host = safe_url(url)
    rationale = validate_rationale(rationale)
    stamp = datetime.now(timezone.utc)
    review = AccessReview(host, safe_url(permission_url)[0], str(uuid4()), actor_id,
                          (stamp + timedelta(seconds=min(ttl_seconds, 604800))).isoformat())
    review.validate(stamp)
    row = db.connection.execute("SELECT revision FROM guild_config WHERE id='guild'").fetchone()
    if not row: raise ResearchError("Server setup must be completed before reviewing website access.")
    return {"business_id": business_id, "url": url, "review": asdict(review), "rationale": rationale,
            "reviewed_at": utc_now(), "expected_config_revision": row[0]}


def save_access(db, proposal, actor_id):
    actor_id = snowflake(actor_id)
    if proposal["review"]["reviewer_id"] != actor_id:
        raise ResearchError("Website-access review belongs to another administrator.")
    AccessReview(**proposal["review"]).validate(datetime.now(timezone.utc))
    with db.transaction() as c:
        row = c.execute("SELECT settings_json,revision FROM guild_config WHERE id='guild'").fetchone()
        if row[1] != proposal["expected_config_revision"]:
            raise ResearchError("Configuration changed; request a new access-review preview.")
        settings = json.loads(row[0])
        records = settings.setdefault("research_access", {})
        if proposal["business_id"] not in records and len(records) >= 64:
            raise ResearchError("The initial release permits at most 64 reviewed business websites. Revoke an unused review first.")
        records[proposal["business_id"]] = {key: value for key, value in proposal.items() if key != "expected_config_revision"}
        c.execute("UPDATE guild_config SET settings_json=?,revision=revision+1,updated_at=? WHERE id='guild'",
                  (json.dumps(settings), utc_now()))
        audit(c, actor_id, "research.access_reviewed", "SUCCESS", proposal["business_id"],
              {"review": proposal["review"], "url": proposal["url"], "rationale": proposal["rationale"], "reviewed_at": proposal["reviewed_at"]})


def revoke_access(db, business_id, actor_id):
    with db.transaction() as c:
        row = c.execute("SELECT settings_json FROM guild_config WHERE id='guild'").fetchone()
        settings = json.loads(row[0])
        settings.get("research_access", {}).pop(business_id, None)
        c.execute("UPDATE guild_config SET settings_json=?,revision=revision+1,updated_at=? WHERE id='guild'",
                  (json.dumps(settings), utc_now()))
        audit(c, snowflake(actor_id), "research.access_revoked", "SUCCESS", business_id)
