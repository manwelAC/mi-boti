from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
from threading import Barrier
from uuid import uuid4

import pytest

from conftest import campaign, job
from mi_boti.domain.registry import RegistryError
from mi_boti.domain.values import utc_now
from mi_boti.repositories.database import Database
from mi_boti.repositories.registry import resolve


def context(db):
    c=db.connection;campaign_id=campaign(c);job_id=job(c);token=str(uuid4());now=utc_now()
    expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    c.execute("UPDATE jobs SET state='RUNNING',lease_token=?,lease_expires_at=? WHERE id=?",(token,expiry,job_id))
    query_id=str(uuid4())
    c.execute("INSERT INTO discovery_queries VALUES (?,?,?,NULL,'osm','fixture-hash','fixture-v1','qc-fixture','{}','RUNNING',1,0,?,NULL,NULL)",(query_id,job_id,campaign_id,now))
    return query_id,token,job_id


def observation(source_id="node/1",**overrides):
    raw={"name":"Fixture Cafe","source_namespace":"osm","source_id":source_id,
         "source_url":"https://www.openstreetmap.org/"+source_id,"observed_at":utc_now(),
         "policy_version":"fixture-v1","attribution":"OSM contributors",
         "address":{"country":"PH","city":"Quezon City","street":"Fixture Road","house_number":"1"}}
    raw.update(overrides);return raw


def test_new_and_duplicate_are_durable_without_quota_or_research(database):
    q,token,j=context(database);raw=observation();first=resolve(database,q,raw,token)
    assert first.state=="NEW"
    assert resolve(database,q,raw,token)==first
    q2,token2,_=context(database);second=resolve(database,q2,raw,token2)
    assert second.state=="EXISTING" and second.business_id==first.business_id
    business=database.connection.execute("SELECT * FROM businesses").fetchone()
    assert business["origin_job_id"]==j and business["origin_hunt_id"] is None
    assert database.connection.execute("SELECT count(*) FROM business_events").fetchone()[0]==2
    for table in ["research_runs","scores","leads","hunt_credits","ai_executions"]:
        assert database.connection.execute("SELECT count(*) FROM "+table).fetchone()[0]==0
    assert not list(database.connection.execute("PRAGMA foreign_key_check"))


@pytest.mark.parametrize("disposition",["PENDING","QUALIFIED","UNQUALIFIED","REJECTED","ARCHIVED"])
def test_every_disposition_participates_in_global_lookup(database,disposition):
    q,t,_=context(database);first=resolve(database,q,observation(),t)
    database.connection.execute("UPDATE businesses SET disposition=? WHERE id=?",(disposition,first.business_id))
    q,t,_=context(database);again=resolve(database,q,observation(website="https://changed.example"),t)
    assert again.state=="EXISTING" and again.business_id==first.business_id


def test_conflicting_source_address_is_held_and_prior_review_is_reused(database):
    q,t,_=context(database);first=resolve(database,q,observation(),t)
    changed=observation(address={"country":"PH","city":"Quezon City","street":"Different Road"})
    q,t,_=context(database);held=resolve(database,q,changed,t)
    q,t,_=context(database);again=resolve(database,q,dict(changed,observed_at=utc_now()),t)
    assert held.state==again.state=="AMBIGUOUS"
    assert again.review_id==held.review_id
    assert held.business_id is None
    assert database.connection.execute("SELECT count(*) FROM identity_reviews").fetchone()[0]==1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]==1
    assert database.connection.execute("SELECT count(*) FROM candidates").fetchone()[0]==3


def test_shared_domain_is_not_a_unique_identity(database):
    q,t,_=context(database);first=resolve(database,q,observation(website="https://brand.example"),t)
    q,t,_=context(database);second=resolve(database,q,observation("way/1",website="https://brand.example"),t)
    assert second.state=="AMBIGUOUS" and second.business_id is None
    assert database.connection.execute("SELECT count(*) FROM identity_claims").fetchone()[0]==1


def test_distinct_explicit_branches_keep_separate_ids(database):
    q,t,_=context(database);a=resolve(database,q,observation(entity_kind="BRANCH",website="https://brand.example"),t)
    address={"country":"PH","city":"Quezon City","street":"Other Road","house_number":"2"}
    q,t,_=context(database);b=resolve(database,q,observation("way/2",entity_kind="BRANCH",website="https://brand.example",address=address),t)
    assert a.state==b.state=="NEW" and a.business_id!=b.business_id


def test_exact_complete_name_address_can_link_a_second_source(database):
    address={"country":"PH","city":"Quezon City","street":"Fixture Road","house_number":"1","unit":"A","postcode":"1101"}
    q,t,_=context(database);a=resolve(database,q,observation(address=address),t)
    q,t,_=context(database);b=resolve(database,q,observation("way/2",address=address),t)
    assert b.state=="EXISTING" and a.business_id==b.business_id
    assert database.connection.execute("SELECT count(*) FROM identity_claims").fetchone()[0]==3


def test_invalid_observation_is_preserved_without_reserving_business(database):
    q,t,_=context(database);raw=observation(name="");result=resolve(database,q,raw,t)
    assert result.state=="INVALID" and result.business_id is None
    row=database.connection.execute("SELECT observation_json FROM candidates").fetchone()
    assert json.loads(row[0])==raw
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]==0


@pytest.mark.parametrize("change",["wrong_token","expired","cancelled","terminal","wrong_policy"])
def test_stale_or_cancelled_results_cannot_write(database,change):
    q,t,j=context(database);raw=observation()
    if change=="wrong_token":t="wrong"
    if change=="expired":database.connection.execute("UPDATE jobs SET lease_expires_at='2000-01-01T00:00:00.000000Z' WHERE id=?",(j,))
    if change=="cancelled":database.connection.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?",(j,))
    if change=="terminal":database.connection.execute("UPDATE jobs SET state='SUCCEEDED' WHERE id=?",(j,))
    if change=="wrong_policy":raw["policy_version"]="unreserved"
    with pytest.raises(RegistryError):resolve(database,q,raw,t)
    assert database.connection.execute("SELECT count(*) FROM candidates").fetchone()[0]==0


def test_separate_sqlite_writers_cannot_reserve_same_source_twice(database):
    contexts=[context(database),context(database)];barrier=Barrier(2);raw=observation()
    def worker(ctx):
        with Database(database.path) as db:
            barrier.wait(timeout=5)
            return resolve(db,ctx[0],raw,ctx[1])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,contexts))
    assert sorted(r.state for r in results)==["EXISTING","NEW"]
    assert len({r.business_id for r in results})==1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]==1
    assert database.connection.execute("SELECT count(*) FROM candidates").fetchone()[0]==2


def test_foreign_source_cannot_commit_under_another_source_reservation(database):
    q,t,_=context(database)
    with pytest.raises(RegistryError):resolve(database,q,observation(source_namespace="unapproved"),t)
    assert database.connection.execute("SELECT count(*) FROM candidates").fetchone()[0]==0


def test_fuzzy_name_with_shared_address_is_reviewed_not_merged(database):
    q,t,_=context(database)
    original=observation(name="one two three four five six seven")
    first=resolve(database,q,original,t)
    q,t,_=context(database)
    second=resolve(database,q,dict(original,source_id="way/8",name="one two three four five six seven eight"),t)
    assert second.state=="AMBIGUOUS" and second.business_id is None
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]==1


def test_disagreeing_strong_claims_never_merge_businesses(database):
    a={"country":"PH","city":"Quezon City","street":"First Road","house_number":"1","unit":"A","postcode":"1101"}
    b={"country":"PH","city":"Quezon City","street":"Second Road","house_number":"2","unit":"B","postcode":"1101"}
    q,t,_=context(database);first=resolve(database,q,observation(address=a,entity_kind="BRANCH"),t)
    q,t,_=context(database);second=resolve(database,q,observation("node/2",address=b,entity_kind="BRANCH"),t)
    assert first.business_id!=second.business_id
    q,t,_=context(database);held=resolve(database,q,observation(address=b,entity_kind="BRANCH"),t)
    assert held.state=="AMBIGUOUS" and held.business_id is None
    review=database.connection.execute("SELECT matches_json FROM identity_reviews WHERE id=?",(held.review_id,)).fetchone()
    assert set(json.loads(review[0]))=={first.business_id,second.business_id}
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0]==2


def test_registry_records_survive_reopening_database(database):
    q,t,_=context(database);first=resolve(database,q,observation(),t)
    with Database(database.path) as reopened:
        assert reopened.connection.execute("SELECT id FROM businesses").fetchone()[0]==first.business_id
        assert reopened.connection.execute("SELECT count(*) FROM identity_claims").fetchone()[0]==1
        q,t,_=context(reopened)
        assert resolve(reopened,q,observation(),t).business_id==first.business_id
