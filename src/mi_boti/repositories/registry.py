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


def _check_parent_link(connection, business_id: str, parent_id: str | None) -> None:
    if parent_id is None:
        return
    if not isinstance(parent_id, str) or parent_id == business_id:
        raise RegistryError("A business cannot be its own parent.")
    cursor = parent_id
    visited = {business_id}
    depth = 0
    while cursor is not None:
        if cursor in visited or depth > 32:
            raise RegistryError("Parent linkage would create a cycle in the business hierarchy.")
        visited.add(cursor)
        row = connection.execute("SELECT parent_id, entity_kind FROM businesses WHERE id=?", (cursor,)).fetchone()
        if row is None:
            raise RegistryError("Selected parent business does not exist.")
        cursor = row["parent_id"]
        depth += 1


def resolve_identity_review(
    db,
    review_id: str,
    actor_id: str,
    *,
    action: str,
    rationale: str,
    target_business_id: str | None = None,
    expected_business_revision: int | None = None,
    entity_kind: str = "BUSINESS",
    parent_id: str | None = None,
    now: str | None = None,
) -> Resolution:
    """Resolve an OPEN identity review with a named actor and audit rationale.

    Never automatically merges two existing businesses and never creates leads,
    scores, AI tasks or retroactive hunt quota credits.
    """
    from ..domain.campaigns import parse_utc, validate_actor, validate_rationale

    actor = validate_actor(actor_id)
    cleaned_rationale = validate_rationale(rationale)
    stamp = now or utc_now()
    parse_utc(stamp)
    if action not in {"LINK_EXISTING", "CREATE_NEW"}:
        raise RegistryError("Identity review resolution action must be LINK_EXISTING or CREATE_NEW.")
    if entity_kind not in {"BUSINESS", "PARENT", "BRANCH"}:
        raise RegistryError("Business entity kind must be BUSINESS, PARENT or BRANCH.")
    if action == "LINK_EXISTING":
        if not isinstance(target_business_id, str) or not target_business_id.strip():
            raise RegistryError("LINK_EXISTING requires a target_business_id.")
        if type(expected_business_revision) is not int or expected_business_revision < 1:
            raise RegistryError("LINK_EXISTING requires a positive expected_business_revision.")
    elif target_business_id is not None:
        raise RegistryError("CREATE_NEW does not accept a target_business_id.")
    with db.transaction() as connection:
        review = connection.execute("SELECT * FROM identity_reviews WHERE id=?", (review_id,)).fetchone()
        if not review or review["state"] != "OPEN":
            raise RegistryError("Identity review was not found or is already resolved.")
        candidate = connection.execute("SELECT * FROM candidates WHERE id=?", (review["candidate_id"],)).fetchone()
        if not candidate or candidate["state"] != "AMBIGUOUS":
            raise RegistryError("Review candidate is not in AMBIGUOUS state.")
        query = connection.execute("SELECT * FROM discovery_queries WHERE id=?", (candidate["query_id"],)).fetchone()
        observation = json.loads(candidate["observation_json"])
        identity = normalize(observation)
        if action == "LINK_EXISTING":
            target = connection.execute("SELECT * FROM businesses WHERE id=?", (target_business_id,)).fetchone()
            if not target:
                raise RegistryError("Selected target business does not exist.")
            if target["revision"] != expected_business_revision:
                raise RegistryError("Target business revision changed; reload before resolving identity review.")
            if parent_id is not None:
                _check_parent_link(connection, target_business_id, parent_id)
            _remember(connection, target_business_id, identity, stamp)
            next_parent = target["parent_id"] if parent_id is None else parent_id
            connection.execute(
                "UPDATE businesses SET parent_id=?, updated_at=?, revision=revision+1 WHERE id=?",
                (next_parent, stamp, target_business_id),
            )
            business_id = target_business_id
            candidate_state = "RESOLVED_EXISTING"
        else:
            for claim in identity.claims:
                existing = connection.execute("SELECT business_id FROM identity_claims WHERE claim_key=?", (claim,)).fetchone()
                if existing:
                    raise RegistryError("A strong identity claim is already owned by an existing business; use LINK_EXISTING.")
            business_id = str(uuid4())
            if parent_id is not None:
                _check_parent_link(connection, business_id, parent_id)
            connection.execute(
                "INSERT INTO businesses(id,name,normalized_name,address_json,normalized_address,country_code,parent_id,entity_kind,disposition,origin_job_id,origin_hunt_id,created_at,updated_at,revision) "
                "VALUES (?,?,?,?,?,?,?,?,'PENDING',?,?,?,?,1)",
                (
                    business_id,
                    observation["name"],
                    identity.name,
                    encoded(observation.get("address", {})),
                    identity.address,
                    identity.country,
                    parent_id,
                    entity_kind,
                    query["job_id"],
                    query["hunt_id"],
                    stamp,
                    stamp,
                ),
            )
            _remember(connection, business_id, identity, stamp)
            candidate_state = "RESOLVED_NEW"
        resolution_payload = encoded(
            {
                "schema_version": 1,
                "action": action,
                "business_id": business_id,
                "rationale": cleaned_rationale,
            }
        )
        connection.execute(
            "UPDATE identity_reviews SET state='RESOLVED', resolution=?, actor_id=?, resolved_at=? WHERE id=?",
            (resolution_payload, actor, stamp, review_id),
        )
        # Update the primary candidate and any duplicate AMBIGUOUS candidates that reused this review.
        linked_candidates = connection.execute(
            "SELECT id, resolution_json FROM candidates WHERE state='AMBIGUOUS' AND (id=? OR observation_key=?)",
            (candidate["id"], candidate["observation_key"]),
        ).fetchall()
        for row in linked_candidates:
            res = json.loads(row["resolution_json"] or "{}")
            if row["id"] != candidate["id"] and res.get("review_id") != review_id:
                continue
            res.update(
                review_id=review_id,
                resolved_by=actor,
                resolved_at=stamp,
                resolution_action=action,
                rationale=cleaned_rationale,
            )
            connection.execute(
                "UPDATE candidates SET state=?, business_id=?, resolution_json=? WHERE id=?",
                (candidate_state, business_id, encoded(res), row["id"]),
            )
        connection.execute(
            "INSERT INTO business_events VALUES (?,?,?,?,?,?)",
            (
                str(uuid4()),
                business_id,
                actor,
                "identity.review_resolved",
                encoded(
                    {
                        "review_id": review_id,
                        "candidate_id": candidate["id"],
                        "action": action,
                        "state": candidate_state,
                        "rationale": cleaned_rationale,
                        "parent_id": parent_id,
                    }
                ),
                stamp,
            ),
        )
        connection.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(uuid4()),
                actor,
                "identity.review_resolve",
                "identity_review",
                review_id,
                "SUCCESS",
                encoded({"action": action, "business_id": business_id, "candidate_state": candidate_state}),
                stamp,
            ),
        )
        return Resolution(candidate["id"], candidate_state, business_id, review_id)


def link_parent_business(
    db,
    business_id: str,
    parent_id: str | None,
    actor_id: str,
    *,
    expected_revision: int,
    entity_kind: str | None = None,
    rationale: str,
    now: str | None = None,
) -> dict:
    """Transactionally link or clear a parent business with cycle detection and revision checks."""
    from ..domain.campaigns import parse_utc, validate_actor, validate_rationale

    actor = validate_actor(actor_id)
    cleaned_rationale = validate_rationale(rationale)
    stamp = now or utc_now()
    parse_utc(stamp)
    if type(expected_revision) is not int or expected_revision < 1:
        raise RegistryError("Expected business revision must be a positive integer.")
    if entity_kind is not None and entity_kind not in {"BUSINESS", "PARENT", "BRANCH"}:
        raise RegistryError("Business entity kind must be BUSINESS, PARENT or BRANCH.")
    with db.transaction() as connection:
        row = connection.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
        if not row:
            raise RegistryError("Business was not found.")
        if row["revision"] != expected_revision:
            raise RegistryError("Business revision changed; reload the current record before updating hierarchy.")
        _check_parent_link(connection, business_id, parent_id)
        next_kind = entity_kind if entity_kind is not None else ("BRANCH" if parent_id is not None else row["entity_kind"])
        if parent_id is not None:
            parent_row = connection.execute("SELECT * FROM businesses WHERE id=?", (parent_id,)).fetchone()
            if parent_row["entity_kind"] == "BUSINESS":
                connection.execute(
                    "UPDATE businesses SET entity_kind='PARENT', updated_at=?, revision=revision+1 WHERE id=?",
                    (stamp, parent_id),
                )
        connection.execute(
            "UPDATE businesses SET parent_id=?, entity_kind=?, updated_at=?, revision=revision+1 WHERE id=?",
            (parent_id, next_kind, stamp, business_id),
        )
        connection.execute(
            "INSERT INTO business_events VALUES (?,?,?,?,?,?)",
            (
                str(uuid4()),
                business_id,
                actor,
                "identity.hierarchy_updated",
                encoded(
                    {
                        "previous_parent_id": row["parent_id"],
                        "parent_id": parent_id,
                        "entity_kind": next_kind,
                        "rationale": cleaned_rationale,
                    }
                ),
                stamp,
            ),
        )
        connection.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                str(uuid4()),
                actor,
                "identity.hierarchy_update",
                "business",
                business_id,
                "SUCCESS",
                encoded({"parent_id": parent_id, "entity_kind": next_kind}),
                stamp,
            ),
        )
        return dict(connection.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone())
