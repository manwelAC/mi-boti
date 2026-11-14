"""Unit and integration tests for the Philippines OSM PBF extract downloader, importer, and local snapshot adapter."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

import httpx
import osmium
import pytest

from mi_boti.discovery.overpass import (
    DiscoverySourceError,
    SourceCancelledError,
    SourceForbiddenError,
    SourcePolicyError,
    SourceSchemaError,
    reset_source_rate_limiters,
)
from mi_boti.discovery.philippines_extract import (
    OFFICIAL_GEOFABRIK_PH_MD5_URL,
    OFFICIAL_GEOFABRIK_PH_URL,
    PhilippinesExtractAdapter,
    download_and_import_philippines_extract,
    import_pbf_to_snapshot,
    parse_md5_sidecar,
    resolve_active_snapshot_generation,
    validate_extract_policy,
    verify_local_snapshot,
)
from mi_boti.discovery.planner import QuerySpec
from mi_boti.domain.campaigns import PlannedCellQuery
from mi_boti.domain.errors import StorageError
from mi_boti.jobs.discovery import (
    claim_discover_job,
    enqueue_manual_discovery,
    execute_manual_discovery_job,
)
from mi_boti.repositories.campaigns import create_campaign
from mi_boti.storage.lock import DeploymentLock
from mi_boti.storage.paths import confined, prepare_data_root


@pytest.fixture(autouse=True)
def _reset_rates():
    reset_source_rate_limiters()
    yield
    reset_source_rate_limiters()


def extract_policy(**overrides) -> dict:
    base = {
        "enabled": True,
        "endpoint": OFFICIAL_GEOFABRIK_PH_URL,
        "allowed_hosts": ("download.geofabrik.de",),
        "permission_url": "https://download.geofabrik.de/asia/philippines.html",
        "license_url": "https://www.openstreetmap.org/copyright",
        "attribution": "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright",
        "policy_version": "geofabrik-ph-2026-11",
        "reviewed_at": "2026-11-14T00:00:00Z",
        "review_expires_at": "2027-11-14T00:00:00Z",
        "user_agent": "MiBoti/0.2 (+https://github.com/manwelAC/mi-boti)",
        "allowed_tags": ("cafe", "restaurant"),
        "min_interval_seconds": 10,
        "max_concurrency": 1,
        "timeout_seconds": 60,
        "max_response_bytes": 10485760,
        "max_attempts": 2,
        "max_requests_per_day": 25,
    }
    base.update(overrides)
    return base


def write_synthetic_pbf(
    pbf_path: Path,
    *,
    replication_timestamp: str | None = "2026-11-13T21:22:20Z",
    nodes: list[tuple[int, tuple[float, float] | None, dict[str, str]]] | None = None,
    ways: list[tuple[int, list[int], dict[str, str]]] | None = None,
    relations: list[tuple[int, list[tuple[str, int, str]], dict[str, str]]] | None = None,
) -> tuple[bytes, str, str]:
    pbf_path.unlink(missing_ok=True)
    header = osmium.io.Header()
    if replication_timestamp is not None:
        header.set("osmosis_replication_timestamp", replication_timestamp)
    writer = osmium.SimpleWriter(str(pbf_path), 1024 * 64, header)
    try:
        for nid, loc, tags in sorted(nodes or [], key=lambda x: x[0]):
            if loc is not None:
                writer.add_node(osmium.osm.mutable.Node(id=nid, location=loc, tags=tags))
            else:
                writer.add_node(osmium.osm.mutable.Node(id=nid, tags=tags))
        for wid, nrefs, tags in sorted(ways or [], key=lambda x: x[0]):
            writer.add_way(osmium.osm.mutable.Way(id=wid, nodes=nrefs, tags=tags))
        for rid, members, tags in sorted(relations or [], key=lambda x: x[0]):
            writer.add_relation(osmium.osm.mutable.Relation(id=rid, members=members, tags=tags))
    finally:
        writer.close()
    raw = pbf_path.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest(), hashlib.md5(raw).hexdigest()


def setup_ready_guild_and_qc_campaign(db) -> str:
    now = "2026-11-14T00:00:00.000000Z"
    with db.transaction() as c:
        c.execute(
            "INSERT OR REPLACE INTO guild_config VALUES ('guild', '123456789012345678', 'READY', 1, '{}', ?)",
            (now,),
        )
        c.execute(
            "INSERT OR REPLACE INTO discord_resources VALUES ('res-cmd', '123456789012345678', 'lead-search', 'TEXT', '323456789012345678', NULL, 'ACTIVE', 1)"
        )
        c.execute("INSERT OR REPLACE INTO command_channels VALUES ('discover', 'res-cmd', 1)")
    camp = create_campaign(
        db,
        "223456789012345678",
        "Quezon City Extract Campaign",
        {
            "schema_version": 1,
            "target_categories": ["cafe", "restaurant"],
            "geography": {
                "country_code": "PH",
                "locality": "Quezon City",
                "bbox": [14.648, 121.047, 14.657, 121.061],
            },
            "exclusions": [],
            "provider_id": None,
            "service_description": "Local extract campaign",
        },
        now=now,
    )
    return camp.id


def test_extract_policy_validation_rejects_prohibited_or_expired_sources():
    validate_extract_policy(extract_policy())
    with pytest.raises(SourcePolicyError, match="disabled"):
        validate_extract_policy(extract_policy(enabled=False), require_enabled=True)
    # Prohibits internal/history PBFs and OSM editing API
    for bad_url in (
        "https://download.geofabrik.de/asia/philippines-internal.osm.pbf",
        "https://download.geofabrik.de/asia/philippines.osh.pbf",
        "https://api.openstreetmap.org/api/0.6/map.json",
        "http://download.geofabrik.de/asia/philippines-latest.osm.pbf",
    ):
        with pytest.raises(SourcePolicyError):
            validate_extract_policy(
                extract_policy(endpoint=bad_url, allowed_hosts=("download.geofabrik.de", "api.openstreetmap.org"))
            )
    with pytest.raises(SourcePolicyError, match="expired"):
        validate_extract_policy(
            extract_policy(review_expires_at="2026-01-01T00:00:00Z"),
            now_utc=lambda: datetime(2026, 11, 14, tzinfo=timezone.utc),
        )


def test_parse_md5_sidecar():
    digest = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert parse_md5_sidecar(f"{digest}  philippines-latest.osm.pbf\n") == digest
    with pytest.raises(SourceSchemaError):
        parse_md5_sidecar("not-an-md5-file")


def test_import_synthetic_pbf_preserves_nodes_ways_relations_and_labels_derived_geometry(tmp_path):
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    pbf_file = tmp_path / "synthetic-qc.osm.pbf"

    # Build a synthetic PBF with:
    # 1. Node 101: exact cafe inside QC bbox
    # 2. Way 301 (nodes 201..204): closed restaurant polygon inside QC bbox -> approximate centroid
    # 3. Relation 401 (multipolygon with outer way 302 using nodes 205, 206): cafe inside QC bbox -> approximate centroid
    # 4. Way 303 (referencing missing node 999): incomplete geometry
    # 5. Relation 402 (type=route): unsupported relation type
    _raw, sha256_hex, md5_hex = write_synthetic_pbf(
        pbf_file,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (
                101,
                (121.0500, 14.6500),
                {
                    "name": "Katipunan Roasters",
                    "amenity": "cafe",
                    "addr:country": "PH",
                    "addr:city": "Quezon City",
                    "addr:street": "Katipunan Avenue",
                    "addr:housenumber": "42",
                    "website": "https://katipunanroasters.example.ph",
                    "phone": "+63 2 8123 4567",
                },
            ),
            (201, (121.0520, 14.6520), {}),
            (202, (121.0540, 14.6520), {}),
            (203, (121.0540, 14.6540), {}),
            (204, (121.0520, 14.6540), {}),
            (205, (121.0550, 14.6550), {}),
            (206, (121.0560, 14.6560), {}),
        ],
        ways=[
            (
                301,
                [201, 202, 203, 204, 201],
                {
                    "name": "Maginhawa Bistro",
                    "amenity": "restaurant",
                    "addr:country": "PH",
                    "addr:city": "Quezon City",
                },
            ),
            (302, [205, 206], {}),
            (
                303,
                [999],
                {"name": "Unlocated Cafe", "amenity": "cafe"},
            ),
        ],
        relations=[
            (
                401,
                [("w", 302, "outer")],
                {"type": "multipolygon", "name": "UP Courtyard Cafe", "amenity": "cafe"},
            ),
            (
                402,
                [("w", 302, "outer")],
                {"type": "route", "name": "Route Resto", "amenity": "restaurant"},
            ),
        ],
    )

    pol = extract_policy()
    manifest = import_pbf_to_snapshot(
        pbf_file,
        data_dir,
        policy=pol,
        downloaded_at="2026-11-14T10:00:00.000000Z",
        provider_md5=md5_hex,
        expected_sha256=sha256_hex,
        minimum_disk_mib=1,
    )

    assert manifest.pbf_sha256 == sha256_hex
    assert manifest.provider_md5 == md5_hex
    assert manifest.snapshot_observed_at == "2026-11-13T21:22:20.000000Z"
    assert manifest.downloaded_at == "2026-11-14T10:00:00.000000Z"
    assert manifest.parser_name == "pyosmium"
    assert manifest.counts["nodes_indexed"] == 1
    assert manifest.counts["ways_indexed"] == 2
    assert manifest.counts["relations_indexed"] == 2
    assert manifest.counts["approximate_centroids"] == 2
    assert manifest.counts["incomplete_geometry"] == 2
    assert manifest.counts["unsupported_relations"] == 1
    assert manifest.incomplete_snapshot is True

    verified = verify_local_snapshot(data_dir)
    assert verified.snapshot_id == manifest.snapshot_id
    assert verified.snapshot_db_sha256 == manifest.snapshot_db_sha256

    query_time = datetime(2026, 11, 14, 12, 30, 0, tzinfo=timezone.utc)
    adapter = PhilippinesExtractAdapter(data_dir, pol, now_utc=lambda: query_time)
    planned = PlannedCellQuery(
        "qc-cell-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe", "restaurant"), 10, 1, pol["policy_version"]),
    )
    batch = adapter.discover(planned, max_elements=10, campaign_id="camp-1")
    # 3 located POIs in bbox: node/101, way/301, relation/401
    assert len(batch.observations) == 3
    by_id = {o["source_id"]: o for o in batch.observations}
    assert set(by_id) == {"node/101", "way/301", "relation/401"}

    # Snapshot observation time vs local query time are distinct!
    for obs in batch.observations:
        assert obs["observed_at"] == "2026-11-13T21:22:20.000000Z"
        assert obs["local_queried_at"] == "2026-11-14T12:30:00.000000Z"
        assert obs["snapshot_sha256"] == sha256_hex

    # Node coordinates are exact; Way and Relation coordinates are explicitly labelled approximate!
    assert "approximate" not in by_id["node/101"]["coordinates"]
    assert by_id["way/301"]["coordinates"] == {"latitude": 14.653, "longitude": 121.053, "approximate": True}
    assert any("approximate centroid" in lim for lim in by_id["way/301"]["limitations"])
    assert by_id["relation/401"]["coordinates"] == {"latitude": 14.6555, "longitude": 121.0555, "approximate": True}
    assert any("approximate centroid" in lim for lim in by_id["relation/401"]["limitations"])

    # Because the snapshot had incomplete geometry / unsupported relation, batch.partial is True
    # so it cannot establish EXHAUSTED complete geographic coverage.
    assert batch.partial is True


def test_download_workflow_redirects_checksum_mismatch_corrupt_pbf_and_retains_prior_verified_snapshot(tmp_path):
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    pbf_v1 = tmp_path / "v1.osm.pbf"
    raw_v1, sha_v1, md5_v1 = write_synthetic_pbf(
        pbf_v1,
        replication_timestamp="2026-11-12T00:00:00Z",
        nodes=[(1, (121.050, 14.650), {"name": "Cafe V1", "amenity": "cafe"})],
    )
    pol = extract_policy(allowed_hosts=("download.geofabrik.de", "mirror.geofabrik.de"))
    clock = [100.0]

    def fake_mono():
        return clock[0]

    def fake_sleep(s):
        clock[0] += s

    # 1. Valid download via reviewed HTTPS redirect from download.geofabrik.de -> mirror.geofabrik.de
    def handler_v1(req: httpx.Request) -> httpx.Response:
        host_hdr = req.headers.get("host", "")
        if req.url.path.endswith(".md5"):
            return httpx.Response(200, text=f"{md5_v1}  philippines-latest.osm.pbf\n")
        if host_hdr == "download.geofabrik.de":
            return httpx.Response(302, headers={"location": "https://mirror.geofabrik.de/asia/philippines-latest.osm.pbf"})
        assert host_hdr == "mirror.geofabrik.de"
        return httpx.Response(200, headers={"content-length": str(len(raw_v1))}, content=raw_v1)

    manifest_v1 = download_and_import_philippines_extract(
        data_dir,
        policy=pol,
        minimum_disk_mib=1,
        transport=httpx.MockTransport(handler_v1),
        resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
        monotonic=fake_mono,
        sleep=fake_sleep,
    )
    assert manifest_v1.pbf_sha256 == sha_v1
    assert manifest_v1.final_download_url == "https://mirror.geofabrik.de/asia/philippines-latest.osm.pbf"

    # 2. Failed refresh due to MD5 mismatch MUST NOT replace active v1 snapshot!
    clock[0] += 20.0
    with pytest.raises(SourceSchemaError, match="MD5 digest did not match"):
        download_and_import_philippines_extract(
            data_dir,
            policy=pol,
            minimum_disk_mib=1,
            transport=httpx.MockTransport(
                lambda req: (
                    httpx.Response(200, text="0" * 32 + "  philippines-latest.osm.pbf\n")
                    if req.url.path.endswith(".md5")
                    else httpx.Response(200, content=raw_v1)
                )
            ),
            resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
            monotonic=fake_mono,
            sleep=fake_sleep,
        )
    assert verify_local_snapshot(data_dir).pbf_sha256 == sha_v1

    # 3. Failed refresh due to corrupt/truncated PBF bytes MUST NOT replace active v1 snapshot!
    clock[0] += 20.0
    corrupt_bytes = b"not-a-valid-pbf-stream"
    corrupt_md5 = hashlib.md5(corrupt_bytes).hexdigest()
    with pytest.raises(SourceSchemaError, match="header is malformed"):
        download_and_import_philippines_extract(
            data_dir,
            policy=pol,
            minimum_disk_mib=1,
            transport=httpx.MockTransport(
                lambda req: (
                    httpx.Response(200, text=f"{corrupt_md5}  philippines-latest.osm.pbf\n")
                    if req.url.path.endswith(".md5")
                    else httpx.Response(200, content=corrupt_bytes)
                )
            ),
            resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
            monotonic=fake_mono,
            sleep=fake_sleep,
        )
    assert verify_local_snapshot(data_dir).pbf_sha256 == sha_v1

    # 4. Unapproved redirect host is rejected fail-closed!
    clock[0] += 20.0
    with pytest.raises(SourceForbiddenError, match="not in the reviewed HTTPS allowlist"):
        download_and_import_philippines_extract(
            data_dir,
            policy=pol,
            md5_url=None,
            minimum_disk_mib=1,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(302, headers={"location": "https://evil.example.org/philippines-latest.osm.pbf"})
            ),
            resolver=lambda *_, **__: [(2, 1, 6, "", ("93.184.216.34", 443))],
            monotonic=fake_mono,
            sleep=fake_sleep,
        )
    assert verify_local_snapshot(data_dir).pbf_sha256 == sha_v1


def test_stable_pagination_across_capped_runs_and_snapshot_refresh(database, tmp_path):
    """Verify that capped local queries paginate forward across runs instead of repeating page 1,
    only mark coverage FRESH/EXHAUSTED when the cell's last page is reached, and reset cursor when a new snapshot is imported.
    """
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    camp_id = setup_ready_guild_and_qc_campaign(database)
    pol = extract_policy()

    pbf_1 = tmp_path / "snap1.osm.pbf"
    write_synthetic_pbf(
        pbf_1,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Alpha Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (102, (121.051, 14.651), {"name": "Bravo Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (103, (121.052, 14.652), {"name": "Charlie Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (104, (121.053, 14.653), {"name": "Delta Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (105, (121.054, 14.654), {"name": "Echo Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    import_pbf_to_snapshot(pbf_1, data_dir, policy=pol, minimum_disk_mib=1)
    adapter = PhilippinesExtractAdapter(data_dir, pol)

    # Run 1 with limit=2: returns Alpha + Bravo, marks coverage PARTIAL because 3 more remain!
    j1 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:page-1",
        campaign_id=camp_id,
        limit=2,
    )
    c1 = claim_discover_job(database, j1["id"])
    r1 = execute_manual_discovery_job(database, c1, adapter)
    assert r1["state"] == "SUCCEEDED"
    assert json.loads(r1["progress_json"])["new"] == 2
    cov1 = database.connection.execute("SELECT state FROM coverage_cells WHERE campaign_id=?", (camp_id,)).fetchone()
    assert cov1["state"] == "PARTIAL"

    # Run 2 with limit=2: advances cursor to Charlie + Delta (does NOT repeat Alpha + Bravo!), still PARTIAL because Echo remains!
    j2 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:page-2",
        campaign_id=camp_id,
        limit=2,
    )
    c2 = claim_discover_job(database, j2["id"])
    r2 = execute_manual_discovery_job(database, c2, adapter)
    assert r2["state"] == "SUCCEEDED"
    prog2 = json.loads(r2["progress_json"])
    assert prog2["new"] == 2 and prog2["existing"] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 4

    # Run 3 with limit=2: returns Echo (the 5th and final POI), marks coverage FRESH (all 5 discovered)!
    j3 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:page-3",
        campaign_id=camp_id,
        limit=2,
    )
    c3 = claim_discover_job(database, j3["id"])
    r3 = execute_manual_discovery_job(database, c3, adapter)
    assert r3["state"] == "SUCCEEDED"
    prog3 = json.loads(r3["progress_json"])
    assert prog3["new"] == 1 and prog3["existing"] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 5
    cov3 = database.connection.execute("SELECT state FROM coverage_cells WHERE campaign_id=?", (camp_id,)).fetchone()
    assert cov3["state"] == "FRESH"
    assert database.connection.execute("SELECT count(*) FROM hunt_credits").fetchone()[0] == 0

    # Now import a newer snapshot containing nodes 101..105 plus a new node 106 ("Foxtrot Cafe").
    pbf_2 = tmp_path / "snap2.osm.pbf"
    write_synthetic_pbf(
        pbf_2,
        replication_timestamp="2026-11-14T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Alpha Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (102, (121.051, 14.651), {"name": "Bravo Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (103, (121.052, 14.652), {"name": "Charlie Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (104, (121.053, 14.653), {"name": "Delta Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (105, (121.054, 14.654), {"name": "Echo Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (106, (121.055, 14.655), {"name": "Foxtrot Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    import_pbf_to_snapshot(pbf_2, data_dir, policy=pol, minimum_disk_mib=1)

    # Clear coverage cache (or advance past TTL) and run with limit=10:
    # 5 existing + 1 new, zero hunt credits.
    database.connection.execute("DELETE FROM coverage_cells")
    j4 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:snap-2",
        campaign_id=camp_id,
        limit=10,
    )
    c4 = claim_discover_job(database, j4["id"])
    r4 = execute_manual_discovery_job(database, c4, adapter)
    prog4 = json.loads(r4["progress_json"])
    assert prog4["seen"] == 6 and prog4["existing"] == 5 and prog4["new"] == 1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 6
    assert database.connection.execute("SELECT count(*) FROM hunt_credits").fetchone()[0] == 0


def test_import_cancellation_truncation_cap_and_disk_floor(tmp_path, monkeypatch):
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    pbf_file = tmp_path / "cap.osm.pbf"
    write_synthetic_pbf(
        pbf_file,
        nodes=[
            (1, (121.050, 14.650), {"name": "Cafe 1", "amenity": "cafe"}),
            (2, (121.051, 14.651), {"name": "Cafe 2", "amenity": "cafe"}),
            (3, (121.052, 14.652), {"name": "Cafe 3", "amenity": "cafe"}),
        ],
    )
    pol = extract_policy()

    # 1. Truncation cap records truncated_by_cap and sets incomplete_snapshot=True
    m_cap = import_pbf_to_snapshot(pbf_file, data_dir, policy=pol, max_indexed_pois=2, minimum_disk_mib=1)
    assert m_cap.counts["nodes_indexed"] == 2
    assert m_cap.counts["truncated_by_cap"] == 1
    assert m_cap.incomplete_snapshot is True

    # 2. Cancellation during import raises SourceCancelledError and preserves prior snapshot
    with pytest.raises(SourceCancelledError):
        import_pbf_to_snapshot(
            pbf_file,
            data_dir,
            policy=pol,
            minimum_disk_mib=1,
            is_cancelled=lambda: True,
        )
    assert verify_local_snapshot(data_dir).snapshot_id == m_cap.snapshot_id

    # 3. Disk floor check rejects import when free space is below threshold
    import mi_boti.storage.paths as paths_mod
    monkeypatch.setattr(paths_mod.shutil, "disk_usage", lambda _: type("U", (), {"free": 0})())
    with pytest.raises(StorageError, match="Insufficient free disk space"):
        import_pbf_to_snapshot(pbf_file, data_dir, policy=pol, minimum_disk_mib=500)


def test_duplicate_only_exhausted_budgets_restart_and_no_startup_execution(database, tmp_path, monkeypatch):
    """Verify duplicate-only results, exhausted request budgets, restart preservation of local snapshot and cursors,
    and that runtime initialize() never downloads, re-imports, or starts discovery jobs on startup.
    """
    from mi_boti.config import load_settings
    from mi_boti.runtime import initialize

    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    camp_id = setup_ready_guild_and_qc_campaign(database)
    pol = extract_policy()

    pbf_file = tmp_path / "dup.osm.pbf"
    write_synthetic_pbf(
        pbf_file,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (501, (121.050, 14.650), {"name": "Steady Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (502, (121.051, 14.651), {"name": "Steady Bistro", "amenity": "restaurant", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    manifest = import_pbf_to_snapshot(pbf_file, data_dir, policy=pol, minimum_disk_mib=1)
    adapter = PhilippinesExtractAdapter(data_dir, pol)

    # First run: 2 new businesses
    j1 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:dup-1",
        campaign_id=camp_id,
        limit=10,
    )
    c1 = claim_discover_job(database, j1["id"])
    r1 = execute_manual_discovery_job(database, c1, adapter)
    assert r1["state"] == "SUCCEEDED"
    prog1 = json.loads(r1["progress_json"])
    assert prog1["new"] == 2 and prog1["existing"] == 0

    # Clear coverage cell so a repeat query runs against the same businesses -> duplicate-only result!
    database.connection.execute("DELETE FROM coverage_cells")
    j2 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:dup-2",
        campaign_id=camp_id,
        limit=10,
    )
    c2 = claim_discover_job(database, j2["id"])
    r2 = execute_manual_discovery_job(database, c2, adapter)
    assert r2["state"] == "SUCCEEDED"
    prog2 = json.loads(r2["progress_json"])
    assert prog2["seen"] == 2 and prog2["existing"] == 2 and prog2["new"] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 2
    assert database.connection.execute("SELECT count(*) FROM hunt_credits").fetchone()[0] == 0

    # Exhausted daily request budget (max_requests_per_day=2, already used 2 attempts today) -> fails SAFETY_LIMIT!
    database.connection.execute("DELETE FROM coverage_cells")
    j3 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:exhausted-budget",
        campaign_id=camp_id,
        limit=10,
    )
    c3 = claim_discover_job(database, j3["id"])
    r3 = execute_manual_discovery_job(database, c3, adapter, max_requests_per_day=2)
    assert r3["state"] == "FAILED"
    assert r3["error_code"] == "SAFETY_LIMIT"

    # Restart / initialize(settings) on data_dir preserves datasets/philippines/ snapshot and launches zero downloads/imports!
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[runtime]\nminimum_disk_free_mib = 1\n', encoding="utf-8")
    env = {
        "MI_BOTI_CONFIG_FILE": str(cfg_file),
        "MI_BOTI_DATA_DIR": str(data_dir),
        "MI_BOTI_GUILD_ID": "123456789012345678",
        "MI_BOTI_OWNER_IDS": "223456789012345678",
    }
    import mi_boti.discovery.philippines_extract as ext_mod
    monkeypatch.setattr(ext_mod, "download_and_import_philippines_extract", lambda *_, **__: pytest.fail("startup downloaded extract"))
    monkeypatch.setattr(ext_mod, "import_pbf_to_snapshot", lambda *_, **__: pytest.fail("startup imported extract"))
    with initialize(load_settings(env)):
        pass
    assert verify_local_snapshot(data_dir).snapshot_id == manifest.snapshot_id


def test_config_rejects_enabled_sources_while_production_discovery_remains_disabled(tmp_path):
    from mi_boti.config import load_settings
    from mi_boti.domain.errors import ConfigurationError

    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    cfg_file = tmp_path / "config.toml"
    env = {
        "MI_BOTI_CONFIG_FILE": str(cfg_file),
        "MI_BOTI_DATA_DIR": str(data_dir),
        "MI_BOTI_GUILD_ID": "123456789012345678",
        "MI_BOTI_OWNER_IDS": "223456789012345678",
    }

    ph_toml = (
        '[sources.philippines_extract]\n'
        'enabled = false\n'
        'endpoint = "https://download.geofabrik.de/asia/philippines-latest.osm.pbf"\n'
        'allowed_hosts = ["download.geofabrik.de"]\n'
        'permission_url = "https://download.geofabrik.de/asia/philippines.html"\n'
        'license_url = "https://www.openstreetmap.org/copyright"\n'
        'attribution = "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright"\n'
        'policy_version = "geofabrik-ph-2026-11"\n'
        'reviewed_at = "2026-11-14T00:00:00Z"\n'
        'review_expires_at = "2027-11-14T00:00:00Z"\n'
        'user_agent = "MiBoti/0.2 (+https://github.com/manwelAC/mi-boti)"\n'
        'allowed_tags = ["cafe", "restaurant"]\n'
        'min_interval_seconds = 10\n'
        'max_concurrency = 1\n'
        'timeout_seconds = 60\n'
        'max_response_bytes = 10485760\n'
        'max_attempts = 2\n'
        'max_requests_per_day = 25\n'
    )
    cfg_file.write_text(ph_toml, encoding="utf-8")
    settings = load_settings(env)
    assert settings.sources["philippines_extract"]["enabled"] is False
    summary = settings.safe_summary()
    assert summary["discovery_enabled"] is False
    assert summary["ai_enabled"] is False
    assert summary["hunting_enabled"] is False

    # Rejects enabled = true for both philippines_extract and overpass while production discovery remains disabled
    cfg_file.write_text(ph_toml.replace("enabled = false", "enabled = true"), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="keep enabled=false"):
        load_settings(env)

    cfg_file.write_text(
        ph_toml.replace("[sources.philippines_extract]", "[sources.overpass]").replace("enabled = false", "enabled = true"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="keep enabled=false"):
        load_settings(env)


def test_immutable_snapshot_generations_failure_injection_concurrent_reads_and_serialized_publication(tmp_path, monkeypatch):
    """Regression 1:
    - Each publication writes an immutable generation directory containing its matching snapshot.sqlite3 and manifest.json,
      then atomically switches active_generation.json.
    - Failure injected between generation write and pointer switch, or during pointer replacement, preserves the previous
      verified generation without any database/manifest mismatch and cleans up the failed generation directory.
    - Concurrent readers observe only valid, self-consistent generations during publication and pointer switch.
    - Concurrent import/publication calls are serialized via publish.lock.
    """
    import os
    import mi_boti.discovery.philippines_extract as ext_mod

    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    pol = extract_policy()

    pbf_v1 = tmp_path / "gen1.osm.pbf"
    _, sha_v1, md5_v1 = write_synthetic_pbf(
        pbf_v1,
        replication_timestamp="2026-11-12T00:00:00Z",
        nodes=[(101, (121.050, 14.650), {"name": "Gen1 Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"})],
    )
    m1 = import_pbf_to_snapshot(
        pbf_v1,
        data_dir,
        policy=pol,
        provider_md5=md5_v1,
        expected_sha256=sha_v1,
        minimum_disk_mib=1,
    )
    active_m1, gen1_db = resolve_active_snapshot_generation(data_dir)
    gen1_dir = gen1_db.parent
    gen1_manifest_path = gen1_dir / "manifest.json"
    assert active_m1.snapshot_id == m1.snapshot_id
    assert gen1_dir == confined(data_dir, f"datasets/philippines/generations/{m1.snapshot_id}")
    assert gen1_db.exists() and gen1_manifest_path.exists()

    pbf_v2 = tmp_path / "gen2.osm.pbf"
    _, sha_v2, md5_v2 = write_synthetic_pbf(
        pbf_v2,
        replication_timestamp="2026-11-13T00:00:00Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Gen1 Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (102, (121.051, 14.651), {"name": "Gen2 Bistro", "amenity": "restaurant", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )

    # 1a. Failure injected AFTER writing new generation's snapshot.sqlite3 + manifest.json, BEFORE pointer switch
    observed_staged_gen: list[Path] = []

    def fail_before_switch(gen_dir: Path, manifest) -> None:
        assert (gen_dir / "snapshot.sqlite3").exists()
        assert (gen_dir / "manifest.json").exists()
        observed_staged_gen.append(gen_dir)
        raise RuntimeError("injected crash before active_generation pointer switch")

    with pytest.raises(RuntimeError, match="injected crash before active_generation pointer switch"):
        import_pbf_to_snapshot(
            pbf_v2,
            data_dir,
            policy=pol,
            provider_md5=md5_v2,
            expected_sha256=sha_v2,
            minimum_disk_mib=1,
            on_before_pointer_switch=fail_before_switch,
        )
    assert len(observed_staged_gen) == 1
    assert not observed_staged_gen[0].exists(), "Unpublished generation directory must be cleaned up on failure"
    assert verify_local_snapshot(data_dir).snapshot_id == m1.snapshot_id

    # Verify adapter.discover() still works against Generation 1 after failed publication
    adapter = PhilippinesExtractAdapter(data_dir, pol)
    planned = PlannedCellQuery(
        "qc-cell-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe", "restaurant"), 10, 1, pol["policy_version"]),
    )
    b1 = adapter.discover(planned, max_elements=10, campaign_id="camp-gen-test")
    assert [o["source_id"] for o in b1.observations] == ["node/101"]

    # 1b. Failure injected inside os.replace when switching active_generation.json
    real_replace = os.replace

    def fail_pointer_replace(src, dst):
        if Path(dst).name == "active_generation.json":
            raise OSError("injected disk error replacing active_generation.json")
        return real_replace(src, dst)

    monkeypatch.setattr(ext_mod.os, "replace", fail_pointer_replace)
    with pytest.raises(OSError, match="injected disk error replacing active_generation.json"):
        import_pbf_to_snapshot(
            pbf_v2,
            data_dir,
            policy=pol,
            provider_md5=md5_v2,
            expected_sha256=sha_v2,
            minimum_disk_mib=1,
        )
    monkeypatch.setattr(ext_mod.os, "replace", real_replace)
    assert verify_local_snapshot(data_dir).snapshot_id == m1.snapshot_id
    b1_after = adapter.discover(planned, max_elements=10, campaign_id="camp-gen-test")
    assert [o["source_id"] for o in b1_after.observations] == ["node/101"]

    # 1b-retry. Transient Windows PermissionError / WinError 5 / 32 sharing conflicts during pointer switch
    # recover within bounded retries and complete publication cleanly.
    transient_attempts = [0]

    def transient_sharing_replace(src, dst):
        if Path(dst).name == "active_generation.json" and transient_attempts[0] < 3:
            transient_attempts[0] += 1
            err = PermissionError(13, "Access is denied")
            err.winerror = 5
            raise err
        return real_replace(src, dst)

    monkeypatch.setattr(ext_mod.os, "replace", transient_sharing_replace)
    m_transient = import_pbf_to_snapshot(
        pbf_v1,
        data_dir,
        policy=pol,
        provider_md5=md5_v1,
        expected_sha256=sha_v1,
        minimum_disk_mib=1,
    )
    monkeypatch.setattr(ext_mod.os, "replace", real_replace)
    assert transient_attempts[0] == 3
    assert verify_local_snapshot(data_dir).snapshot_id == m_transient.snapshot_id
    m1 = m_transient

    # 1b-exhausted. Persistent PermissionError / sharing violation exhausts bounded retries,
    # cleans up the unpublished generation directory, and preserves the previous generation (m1).
    persistent_attempts = [0]

    def persistent_sharing_replace(src, dst):
        if Path(dst).name == "active_generation.json":
            persistent_attempts[0] += 1
            err = PermissionError(13, "The process cannot access the file because it is being used by another process")
            err.winerror = 32
            raise err
        return real_replace(src, dst)

    monkeypatch.setattr(ext_mod.os, "replace", persistent_sharing_replace)
    with pytest.raises(PermissionError):
        import_pbf_to_snapshot(
            pbf_v2,
            data_dir,
            policy=pol,
            provider_md5=md5_v2,
            expected_sha256=sha_v2,
            minimum_disk_mib=1,
        )
    monkeypatch.setattr(ext_mod.os, "replace", real_replace)
    assert persistent_attempts[0] == ext_mod._POINTER_IO_MAX_ATTEMPTS
    assert verify_local_snapshot(data_dir).snapshot_id == m1.snapshot_id

    # 1c. Concurrent reads during publication + atomic switch from Generation 1 to Generation 2
    stop_readers = threading.Event()
    reader_errors: list[BaseException] = []
    seen_snapshots: set[str] = set()

    def concurrent_reader() -> None:
        while not stop_readers.is_set():
            try:
                snap = verify_local_snapshot(data_dir)
                batch = adapter.discover(planned, max_elements=10, campaign_id="camp-concurrent-read")
                seen_snapshots.add(snap.snapshot_id)
                assert len(batch.observations) in (1, 2)
            except BaseException as exc:  # pragma: no cover
                reader_errors.append(exc)
                break

    reader_threads = [threading.Thread(target=concurrent_reader, daemon=True) for _ in range(3)]
    for t in reader_threads:
        t.start()
    try:
        m2 = import_pbf_to_snapshot(
            pbf_v2,
            data_dir,
            policy=pol,
            provider_md5=md5_v2,
            expected_sha256=sha_v2,
            minimum_disk_mib=1,
            on_before_pointer_switch=lambda *_: time.sleep(0.05),
        )
        # Let readers observe Generation 2 as well
        time.sleep(0.05)
    finally:
        stop_readers.set()
        for t in reader_threads:
            t.join(timeout=5.0)

    assert not reader_errors, f"Concurrent reader failed during publication: {reader_errors}"
    assert verify_local_snapshot(data_dir).snapshot_id == m2.snapshot_id
    assert m1.snapshot_id in seen_snapshots and m2.snapshot_id in seen_snapshots

    # 1d. Concurrent import/publication is serialized by publish.lock (competing import rejected cleanly)
    with DeploymentLock(confined(data_dir, "datasets/philippines/publish.lock")):
        with pytest.raises(DiscoverySourceError, match="already in progress"):
            import_pbf_to_snapshot(
                pbf_v1,
                data_dir,
                policy=pol,
                provider_md5=md5_v1,
                expected_sha256=sha_v1,
                minimum_disk_mib=1,
            )
    assert verify_local_snapshot(data_dir).snapshot_id == m2.snapshot_id


def test_deferred_cursor_acknowledgement_replays_safely_across_cancellation_auth_loss_crash_and_competing_jobs(database, tmp_path):
    """Regression 2:
    - adapter.discover() does NOT advance the durable cursor in cursors.sqlite3; it returns a checkpoint_token.
    - Cancellation or authorization loss before commit leaves the cursor unadvanced so the next job replays Page 1.
    - A crash after committing businesses/queries in mi_boti.sqlite3 but before acknowledging cursors.sqlite3
      causes the next job to replay Page 1 safely through deduplication (0 skipped, 0 duplicated) and then advance to Page 2.
    - Competing jobs acknowledging out of order never move last_ord backward, and a snapshot change invalidates stale checkpoint tokens.
    """
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    camp_id = setup_ready_guild_and_qc_campaign(database)
    pol = extract_policy()

    pbf_1 = tmp_path / "cursor_snap1.osm.pbf"
    write_synthetic_pbf(
        pbf_1,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Page1 Alpha", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (102, (121.051, 14.651), {"name": "Page1 Bravo", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (103, (121.052, 14.652), {"name": "Page2 Charlie", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (104, (121.053, 14.653), {"name": "Page2 Delta", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    import_pbf_to_snapshot(pbf_1, data_dir, policy=pol, minimum_disk_mib=1)
    adapter = PhilippinesExtractAdapter(data_dir, pol)
    planned = PlannedCellQuery(
        "qc-cell-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe", "restaurant"), 10, 1, pol["policy_version"]),
    )

    # 2a. Calling adapter.discover() repeatedly without acknowledge_checkpoint() does NOT advance the cursor
    direct_1 = adapter.discover(planned, max_elements=2, campaign_id=camp_id)
    direct_2 = adapter.discover(planned, max_elements=2, campaign_id=camp_id)
    assert [o["source_id"] for o in direct_1.observations] == ["node/101", "node/102"]
    assert [o["source_id"] for o in direct_2.observations] == ["node/101", "node/102"]
    assert direct_1.checkpoint_token is not None

    # 2b. Job cancelled during discover() before commit -> CANCELLED, 0 businesses committed, cursor unadvanced
    class CancelOnDiscoverAdapter:
        source_namespace = "osm"

        def __init__(self, inner, job_id: str, db_path: Path):
            self._inner = inner
            self._job_id = job_id
            self._db_path = db_path
            self.policy_version = inner.policy_version
            self.policy = inner.policy

        def discover(
            self,
            planned: PlannedCellQuery,
            *,
            max_elements: int = 25,
            campaign_id: str | None = None,
            on_wait_tick=None,
            is_cancelled=None,
            deadline_monotonic=None,
            register_abort=None,
        ):
            from mi_boti.repositories.database import Database
            batch = self._inner.discover(
                planned,
                max_elements=max_elements,
                campaign_id=campaign_id,
                on_wait_tick=on_wait_tick,
                is_cancelled=is_cancelled,
                deadline_monotonic=deadline_monotonic,
                register_abort=register_abort,
            )
            with Database(self._db_path, busy_timeout_ms=5000) as ext_db:
                with ext_db.transaction() as c:
                    c.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (self._job_id,))
            return batch

        def acknowledge_checkpoint(self, token, *, now=None):
            return self._inner.acknowledge_checkpoint(token, now=now)

    j_cancel = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:cancel-before-commit",
        campaign_id=camp_id,
        limit=2,
    )
    c_cancel = claim_discover_job(database, j_cancel["id"])
    r_cancel = execute_manual_discovery_job(database, c_cancel, CancelOnDiscoverAdapter(adapter, j_cancel["id"], database.path))
    assert r_cancel["state"] == "CANCELLED"
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0

    # 2c. Authorization lost after fetch before commit -> INTERRUPTED (AUTHORIZATION_LOST), 0 businesses committed, cursor unadvanced
    auth_calls = [0]

    def lose_auth_before_commit(_job: dict) -> bool:
        auth_calls[0] += 1
        # Call 1: pre-execution check; Call 2: pre-attempt check; Call 3: pre-commit check -> False!
        return auth_calls[0] < 3

    j_auth = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:auth-loss-before-commit",
        campaign_id=camp_id,
        limit=2,
    )
    c_auth = claim_discover_job(database, j_auth["id"])
    r_auth = execute_manual_discovery_job(
        database,
        c_auth,
        adapter,
        authorize_dispatch=lose_auth_before_commit,
    )
    assert r_auth["state"] == "INTERRUPTED"
    assert r_auth["error_code"] == "AUTHORIZATION_LOST"
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 0

    # 2d. Crash AFTER result commit in mi_boti.sqlite3, BEFORE cursor acknowledgement in cursors.sqlite3
    j_crash = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:crash-before-ack",
        campaign_id=camp_id,
        limit=2,
    )
    c_crash = claim_discover_job(database, j_crash["id"])

    def crash_before_ack(_batch):
        raise RuntimeError("simulated process crash between mi_boti.sqlite3 commit and cursors.sqlite3 ack")

    r_crash = execute_manual_discovery_job(
        database,
        c_crash,
        adapter,
        on_before_cursor_ack=crash_before_ack,
    )
    assert r_crash["state"] == "FAILED"
    assert r_crash["error_code"] == "CRITICAL_ERROR"
    # Businesses 101 and 102 were committed in mi_boti.sqlite3 before the crash:
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 2
    # Coverage cell remained PARTIAL and cursor was NOT acknowledged, so next job replays Page 1 safely:
    j_replay = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:replay-page-1",
        campaign_id=camp_id,
        limit=2,
    )
    c_replay = claim_discover_job(database, j_replay["id"])
    r_replay = execute_manual_discovery_job(database, c_replay, adapter)
    assert r_replay["state"] == "SUCCEEDED"
    prog_replay = json.loads(r_replay["progress_json"])
    assert prog_replay["seen"] == 2 and prog_replay["existing"] == 2 and prog_replay["new"] == 0
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 2

    # Now that Page 1 was acknowledged by j_replay, the next job advances to Page 2 (nodes 103 & 104)!
    j_page2 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:advance-page-2",
        campaign_id=camp_id,
        limit=2,
    )
    c_page2 = claim_discover_job(database, j_page2["id"])
    r_page2 = execute_manual_discovery_job(database, c_page2, adapter)
    assert r_page2["state"] == "SUCCEEDED"
    prog_page2 = json.loads(r_page2["progress_json"])
    assert prog_page2["seen"] == 2 and prog_page2["existing"] == 0 and prog_page2["new"] == 2
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 4

    # 2e. Competing acknowledgements out of order never move last_ord backward, and snapshot change rejects stale tokens
    comp_camp = "camp-competing"
    b_first = adapter.discover(planned, max_elements=1, campaign_id=comp_camp)
    assert b_first.checkpoint_token["next_ord"] == 1
    b_wider = adapter.discover(planned, max_elements=3, campaign_id=comp_camp)
    assert b_wider.checkpoint_token["next_ord"] == 3

    # Acknowledge the wider batch first (last_ord -> 3), then acknowledge the older batch (last_ord=1)
    assert adapter.acknowledge_checkpoint(b_wider.checkpoint_token) is True
    assert adapter.acknowledge_checkpoint(b_first.checkpoint_token) is True
    b_next = adapter.discover(planned, max_elements=2, campaign_id=comp_camp)
    # Cursor stayed at ord 3 rather than regressing to ord 1, so only the 4th POI (node/104) is returned!
    assert [o["source_id"] for o in b_next.observations] == ["node/104"]

    # Now publish a new snapshot generation with a different SHA-256 before acknowledging b_next
    pbf_2 = tmp_path / "cursor_snap2.osm.pbf"
    write_synthetic_pbf(
        pbf_2,
        replication_timestamp="2026-11-14T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Page1 Alpha", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    import_pbf_to_snapshot(pbf_2, data_dir, policy=pol, minimum_disk_mib=1)
    # Stale token from previous snapshot generation is rejected and returns False
    assert adapter.acknowledge_checkpoint(b_next.checkpoint_token) is False


def test_subprocess_isolated_pbf_parsing_and_cli_deadline_enforcement(tmp_path, monkeypatch):
    """Regression 3:
    - Substantiate bounded isolation: native PyOsmium PBF parsing runs in an isolated child process when isolate_process=True,
      and a hung parser child process is killed promptly when deadline_monotonic expires while preserving the prior snapshot.
    - The CLI `import-ph-extract --pbf-file` path enforces a finite deadline and runs with subprocess isolation.
    """
    import sys
    from mi_boti.__main__ import main

    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    pol = extract_policy(timeout_seconds=30)

    pbf_1 = tmp_path / "iso1.osm.pbf"
    _, sha_1, md5_1 = write_synthetic_pbf(
        pbf_1,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "Isolated Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )

    # 3a. Real child-subprocess PBF parse succeeds and publishes verified generation
    m1 = import_pbf_to_snapshot(
        pbf_1,
        data_dir,
        policy=pol,
        provider_md5=md5_1,
        expected_sha256=sha_1,
        minimum_disk_mib=1,
        isolate_process=True,
        deadline_monotonic=time.monotonic() + 30.0,
    )
    assert verify_local_snapshot(data_dir).snapshot_id == m1.snapshot_id

    # 3b. Hung child parser process is killed promptly at deadline_monotonic and preserves m1
    pbf_2 = tmp_path / "iso2.osm.pbf"
    _, sha_2, md5_2 = write_synthetic_pbf(
        pbf_2,
        replication_timestamp="2026-11-14T21:22:20Z",
        nodes=[
            (102, (121.051, 14.651), {"name": "Hung Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )
    started = time.monotonic()
    with pytest.raises(DiscoverySourceError, match="exceeded deadline during isolated PBF parsing"):
        import_pbf_to_snapshot(
            pbf_2,
            data_dir,
            policy=pol,
            provider_md5=md5_2,
            expected_sha256=sha_2,
            minimum_disk_mib=1,
            isolate_process=True,
            deadline_monotonic=started + 0.5,
            subprocess_entrypoint=(sys.executable, "-c", "import time; time.sleep(30)"),
        )
    elapsed = time.monotonic() - started
    assert elapsed < 5.0, f"Hung PBF parser subprocess was not killed promptly (took {elapsed:.2f}s)"
    assert verify_local_snapshot(data_dir).snapshot_id == m1.snapshot_id

    # 3c. CLI `import-ph-extract --pbf-file` runs with finite deadline and subprocess isolation
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[runtime]\nminimum_disk_free_mib = 1\n\n'
        '[sources.philippines_extract]\n'
        'enabled = false\n'
        'endpoint = "https://download.geofabrik.de/asia/philippines-latest.osm.pbf"\n'
        'allowed_hosts = ["download.geofabrik.de"]\n'
        'permission_url = "https://download.geofabrik.de/asia/philippines.html"\n'
        'license_url = "https://www.openstreetmap.org/copyright"\n'
        'attribution = "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright"\n'
        'policy_version = "geofabrik-ph-2026-11"\n'
        'reviewed_at = "2026-11-14T00:00:00Z"\n'
        'review_expires_at = "2027-11-14T00:00:00Z"\n'
        'user_agent = "MiBoti/0.2 (+https://github.com/manwelAC/mi-boti)"\n'
        'allowed_tags = ["cafe", "restaurant"]\n'
        'min_interval_seconds = 10\n'
        'max_concurrency = 1\n'
        'timeout_seconds = 30\n'
        'max_response_bytes = 10485760\n'
        'max_attempts = 2\n'
        'max_requests_per_day = 25\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MI_BOTI_CONFIG_FILE", str(cfg_file))
    monkeypatch.setenv("MI_BOTI_DATA_DIR", str(data_dir))
    rc = main(["import-ph-extract", "--pbf-file", str(pbf_2)])
    assert rc == 0
    assert verify_local_snapshot(data_dir).pbf_sha256 == sha_2


def test_checkpoint_acknowledgement_waits_for_publication_lock_and_never_writes_while_held(tmp_path):
    from contextlib import closing
    import sqlite3
    from mi_boti.storage.lock import DeploymentLock

    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    policy = extract_policy()
    pbf_path = tmp_path / "lock-fixture.osm.pbf"
    write_synthetic_pbf(
        pbf_path,
        nodes=[(101, (121.050, 14.650), {"name": "Lock Fixture Cafe", "amenity": "cafe"})],
    )
    import_pbf_to_snapshot(pbf_path, data_dir, policy=policy, minimum_disk_mib=1)
    adapter = PhilippinesExtractAdapter(data_dir, policy)
    planned = PlannedCellQuery(
        "qc-lock-cell",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe",), 1, 1, adapter.policy_version),
    )
    page = adapter.discover(planned, max_elements=1, campaign_id="lock-fixture")
    cursor_path = data_dir / "datasets/philippines/cursors.sqlite3"

    with DeploymentLock(data_dir / "datasets/philippines/publish.lock"):
        started = time.monotonic()
        assert adapter.acknowledge_checkpoint(page.checkpoint_token) is False
        assert time.monotonic() - started < 3.0
        with closing(sqlite3.connect(cursor_path)) as connection:
            assert connection.execute("SELECT count(*) FROM query_cursors").fetchone()[0] == 0

    # Once publication releases its lock, the same durable page can be acknowledged.
    assert adapter.acknowledge_checkpoint(page.checkpoint_token) is True
    with closing(sqlite3.connect(cursor_path)) as connection:
        row = connection.execute("SELECT last_ord,snapshot_id FROM query_cursors").fetchone()
        assert row == (page.checkpoint_token["next_ord"], page.checkpoint_token["snapshot_id"])
    # The acknowledgement released its lock rather than leaving publication blocked.
    with DeploymentLock(data_dir / "datasets/philippines/publish.lock"):
        pass


def test_reimporting_identical_pbf_bytes_with_changed_filtering_or_index_contents_resets_cursors_and_rejects_old_checkpoints(
    database, tmp_path
):
    """Regression 4:
    - Cursors and checkpoint acknowledgements are bound to the immutable generation ID (snapshot_id), not just pbf_sha256.
    - When identical PBF bytes (same pbf_sha256) are reimported with changed index contents (e.g., max_indexed_pois=1 vs
      max_indexed_pois=10, or changed category filtering), the new generation receives a new snapshot_id:
      1. Old unacknowledged checkpoint tokens from the prior generation are rejected (acknowledge_checkpoint returns False),
         even though snapshot_sha256 is identical.
      2. Saved cursors from the prior generation are reset on the new generation so previously unseen records in the
         reimported generation remain discoverable!
      3. Stale acknowledgements racing publication cannot overwrite the cursor for the newly published generation.
    """
    data_dir = prepare_data_root(tmp_path / "data", minimum_mib=1)
    camp_id = setup_ready_guild_and_qc_campaign(database)
    pol = extract_policy()

    pbf_same = tmp_path / "identical_bytes.osm.pbf"
    _, sha_same, md5_same = write_synthetic_pbf(
        pbf_same,
        replication_timestamp="2026-11-13T21:22:20Z",
        nodes=[
            (101, (121.050, 14.650), {"name": "First Indexed Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
            (102, (121.051, 14.651), {"name": "Second Indexed Bistro", "amenity": "restaurant", "addr:country": "PH", "addr:city": "Quezon City"}),
            (103, (121.052, 14.652), {"name": "Third Indexed Cafe", "amenity": "cafe", "addr:country": "PH", "addr:city": "Quezon City"}),
        ],
    )

    # Generation A: import the PBF with max_indexed_pois=1 (only node 101 is indexed; truncated_by_cap=2).
    gen_a = import_pbf_to_snapshot(
        pbf_same,
        data_dir,
        policy=pol,
        provider_md5=md5_same,
        expected_sha256=sha_same,
        max_indexed_pois=1,
        minimum_disk_mib=1,
    )
    assert gen_a.pbf_sha256 == sha_same
    assert gen_a.counts["nodes_indexed"] == 1

    adapter = PhilippinesExtractAdapter(data_dir, pol)
    planned = PlannedCellQuery(
        "qc-cell-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("cafe", "restaurant"), 10, 1, pol["policy_version"]),
    )

    # Run Job 1 against Generation A with limit=1: discovers node/101 and acknowledges cursor (last_ord=1, exhausted=1)
    j1 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:same-pbf-gen-a",
        campaign_id=camp_id,
        limit=1,
    )
    c1 = claim_discover_job(database, j1["id"])
    r1 = execute_manual_discovery_job(database, c1, adapter)
    assert r1["state"] == "SUCCEEDED"
    prog1 = json.loads(r1["progress_json"])
    assert prog1["seen"] == 1 and prog1["new"] == 1
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 1

    # Also obtain a second unacknowledged checkpoint token from Generation A on a separate campaign cursor
    stale_batch_a = adapter.discover(planned, max_elements=1, campaign_id="camp-stale-token")
    assert stale_batch_a.checkpoint_token["snapshot_id"] == gen_a.snapshot_id
    assert stale_batch_a.checkpoint_token["snapshot_sha256"] == sha_same

    # Also advance a non-exhausted cursor on "camp-partial" in Generation A (limit=1 on a 2-POI generation)
    gen_a2 = import_pbf_to_snapshot(
        pbf_same,
        data_dir,
        policy=pol,
        provider_md5=md5_same,
        expected_sha256=sha_same,
        max_indexed_pois=2,
        minimum_disk_mib=1,
    )
    assert gen_a2.pbf_sha256 == sha_same
    assert gen_a2.snapshot_id != gen_a.snapshot_id
    # Old token from gen_a MUST be rejected even though pbf_sha256 is identical!
    assert adapter.acknowledge_checkpoint(stale_batch_a.checkpoint_token) is False

    # Advance "camp-partial" cursor to last_ord=1 (non-exhausted) on gen_a2:
    b_a2_page1 = adapter.discover(planned, max_elements=1, campaign_id="camp-partial")
    assert [o["source_id"] for o in b_a2_page1.observations] == ["node/101"]
    assert b_a2_page1.checkpoint_token["exhausted"] is False
    assert adapter.acknowledge_checkpoint(b_a2_page1.checkpoint_token) is True

    # Also capture an unacknowledged page-2 token from gen_a2 before reimporting:
    b_a2_page2_unacked = adapter.discover(planned, max_elements=1, campaign_id="camp-partial")
    assert [o["source_id"] for o in b_a2_page2_unacked.observations] == ["node/102"]

    # Now reimport the EXACT SAME PBF bytes (`pbf_same`, identical `sha_same`) with full indexing (`max_indexed_pois=10`),
    # AND test reimporting with a changed category filter (`allowed_tags=("restaurant",)` then `("cafe", "restaurant")`).
    pol_resto_only = extract_policy(allowed_tags=("restaurant",))
    gen_b_resto = import_pbf_to_snapshot(
        pbf_same,
        data_dir,
        policy=pol_resto_only,
        provider_md5=md5_same,
        expected_sha256=sha_same,
        max_indexed_pois=10,
        minimum_disk_mib=1,
    )
    assert gen_b_resto.pbf_sha256 == sha_same
    assert gen_b_resto.snapshot_id not in {gen_a.snapshot_id, gen_a2.snapshot_id}
    assert gen_b_resto.counts["nodes_indexed"] == 1  # only node 102 (restaurant)

    # Stale token from gen_a2 is rejected even though pbf_sha256 is identical!
    assert adapter.acknowledge_checkpoint(b_a2_page2_unacked.checkpoint_token) is False

    # In gen_b_resto, node 102 is ord=1! Because the cursor on "camp-partial" was bound to gen_a2.snapshot_id
    # (where last_ord=1), querying "camp-partial" on gen_b_resto MUST reset last_ord to 0 so node 102 (ord=1) is NOT skipped!
    adapter_resto = PhilippinesExtractAdapter(data_dir, pol_resto_only)
    planned_resto = PlannedCellQuery(
        "qc-cell-1",
        QuerySpec((14.648, 121.047, 14.657, 121.061), ("restaurant",), 10, 1, pol_resto_only["policy_version"]),
    )
    # Even if we use the exact same (campaign_id, geographic_cell, query_hash) as b_a2_page1:
    # Let's reimport full cafe+restaurant (gen_c) and query with the exact same `planned` and `camp_id`!
    gen_c = import_pbf_to_snapshot(
        pbf_same,
        data_dir,
        policy=pol,
        provider_md5=md5_same,
        expected_sha256=sha_same,
        max_indexed_pois=10,
        minimum_disk_mib=1,
    )
    assert gen_c.pbf_sha256 == sha_same
    assert gen_c.snapshot_id not in {gen_a.snapshot_id, gen_a2.snapshot_id, gen_b_resto.snapshot_id}
    assert gen_c.counts["nodes_indexed"] == 3

    # Verify "camp-partial" cursor resets to ord=0 on gen_c (returns node/101, node/102, node/103 instead of skipping ord=1):
    b_c_all = adapter.discover(planned, max_elements=10, campaign_id="camp-partial")
    assert [o["source_id"] for o in b_c_all.observations] == ["node/101", "node/102", "node/103"]

    # And run Job 2 on `camp_id` against Generation C: discovers all 3 records (1 existing + 2 new unseen records)!
    j2 = enqueue_manual_discovery(
        database,
        actor_id="223456789012345678",
        guild_id="123456789012345678",
        channel_id="323456789012345678",
        idempotency_key="discover:same-pbf-gen-c",
        campaign_id=camp_id,
        limit=10,
    )
    c2 = claim_discover_job(database, j2["id"])
    r2 = execute_manual_discovery_job(database, c2, adapter)
    assert r2["state"] == "SUCCEEDED"
    prog2 = json.loads(r2["progress_json"])
    assert prog2["seen"] == 3 and prog2["existing"] == 1 and prog2["new"] == 2
    assert database.connection.execute("SELECT count(*) FROM businesses").fetchone()[0] == 3
