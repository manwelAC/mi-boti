"""Offline research invariants shared by backup verification and diagnostics."""

import hashlib
import json
import re

from ..domain.errors import StorageError


def verify_excerpt(fact, raw_limits):
    try:
        limits = json.loads(raw_limits)
    except (ValueError, TypeError):
        raise StorageError("Research evidence limitations are malformed.") from None
    if not isinstance(limits, list): raise StorageError("Research evidence limitations are malformed.")
    markers = [item.removeprefix("Excerpt SHA-256: ") for item in limits if isinstance(item, str) and item.startswith("Excerpt SHA-256: ")]
    if not markers: return False
    prefix = "Public page excerpt (source assertion): "
    if len(markers) != 1 or not re.fullmatch(r"[0-9a-f]{64}", markers[0]) or not fact.startswith(prefix):
        raise StorageError("Research excerpt hash metadata is invalid.")
    if hashlib.sha256(fact.removeprefix(prefix).encode()).hexdigest() != markers[0]:
        raise StorageError("Research excerpt no longer matches its recorded hash.")
    return True


def verify_research_integrity(connection):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"research_runs", "evidence"} <= tables:
        return {"research_runs": 0, "evidence": 0, "excerpt_hashes": 0}
    mismatch = connection.execute(
        "SELECT 1 FROM evidence e JOIN research_runs r ON r.id=e.research_run_id "
        "WHERE e.business_id<>r.business_id LIMIT 1"
    ).fetchone()
    if mismatch:
        raise StorageError("Research evidence refers to a different business than its research run.")
    if connection.execute(
        "SELECT 1 FROM research_runs r JOIN jobs j ON j.id=r.job_id "
        "WHERE j.kind<>'RESEARCH' OR (j.business_id IS NOT NULL AND j.business_id<>r.business_id) LIMIT 1"
    ).fetchone():
        raise StorageError("Research run and job provenance disagree.")
    if connection.execute(
        "SELECT 1 FROM research_runs r WHERE r.state IN ('SUCCEEDED','PARTIAL') "
        "AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.research_run_id=r.id) LIMIT 1"
    ).fetchone():
        raise StorageError("Successful research run has no retained evidence.")
    hashes = 0
    for row in connection.execute("SELECT extracted_fact,limitations_json FROM evidence WHERE research_run_id IS NOT NULL"):
        hashes += int(verify_excerpt(row[0], row[1]))
    return {
        "research_runs": connection.execute("SELECT count(*) FROM research_runs").fetchone()[0],
        "evidence": connection.execute("SELECT count(*) FROM evidence WHERE research_run_id IS NOT NULL").fetchone()[0],
        "excerpt_hashes": hashes,
    }
