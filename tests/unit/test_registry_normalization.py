import pytest
from mi_boti.domain.registry import domain, normalized_text, normalize, RegistryError, phone


def observation():
    return {"name":"  CAFÉ — TEST  ","source_namespace":"osm","source_id":"node/1",
        "source_url":"https://www.openstreetmap.org/node/1","observed_at":"2026-11-14T00:00:00.000000Z",
        "policy_version":"fixture-v1","attribution":"OSM contributors","address":{"country":"PH"}}


def test_unicode_and_domain_normalization_preserve_identity_boundaries():
    assert normalized_text("Ｃａｆé — TEST") == "café test"
    assert domain("https://WWW.Example.COM:443/contact") == "example.com"
    assert domain("https://shop.example.com") == "shop.example.com"
    assert domain("https://tenant.example.com") != domain("https://other.example.com")
    assert domain("https://例え.jp") == "xn--r8jz45g.jp"


@pytest.mark.parametrize("url", ["file:///etc/passwd","http://localhost","https://127.0.0.1", "http://169.254.169.254", "https://user:password@example.com", "https://example.com:444", "https://-bad.example", "http://[::1]"])
def test_unsafe_urls_do_not_supply_identity_signals(url):
    assert domain(url) is None


def test_supporting_signals_never_create_strong_domain_phone_claims():
    raw=observation();raw.update(website="https://www.example.com",phone="0917 123 4567",email="Owner@EXAMPLE.COM")
    identity=normalize(raw)
    assert identity.name == "café test"
    assert len(identity.claims) == 1
    assert ("DOMAIN","hostname","example.com","SUPPORTING") in identity.identifiers
    assert ("PHONE","e164","+639171234567","SUPPORTING") in identity.identifiers
    assert ("EMAIL","published","Owner@example.com","SUPPORTING") in identity.identifiers
    assert raw["name"] == "  CAFÉ — TEST  "
    assert phone("123", "PH") is None


def test_missing_unit_does_not_create_name_address_claim():
    raw=observation();raw["address"].update(city="Quezon City",street="Test Street",house_number="1",postcode="1101")
    assert len(normalize(raw).claims)==1
    raw["address"]["unit"]="A"
    assert len(normalize(raw).claims)==2


@pytest.mark.parametrize("key,value",[("name","---"),("source_namespace","bad:namespace"),("observed_at","2026-02-30T00:00:00.000000Z"),("observed_at","2026-11-14T00:00:00Z"),("address",{"country":"Philippines"})])
def test_invalid_observations_fail_validation(key,value):
    raw=observation();raw[key]=value
    with pytest.raises(RegistryError):normalize(raw)


def test_email_subdomain_and_local_part_are_preserved():
    raw=observation();raw["email"]="Owner@WWW.Example.COM"
    assert ("EMAIL","published","Owner@www.example.com","SUPPORTING") in normalize(raw).identifiers


@pytest.mark.parametrize("email",["Owner@example.com/path","Owner@example.com:443","Owner@user:password@example.com"])
def test_malformed_email_host_does_not_become_a_signal(email):
    raw=observation();raw["email"]=email
    assert all(identifier[0]!="EMAIL" for identifier in normalize(raw).identifiers)
