import threading
import httpx
import pytest

from mi_boti.discovery import overpass as mod
from mi_boti.discovery.overpass import (
    ATTRIBUTION,
    DiscoverySourceError,
    OverpassDiscoveryAdapter,
    SourceCancelledError,
    SourceForbiddenError,
    SourcePolicyError,
    SourceRateLimitError,
    parse_overpass,
    reset_source_rate_limiters,
)
from mi_boti.discovery.planner import QuerySpec
from mi_boti.domain.campaigns import PlannedCellQuery
from mi_boti.domain.registry import RegistryError

STAMP = "2026-11-14T00:00:00.000000Z"


@pytest.fixture(autouse=True)
def _clear_rate_limiters():
    reset_source_rate_limiters()
    yield
    reset_source_rate_limiters()


def parse(payload, **options):
    return parse_overpass(payload, observed_at=STAMP, policy_version="fixture-v1", **options)


def test_source_identifiers_provenance_and_missing_name_are_preserved():
    result = parse({"elements": [{"type": kind, "id": 7, "tags": {"amenity": "cafe"}} for kind in ["node", "way", "relation"]]})
    assert [r["source_id"] for r in result.observations] == ["node/7", "way/7", "relation/7"]
    assert all(r["observed_at"] == STAMP and r["attribution"] == ATTRIBUTION for r in result.observations)
    assert all(r["name"] == "" for r in result.observations)
    assert all(r["coordinates"] is None and r["limitations"] for r in result.observations)


def test_only_published_fields_are_copied_and_no_country_is_guessed():
    result = parse({"elements": [{"type": "node", "id": 1, "lat": 14.65, "lon": 121.05, "tags": {"name": "Fixture Cafe", "contact:website": "https://fixture.example", "amenity": "cafe"}}]})
    raw = result.observations[0]
    assert raw["coordinates"] == {"latitude": 14.65, "longitude": 121.05}
    assert raw["website"] == "https://fixture.example" and raw["address"] == {}
    assert raw["email"] is None and raw["phone"] is None
    assert raw["source_url"] == "https://www.openstreetmap.org/node/1"


def test_partial_remark_is_not_reported_as_complete():
    result = parse({"elements": [], "remark": "runtime error: timeout"})
    assert result.partial and result.limitations
    assert parse({"elements": []}).observations == ()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"elements": {}},
        {"elements": [None]},
        {"elements": [{"type": "node", "id": True}]},
        {"elements": [{"type": "relation", "id": 0}]},
        {"elements": [{"type": "node", "id": 1, "tags": {"name": 123}}]},
    ],
)
def test_malformed_responses_fail_closed(payload):
    with pytest.raises(RegistryError):
        parse(payload)


def test_reserved_observation_limit_is_enforced():
    with pytest.raises(RegistryError):
        parse({"elements": [{"type": "node", "id": 1}, {"type": "node", "id": 2}]}, max_elements=1)


def test_hitting_output_cap_never_claims_complete_coverage():
    result = parse({"elements": [{"type": "node", "id": 1}]}, max_elements=1)
    assert result.partial and result.limitations


def valid_policy(**overrides):
    base = {
        "enabled": True,
        "endpoint": "https://overpass-api.de/api/interpreter",
        "allowed_hosts": ["overpass-api.de"],
        "permission_url": "https://dev.overpass-api.de/overpass-doc/en/preface/commons.html",
        "license_url": "https://www.openstreetmap.org/copyright",
        "attribution": ATTRIBUTION,
        "policy_version": "overpass-2026-11",
        "reviewed_at": "2026-11-14T00:00:00Z",
        "review_expires_at": "2027-11-14T00:00:00Z",
        "user_agent": "MiBoti/0.2 (+https://github.com/manwelAC/mi-boti)",
        "allowed_tags": ["cafe", "restaurant"],
        "min_interval_seconds": 10,
        "max_concurrency": 1,
        "timeout_seconds": 20,
        "max_response_bytes": 1048576,
        "max_attempts": 3,
        "max_requests_per_day": 50,
    }
    base.update(overrides)
    return base


def test_overpass_adapter_pins_validated_public_ip_and_preserves_host_and_sni():
    sleeps = []
    clock = [100.0]
    seen_requests = []

    def fake_monotonic():
        return clock[0]

    def fake_sleep(seconds):
        sleeps.append(round(seconds, 2))
        clock[0] += seconds

    def fake_resolver(host, port, type=0):
        assert host == "overpass-api.de" and port == 443
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(request: httpx.Request):
        seen_requests.append(request)
        # Actual connection destination must be the pinned IPv4 literal, NOT the hostname!
        assert request.url.host == "93.184.216.34"
        assert request.url.path == "/api/interpreter"
        assert request.headers["host"] == "overpass-api.de"
        assert request.extensions.get("sni_hostname") == "overpass-api.de"
        assert request.headers["user-agent"].startswith("MiBoti/0.2")
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 42,
                        "lat": 14.651,
                        "lon": 121.051,
                        "tags": {"name": "Dynamic QC Cafe", "amenity": "cafe"},
                    }
                ]
            },
        )

    adapter = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(handler),
        resolver=fake_resolver,
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe", "restaurant"), 10, 1, "overpass-2026-11"),
    )
    first = adapter.discover(planned, max_elements=10)
    assert len(first.observations) == 1
    assert first.observations[0]["name"] == "Dynamic QC Cafe"
    assert sleeps == []

    # Second call 3 seconds later sleeps in bounded increments summing to 7 seconds.
    clock[0] += 3.0
    adapter.discover(planned, max_elements=10)
    assert round(sum(sleeps), 2) == 7.0
    assert len(seen_requests) == 2


def test_overpass_adapter_pins_validated_ipv6_destination_with_brackets_and_sni():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        assert request.url.host == "2606:2800:220:1:248:1893:25c8:1946"
        assert str(request.url).startswith("https://[2606:2800:220:1:248:1893:25c8:1946]/api/interpreter")
        assert request.headers["host"] == "overpass-api.de"
        assert request.extensions.get("sni_hostname") == "overpass-api.de"
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})

    adapter = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(handler),
        resolver=lambda *_, **__: [(10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0))],
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    batch = adapter.discover(planned, max_elements=5)
    assert batch.observations == ()
    assert len(seen) == 1


@pytest.mark.parametrize(
    "dns_records",
    [
        [(2, 1, 6, "", ("127.0.0.1", 443))],
        [(2, 1, 6, "", ("10.0.0.1", 443))],
        [(2, 1, 6, "", ("169.254.169.254", 443))],
        [(10, 1, 6, "", ("::1", 443, 0, 0))],
        [(10, 1, 6, "", ("::ffff:127.0.0.1", 443, 0, 0))],
        [(10, 1, 6, "", ("::ffff:10.0.0.1", 443, 0, 0))],
        [(10, 1, 6, "", ("::ffff:169.254.169.254", 443, 0, 0))],
        [(10, 1, 6, "", ("fe80::1", 443, 0, 0))],
        # Mixed public + private DNS answers must fail closed!
        [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("10.0.0.1", 443))],
        [(2, 1, 6, "", ("93.184.216.34", 443)), (10, 1, 6, "", ("::ffff:192.168.1.1", 443, 0, 0))],
    ],
)
def test_overpass_adapter_blocks_non_global_and_mixed_dns_answers(dns_records):
    called = []
    adapter = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(lambda req: called.append(req)),
        resolver=lambda *_, **__: dns_records,
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    with pytest.raises(SourceForbiddenError):
        adapter.discover(planned, max_elements=5)
    assert called == []


def test_overpass_adapter_prevents_dns_rebinding_across_calls_and_pins_exact_ip():
    """Verify DNS is re-evaluated per request and HTTPX never re-resolves the hostname."""
    dns_answers = [
        [(2, 1, 6, "", ("93.184.216.34", 443))],
        [(2, 1, 6, "", ("127.0.0.1", 443))],  # Rebound to loopback on second call
    ]
    connected_hosts = []
    clock = [100.0]

    def handler(request: httpx.Request):
        connected_hosts.append(request.url.host)
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})

    adapter = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(handler),
        resolver=lambda *_, **__: dns_answers.pop(0),
        monotonic=lambda: clock[0],
        sleep=lambda s: clock.__setitem__(0, clock[0] + s),
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    adapter.discover(planned, max_elements=5)
    assert connected_hosts == ["93.184.216.34"]

    clock[0] += 15.0
    with pytest.raises(SourceForbiddenError):
        adapter.discover(planned, max_elements=5)
    assert connected_hosts == ["93.184.216.34"]


@pytest.mark.parametrize(
    "status,headers,body,expected_exc",
    [
        (301, {"location": "https://overpass-api.de/other"}, b"", "SourceForbiddenError"),
        (302, {"location": "http://127.0.0.1/"}, b"", "SourceForbiddenError"),
        (307, {"location": "https://[::ffff:127.0.0.1]/"}, b"", "SourceForbiddenError"),
        (403, {"content-type": "application/json"}, b"{}", "SourceForbiddenError"),
        (429, {"content-type": "application/json", "retry-after": "15"}, b"{}", "SourceRateLimitError"),
        (503, {"content-type": "application/json"}, b"{}", "DiscoverySourceError"),
        (200, {"content-type": "text/html"}, b"<html></html>", "SourceSchemaError"),
        (200, {"content-type": "application/json"}, b"x" * 2048, "DiscoverySourceError"),
    ],
)
def test_overpass_adapter_rejects_redirects_errors_bad_mime_and_oversized_body(status, headers, body, expected_exc):
    adapter = mod.OverpassDiscoveryAdapter(
        valid_policy(max_response_bytes=1024),
        transport=httpx.MockTransport(lambda _: httpx.Response(status, headers=headers, content=body)),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    with pytest.raises(getattr(mod, expected_exc)):
        adapter.discover(planned, max_elements=5)


def test_osm_editing_api_map_json_is_rejected_by_policy():
    with pytest.raises(SourcePolicyError, match="prohibited for read-only business discovery"):
        OverpassDiscoveryAdapter(
            valid_policy(
                endpoint="https://api.openstreetmap.org/api/0.6/map.json",
                allowed_hosts=["api.openstreetmap.org"],
            )
        )


def test_source_wide_rate_limiting_shared_across_adapter_instances_and_honors_retry_after():
    clock = [500.0]
    sleeps = []

    def fake_monotonic():
        return clock[0]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    #Instance 1 receives HTTP 429 with Retry-After: 15 (within 20s timeout_seconds)
    responses = [
        httpx.Response(429, headers={"content-type": "application/json", "retry-after": "15"}, json={}),
        httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []}),
    ]

    adapter_one = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=20),
        transport=httpx.MockTransport(lambda _: responses.pop(0)),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    with pytest.raises(SourceRateLimitError) as exc_info:
        adapter_one.discover(planned, max_elements=5)
    assert exc_info.value.retry_after_seconds == 15.0

    # A brand-new adapter instance for the same source must NOT reset the rate limiter or Retry-After!
    adapter_two = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=20),
        transport=httpx.MockTransport(lambda _: responses.pop(0)),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    # If Retry-After exceeds deadline_monotonic, it fails immediately without waiting past the deadline.
    with pytest.raises(SourceRateLimitError, match="exceeds remaining job deadline"):
        adapter_two.discover(planned, max_elements=5, deadline_monotonic=clock[0] + 10.0)

    # With sufficient deadline, adapter_two waits the full 15 seconds required by Retry-After.
    adapter_two.discover(planned, max_elements=5, deadline_monotonic=clock[0] + 60.0)
    assert round(sum(sleeps), 2) == 15.0


def test_source_wide_concurrency_and_cancellation_during_rate_limit_wait():
    clock = [1000.0]
    lock = threading.Lock()

    def fake_monotonic():
        with lock:
            return clock[0]

    def fake_sleep(seconds):
        with lock:
            clock[0] += seconds

    adapter_a = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    adapter_b = OverpassDiscoveryAdapter(
        valid_policy(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )
    adapter_a.discover(planned, max_elements=5)

    # Second adapter starts 1 second later, enters rate-limit wait, and gets cancelled after 2 ticks.
    clock[0] += 1.0
    ticks = [0]

    def cancel_after_two_ticks():
        ticks[0] += 1
        return ticks[0] > 2

    with pytest.raises(SourceCancelledError):
        adapter_b.discover(planned, max_elements=5, is_cancelled=cancel_after_two_ticks)


def test_total_monotonic_deadline_rejects_slow_dns_late_headers_and_slow_stream():
    clock = [2000.0]

    def fake_monotonic():
        return clock[0]

    def fake_sleep(seconds):
        clock[0] += seconds

    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )

    # 1. Slow DNS resolution that crosses the total deadline is rejected before connecting.
    connected = []

    def slow_resolver(*_, **__):
        clock[0] += 6.0
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    adapter_dns = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=5),
        transport=httpx.MockTransport(lambda req: connected.append(req)),
        resolver=slow_resolver,
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    with pytest.raises(DiscoverySourceError, match="exceeded total deadline"):
        adapter_dns.discover(planned, max_elements=5)
    assert connected == []

    # 2. Late response headers arriving after the total deadline are rejected.
    reset_source_rate_limiters()

    def late_header_handler(_req):
        clock[0] += 6.0
        return httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})

    adapter_hdr = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=5),
        transport=httpx.MockTransport(late_header_handler),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    with pytest.raises(DiscoverySourceError, match="after total deadline"):
        adapter_hdr.discover(planned, max_elements=5)

    # 3. Slow streaming body that crosses the total deadline mid-stream is rejected.
    reset_source_rate_limiters()

    class SlowByteStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"elements": ['
            clock[0] += 6.0
            yield b"]}"

    adapter_stream = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=5),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "application/json"}, stream=SlowByteStream())
        ),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_monotonic,
        sleep=fake_sleep,
    )
    with pytest.raises(DiscoverySourceError, match="exceeded total deadline"):
        adapter_stream.discover(planned, max_elements=5)


def test_stalled_dns_resolver_lifecycle_bounds_threads_blocks_admission_and_reports_honest_shutdown():
    """Regression: when DNS resolver blocks without cooperating with register_abort, worker count stays <= 1,
    repeated calls are rejected while the resolver is wedged, and shutdown honestly reports drained=False until released.
    """
    import time

    reset_source_rate_limiters()
    release_dns = threading.Event()
    entered_dns = threading.Event()
    resolver_calls = [0]

    def wedged_resolver(*_, **__):
        resolver_calls[0] += 1
        entered_dns.set()
        release_dns.wait(timeout=5.0)
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    adapter = OverpassDiscoveryAdapter(
        valid_policy(timeout_seconds=20),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"content-type": "application/json"}, json={"elements": []})
        ),
        resolver=wedged_resolver,
    )
    planned = PlannedCellQuery(
        "qc-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 5, 1, "overpass-2026-11"),
    )

    try:
        t0 = time.monotonic()
        with pytest.raises(DiscoverySourceError, match="DNS resolution timed out"):
            adapter.discover(planned, max_elements=5, deadline_monotonic=t0 + 0.08)
        assert entered_dns.is_set()
        assert resolver_calls[0] == 1
        # Exactly 1 tracked resolver thread is still alive; no second thread was spawned.
        assert mod.active_resolver_worker_count() == 1

        # Repeated attempts while the DNS thread is still wedged fail closed immediately without spawning more threads!
        for _ in range(3):
            with pytest.raises(DiscoverySourceError, match="still occupied by an uncompleted timed-out DNS lookup"):
                adapter.discover(planned, max_elements=5, deadline_monotonic=time.monotonic() + 1.0)
        assert resolver_calls[0] == 1
        assert mod.active_resolver_worker_count() == 1

        # Shutdown while still blocked must NOT claim the detached resolver thread was terminated.
        status_while_blocked = mod.shutdown_resolver_workers(timeout=0.03)
        assert status_while_blocked == {"drained": False, "remaining": 1}
    finally:
        release_dns.set()

    status_after_release = mod.shutdown_resolver_workers(timeout=1.0)
    assert status_after_release == {"drained": True, "remaining": 0}
    assert mod.active_resolver_worker_count() == 0
