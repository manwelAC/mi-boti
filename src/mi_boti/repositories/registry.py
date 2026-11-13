"""Transactional global identity reservations; no network, AI or quota writes."""

from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4

from ..domain.registry import RegistryError, normalize, encoded, name_similarity, address_conflict
from ..domain.values import utc_now


@dataclass(frozen=True)
class Resolution:
    candidate_id: str
    state: str
    business_id: str | None
    review_id: str | None = None


def _lease(connection, query_id, lease_token, now):
    query = connection.execute("SELECT * FROM discovery_queries WHERE id=?", (query_id,)).fetchone()
    job = connection.execute("SELECT * FROM jobs WHERE id=?", (query["job_id"],)).fetchone() if query else None
    if (not query or not job or query["state"] != "RUNNING" or job["kind"] != "DISCOVER"
            or job["state"] != "RUNNING" or not lease_token or job["lease_token"] != lease_token
            or not job["lease_expires_at"] or job["lease_expires_at"] <= now or job["cancel_requested"]
            or query["hunt_id"] != job["hunt_id"] or query["attempts"] < 1):
        raise RegistryError("Discovery results require a current, uncancelled job lease and running query.")
    if job["hunt_id"]:
        hunt = connection.execute("SELECT state,campaign_id FROM hunts WHERE id=?", (job["hunt_id"],)).fetchone()
        if not hunt or hunt[0] != "RUNNING" or hunt[1] != query["campaign_id"]:
            raise RegistryError("Hunt no longer admits discovery results.")
    return query, job


def _remember(connection, business_id, identity, now):
    for kind, namespace, value, strength in identity.identifiers:
        connection.execute("INSERT OR IGNORE INTO business_identifiers VALUES (?,?,?,?,?,?,?)",
                           (str(uuid4()), business_id, kind, namespace, value, strength, now))
    for claim in identity.claims:
        existing = connection.execute("SELECT business_id FROM identity_claims WHERE claim_key=?", (claim,)).fetchone()
        if existing and existing[0] != business_id:
            raise RegistryError("Strong identity ownership changed; result was not committed.")
        connection.execute("INSERT OR IGNORE INTO identity_claims VALUES (?,?,?)", (claim, business_id, now))


def resolve(db, query_id, observation, lease_token, *, now=None, similarity_threshold=0.85):
    """Call from a currently authorized discovery worker. Origin ownership is immutable.

    BEGIN IMMEDIATE serializes signal rechecks and claims across SQLite connections.
    Same observations replay idempotently; all dispositions participate in lookup.
    """
    now = now or utc_now()
    if not isinstance(observation, dict) or not 0 < similarity_threshold <= 1:
        raise RegistryError("Invalid bounded registry input.")
    try:
        raw = encoded(observation)
    except (ValueError, TypeError):
        raise RegistryError("Observation is not valid JSON.") from None
    if len(raw.encode("utf-8")) > 65536:
        raise RegistryError("Observation exceeds the registry payload limit.")
    fingerprint = hashlib.sha256(encoded({k: v for k, v in observation.items() if k != "observed_at"}).encode()).hexdigest()
    try:
        identity = normalize(observation)
        invalid = False
    except RegistryError:
        identity, invalid = None, True
    with db.transaction() as connection:
        query, job = _lease(connection, query_id, lease_token, now)
        if not invalid and query["policy_version"] != observation["policy_version"]:
            raise RegistryError("Observation does not match the reserved source policy version.")
        if not invalid and query["source"] != observation["source_namespace"]:
            raise RegistryError("Observation does not match the reserved source namespace.")
        prior = connection.execute("SELECT * FROM candidates WHERE query_id=? AND observation_key=?", (query_id, fingerprint)).fetchone()
        if prior:
            details = json.loads(prior["resolution_json"] or "{}")
            return Resolution(prior["id"], prior["state"], prior["business_id"], details.get("review_id"))
        candidate_id, business_id, review_id = str(uuid4()), None, None
        details = {"schema_version": 1}
        if invalid:
            state = "INVALID"
            details["reason"] = "INVALID_NAME_OR_PROVENANCE"
        else:
            pending = connection.execute("SELECT r.id FROM identity_reviews r JOIN candidates c ON c.id=r.candidate_id WHERE c.observation_key=? AND r.state='OPEN' LIMIT 1", (fingerprint,)).fetchone()
            matches, strong = {}, set()
            for claim in identity.claims:
                for row in connection.execute("SELECT b.* FROM identity_claims i JOIN businesses b ON b.id=i.business_id WHERE i.claim_key=?", (claim,)):
                    matches[row["id"]] = row
                    strong.add(row["id"])
            for kind, namespace, value, _ in identity.identifiers:
                if kind == "SOURCE":
                    continue
                for row in connection.execute("SELECT b.* FROM business_identifiers i JOIN businesses b ON b.id=i.business_id WHERE i.kind=? AND i.namespace=? AND i.value=?", (kind, namespace, value)):
                    if name_similarity(identity.name, row["normalized_name"]) >= similarity_threshold:
                        matches[row["id"]] = row
            if identity.address:
                for row in connection.execute("SELECT * FROM businesses WHERE normalized_address=?", (identity.address,)):
                    if name_similarity(identity.name, row["normalized_name"]) >= similarity_threshold:
                        matches[row["id"]] = row
            for row in connection.execute("SELECT * FROM businesses WHERE normalized_name=?", (identity.name,)):
                # Explicit branches at distinct full addresses may share brand signals.
                distinct_branch = (observation.get("entity_kind") == "BRANCH" and row["entity_kind"] == "BRANCH"
                                   and identity.address and row["normalized_address"]
                                   and all(json.loads(identity.address).get(k) and json.loads(row["normalized_address"]).get(k)
                                           for k in ("country", "city", "street", "house_number"))
                                   and address_conflict(identity.address, row["normalized_address"]))
                if distinct_branch and row["id"] not in strong:
                    matches.pop(row["id"], None)
                else:
                    matches[row["id"]] = row
            if pending:
                state, review_id = "AMBIGUOUS", pending[0]
                details.update(reason="PRIOR_UNRESOLVED_IDENTITY", review_id=review_id)
            elif len(strong) == 1 and set(matches) == strong:
                row = matches[next(iter(strong))]
                if (address_conflict(identity.address, row["normalized_address"])
                        or name_similarity(identity.name, row["normalized_name"]) < similarity_threshold
                        or observation.get("entity_kind", "BUSINESS") != row["entity_kind"]):
                    state = "AMBIGUOUS"
                else:
                    state, business_id = "EXISTING", row["id"]
            elif matches:
                state = "AMBIGUOUS"
            else:
                state, business_id = "NEW", str(uuid4())
                connection.execute("INSERT INTO businesses(id,name,normalized_name,address_json,normalized_address,country_code,entity_kind,disposition,origin_job_id,origin_hunt_id,created_at,updated_at,revision) VALUES (?,?,?,?,?,?,?,'PENDING',?,?,?,?,1)",
                    (business_id, observation["name"], identity.name, encoded(observation.get("address", {})), identity.address,
                     identity.country, observation.get("entity_kind", "BUSINESS"), job["id"], job["hunt_id"], now, now))
            if state == "AMBIGUOUS" and not review_id:
                review_id = str(uuid4())
                details.update(reason="IDENTITY_REVIEW_REQUIRED", review_id=review_id)
            if business_id:
                _remember(connection, business_id, identity, now)
        connection.execute("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?)", (candidate_id, query_id, fingerprint, raw, state, business_id, encoded(details), now))
        if state == "AMBIGUOUS" and not pending:
            connection.execute("INSERT INTO identity_reviews VALUES (?,?,?,'OPEN',NULL,NULL,NULL)", (review_id, candidate_id, encoded(sorted(matches))))
        if business_id:
            connection.execute("INSERT INTO business_events VALUES (?,?,?,?,?,?)", (str(uuid4()), business_id, job["actor_id"], "discovery.observed",
                encoded({"candidate_id": candidate_id, "query_id": query_id, "state": state, "source_url": observation["source_url"], "source_identifier": observation["source_namespace"]+":"+observation["source_id"], "observed_at": observation["observed_at"], "policy_version": observation["policy_version"], "attribution": observation["attribution"]}), now))
        return Resolution(candidate_id, state, business_id, review_id)
