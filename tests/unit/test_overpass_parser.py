import pytest
from mi_boti.discovery.overpass import parse_overpass, ATTRIBUTION
from mi_boti.domain.registry import RegistryError

STAMP="2026-11-14T00:00:00.000000Z"


def parse(payload,**options):
    return parse_overpass(payload,observed_at=STAMP,policy_version="fixture-v1",**options)


def test_source_identifiers_provenance_and_missing_name_are_preserved():
    result=parse({"elements":[{"type":kind,"id":7,"tags":{"amenity":"cafe"}} for kind in ["node","way","relation"]]})
    assert [r["source_id"] for r in result.observations]==["node/7","way/7","relation/7"]
    assert all(r["observed_at"]==STAMP and r["attribution"]==ATTRIBUTION for r in result.observations)
    assert all(r["name"]=="" for r in result.observations)
    assert all(r["coordinates"] is None and r["limitations"] for r in result.observations)


def test_only_published_fields_are_copied_and_no_country_is_guessed():
    result=parse({"elements":[{"type":"node","id":1,"lat":14.65,"lon":121.05,"tags":{"name":"Fixture Cafe","contact:website":"https://fixture.example","amenity":"cafe"}}]})
    raw=result.observations[0]
    assert raw["coordinates"]=={"latitude":14.65,"longitude":121.05}
    assert raw["website"]=="https://fixture.example" and raw["address"]=={}
    assert raw["email"] is None and raw["phone"] is None
    assert raw["source_url"]=="https://www.openstreetmap.org/node/1"


def test_partial_remark_is_not_reported_as_complete():
    result=parse({"elements":[],"remark":"runtime error: timeout"})
    assert result.partial and result.limitations
    assert parse({"elements":[]}).observations==()


@pytest.mark.parametrize("payload",[{},[],{"elements":{}},{"elements":[None]},
    {"elements":[{"type":"node","id":True}]},{"elements":[{"type":"relation","id":0}]},
    {"elements":[{"type":"node","id":1,"tags":{"name":123}}]}])
def test_malformed_responses_fail_closed(payload):
    with pytest.raises(RegistryError):parse(payload)


def test_reserved_observation_limit_is_enforced():
    with pytest.raises(RegistryError):parse({"elements":[{"type":"node","id":1},{"type":"node","id":2}]},max_elements=1)


def test_hitting_output_cap_never_claims_complete_coverage():
    result=parse({"elements":[{"type":"node","id":1}]},max_elements=1)
    assert result.partial and result.limitations
