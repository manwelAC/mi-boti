"""Bounded Philippines OSM PBF extract downloader, subprocess-isolated PyOsmium importer, and local snapshot adapter.

Implements docs/PHILIPPINES-EXTRACT-PLAN.md:
- Never downloads or imports automatically on bot startup, reconnect, or import.
- Enforces SSRF IP pinning, reviewed redirect policy (HTTPS only, allowlisted hosts, <=3 hops),
  TLS SNI/certificate verification, source-wide rate limiting, disk-space and byte ceilings,
  and provider MD5 error-detection plus local SHA-256 verification.
- Parses PBF in bounded subprocess isolation (`isolate_process=True`) using PyOsmium (osmium==4.3.2)
  with a disk-backed temporary SQLite scratch workspace and an enforced monotonic deadline so native
  C++ parsing hangs or crashes can be forcibly terminated without corrupting or stalling the parent process.
- Publishes immutable snapshot generations under `datasets/philippines/generations/<snapshot_id>/`
  (`snapshot.sqlite3` + `manifest.json`), serialized via an exclusive OS file lock (`publish.lock`),
  and switches the single active-generation pointer (`datasets/philippines/active_generation.json`)
  in one atomic `os.replace`, preserving the previous verified generation on any failure.
- Preserves distinct OSM node/way/relation identities, published tags, and provenance;
  distinguishes extract snapshot_observed_at from local_queried_at; labels derived
  way/relation centroids as approximate; and records skipped/incomplete geometry so
  incomplete snapshots never claim EXHAUSTED geographic coverage.
- Separates page fetching (`discover()`) from durable cursor advancement (`acknowledge_checkpoint()`),
  advancing the cursor only after candidate/registry results are durably committed under valid
  authorization and lease ownership. Unacknowledged pages replay safely through deduplication.
"""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Callable, Mapping
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from ..domain.errors import LockError
from ..domain.registry import RegistryError, encoded
from ..storage.lock import DeploymentLock
from ..storage.paths import confined, ensure_disk_space, reject_links
from .overpass import (
    ATTRIBUTION,
    DiscoveryBatch,
    DiscoverySourceError,
    SourceCancelledError,
    SourceForbiddenError,
    SourcePolicyError,
    SourceRateLimitError,
    SourceSchemaError,
    _SourceRateState,
    _get_source_rate_state,
    format_pinned_url,
    parse_retry_after,
    resolve_public_host,
)

OFFICIAL_GEOFABRIK_PH_URL = "https://download.geofabrik.de/asia/philippines-latest.osm.pbf"
OFFICIAL_GEOFABRIK_PH_MD5_URL = "https://download.geofabrik.de/asia/philippines-latest.osm.pbf.md5"
DEFAULT_ALLOWED_DOWNLOAD_HOSTS = ("download.geofabrik.de",)
MAX_EXTRACT_BYTES_DEFAULT = 1073741824  # 1 GiB ceiling for ~585 MB regional PBF
MAX_REDIRECT_HOPS = 3

SNAPSHOT_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS snapshot_meta (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL
    ) STRICT;
    """,
    """
    CREATE TABLE IF NOT EXISTS poi_records (
        ord INTEGER NOT NULL PRIMARY KEY,
        osm_type TEXT NOT NULL CHECK(osm_type IN ('node', 'way', 'relation')),
        osm_id INTEGER NOT NULL CHECK(osm_id > 0),
        category TEXT NOT NULL,
        lat REAL,
        lon REAL,
        coord_approximate INTEGER NOT NULL CHECK(coord_approximate IN (0, 1)),
        geometry_incomplete INTEGER NOT NULL CHECK(geometry_incomplete IN (0, 1)),
        name TEXT NOT NULL,
        tags_json TEXT NOT NULL,
        limitations_json TEXT NOT NULL,
        UNIQUE(osm_type, osm_id)
    ) STRICT;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_poi_category_lat_lon
    ON poi_records(category, lat, lon, ord);
    """,
)

CURSORS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS query_cursors (
    campaign_id TEXT NOT NULL,
    geographic_cell TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    last_ord INTEGER NOT NULL CHECK(last_ord >= 0),
    exhausted INTEGER NOT NULL CHECK(exhausted IN (0, 1)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(campaign_id, geographic_cell, query_hash)
) STRICT;
"""

_WINDOWS_SHARING_WINERRORS = frozenset({5, 32, 33})
_POINTER_IO_MAX_ATTEMPTS = 25
_POINTER_IO_BASE_SLEEP_SECONDS = 0.004


def _is_transient_windows_sharing_error(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in _WINDOWS_SHARING_WINERRORS


def _replace_file_with_sharing_retry(
    src: Path,
    dst: Path,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    deadline_monotonic: float | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    """Atomically replace dst with src, retrying bounded Windows sharing violations caused by concurrent readers."""
    attempt = 0
    while True:
        attempt += 1
        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("File publication cancelled during atomic pointer switch.")
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if not _is_transient_windows_sharing_error(exc) or attempt >= _POINTER_IO_MAX_ATTEMPTS:
                raise
            now_m = monotonic()
            if deadline_monotonic is not None and now_m >= deadline_monotonic:
                raise
            delay = min(_POINTER_IO_BASE_SLEEP_SECONDS * attempt, 0.04)
            if deadline_monotonic is not None:
                delay = min(delay, max(0.001, deadline_monotonic - now_m))
            sleep(delay)


def _read_text_with_sharing_retry(
    path: Path,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Read UTF-8 text from path, retrying bounded Windows sharing violations during concurrent atomic replacement."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        except OSError as exc:
            if not _is_transient_windows_sharing_error(exc) or attempt >= _POINTER_IO_MAX_ATTEMPTS:
                raise
            sleep(min(_POINTER_IO_BASE_SLEEP_SECONDS * attempt, 0.02))


def _ensure_cursors_schema(cur_conn: sqlite3.Connection) -> None:
    """Ensure query_cursors table exists and contains snapshot_id (upgrading legacy tables without snapshot_id)."""
    cur_conn.execute(CURSORS_SCHEMA_SQL)
    cols = {row[1] for row in cur_conn.execute("PRAGMA table_info(query_cursors)").fetchall()}
    if "snapshot_id" not in cols:
        cur_conn.execute("DROP TABLE query_cursors")
        cur_conn.execute(CURSORS_SCHEMA_SQL)


@dataclass(frozen=True)
class ExtractSnapshotManifest:
    snapshot_id: str
    provider_url: str
    final_download_url: str
    downloaded_at: str
    snapshot_observed_at: str
    pbf_bytes: int
    provider_md5: str | None
    pbf_sha256: str
    snapshot_db_sha256: str
    snapshot_db_bytes: int
    parser_name: str
    parser_version: str
    policy_version: str
    attribution: str
    allowed_categories: tuple[str, ...]
    counts: Mapping[str, int]
    incomplete_snapshot: bool
    limitations: tuple[str, ...]


def require_osmium():
    """Import and return osmium (PyOsmium), failing closed with SourcePolicyError if absent."""
    try:
        import osmium  # type: ignore[import-not-found]
        version = importlib.metadata.version("osmium")
        return osmium, version
    except Exception:
        raise SourcePolicyError(
            "Optional discovery dependency 'osmium==4.3.2' (PyOsmium) is not installed in this environment."
        ) from None


def parse_md5_sidecar(text: str) -> str:
    """Extract the 32-hex-character MD5 error-detection digest from a Geofabrik .md5 sidecar."""
    if not isinstance(text, str):
        raise SourceSchemaError("Provider MD5 sidecar is not valid text.")
    match = re.search(r"\b([0-9a-fA-F]{32})\b", text.strip())
    if not match:
        raise SourceSchemaError("Provider MD5 sidecar did not contain a valid 32-character hex digest.")
    return match.group(1).lower()


def validate_extract_policy(
    policy: Mapping[str, object],
    *,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    require_enabled: bool = True,
) -> dict:
    if not isinstance(policy, Mapping):
        raise SourcePolicyError("Extract discovery policy must be a mapping.")
    if require_enabled and not policy.get("enabled"):
        raise SourcePolicyError("Discovery source is disabled in configuration.")
    try:
        reviewed_at = datetime.fromisoformat(str(policy["reviewed_at"]).replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(str(policy["review_expires_at"]).replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None or expires_at.tzinfo is None:
            raise ValueError
    except (KeyError, ValueError):
        raise SourcePolicyError("Discovery source policy requires timezone-aware reviewed_at and review_expires_at.") from None
    if expires_at <= now_utc():
        raise SourcePolicyError("Discovery source policy review has expired; review terms before running discovery.")
    endpoint = str(policy.get("endpoint", ""))
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or "").lower().rstrip(".")
    allowed_hosts = tuple(str(h).lower().rstrip(".") for h in policy.get("allowed_hosts", ()))
    if (
        parsed.scheme != "https"
        or not host
        or parsed.port not in (None, 443)
        or not allowed_hosts
        or host not in allowed_hosts
    ):
        raise SourcePolicyError("Extract source endpoint violates HTTPS/host allowlist policy.")
    norm_path = parsed.path.lower()
    if (
        host == "api.openstreetmap.org"
        or "/api/0.6/" in norm_path
        or "internal" in norm_path
        or "osh.pbf" in norm_path
        or not norm_path.endswith(".osm.pbf")
    ):
        raise SourcePolicyError(
            "Extract source endpoint must point to a public regional .osm.pbf extract (never internal/history metadata or editing APIs)."
        )
    user_agent = str(policy.get("user_agent", "")).strip()
    if not user_agent or any(c in user_agent for c in "\r\n\x00"):
        raise SourcePolicyError("Extract source requires a descriptive user_agent.")
    allowed_tags = tuple(str(t) for t in policy.get("allowed_tags", ()))
    if not allowed_tags or any(t not in {"cafe", "restaurant"} for t in allowed_tags):
        raise SourcePolicyError("Extract source allowed_tags must be within approved categories (cafe, restaurant).")
    min_interval = int(policy.get("min_interval_seconds", 0))
    max_conc = int(policy.get("max_concurrency", 0))
    timeout_sec = int(policy.get("timeout_seconds", 0))
    max_bytes = int(policy.get("max_response_bytes", 0))
    max_attempts = int(policy.get("max_attempts", 0))
    max_daily = int(policy.get("max_requests_per_day", 0))
    if (
        min_interval < 10
        or max_conc != 1
        or not 1 <= timeout_sec <= 1800
        or not 1024 <= max_bytes <= 2147483648
        or not 1 <= max_attempts <= 3
        or max_daily < 1
    ):
        raise SourcePolicyError("Extract source policy limits are outside safety bounds.")
    return dict(policy)


def _acquire_download_slot(
    state: _SourceRateState,
    *,
    min_interval: float,
    op_deadline: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    is_cancelled: Callable[[], bool] | None,
    on_wait_tick: Callable[[], None] | None,
) -> None:
    while True:
        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Extract download cancelled while waiting for rate slot.")
        if on_wait_tick is not None:
            on_wait_tick()
        with state.cond:
            now = monotonic()
            if now >= op_deadline:
                raise DiscoverySourceError("Extract download timed out while waiting for source rate slot.")
            alive_resolvers = {t for t in state.active_resolver_threads if t.is_alive()}
            state.active_resolver_threads = alive_resolvers
            if alive_resolvers:
                raise DiscoverySourceError("Extract source resolver is still occupied by a timed-out DNS lookup.")
            if state.in_flight:
                wait_for = min(0.05, max(0.001, op_deadline - now))
            else:
                earliest = now
                if state.last_start is not None:
                    earliest = max(earliest, state.last_start + min_interval)
                if state.retry_not_before is not None:
                    earliest = max(earliest, state.retry_not_before)
                if earliest > op_deadline:
                    raise SourceRateLimitError(
                        "Extract source rate wait or Retry-After exceeds download deadline.",
                        retry_after_seconds=max(0.0, earliest - now),
                    )
                if earliest <= now:
                    state.in_flight = True
                    return
                wait_for = min(earliest - now, 0.25, max(0.001, op_deadline - now))
        sleep(wait_for)


def _resolve_host_bounded(
    state: _SourceRateState,
    host: str,
    port: int,
    *,
    resolver: Callable[..., list],
    op_deadline: float,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
    is_cancelled: Callable[[], bool] | None,
    on_wait_tick: Callable[[], None] | None,
) -> tuple[str, ...]:
    with state.cond:
        alive = {t for t in state.active_resolver_threads if t.is_alive()}
        state.active_resolver_threads = alive
        if alive:
            raise DiscoverySourceError("Extract source resolver is still occupied by a timed-out DNS lookup.")

    res_box: dict[str, object] = {}
    done_evt = threading.Event()

    def _dns_worker() -> None:
        try:
            res_box["ips"] = resolve_public_host(host, port, resolver=resolver)
        except BaseException as exc:
            res_box["exc"] = exc
        finally:
            with state.cond:
                state.active_resolver_threads = {
                    t for t in state.active_resolver_threads
                    if t is not threading.current_thread() and t.is_alive()
                }
                state.cond.notify_all()
            done_evt.set()

    t = threading.Thread(target=_dns_worker, name=f"mi-boti-ext-dns-{host[:20]}", daemon=True)
    with state.cond:
        state.active_resolver_threads.add(t)
    t.start()

    while not done_evt.is_set():
        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Extract download cancelled during DNS resolution.")
        if on_wait_tick is not None:
            on_wait_tick()
        now_m = monotonic()
        if now_m >= op_deadline:
            raise DiscoverySourceError("Extract source DNS resolution timed out.")
        step = min(0.02, max(0.001, op_deadline - now_m))
        if monotonic is time.monotonic and sleep is time.sleep:
            done_evt.wait(timeout=step)
        else:
            if not done_evt.wait(timeout=0.002):
                if not done_evt.is_set():
                    sleep(step)

    if "exc" in res_box:
        raise res_box["exc"]  # type: ignore[misc]
    if monotonic() >= op_deadline:
        raise DiscoverySourceError("Extract source DNS resolution exceeded deadline.")
    return res_box["ips"]  # type: ignore[return-value]


def _stream_pinned_https_to_file(
    url: str,
    target_file: Path,
    *,
    allowed_hosts: tuple[str, ...],
    user_agent: str,
    max_bytes: int,
    op_deadline: float,
    min_interval: float,
    rate_key: str,
    transport: httpx.BaseTransport | None = None,
    resolver: Callable[..., list] = socket.getaddrinfo,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    is_cancelled: Callable[[], bool] | None = None,
    on_wait_tick: Callable[[], None] | None = None,
    register_abort: Callable[[Callable[[], None]], None] | None = None,
) -> dict[str, object]:
    """Download an HTTPS resource with SSRF IP pinning, reviewed redirect hops, and streaming hash calculation."""
    current_url = url
    allowed_set = {h.lower().rstrip(".") for h in allowed_hosts}
    state = _get_source_rate_state(rate_key)

    for hop in range(MAX_REDIRECT_HOPS + 1):
        parsed = urlsplit(current_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or host not in allowed_set
        ):
            raise SourceForbiddenError(f"Download URL host '{host or current_url}' is not in the reviewed HTTPS allowlist.")
        norm_path = parsed.path.lower()
        if "internal" in norm_path or "osh.pbf" in norm_path:
            raise SourceForbiddenError("Downloading restricted OSM contributor/history files is prohibited.")

        _acquire_download_slot(
            state,
            min_interval=min_interval if hop == 0 else 0.0,
            op_deadline=op_deadline,
            monotonic=monotonic,
            sleep=sleep,
            is_cancelled=is_cancelled,
            on_wait_tick=on_wait_tick,
        )
        try:
            if is_cancelled is not None and is_cancelled():
                raise SourceCancelledError("Download cancelled before DNS resolution.")
            validated_ips = _resolve_host_bounded(
                state,
                host,
                443,
                resolver=resolver,
                op_deadline=op_deadline,
                monotonic=monotonic,
                sleep=sleep,
                is_cancelled=is_cancelled,
                on_wait_tick=on_wait_tick,
            )
            pinned_ip = validated_ips[0]
            pinned_url, ascii_host = format_pinned_url(current_url, pinned_ip)
            with state.cond:
                if hop == 0:
                    state.last_start = monotonic()

            rem = op_deadline - monotonic()
            if rem <= 0:
                raise DiscoverySourceError("Download exceeded total deadline before HTTP connect.")
            timeout = httpx.Timeout(
                rem,
                connect=min(20.0, rem),
                read=min(60.0, rem),
                write=min(20.0, rem),
                pool=min(20.0, rem),
            )
            headers = {
                "Host": ascii_host,
                "User-Agent": user_agent,
            }
            extensions = {"sni_hostname": ascii_host}
            client = httpx.Client(
                transport=transport,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            )
            if register_abort is not None:
                register_abort(client.close)
            try:
                with client:
                    with client.stream("GET", pinned_url, headers=headers, extensions=extensions) as response:
                        if is_cancelled is not None and is_cancelled():
                            raise SourceCancelledError("Download cancelled after response headers.")
                        if monotonic() > op_deadline:
                            raise DiscoverySourceError("Download response headers arrived after deadline.")
                        if 300 <= response.status_code < 400:
                            if hop >= MAX_REDIRECT_HOPS:
                                raise SourceForbiddenError("Download exceeded maximum redirect hops.")
                            loc = response.headers.get("location")
                            if not loc:
                                raise SourceForbiddenError("Redirect response is missing Location header.")
                            current_url = urljoin(current_url, loc)
                            continue
                        if response.status_code in {401, 403}:
                            raise SourceForbiddenError("Extract provider denied access (HTTP 401/403).")
                        if response.status_code == 429:
                            retry_secs = parse_retry_after(response.headers.get("retry-after"), now_utc=now_utc())
                            with state.cond:
                                now_m = monotonic()
                                wait_s = retry_secs if retry_secs is not None else min_interval
                                state.retry_not_before = max(state.retry_not_before or now_m, now_m + wait_s)
                            raise SourceRateLimitError(
                                "Extract provider rate-limited the download (HTTP 429).",
                                retry_after_seconds=retry_secs,
                            )
                        if response.status_code >= 500:
                            raise DiscoverySourceError(
                                f"Extract provider returned server error (HTTP {response.status_code})."
                            )
                        if response.status_code != 200:
                            raise DiscoverySourceError(
                                f"Extract provider returned unexpected HTTP {response.status_code}."
                            )
                        cl_header = response.headers.get("content-length")
                        expected_len: int | None = None
                        if cl_header is not None:
                            try:
                                expected_len = int(cl_header)
                            except ValueError:
                                raise SourceSchemaError("Invalid Content-Length header from extract provider.") from None
                            if expected_len < 0 or expected_len > max_bytes:
                                raise DiscoverySourceError("Extract Content-Length exceeds max_response_bytes ceiling.")

                        sha256_hasher = hashlib.sha256()
                        md5_hasher = hashlib.md5()
                        total_bytes = 0
                        with target_file.open("wb") as handle:
                            for chunk in response.iter_bytes(chunk_size=65536):
                                if is_cancelled is not None and is_cancelled():
                                    raise SourceCancelledError("Download cancelled while streaming extract.")
                                if monotonic() > op_deadline:
                                    raise DiscoverySourceError("Download streaming exceeded total deadline.")
                                if on_wait_tick is not None:
                                    on_wait_tick()
                                total_bytes += len(chunk)
                                if total_bytes > max_bytes:
                                    raise DiscoverySourceError("Downloaded extract exceeded max_response_bytes ceiling.")
                                sha256_hasher.update(chunk)
                                md5_hasher.update(chunk)
                                handle.write(chunk)
                            handle.flush()
                            os.fsync(handle.fileno())
                        if expected_len is not None and total_bytes != expected_len:
                            raise DiscoverySourceError("Downloaded extract was truncated before Content-Length bytes arrived.")
                        if total_bytes == 0:
                            raise SourceSchemaError("Downloaded extract file is empty.")
                        if monotonic() > op_deadline:
                            raise DiscoverySourceError("Download completed after total deadline.")
                        return {
                            "final_url": current_url,
                            "bytes": total_bytes,
                            "sha256": sha256_hasher.hexdigest(),
                            "md5": md5_hasher.hexdigest(),
                            "last_modified": response.headers.get("last-modified"),
                        }
            except DiscoverySourceError:
                raise
            except (httpx.TimeoutException, TimeoutError):
                raise DiscoverySourceError("Extract download timed out.") from None
            except (httpx.HTTPError, OSError):
                if is_cancelled is not None and is_cancelled():
                    raise SourceCancelledError("Extract download cancelled.") from None
                raise DiscoverySourceError("Extract download network transport failed.") from None
        finally:
            with state.cond:
                state.in_flight = False
                state.cond.notify_all()
    raise SourceForbiddenError("Download exceeded maximum redirect hops.")


def _canonicalize_osm_timestamp(raw_ts: str | None) -> str | None:
    if not raw_ts or not isinstance(raw_ts, str):
        return None
    try:
        dt = datetime.fromisoformat(raw_ts.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return None


def _copy_valid_tags(raw_tags) -> dict[str, str] | None:
    """Copy transient PyOsmium TagList into a plain bounded Python dict before advancing iterator."""
    tags: dict[str, str] = {}
    count = 0
    for tag in raw_tags:
        count += 1
        if count > 256:
            return None
        k, v = tag.k, tag.v
        if not isinstance(k, str) or not isinstance(v, str) or len(k) > 256 or len(v) > 2048:
            return None
        tags[k] = v
    return tags


def _parse_pbf_in_isolated_subprocess(
    *,
    pbf_path: Path,
    work_dir: Path,
    allowed_categories: tuple[str, ...],
    max_indexed_pois: int,
    deadline_monotonic: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    is_cancelled: Callable[[], bool] | None = None,
    on_wait_tick: Callable[[], None] | None = None,
    register_abort: Callable[[Callable[[], None]], None] | None = None,
    subprocess_entrypoint: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Execute PyOsmium PBF parsing inside a bounded child subprocess with enforced deadline/cancellation."""
    rem = deadline_monotonic - monotonic()
    if rem <= 0:
        raise DiscoverySourceError("Extract import exceeded deadline before starting isolated parser subprocess.")
    req_path = work_dir / "parse_request.json"
    out_path = work_dir / "parse_result.json"
    req_payload = {
        "pbf_path": str(pbf_path.resolve()),
        "work_dir": str(work_dir.resolve()),
        "allowed_categories": list(allowed_categories),
        "max_indexed_pois": int(max_indexed_pois),
        "timeout_seconds": max(0.05, float(rem)),
        "out_path": str(out_path.resolve()),
    }
    req_path.write_text(json.dumps(req_payload), encoding="utf-8")

    cmd = list(
        subprocess_entrypoint
        if subprocess_entrypoint is not None
        else (
            sys.executable,
            "-c",
            "import sys; from mi_boti.discovery.philippines_extract import _subprocess_parse_worker_main; raise SystemExit(_subprocess_parse_worker_main(sys.argv[1]))",
            str(req_path.resolve()),
        )
    )
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def _kill_proc() -> None:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    if register_abort is not None:
        register_abort(_kill_proc)

    try:
        while proc.poll() is None:
            if is_cancelled is not None and is_cancelled():
                _kill_proc()
                proc.wait(timeout=5.0)
                raise SourceCancelledError("Extract import cancelled during isolated PBF parsing.")
            if on_wait_tick is not None:
                on_wait_tick()
            now_m = monotonic()
            if now_m >= deadline_monotonic:
                _kill_proc()
                proc.wait(timeout=5.0)
                raise DiscoverySourceError("Extract import exceeded deadline during isolated PBF parsing.")
            step = min(0.05, max(0.002, deadline_monotonic - now_m))
            sleep(step)

        _stdout, stderr = proc.communicate(timeout=5.0)
        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Extract import cancelled during isolated PBF parsing.")
        if monotonic() > deadline_monotonic:
            raise DiscoverySourceError("Extract import exceeded deadline after isolated PBF parsing.")
        if proc.returncode != 0 or not out_path.is_file():
            err_msg = (stderr or "").strip().splitlines()[-1:]
            detail = err_msg[0] if err_msg else f"exit code {proc.returncode}"
            if "Cancelled" in detail:
                raise SourceCancelledError(detail)
            if "exceeded deadline" in detail:
                raise DiscoverySourceError(detail)
            raise SourceSchemaError(f"Isolated PBF parser failed ({detail}).")
        return json.loads(out_path.read_text(encoding="utf-8"))
    finally:
        _kill_proc()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()


def _subprocess_parse_worker_main(req_file: str) -> int:
    """Child process entrypoint for isolated PyOsmium PBF parsing."""
    try:
        req = json.loads(Path(req_file).read_text(encoding="utf-8"))
        pbf_path = Path(req["pbf_path"])
        work_dir = Path(req["work_dir"])
        allowed_categories = tuple(req["allowed_categories"])
        max_indexed_pois = int(req["max_indexed_pois"])
        deadline_m = time.monotonic() + float(req["timeout_seconds"])
        out_path = Path(req["out_path"])
        res = _parse_pbf_to_staging_db_inprocess(
            pbf_path=pbf_path,
            work_dir=work_dir,
            allowed_categories=allowed_categories,
            max_indexed_pois=max_indexed_pois,
            deadline_monotonic=deadline_m,
            monotonic=time.monotonic,
            is_cancelled=None,
            on_wait_tick=None,
        )
        out_path.write_text(json.dumps(res), encoding="utf-8")
        return 0
    except DiscoverySourceError as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    except BaseException as exc:
        print(f"SourceSchemaError: {exc}", file=sys.stderr)
        return 3


def _parse_pbf_to_staging_db_inprocess(
    *,
    pbf_path: Path,
    work_dir: Path,
    allowed_categories: tuple[str, ...],
    max_indexed_pois: int,
    deadline_monotonic: float,
    monotonic: Callable[[], float],
    is_cancelled: Callable[[], bool] | None,
    on_wait_tick: Callable[[], None] | None,
) -> dict[str, object]:
    """Run two-pass PyOsmium streaming extraction into work_dir/snapshot.sqlite3.partial."""
    osmium, _osmium_version = require_osmium()
    tag_pairs = tuple(("amenity", cat) for cat in allowed_categories)
    staging_db_path = work_dir / "snapshot.sqlite3.partial"
    coord_cache_db_path = work_dir / "poi_geom_scratch.sqlite3"

    try:
        reader = osmium.io.Reader(
            osmium.io.File(str(pbf_path), "pbf"),
            osmium.osm.osm_entity_bits.NOTHING,
        )
        try:
            header = reader.header()
            raw_header_ts = header.get("osmosis_replication_timestamp") or header.get("timestamp")
        finally:
            reader.close()
    except Exception:
        raise SourceSchemaError("Local PBF extract header is malformed or unreadable.") from None

    counts = {
        "nodes_indexed": 0,
        "ways_indexed": 0,
        "relations_indexed": 0,
        "approximate_centroids": 0,
        "incomplete_geometry": 0,
        "unsupported_relations": 0,
        "skipped_invalid_tags": 0,
        "truncated_by_cap": 0,
    }

    with closing(sqlite3.connect(coord_cache_db_path)) as scratch_conn, closing(
        sqlite3.connect(staging_db_path)
    ) as stage_conn:
        scratch_conn.execute("PRAGMA synchronous = OFF")
        scratch_conn.execute("PRAGMA journal_mode = MEMORY")
        scratch_conn.execute("CREATE TABLE needed_ways (way_id INTEGER PRIMARY KEY)")
        scratch_conn.execute(
            "CREATE TABLE way_nodes (way_id INTEGER NOT NULL, seq INTEGER NOT NULL, node_id INTEGER NOT NULL, PRIMARY KEY(way_id, seq))"
        )
        scratch_conn.execute("CREATE TABLE needed_nodes (node_id INTEGER PRIMARY KEY, lat REAL, lon REAL)")
        scratch_conn.execute(
            "CREATE TABLE pending_ways (osm_id INTEGER PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL, tags_json TEXT NOT NULL)"
        )
        scratch_conn.execute(
            "CREATE TABLE pending_relations ("
            "osm_id INTEGER PRIMARY KEY, category TEXT NOT NULL, rel_type TEXT NOT NULL, "
            "name TEXT NOT NULL, tags_json TEXT NOT NULL, members_json TEXT NOT NULL)"
        )

        stage_conn.execute("PRAGMA foreign_keys = ON")
        stage_conn.execute("PRAGMA journal_mode = WAL")
        for ddl in SNAPSHOT_SCHEMA_SQL:
            stage_conn.execute(ddl)

        total_candidates = 0
        ord_counter = 0
        pbf_file_obj = osmium.io.File(str(pbf_path), "pbf")
        try:
            fp_pois = osmium.FileProcessor(pbf_file_obj).with_filter(osmium.filter.TagFilter(*tag_pairs))
            with stage_conn, scratch_conn:
                for obj in fp_pois:
                    if is_cancelled is not None and is_cancelled():
                        raise SourceCancelledError("Extract import cancelled during POI scan.")
                    if monotonic() > deadline_monotonic:
                        raise DiscoverySourceError("Extract import exceeded deadline during POI scan.")
                    if on_wait_tick is not None and total_candidates % 250 == 0:
                        on_wait_tick()

                    tags = _copy_valid_tags(obj.tags)
                    if tags is None:
                        counts["skipped_invalid_tags"] += 1
                        continue
                    cat = tags.get("amenity", "")
                    if cat not in allowed_categories:
                        continue
                    if total_candidates >= max_indexed_pois:
                        counts["truncated_by_cap"] += 1
                        continue
                    total_candidates += 1
                    name_val = tags.get("name", "")
                    tags_str = encoded(tags)

                    if obj.is_node():
                        osm_id = int(obj.id)
                        loc = obj.location
                        if loc.valid():
                            lat, lon = round(float(loc.lat), 7), round(float(loc.lon), 7)
                            geom_inc = 0
                            lims = [
                                "OSM tags are public observations from a regional extract, not independently verified business facts."
                            ]
                        else:
                            lat, lon = None, None
                            geom_inc = 1
                            counts["incomplete_geometry"] += 1
                            lims = [
                                "OSM tags are public observations from a regional extract, not independently verified business facts.",
                                "Source supplied no usable coordinates.",
                            ]
                        ord_counter += 1
                        stage_conn.execute(
                            "INSERT OR IGNORE INTO poi_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                ord_counter,
                                "node",
                                osm_id,
                                cat,
                                lat,
                                lon,
                                0,
                                geom_inc,
                                name_val,
                                tags_str,
                                encoded(lims),
                            ),
                        )
                        counts["nodes_indexed"] += 1
                    elif obj.is_way():
                        osm_id = int(obj.id)
                        node_refs = [int(n.ref) for n in obj.nodes]
                        scratch_conn.execute(
                            "INSERT OR IGNORE INTO pending_ways VALUES (?,?,?,?)",
                            (osm_id, cat, name_val, tags_str),
                        )
                        scratch_conn.execute("INSERT OR IGNORE INTO needed_ways VALUES (?)", (osm_id,))
                        for seq_idx, nref in enumerate(node_refs):
                            scratch_conn.execute(
                                "INSERT OR IGNORE INTO way_nodes VALUES (?,?,?)",
                                (osm_id, seq_idx, nref),
                            )
                            scratch_conn.execute(
                                "INSERT OR IGNORE INTO needed_nodes(node_id) VALUES (?)",
                                (nref,),
                            )
                    elif obj.is_relation():
                        osm_id = int(obj.id)
                        rel_type = tags.get("type", "")
                        members = [(str(m.type), int(m.ref), str(m.role)) for m in obj.members]
                        scratch_conn.execute(
                            "INSERT OR IGNORE INTO pending_relations VALUES (?,?,?,?,?,?)",
                            (osm_id, cat, rel_type, name_val, tags_str, encoded(members)),
                        )
                        for m_type, m_ref, _m_role in members:
                            if m_type == "w":
                                scratch_conn.execute("INSERT OR IGNORE INTO needed_ways VALUES (?)", (m_ref,))
                            elif m_type == "n":
                                scratch_conn.execute(
                                    "INSERT OR IGNORE INTO needed_nodes(node_id) VALUES (?)",
                                    (m_ref,),
                                )
        except DiscoverySourceError:
            raise
        except Exception:
            raise SourceSchemaError("Local PBF extract stream is corrupt or truncated.") from None

        has_pending_ways = scratch_conn.execute("SELECT count(*) FROM pending_ways").fetchone()[0] > 0
        has_pending_rels = scratch_conn.execute("SELECT count(*) FROM pending_relations").fetchone()[0] > 0

        if has_pending_rels:
            needed_way_ids = {
                r[0]
                for r in scratch_conn.execute(
                    "SELECT way_id FROM needed_ways WHERE way_id NOT IN (SELECT DISTINCT way_id FROM way_nodes)"
                )
            }
            if needed_way_ids:
                try:
                    fp_ways = osmium.FileProcessor(
                        osmium.io.File(str(pbf_path), "pbf"), osmium.osm.osm_entity_bits.WAY
                    ).with_filter(osmium.filter.IdFilter(needed_way_ids))
                    with scratch_conn:
                        for w_obj in fp_ways:
                            if is_cancelled is not None and is_cancelled():
                                raise SourceCancelledError("Extract import cancelled during relation way resolution.")
                            if monotonic() > deadline_monotonic:
                                raise DiscoverySourceError("Extract import exceeded deadline during relation way resolution.")
                            wid = int(w_obj.id)
                            for seq_idx, nref in enumerate(int(n.ref) for n in w_obj.nodes):
                                scratch_conn.execute(
                                    "INSERT OR IGNORE INTO way_nodes VALUES (?,?,?)",
                                    (wid, seq_idx, nref),
                                )
                                scratch_conn.execute(
                                    "INSERT OR IGNORE INTO needed_nodes(node_id) VALUES (?)",
                                    (nref,),
                                )
                except DiscoverySourceError:
                    raise
                except Exception:
                    raise SourceSchemaError("Local PBF extract failed during member-way scan.") from None

        if has_pending_ways or has_pending_rels:
            needed_node_ids = {r[0] for r in scratch_conn.execute("SELECT node_id FROM needed_nodes")}
            if needed_node_ids:
                try:
                    fp_nodes = osmium.FileProcessor(
                        osmium.io.File(str(pbf_path), "pbf"), osmium.osm.osm_entity_bits.NODE
                    ).with_filter(osmium.filter.IdFilter(needed_node_ids))
                    with scratch_conn:
                        for idx_n, n_obj in enumerate(fp_nodes):
                            if is_cancelled is not None and is_cancelled():
                                raise SourceCancelledError("Extract import cancelled during node coordinate lookup.")
                            if monotonic() > deadline_monotonic:
                                raise DiscoverySourceError("Extract import exceeded deadline during node coordinate lookup.")
                            if on_wait_tick is not None and idx_n % 1000 == 0:
                                on_wait_tick()
                            loc = n_obj.location
                            if loc.valid():
                                scratch_conn.execute(
                                    "UPDATE needed_nodes SET lat=?, lon=? WHERE node_id=?",
                                    (round(float(loc.lat), 7), round(float(loc.lon), 7), int(n_obj.id)),
                                )
                except DiscoverySourceError:
                    raise
                except Exception:
                    raise SourceSchemaError("Local PBF extract failed during node coordinate scan.") from None

        with stage_conn:
            for w_row in scratch_conn.execute(
                "SELECT osm_id, category, name, tags_json FROM pending_ways ORDER BY osm_id ASC"
            ):
                osm_id, cat, name_val, tags_str = w_row
                coords = scratch_conn.execute(
                    "SELECT n.lat, n.lon FROM way_nodes wn "
                    "JOIN needed_nodes n ON n.node_id = wn.node_id "
                    "WHERE wn.way_id=? ORDER BY wn.seq ASC",
                    (osm_id,),
                ).fetchall()
                total_refs = len(coords)
                valid_pts = [(r[0], r[1]) for r in coords if r[0] is not None and r[1] is not None]
                lims = [
                    "OSM tags are public observations from a regional extract, not independently verified business facts."
                ]
                if total_refs >= 2 and len(valid_pts) == total_refs:
                    pts = valid_pts[:-1] if len(valid_pts) > 2 and valid_pts[0] == valid_pts[-1] else valid_pts
                    lat = round(sum(p[0] for p in pts) / len(pts), 7)
                    lon = round(sum(p[1] for p in pts) / len(pts), 7)
                    approx = 1
                    geom_inc = 0
                    counts["approximate_centroids"] += 1
                    lims.append("Coordinates are an approximate centroid derived from OSM way node locations.")
                elif valid_pts:
                    lat = round(sum(p[0] for p in valid_pts) / len(valid_pts), 7)
                    lon = round(sum(p[1] for p in valid_pts) / len(valid_pts), 7)
                    approx = 1
                    geom_inc = 1
                    counts["approximate_centroids"] += 1
                    counts["incomplete_geometry"] += 1
                    lims.append(
                        "Coordinates are an approximate centroid derived from partial OSM way nodes; geometry is incomplete."
                    )
                else:
                    lat, lon = None, None
                    approx = 0
                    geom_inc = 1
                    counts["incomplete_geometry"] += 1
                    lims.append("Source supplied no usable coordinates; way node locations were missing.")
                ord_counter += 1
                stage_conn.execute(
                    "INSERT OR IGNORE INTO poi_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ord_counter, "way", osm_id, cat, lat, lon, approx, geom_inc, name_val, tags_str, encoded(lims)),
                )
                counts["ways_indexed"] += 1

            for r_row in scratch_conn.execute(
                "SELECT osm_id, category, rel_type, name, tags_json, members_json FROM pending_relations ORDER BY osm_id ASC"
            ):
                osm_id, cat, rel_type, name_val, tags_str, members_str = r_row
                members = json.loads(members_str)
                lims = [
                    "OSM tags are public observations from a regional extract, not independently verified business facts."
                ]
                if rel_type not in {"multipolygon", "site", "building"}:
                    counts["unsupported_relations"] += 1
                    counts["incomplete_geometry"] += 1
                    lims.append(
                        f"Unsupported OSM relation type '{rel_type or 'unspecified'}'; geometry was not derived."
                    )
                    ord_counter += 1
                    stage_conn.execute(
                        "INSERT OR IGNORE INTO poi_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (ord_counter, "relation", osm_id, cat, None, None, 0, 1, name_val, tags_str, encoded(lims)),
                    )
                    counts["relations_indexed"] += 1
                    continue

                outer_members = [m for m in members if m[2] in {"outer", "", "building", "part"}] or members
                pts: list[tuple[float, float]] = []
                missing_member = False
                for m_type, m_ref, _m_role in outer_members:
                    if m_type == "w":
                        w_coords = scratch_conn.execute(
                            "SELECT n.lat, n.lon FROM way_nodes wn "
                            "JOIN needed_nodes n ON n.node_id = wn.node_id "
                            "WHERE wn.way_id=? ORDER BY wn.seq ASC",
                            (m_ref,),
                        ).fetchall()
                        if not w_coords or any(c[0] is None or c[1] is None for c in w_coords):
                            missing_member = True
                        pts.extend((c[0], c[1]) for c in w_coords if c[0] is not None and c[1] is not None)
                    elif m_type == "n":
                        n_coord = scratch_conn.execute(
                            "SELECT lat, lon FROM needed_nodes WHERE node_id=?",
                            (m_ref,),
                        ).fetchone()
                        if not n_coord or n_coord[0] is None or n_coord[1] is None:
                            missing_member = True
                        else:
                            pts.append((n_coord[0], n_coord[1]))
                    else:
                        missing_member = True

                if pts and not missing_member:
                    lat = round(sum(p[0] for p in pts) / len(pts), 7)
                    lon = round(sum(p[1] for p in pts) / len(pts), 7)
                    approx = 1
                    geom_inc = 0
                    counts["approximate_centroids"] += 1
                    lims.append("Coordinates are an approximate centroid derived from OSM relation member geometry.")
                elif pts:
                    lat = round(sum(p[0] for p in pts) / len(pts), 7)
                    lon = round(sum(p[1] for p in pts) / len(pts), 7)
                    approx = 1
                    geom_inc = 1
                    counts["approximate_centroids"] += 1
                    counts["incomplete_geometry"] += 1
                    lims.append(
                        "Coordinates are an approximate centroid derived from partial OSM relation members; geometry is incomplete."
                    )
                else:
                    lat, lon = None, None
                    approx = 0
                    geom_inc = 1
                    counts["incomplete_geometry"] += 1
                    lims.append("Source supplied no usable coordinates for relation members.")

                ord_counter += 1
                stage_conn.execute(
                    "INSERT OR IGNORE INTO poi_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ord_counter, "relation", osm_id, cat, lat, lon, approx, geom_inc, name_val, tags_str, encoded(lims)),
                )
                counts["relations_indexed"] += 1

    return {
        "raw_header_ts": raw_header_ts or "",
        "counts": counts,
    }


def import_pbf_to_snapshot(
    pbf_path: Path,
    data_dir: Path,
    *,
    policy: Mapping[str, object],
    provider_url: str = OFFICIAL_GEOFABRIK_PH_URL,
    final_download_url: str | None = None,
    downloaded_at: str | None = None,
    provider_md5: str | None = None,
    expected_sha256: str | None = None,
    minimum_disk_mib: int = 500,
    max_indexed_pois: int = 250000,
    deadline_monotonic: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    is_cancelled: Callable[[], bool] | None = None,
    on_wait_tick: Callable[[], None] | None = None,
    register_abort: Callable[[Callable[[], None]], None] | None = None,
    isolate_process: bool = False,
    subprocess_entrypoint: tuple[str, ...] | None = None,
    on_before_pointer_switch: Callable[[Path, Path], None] | None = None,
) -> ExtractSnapshotManifest:
    """Parse a local .osm.pbf file with an enforced deadline and publish an immutable generation.

    - Enforces a finite monotonic deadline across both CLI `--pbf-file` and download imports.
    - When `isolate_process=True`, executes native PyOsmium PBF parsing inside a bounded child
      subprocess so uncooperative native hangs or crashes can be forcibly killed at the deadline.
    - Serializes publication via an exclusive OS file lock (`datasets/philippines/publish.lock`).
    - Publishes each snapshot into an immutable generation directory
      `datasets/philippines/generations/<snapshot_id>/` (`snapshot.sqlite3` + `manifest.json`)
      and switches the single active-generation pointer (`datasets/philippines/active_generation.json`)
      in one atomic `os.replace`, preserving the previous verified generation on any failure.
    """
    validated_policy = validate_extract_policy(policy, now_utc=now_utc, require_enabled=False)
    _osmium, osmium_version = require_osmium()
    reject_links(pbf_path)
    reject_links(data_dir)
    if not pbf_path.is_file():
        raise DiscoverySourceError("Local PBF extract file does not exist.")
    pbf_size = pbf_path.stat().st_size
    if pbf_size <= 0:
        raise SourceSchemaError("Local PBF extract file is empty.")
    max_bytes = int(validated_policy.get("max_response_bytes", MAX_EXTRACT_BYTES_DEFAULT))
    if pbf_size > max_bytes:
        raise DiscoverySourceError("Local PBF extract exceeds max_response_bytes ceiling.")

    policy_timeout = float(validated_policy.get("timeout_seconds", 60))
    effective_deadline = (
        deadline_monotonic
        if deadline_monotonic is not None
        else (monotonic() + max(policy_timeout, 1.0))
    )
    if monotonic() >= effective_deadline:
        raise DiscoverySourceError("Extract import exceeded deadline before starting.")

    ensure_disk_space(data_dir, minimum_disk_mib, min(pbf_size, 256 * 1024 * 1024))

    dataset_dir = confined(data_dir, "datasets")
    dataset_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    ph_dir = confined(data_dir, "datasets/philippines")
    ph_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    generations_dir = confined(data_dir, "datasets/philippines/generations")
    generations_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Serialize concurrent import/publication operations using an OS-held file lock.
    publish_lock_path = confined(data_dir, "datasets/philippines/publish.lock")
    try:
        pub_lock = DeploymentLock(publish_lock_path).acquire()
    except LockError:
        raise DiscoverySourceError(
            "Another Philippines extract import or publication is already in progress."
        ) from None

    import_uuid = str(uuid4())
    work_dir = confined(data_dir, f"tmp/extract_import_{import_uuid}")
    work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging_db_path = work_dir / "snapshot.sqlite3.partial"
    gen_dir: Path | None = None
    published_successfully = False

    try:
        # Compute SHA-256 and MD5 in bounded chunks.
        sha256_h = hashlib.sha256()
        md5_h = hashlib.md5()
        with pbf_path.open("rb") as f:
            while chunk := f.read(1024 * 1024):
                if is_cancelled is not None and is_cancelled():
                    raise SourceCancelledError("Extract import cancelled during hash verification.")
                if monotonic() > effective_deadline:
                    raise DiscoverySourceError("Extract import exceeded deadline during hash verification.")
                if on_wait_tick is not None:
                    on_wait_tick()
                sha256_h.update(chunk)
                md5_h.update(chunk)
        actual_sha256 = sha256_h.hexdigest()
        actual_md5 = md5_h.hexdigest()
        if expected_sha256 is not None and actual_sha256.lower() != expected_sha256.lower():
            raise SourceSchemaError("Local PBF extract SHA-256 did not match expected digest.")
        if provider_md5 is not None and actual_md5.lower() != provider_md5.lower():
            raise SourceSchemaError("Local PBF extract MD5 did not match provider .md5 error-detection digest.")

        allowed_categories = tuple(sorted(set(str(c) for c in validated_policy["allowed_tags"])))

        if isolate_process:
            parse_out = _parse_pbf_in_isolated_subprocess(
                pbf_path=pbf_path,
                work_dir=work_dir,
                allowed_categories=allowed_categories,
                max_indexed_pois=max_indexed_pois,
                deadline_monotonic=effective_deadline,
                monotonic=monotonic,
                sleep=sleep,
                is_cancelled=is_cancelled,
                on_wait_tick=on_wait_tick,
                register_abort=register_abort,
                subprocess_entrypoint=subprocess_entrypoint,
            )
        else:
            parse_out = _parse_pbf_to_staging_db_inprocess(
                pbf_path=pbf_path,
                work_dir=work_dir,
                allowed_categories=allowed_categories,
                max_indexed_pois=max_indexed_pois,
                deadline_monotonic=effective_deadline,
                monotonic=monotonic,
                is_cancelled=is_cancelled,
                on_wait_tick=on_wait_tick,
            )

        raw_header_ts = str(parse_out.get("raw_header_ts") or "")
        counts = dict(parse_out["counts"])  # type: ignore[arg-type]

        dl_stamp = downloaded_at or now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        header_stamp = _canonicalize_osm_timestamp(raw_header_ts)
        snapshot_observed_at = header_stamp or dl_stamp
        extra_limitations: list[str] = []
        if header_stamp is None:
            extra_limitations.append(
                "PBF header lacked osmosis_replication_timestamp; snapshot_observed_at falls back to import timestamp."
            )

        incomplete_snapshot = bool(
            counts["incomplete_geometry"] > 0
            or counts["unsupported_relations"] > 0
            or counts["skipped_invalid_tags"] > 0
            or counts["truncated_by_cap"] > 0
        )
        if counts["incomplete_geometry"] > 0:
            extra_limitations.append(
                f"{counts['incomplete_geometry']} OSM element(s) had missing or incomplete geometry."
            )
        if counts["unsupported_relations"] > 0:
            extra_limitations.append(
                f"{counts['unsupported_relations']} relation(s) had unsupported relation types."
            )
        if counts["skipped_invalid_tags"] > 0:
            extra_limitations.append(
                f"{counts['skipped_invalid_tags']} element(s) were skipped due to oversized or invalid tag structures."
            )
        if counts["truncated_by_cap"] > 0:
            extra_limitations.append(
                f"Import reached max_indexed_pois={max_indexed_pois} and truncated {counts['truncated_by_cap']} element(s)."
            )

        snapshot_id = str(uuid4())
        meta_items = {
            "snapshot_id": snapshot_id,
            "provider_url": provider_url,
            "final_download_url": final_download_url or provider_url,
            "downloaded_at": dl_stamp,
            "snapshot_observed_at": snapshot_observed_at,
            "pbf_bytes": str(pbf_size),
            "provider_md5": provider_md5 or "",
            "pbf_sha256": actual_sha256,
            "parser_name": "pyosmium",
            "parser_version": osmium_version,
            "policy_version": str(validated_policy["policy_version"]),
            "attribution": ATTRIBUTION,
            "allowed_categories": encoded(list(allowed_categories)),
            "counts_json": encoded(counts),
            "incomplete_snapshot": "1" if incomplete_snapshot else "0",
            "limitations_json": encoded(extra_limitations),
        }
        with closing(sqlite3.connect(staging_db_path)) as stage_conn:
            with stage_conn:
                for k, v in meta_items.items():
                    stage_conn.execute("INSERT OR REPLACE INTO snapshot_meta VALUES (?,?)", (k, v))
            stage_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            stage_conn.execute("PRAGMA journal_mode = DELETE")
            quick_chk = stage_conn.execute("PRAGMA quick_check").fetchone()
            if not quick_chk or quick_chk[0] != "ok":
                raise SourceSchemaError("Staged snapshot database failed SQLite quick_check.")

        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Extract import cancelled before generation publication.")
        if monotonic() > effective_deadline:
            raise DiscoverySourceError("Extract import exceeded deadline before generation publication.")

        # Publish an immutable generation directory containing both snapshot.sqlite3 and manifest.json,
        # then atomically switch the single active_generation.json pointer.
        gen_dir = confined(data_dir, f"datasets/philippines/generations/{snapshot_id}")
        gen_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        gen_db_path = gen_dir / "snapshot.sqlite3"
        shutil.copy2(staging_db_path, gen_db_path)
        with gen_db_path.open("r+b") as dbf:
            os.fsync(dbf.fileno())

        db_bytes = gen_db_path.stat().st_size
        db_sha256 = hashlib.sha256(gen_db_path.read_bytes()).hexdigest()

        manifest = ExtractSnapshotManifest(
            snapshot_id=snapshot_id,
            provider_url=provider_url,
            final_download_url=final_download_url or provider_url,
            downloaded_at=dl_stamp,
            snapshot_observed_at=snapshot_observed_at,
            pbf_bytes=pbf_size,
            provider_md5=provider_md5,
            pbf_sha256=actual_sha256,
            snapshot_db_sha256=db_sha256,
            snapshot_db_bytes=db_bytes,
            parser_name="pyosmium",
            parser_version=osmium_version,
            policy_version=str(validated_policy["policy_version"]),
            attribution=ATTRIBUTION,
            allowed_categories=allowed_categories,
            counts=counts,
            incomplete_snapshot=incomplete_snapshot,
            limitations=tuple(extra_limitations),
        )
        manifest_payload = {
            "schema_version": 1,
            "snapshot_id": manifest.snapshot_id,
            "provider_url": manifest.provider_url,
            "final_download_url": manifest.final_download_url,
            "downloaded_at": manifest.downloaded_at,
            "snapshot_observed_at": manifest.snapshot_observed_at,
            "pbf_bytes": manifest.pbf_bytes,
            "provider_md5": manifest.provider_md5,
            "pbf_sha256": manifest.pbf_sha256,
            "snapshot_db_sha256": manifest.snapshot_db_sha256,
            "snapshot_db_bytes": manifest.snapshot_db_bytes,
            "parser_name": manifest.parser_name,
            "parser_version": manifest.parser_version,
            "policy_version": manifest.policy_version,
            "attribution": manifest.attribution,
            "allowed_categories": list(manifest.allowed_categories),
            "counts": dict(manifest.counts),
            "incomplete_snapshot": manifest.incomplete_snapshot,
            "limitations": list(manifest.limitations),
        }
        gen_manifest_path = gen_dir / "manifest.json"
        with gen_manifest_path.open("w", encoding="utf-8") as mf:
            mf.write(json.dumps(manifest_payload, indent=2, sort_keys=True))
            mf.flush()
            os.fsync(mf.fileno())

        # Verify the newly written immutable generation before switching the active pointer.
        _verify_generation_dir(gen_dir, expected_snapshot_id=snapshot_id)

        if on_before_pointer_switch is not None:
            on_before_pointer_switch(gen_dir, confined(data_dir, "datasets/philippines/active_generation.json"))

        pointer_payload = {
            "schema_version": 1,
            "active_snapshot_id": snapshot_id,
            "switched_at": now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        pointer_path = confined(data_dir, "datasets/philippines/active_generation.json")
        temp_pointer = confined(data_dir, f"datasets/philippines/active_generation.{import_uuid}.json.partial")
        try:
            with temp_pointer.open("w", encoding="utf-8") as pf:
                pf.write(json.dumps(pointer_payload, indent=2, sort_keys=True))
                pf.flush()
                os.fsync(pf.fileno())
            _replace_file_with_sharing_retry(
                temp_pointer,
                pointer_path,
                monotonic=monotonic,
                sleep=sleep,
                deadline_monotonic=effective_deadline,
                is_cancelled=is_cancelled,
            )
            published_successfully = True
        finally:
            temp_pointer.unlink(missing_ok=True)

        return manifest
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if not published_successfully and gen_dir is not None:
            shutil.rmtree(gen_dir, ignore_errors=True)
        pub_lock.release()


def download_and_import_philippines_extract(
    data_dir: Path,
    *,
    policy: Mapping[str, object],
    md5_url: str | None = OFFICIAL_GEOFABRIK_PH_MD5_URL,
    minimum_disk_mib: int = 500,
    max_indexed_pois: int = 250000,
    retain_pbf: bool = True,
    transport: httpx.BaseTransport | None = None,
    resolver: Callable[..., list] = socket.getaddrinfo,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    is_cancelled: Callable[[], bool] | None = None,
    on_wait_tick: Callable[[], None] | None = None,
    register_abort: Callable[[Callable[[], None]], None] | None = None,
    rate_limit_key: str | None = None,
) -> ExtractSnapshotManifest:
    """Explicitly invoked bounded download + verification + import of the Philippines OSM PBF extract.

    Never replaces the active verified snapshot if download, MD5 check, or PBF parsing fails.
    """
    validated = validate_extract_policy(policy, now_utc=now_utc, require_enabled=False)
    require_osmium()
    reject_links(data_dir)
    endpoint = str(validated["endpoint"])
    allowed_hosts = tuple(str(h) for h in validated["allowed_hosts"])
    user_agent = str(validated["user_agent"]).strip()
    max_bytes = int(validated["max_response_bytes"])
    timeout_sec = float(validated["timeout_seconds"])
    min_interval = max(10.0, float(validated["min_interval_seconds"]))
    max_attempts = min(3, int(validated["max_attempts"]))
    host = (urlsplit(endpoint).hostname or "").lower().rstrip(".")
    r_key = rate_limit_key or f"osm_extract:{host}"

    # Ensure sufficient free disk space for both the incoming PBF and staging snapshot.
    ensure_disk_space(data_dir, minimum_disk_mib, min(max_bytes, 650 * 1024 * 1024))

    dl_uuid = str(uuid4())
    work_dir = confined(data_dir, f"tmp/extract_dl_{dl_uuid}")
    work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp_pbf = work_dir / "philippines-latest.osm.pbf.partial"
    temp_md5 = work_dir / "philippines-latest.osm.pbf.md5.partial"

    try:
        expected_md5: str | None = None
        if md5_url:
            md5_deadline = monotonic() + min(30.0, timeout_sec)
            _stream_pinned_https_to_file(
                md5_url,
                temp_md5,
                allowed_hosts=allowed_hosts,
                user_agent=user_agent,
                max_bytes=65536,
                op_deadline=md5_deadline,
                min_interval=min_interval,
                rate_key=r_key,
                transport=transport,
                resolver=resolver,
                monotonic=monotonic,
                sleep=sleep,
                now_utc=now_utc,
                is_cancelled=is_cancelled,
                on_wait_tick=on_wait_tick,
                register_abort=register_abort,
            )
            expected_md5 = parse_md5_sidecar(temp_md5.read_text(encoding="utf-8", errors="replace"))

        dl_info: dict[str, object] | None = None
        last_err: DiscoverySourceError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                op_deadline = monotonic() + timeout_sec
                dl_info = _stream_pinned_https_to_file(
                    endpoint,
                    temp_pbf,
                    allowed_hosts=allowed_hosts,
                    user_agent=user_agent,
                    max_bytes=max_bytes,
                    op_deadline=op_deadline,
                    min_interval=min_interval,
                    rate_key=r_key,
                    transport=transport,
                    resolver=resolver,
                    monotonic=monotonic,
                    sleep=sleep,
                    now_utc=now_utc,
                    is_cancelled=is_cancelled,
                    on_wait_tick=on_wait_tick,
                    register_abort=register_abort,
                )
                break
            except (SourceForbiddenError, SourcePolicyError, SourceSchemaError, SourceCancelledError):
                raise
            except DiscoverySourceError as err:
                last_err = err
                temp_pbf.unlink(missing_ok=True)
                if attempt >= max_attempts:
                    raise
        assert dl_info is not None or last_err is not None
        if dl_info is None:
            raise last_err  # type: ignore[misc]

        downloaded_at = now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if expected_md5 is not None and str(dl_info["md5"]).lower() != expected_md5.lower():
            raise SourceSchemaError(
                "Downloaded PBF MD5 digest did not match provider .md5 error-detection checksum."
            )

        import_deadline = monotonic() + max(timeout_sec, 300.0)
        manifest = import_pbf_to_snapshot(
            temp_pbf,
            data_dir,
            policy=validated,
            provider_url=endpoint,
            final_download_url=str(dl_info["final_url"]),
            downloaded_at=downloaded_at,
            provider_md5=expected_md5,
            expected_sha256=str(dl_info["sha256"]),
            minimum_disk_mib=minimum_disk_mib,
            max_indexed_pois=max_indexed_pois,
            deadline_monotonic=import_deadline,
            monotonic=monotonic,
            sleep=sleep,
            now_utc=now_utc,
            is_cancelled=is_cancelled,
            on_wait_tick=on_wait_tick,
            register_abort=register_abort,
            isolate_process=(monotonic is time.monotonic and sleep is time.sleep),
        )
        if retain_pbf:
            final_pbf = confined(data_dir, "datasets/philippines/philippines-latest.osm.pbf")
            stage_pbf = confined(data_dir, f"datasets/philippines/philippines-latest.{dl_uuid}.osm.pbf.partial")
            try:
                shutil.copy2(temp_pbf, stage_pbf)
                _replace_file_with_sharing_retry(
                    stage_pbf,
                    final_pbf,
                    monotonic=monotonic,
                    sleep=sleep,
                    deadline_monotonic=import_deadline,
                    is_cancelled=is_cancelled,
                )
            finally:
                stage_pbf.unlink(missing_ok=True)
        return manifest
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _verify_generation_dir(
    gen_dir: Path,
    *,
    expected_snapshot_id: str | None = None,
) -> tuple[ExtractSnapshotManifest, Path]:
    """Verify the integrity, SHA-256, SQLite quick_check, and metadata of an immutable generation directory."""
    reject_links(gen_dir)
    manifest_path = gen_dir / "manifest.json"
    db_path = gen_dir / "snapshot.sqlite3"
    if not manifest_path.is_file() or not db_path.is_file():
        raise DiscoverySourceError("Snapshot generation directory is missing manifest.json or snapshot.sqlite3.")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise SourceSchemaError("Snapshot generation manifest.json is unreadable or malformed.") from None
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SourceSchemaError("Snapshot generation manifest schema_version is unsupported.")
    snap_id = str(raw.get("snapshot_id", "")).strip()
    if not snap_id or (expected_snapshot_id is not None and snap_id != expected_snapshot_id):
        raise SourceSchemaError("Snapshot generation ID does not match active generation pointer.")

    actual_bytes = db_path.stat().st_size
    if actual_bytes != int(raw.get("snapshot_db_bytes", -1)):
        raise SourceSchemaError("Snapshot generation database byte size does not match its manifest.")
    sha256_h = hashlib.sha256()
    with db_path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            sha256_h.update(chunk)
    if sha256_h.hexdigest() != str(raw.get("snapshot_db_sha256", "")):
        raise SourceSchemaError("Snapshot generation database SHA-256 failed integrity verification.")

    try:
        with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            chk = conn.execute("PRAGMA quick_check").fetchone()
            if not chk or chk[0] != "ok":
                raise SourceSchemaError("Snapshot generation database failed SQLite quick_check.")
            meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM snapshot_meta")}
    except sqlite3.Error:
        raise SourceSchemaError("Snapshot generation SQLite database could not be opened or verified.") from None

    if meta.get("pbf_sha256") != raw.get("pbf_sha256") or meta.get("snapshot_id") != snap_id:
        raise SourceSchemaError("Snapshot generation SQLite metadata disagrees with manifest.json.")

    manifest = ExtractSnapshotManifest(
        snapshot_id=snap_id,
        provider_url=str(raw["provider_url"]),
        final_download_url=str(raw["final_download_url"]),
        downloaded_at=str(raw["downloaded_at"]),
        snapshot_observed_at=str(raw["snapshot_observed_at"]),
        pbf_bytes=int(raw["pbf_bytes"]),
        provider_md5=raw.get("provider_md5") or None,
        pbf_sha256=str(raw["pbf_sha256"]),
        snapshot_db_sha256=str(raw["snapshot_db_sha256"]),
        snapshot_db_bytes=actual_bytes,
        parser_name=str(raw["parser_name"]),
        parser_version=str(raw["parser_version"]),
        policy_version=str(raw["policy_version"]),
        attribution=str(raw["attribution"]),
        allowed_categories=tuple(raw["allowed_categories"]),
        counts=dict(raw["counts"]),
        incomplete_snapshot=bool(raw["incomplete_snapshot"]),
        limitations=tuple(raw["limitations"]),
    )
    return manifest, db_path


def resolve_active_snapshot_generation(data_dir: Path) -> tuple[ExtractSnapshotManifest, Path]:
    """Read active_generation.json and verify its immutable snapshot generation directory."""
    reject_links(data_dir)
    pointer_path = confined(data_dir, "datasets/philippines/active_generation.json")
    try:
        raw_pointer = _read_text_with_sharing_retry(pointer_path)
    except FileNotFoundError:
        raise DiscoverySourceError("Verified Philippines extract snapshot is not present in datasets/philippines/.") from None
    except (OSError, UnicodeError):
        raise SourceSchemaError("Active generation pointer active_generation.json is unreadable or malformed.") from None
    try:
        pointer = json.loads(raw_pointer)
    except ValueError:
        raise SourceSchemaError("Active generation pointer active_generation.json is unreadable or malformed.") from None
    if not isinstance(pointer, dict) or pointer.get("schema_version") != 1:
        raise SourceSchemaError("Active generation pointer schema_version is unsupported.")
    active_id = str(pointer.get("active_snapshot_id", "")).strip()
    if not active_id or any(c in active_id for c in "/\\.."):
        raise SourceSchemaError("Active generation pointer contains an invalid snapshot_id.")
    gen_dir = confined(data_dir, f"datasets/philippines/generations/{active_id}")
    if not gen_dir.is_dir():
        raise DiscoverySourceError("Active generation directory referenced by active_generation.json does not exist.")
    return _verify_generation_dir(gen_dir, expected_snapshot_id=active_id)


def verify_local_snapshot(data_dir: Path) -> ExtractSnapshotManifest:
    """Verify the integrity, SHA-256, schema, and provenance of the active local Philippines snapshot."""
    manifest, _db_path = resolve_active_snapshot_generation(data_dir)
    return manifest


class PhilippinesExtractAdapter:
    """DiscoverySourcePort backed by the verified local Philippines OSM extract snapshot.

    - Never fetches the network extract per `/discover` command.
    - Reads the immutable generation referenced by `active_generation.json`, verifying its
      SHA-256 and policy before querying.
    - Distinguishes original `snapshot_observed_at` (`observed_at`) from `local_queried_at`.
    - Returns a `checkpoint_token` from `discover()` without mutating `cursors.sqlite3`.
      The worker calls `acknowledge_checkpoint()` ONLY after candidate/registry results and
      query/job progress are durably committed in `mi_boti.sqlite3` under valid authorization
      and lease ownership. Unacknowledged pages replay safely through deduplication.
    """

    source_namespace = "osm"

    def __init__(
        self,
        data_dir: Path,
        policy: Mapping[str, object],
        *,
        now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.data_dir = data_dir
        self.policy = dict(policy)
        self._now_utc = now_utc
        self._monotonic = monotonic
        self.validate_policy()

    @property
    def policy_version(self) -> str:
        return str(self.policy["policy_version"])

    def validate_policy(self) -> None:
        validate_extract_policy(self.policy, now_utc=self._now_utc, require_enabled=True)

    def acknowledge_checkpoint(
        self,
        checkpoint_token: Mapping[str, object],
        *,
        now: str | None = None,
    ) -> bool:
        """Advance the durable cursor in cursors.sqlite3 after candidate/registry commit succeeds.

        Binds cursors and checkpoint acknowledgements to the immutable generation ID (snapshot_id)
        as well as snapshot_sha256, acquires publish.lock so an acknowledgement cannot race an
        in-flight publication pointer switch, enforces monotonic forward progress per
        (campaign_id, geographic_cell, query_hash, snapshot_id), and refuses to overwrite a cursor
        if the active snapshot generation has changed.
        """
        if not isinstance(checkpoint_token, Mapping):
            raise SourceSchemaError("Invalid checkpoint_token for cursor acknowledgement.")
        campaign_id = str(checkpoint_token.get("campaign_id", "")).strip()
        cell_id = str(checkpoint_token.get("geographic_cell", "")).strip()
        q_hash = str(checkpoint_token.get("query_hash", "")).strip()
        snap_id = str(checkpoint_token.get("snapshot_id", "")).strip()
        snap_sha = str(checkpoint_token.get("snapshot_sha256", "")).strip()
        next_ord = int(checkpoint_token.get("next_ord", -1))
        exhausted_flag = 1 if bool(checkpoint_token.get("exhausted")) else 0
        if (
            not campaign_id
            or not cell_id
            or not q_hash
            or not snap_id
            or any(c in snap_id for c in "/\\..")
            or not snap_sha
            or next_ord < 0
        ):
            raise SourceSchemaError("Incomplete or invalid checkpoint_token fields for cursor acknowledgement.")

        # Coordinate with publish.lock so a checkpoint acknowledgement cannot race an in-flight
        # active_generation.json pointer switch. Wait briefly for a concurrent publication to finish;
        # if publication finished, active_manifest.snapshot_id will have changed and we return False.
        pub_lock_path = confined(self.data_dir, "datasets/philippines/publish.lock")
        pub_lock: DeploymentLock | None = None
        lock_deadline = self._monotonic() + 2.0
        while True:
            try:
                pub_lock = DeploymentLock(pub_lock_path).acquire()
                break
            except LockError:
                if self._monotonic() >= lock_deadline:
                    return False
                time.sleep(0.01)

        try:
            try:
                active_manifest, _ = resolve_active_snapshot_generation(self.data_dir)
            except DiscoverySourceError:
                return False
            if active_manifest.snapshot_id != snap_id or active_manifest.pbf_sha256 != snap_sha:
                return False

            stamp = now or self._now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            cursors_db_path = confined(self.data_dir, "datasets/philippines/cursors.sqlite3")
            with closing(sqlite3.connect(cursors_db_path, timeout=5.0)) as cur_conn:
                cur_conn.row_factory = sqlite3.Row
                _ensure_cursors_schema(cur_conn)
                cur_conn.execute("BEGIN IMMEDIATE")
                try:
                    cur_row = cur_conn.execute(
                        "SELECT last_ord, snapshot_id, snapshot_sha256, exhausted FROM query_cursors "
                        "WHERE campaign_id=? AND geographic_cell=? AND query_hash=?",
                        (campaign_id, cell_id, q_hash),
                    ).fetchone()
                    if (
                        cur_row is not None
                        and cur_row["snapshot_id"] == snap_id
                        and cur_row["snapshot_sha256"] == snap_sha
                    ):
                        prior_ord = int(cur_row["last_ord"])
                        prior_exh = int(cur_row["exhausted"])
                        # If the cursor was NOT exhausted, never move last_ord backward when competing jobs race.
                        if not prior_exh and next_ord < prior_ord:
                            merged_ord = prior_ord
                            merged_exh = prior_exh
                        elif not prior_exh and next_ord == prior_ord:
                            merged_ord = prior_ord
                            merged_exh = max(prior_exh, exhausted_flag)
                        else:
                            merged_ord = next_ord
                            merged_exh = exhausted_flag
                    else:
                        merged_ord = next_ord
                        merged_exh = exhausted_flag

                    cur_conn.execute(
                        "INSERT INTO query_cursors VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(campaign_id, geographic_cell, query_hash) DO UPDATE SET "
                        "snapshot_id=excluded.snapshot_id, snapshot_sha256=excluded.snapshot_sha256, "
                        "last_ord=excluded.last_ord, exhausted=excluded.exhausted, updated_at=excluded.updated_at",
                        (
                            campaign_id,
                            cell_id,
                            q_hash,
                            snap_id,
                            snap_sha,
                            merged_ord,
                            merged_exh,
                            stamp,
                        ),
                    )
                    cur_conn.commit()
                    return True
                except BaseException:
                    cur_conn.rollback()
                    raise
        finally:
            if pub_lock is not None:
                pub_lock.release()

    def discover(
        self,
        planned,
        *,
        max_elements: int = 25,
        campaign_id: str = "default",
        on_wait_tick: Callable[[], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        deadline_monotonic: float | None = None,
        register_abort: Callable[[Callable[[], None]], None] | None = None,
    ) -> DiscoveryBatch:
        self.validate_policy()
        allowed_tags = set(self.policy.get("allowed_tags", ()))
        if any(cat not in allowed_tags for cat in planned.spec.categories):
            raise SourcePolicyError("Planned query categories are not permitted by extract source policy.")
        limit = min(int(max_elements), int(planned.spec.limit), 100)
        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Discovery query cancelled before local snapshot lookup.")
        if deadline_monotonic is not None and self._monotonic() >= deadline_monotonic:
            raise DiscoverySourceError("Discovery query exceeded deadline before local snapshot lookup.")
        if on_wait_tick is not None:
            on_wait_tick()

        manifest, db_path = resolve_active_snapshot_generation(self.data_dir)
        if manifest.policy_version != self.policy_version:
            raise SourcePolicyError("Active local extract snapshot policy_version does not match configured policy.")

        cursors_db_path = confined(self.data_dir, "datasets/philippines/cursors.sqlite3")
        south, west, north, east = planned.spec.bbox
        categories = tuple(sorted(set(planned.spec.categories)))
        q_hash = planned.spec.fingerprint
        cell_id = str(planned.geographic_cell)
        local_queried_at = self._now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        with closing(sqlite3.connect(cursors_db_path, timeout=5.0)) as cur_conn:
            cur_conn.row_factory = sqlite3.Row
            _ensure_cursors_schema(cur_conn)
            cur_row = cur_conn.execute(
                "SELECT last_ord, snapshot_id, snapshot_sha256, exhausted FROM query_cursors "
                "WHERE campaign_id=? AND geographic_cell=? AND query_hash=?",
                (campaign_id, cell_id, q_hash),
            ).fetchone()

            if (
                cur_row is not None
                and cur_row["snapshot_id"] == manifest.snapshot_id
                and cur_row["snapshot_sha256"] == manifest.pbf_sha256
            ):
                last_ord = 0 if cur_row["exhausted"] else int(cur_row["last_ord"])
            else:
                last_ord = 0

        with closing(sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5.0)) as conn:
            conn.row_factory = sqlite3.Row
            if register_abort is not None:
                register_abort(conn.interrupt)

            placeholders = ",".join("?" for _ in categories)
            # Fetch limit + 1 rows after last_ord to detect whether more matching records remain in this cell.
            rows = conn.execute(
                f"SELECT * FROM poi_records "
                f"WHERE category IN ({placeholders}) "
                f"AND lat IS NOT NULL AND lon IS NOT NULL "
                f"AND lat >= ? AND lat <= ? AND lon >= ? AND lon <= ? "
                f"AND ord > ? "
                f"ORDER BY ord ASC LIMIT ?",
                (*categories, south, north, west, east, last_ord, limit + 1),
            ).fetchall()

            if is_cancelled is not None and is_cancelled():
                raise SourceCancelledError("Discovery query cancelled during local snapshot read.")
            if deadline_monotonic is not None and self._monotonic() > deadline_monotonic:
                raise DiscoverySourceError("Discovery query exceeded deadline during local snapshot read.")

            has_more_pages = len(rows) > limit
            page_rows = rows[:limit]
            new_last_ord = int(page_rows[-1]["ord"]) if page_rows else last_ord
            cell_exhausted_in_snapshot = not has_more_pages

        checkpoint_token = {
            "campaign_id": campaign_id,
            "geographic_cell": cell_id,
            "query_hash": q_hash,
            "snapshot_id": manifest.snapshot_id,
            "snapshot_sha256": manifest.pbf_sha256,
            "previous_ord": last_ord,
            "next_ord": new_last_ord,
            "exhausted": cell_exhausted_in_snapshot,
        }

        observations = []
        any_incomplete_row = False
        for r in page_rows:
            tags = json.loads(r["tags_json"])
            row_lims = list(json.loads(r["limitations_json"]))
            if r["geometry_incomplete"]:
                any_incomplete_row = True
            address = {
                field: tags["addr:" + tag]
                for field, tag in (
                    ("country", "country"),
                    ("city", "city"),
                    ("street", "street"),
                    ("house_number", "housenumber"),
                    ("unit", "unit"),
                    ("postcode", "postcode"),
                )
                if "addr:" + tag in tags
            }
            osm_type = r["osm_type"]
            osm_id = int(r["osm_id"])
            coords = {"latitude": float(r["lat"]), "longitude": float(r["lon"])}
            if r["coord_approximate"]:
                coords["approximate"] = True
            observations.append(
                {
                    "name": r["name"],
                    "source_namespace": "osm",
                    "source_id": f"{osm_type}/{osm_id}",
                    "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    "observed_at": manifest.snapshot_observed_at,
                    "local_queried_at": local_queried_at,
                    "snapshot_id": manifest.snapshot_id,
                    "snapshot_sha256": manifest.pbf_sha256,
                    "policy_version": self.policy_version,
                    "attribution": ATTRIBUTION,
                    "address": address,
                    "website": tags.get("website", tags.get("contact:website")),
                    "phone": tags.get("phone", tags.get("contact:phone")),
                    "email": tags.get("email", tags.get("contact:email")),
                    "coordinates": coords,
                    "category": r["category"],
                    "limitations": row_lims,
                }
            )

        batch_lims = list(manifest.limitations)
        if has_more_pages:
            batch_lims.append(
                "Local snapshot query reached the per-query observation cap; additional matching records remain after the saved cursor."
            )
        if manifest.incomplete_snapshot:
            batch_lims.append(
                "Local extract snapshot has recorded geometry or truncation limitations; complete geographic coverage is not established."
            )
        partial = bool(has_more_pages or manifest.incomplete_snapshot or any_incomplete_row)
        return DiscoveryBatch(
            observations=tuple(observations),
            partial=partial,
            limitations=tuple(batch_lims),
            attribution=ATTRIBUTION,
            checkpoint_token=checkpoint_token,
        )
