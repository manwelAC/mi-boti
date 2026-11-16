from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

import pytest

from test_identity_ui import seed
from mi_boti.domain.values import utc_now
from mi_boti.research.collector import Collection, PageObservation, ResearchError
from mi_boti.repositories.research import begin_run, finish_run


def research_job(db, business):
    job_id, token = str(uuid4()), str(uuid4())
    now = utc_now()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    db.connection.execute(
        "INSERT INTO jobs(id,kind,payload_json,idempotency_key,actor_id,state,attempt,max_attempts,progress_json,cancel_requested,created_at,updated_at,lease_token,lease_expires_at) "
        "VALUES (?,'RESEARCH',?,?,'223456789012345678','RUNNING',1,1,'{}',0,?,?,?,?)",
        (job_id, json.dumps({"business_id": business, "refresh": True, "analyze": False}), job_id, now, now, token, expires),
    )
    return job_id, token


def test_immutable_refresh_provenance_and_stale_lease(database):
    business, review = seed(database)
    database.connection.execute("UPDATE identity_reviews SET state='RESOLVED' WHERE id=?", (review,))
    page = PageObservation("https://public.example/", "https://public.example/", utc_now(), "Public booking page.",
                           hashlib.sha256(b"Public booking page.").hexdigest(), "review-v1", ("Not independently verified.",))
    result = Collection("SUCCEEDED", (page,), 2, ())
    job, token = research_job(database, business)
    run = begin_run(database, job, token)
    with pytest.raises(ResearchError): finish_run(database, run, "stale", result)
    with pytest.raises(ResearchError): finish_run(database, run, token, replace(result, pages=(replace(page, excerpt_sha256="bad"),)))
    evidence = finish_run(database, run, token, result)
    original = tuple(database.connection.execute("SELECT * FROM evidence WHERE id=?", (evidence[0],)).fetchone())
    with pytest.raises(ResearchError): finish_run(database, run, token, result)
    job2, token2 = research_job(database, business)
    run2 = begin_run(database, job2, token2)
    assert finish_run(database, run2, token2, result) != evidence
    assert tuple(database.connection.execute("SELECT * FROM evidence WHERE id=?", (evidence[0],)).fetchone()) == original
    for table in ("findings", "scores", "leads", "hunt_credits"):
        assert database.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_identity_and_explicit_refresh_are_required(database):
    business, _ = seed(database)
    job, token = research_job(database, business)
    with pytest.raises(ResearchError, match="identity review"): begin_run(database, job, token)
    database.connection.execute("UPDATE jobs SET payload_json=? WHERE id=?", (json.dumps({"business_id": business, "refresh": False}), job))
    with pytest.raises(ResearchError, match="explicit refresh"): begin_run(database, job, token)
