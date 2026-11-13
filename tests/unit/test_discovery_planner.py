import pytest
from mi_boti.discovery.planner import QuerySpec
from mi_boti.domain.registry import RegistryError


def query(**changes):
    values=dict(bbox=(14.648,121.047,14.657,121.061),categories=("restaurant","cafe"),limit=5,target_version=1,policy_version="probe-only")
    values.update(changes)
    return QuerySpec(**values)


def test_tag_order_and_repeats_do_not_change_fingerprint():
    a=query();b=query(categories=("cafe","restaurant","cafe"))
    assert a.fingerprint==b.fingerprint and a.overpass_query()==b.overpass_query()
    assert a.overpass_query()=='[out:json][timeout:10][maxsize:16777216];nwr["amenity"~"^(cafe|restaurant)$"](14.648,121.047,14.657,121.061);out center tags 5;'
    assert query(limit=6).fingerprint!=a.fingerprint
    assert query(target_version=2).fingerprint!=a.fingerprint
    assert query(policy_version="other").fingerprint!=a.fingerprint


@pytest.mark.parametrize("changes",[{"bbox":(float("nan"),121,15,122)},{"bbox":(14,121,16,122)},
    {"bbox":(14,121,13,122)},{"bbox":(14,121,14.000000001,121.000000001)},
    {"categories":("cafe];out;",)},{"categories":()},{"limit":101},{"limit":True},
    {"target_version":0},{"policy_version":""}])
def test_invalid_or_unbounded_query_inputs_are_rejected(changes):
    with pytest.raises(RegistryError):query(**changes)
