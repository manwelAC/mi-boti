"""Bounded Overpass JSON translation and SSRF-pinned, rate-limited source adapter."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ipaddress
import json
import math
import socket
import threading
import time
from typing import Callable, Mapping
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..domain.errors import AppError
from ..domain.registry import RegistryError, encoded

ATTRIBUTION = "© OpenStreetMap contributors — ODbL; https://www.openstreetmap.org/copyright"


class DiscoverySourceError(AppError):
    code = "SOURCE_UNAVAILABLE"


class SourcePolicyError(DiscoverySourceError):
    code = "POLICY_UNKNOWN"


class SourceForbiddenError(DiscoverySourceError):
    code = "SOURCE_FORBIDDEN"


class SourceRateLimitError(DiscoverySourceError):
    code = "SOURCE_RATE_LIMIT"

    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class SourceSchemaError(DiscoverySourceError):
    code = "SOURCE_SCHEMA_CHANGED"


class SourceCancelledError(DiscoverySourceError):
    code = "OPERATOR_CANCELLED"


def validate_public_ip(raw_ip: str) -> str:
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        raise SourceForbiddenError("Source resolved to an invalid IP address.") from None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        mapped = addr.ipv4_mapped
        if (
            not mapped.is_global
            or mapped.is_private
            or mapped.is_loopback
            or mapped.is_link_local
            or mapped.is_multicast
            or mapped.is_reserved
            or mapped.is_unspecified
        ):
            raise SourceForbiddenError("Source resolved to a non-global IPv4-mapped IPv6 address.")
    if (
        not addr.is_global
        or addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    ):
        raise SourceForbiddenError("Source resolved to a forbidden non-global network address.")
    return str(addr)


def resolve_public_host(
    hostname: str,
    port: int = 443,
    *,
    resolver: Callable[..., list] = socket.getaddrinfo,
) -> tuple[str, ...]:
    if not isinstance(hostname, str) or not hostname:
        raise SourceForbiddenError("Source hostname is missing.")
    try:
        ascii_host = hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise SourceForbiddenError("Source hostname failed IDNA validation.") from None
    if ascii_host == "localhost" or ascii_host.endswith((".localhost", ".local", ".internal")):
        raise SourceForbiddenError("Localhost and internal source hostnames are prohibited.")
    try:
        infos = resolver(ascii_host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise DiscoverySourceError("Could not resolve discovery source hostname.") from None
    if not infos:
        raise DiscoverySourceError("Discovery source hostname returned no addresses.")
    validated = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        # Every returned answer must be globally routable; mixed public/private answers fail closed.
        ip_str = validate_public_ip(sockaddr[0])
        if ip_str not in validated:
            validated.append(ip_str)
    if not validated:
        raise SourceForbiddenError("No valid global IP address available for discovery source.")
    return tuple(validated)


def format_pinned_url(endpoint: str, pinned_ip: str) -> tuple[str, str]:
    """Rewrite endpoint URL host to literal pinned_ip and return (pinned_url, ascii_host)."""
    parsed = urlsplit(endpoint)
    ascii_host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    ip_obj = ipaddress.ip_address(pinned_ip)
    host_literal = f"[{ip_obj}]" if isinstance(ip_obj, ipaddress.IPv6Address) else str(ip_obj)
    netloc = f"{host_literal}:{parsed.port}" if parsed.port else host_literal
    pinned_url = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    return pinned_url, ascii_host


def parse_retry_after(raw_value: str | None, *, now_utc: datetime) -> float | None:
    if not raw_value:
        return None
    text = raw_value.strip()
    if not text:
        return None
    try:
        seconds = float(text)
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (dt - now_utc).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass
class _SourceRateState:
    cond: threading.Condition = field(default_factory=threading.Condition)
    in_flight: bool = False
    last_start: float | None = None
    retry_not_before: float | None = None
    active_resolver_threads: set[threading.Thread] = field(default_factory=set)


_GLOBAL_SOURCE_RATES_GUARD = threading.Lock()
_GLOBAL_SOURCE_RATES: dict[str, _SourceRateState] = {}


def _get_source_rate_state(key: str) -> _SourceRateState:
    with _GLOBAL_SOURCE_RATES_GUARD:
        state = _GLOBAL_SOURCE_RATES.get(key)
        if state is None:
            state = _SourceRateState()
            _GLOBAL_SOURCE_RATES[key] = state
        return state


def active_resolver_worker_count(rate_key: str | None = None) -> int:
    """Return the number of currently alive DNS resolver threads across source rate limiters."""
    with _GLOBAL_SOURCE_RATES_GUARD:
        states = (
            [_GLOBAL_SOURCE_RATES[rate_key]]
            if rate_key is not None and rate_key in _GLOBAL_SOURCE_RATES
            else ([] if rate_key is not None else list(_GLOBAL_SOURCE_RATES.values()))
        )
    count = 0
    for state in states:
        with state.cond:
            alive = {t for t in state.active_resolver_threads if t.is_alive()}
            state.active_resolver_threads = alive
            count += len(alive)
    return count


def shutdown_resolver_workers(*, timeout: float = 1.0, rate_key: str | None = None) -> dict[str, object]:
    """Wait up to timeout seconds for tracked DNS resolver threads to exit.

    Never claims threads were terminated if they remain detached/blocked in OS DNS resolution.
    """
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _GLOBAL_SOURCE_RATES_GUARD:
        states = (
            [_GLOBAL_SOURCE_RATES[rate_key]]
            if rate_key is not None and rate_key in _GLOBAL_SOURCE_RATES
            else ([] if rate_key is not None else list(_GLOBAL_SOURCE_RATES.values()))
        )
    threads: list[threading.Thread] = []
    for state in states:
        with state.cond:
            threads.extend(t for t in state.active_resolver_threads if t.is_alive())
    for t in threads:
        rem = max(0.0, deadline - time.monotonic())
        t.join(timeout=rem)
    remaining = active_resolver_worker_count(rate_key=rate_key)
    return {"drained": remaining == 0, "remaining": remaining}


def reset_source_rate_limiters() -> None:
    """Clear shared process-wide source rate-limiters (for isolated test runs)."""
    with _GLOBAL_SOURCE_RATES_GUARD:
        _GLOBAL_SOURCE_RATES.clear()


class OverpassDiscoveryAdapter:
    """Policy-gated, source-wide rate-limited, SSRF-pinned Overpass API adapter."""

    source_namespace = "osm"

    def __init__(
        self,
        policy: Mapping[str, object],
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Callable[..., list] = socket.getaddrinfo,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        rate_limit_key: str | None = None,
    ):
        self.policy = dict(policy)
        self._transport = transport
        self._resolver = resolver
        self._monotonic = monotonic
        self._sleep = sleep
        self._now_utc = now_utc
        self.validate_policy()
        endpoint_host = (urlsplit(str(self.policy["endpoint"])).hostname or "").lower().rstrip(".")
        self._rate_key = rate_limit_key or f"{self.source_namespace}:{endpoint_host}"

    @property
    def policy_version(self) -> str:
        return str(self.policy["policy_version"])

    def validate_policy(self) -> None:
        if not self.policy.get("enabled"):
            raise SourcePolicyError("Discovery source is disabled in configuration.")
        try:
            expires_at = datetime.fromisoformat(str(self.policy["review_expires_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            raise SourcePolicyError("Discovery source policy review_expires_at is invalid.") from None
        if expires_at <= self._now_utc():
            raise SourcePolicyError("Discovery source policy review has expired; review terms before running discovery.")
        endpoint = str(self.policy.get("endpoint", ""))
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed_hosts = [str(h).lower().rstrip(".") for h in self.policy.get("allowed_hosts", ())]
        if parsed.scheme != "https" or not host or parsed.port not in (None, 443) or host not in allowed_hosts:
            raise SourcePolicyError("Discovery source endpoint violates host/HTTPS allowlist policy.")
        # OSM editing API (/api/0.6/*) is strictly prohibited for read-only discovery projects.
        norm_path = parsed.path.rstrip("/").lower()
        if host == "api.openstreetmap.org" or "/api/0.6/" in norm_path or norm_path.endswith("/map.json"):
            raise SourcePolicyError(
                "The OpenStreetMap editing API (/api/0.6/map.json) is prohibited for read-only business discovery."
            )
        if int(self.policy.get("min_interval_seconds", 0)) < 10 or int(self.policy.get("max_concurrency", 0)) != 1:
            raise SourcePolicyError("Overpass source requires min_interval_seconds >= 10 and max_concurrency == 1.")

    def _acquire_slot(
        self,
        state: _SourceRateState,
        *,
        min_interval: float,
        op_deadline: float,
        job_deadline: float | None,
        on_wait_tick: Callable[[], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> None:
        while True:
            if is_cancelled is not None and is_cancelled():
                raise SourceCancelledError("Discovery request cancelled while waiting for source rate slot.")
            if on_wait_tick is not None:
                on_wait_tick()
            with state.cond:
                now = self._monotonic()
                if now >= op_deadline:
                    if job_deadline is not None and op_deadline <= job_deadline and now >= job_deadline:
                        raise SourceRateLimitError(
                            "Source rate limit or Retry-After exceeds remaining job deadline.",
                            retry_after_seconds=0.0,
                        )
                    raise DiscoverySourceError("Discovery source request timed out while waiting for rate slot.")
                wait_for = 0.0
                alive_resolvers = {t for t in state.active_resolver_threads if t.is_alive()}
                state.active_resolver_threads = alive_resolvers
                if alive_resolvers:
                    raise DiscoverySourceError(
                        "Discovery source resolver is still occupied by an uncompleted timed-out DNS lookup."
                    )
                if state.in_flight:
                    wait_for = min(0.05, max(0.001, op_deadline - now))
                else:
                    earliest = now
                    if state.last_start is not None:
                        earliest = max(earliest, state.last_start + min_interval)
                    if state.retry_not_before is not None:
                        earliest = max(earliest, state.retry_not_before)
                    if job_deadline is not None and earliest > job_deadline:
                        raise SourceRateLimitError(
                            "Source rate limit or Retry-After exceeds remaining job deadline.",
                            retry_after_seconds=max(0.0, earliest - now),
                        )
                    if earliest > op_deadline:
                        raise DiscoverySourceError("Discovery source rate wait exceeds total request timeout.")
                    if earliest <= now:
                        state.in_flight = True
                        return
                    wait_for = min(earliest - now, 0.25, max(0.001, op_deadline - now))
            # Sleep outside the condition lock in bounded increments so heartbeats and cancellation stay responsive.
            self._sleep(wait_for)

    def _resolve_public_host_bounded(
        self,
        state: _SourceRateState,
        host: str,
        port: int,
        *,
        op_deadline: float,
        on_wait_tick: Callable[[], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> tuple[str, ...]:
        """Run DNS resolution in a tracked, bounded daemon thread so stalled DNS cannot leak threads or hang shutdown."""
        with state.cond:
            alive = {t for t in state.active_resolver_threads if t.is_alive()}
            state.active_resolver_threads = alive
            if alive:
                raise DiscoverySourceError(
                    "Discovery source resolver is still occupied by an uncompleted timed-out DNS lookup."
                )

        res_box: dict[str, object] = {}
        done_evt = threading.Event()

        def _dns_target() -> None:
            try:
                res_box["ips"] = resolve_public_host(host, port, resolver=self._resolver)
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

        dns_thread = threading.Thread(
            target=_dns_target,
            name=f"mi-boti-dns-{host[:24]}",
            daemon=True,
        )
        with state.cond:
            state.active_resolver_threads.add(dns_thread)
        dns_thread.start()

        while not done_evt.is_set():
            if is_cancelled is not None and is_cancelled():
                raise SourceCancelledError("Discovery request cancelled during DNS resolution.")
            if on_wait_tick is not None:
                on_wait_tick()
            now_m = self._monotonic()
            if now_m >= op_deadline:
                raise DiscoverySourceError("Discovery source DNS resolution timed out.")
            wait_step = min(0.02, max(0.001, op_deadline - now_m))
            if self._monotonic is time.monotonic and self._sleep is time.sleep:
                done_evt.wait(timeout=wait_step)
            else:
                if not done_evt.wait(timeout=0.002):
                    if not done_evt.is_set():
                        self._sleep(wait_step)

        if is_cancelled is not None and is_cancelled():
            raise SourceCancelledError("Discovery request cancelled during DNS resolution.")
        if "exc" in res_box:
            raise res_box["exc"]  # type: ignore[misc]
        if self._monotonic() >= op_deadline:
            raise DiscoverySourceError("Discovery source request exceeded total deadline during DNS resolution.")
        return res_box["ips"]  # type: ignore[return-value]

    def discover(
        self,
        planned,
        *,
        max_elements: int = 25,
        on_wait_tick: Callable[[], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        deadline_monotonic: float | None = None,
        register_abort: Callable[[Callable[[], None]], None] | None = None,
    ) -> "DiscoveryBatch":
        self.validate_policy()
        allowed_tags = set(self.policy.get("allowed_tags", ()))
        if any(cat not in allowed_tags for cat in planned.spec.categories):
            raise SourcePolicyError("Planned query categories are not permitted by source policy.")
        limit = min(int(max_elements), int(planned.spec.limit), 100)
        query_spec = type(planned.spec)(
            bbox=planned.spec.bbox,
            categories=planned.spec.categories,
            limit=limit,
            target_version=planned.spec.target_version,
            policy_version=self.policy_version,
        )
        endpoint = str(self.policy["endpoint"])
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").lower().rstrip(".")
        max_bytes = min(int(self.policy.get("max_response_bytes", 5242880)), 5242880)
        timeout_sec = min(float(self.policy.get("timeout_seconds", 20)), 30.0)
        min_interval = max(float(self.policy.get("min_interval_seconds", 10)), 10.0)
        user_agent = str(self.policy.get("user_agent", "")).strip()
        if not user_agent:
            raise SourcePolicyError("Discovery source requires a descriptive user_agent.")

        # Total monotonic deadline across slot wait, DNS, connect, response headers, and body streaming.
        start_m = self._monotonic()
        op_deadline = start_m + timeout_sec
        if deadline_monotonic is not None:
            op_deadline = min(op_deadline, deadline_monotonic)

        state = _get_source_rate_state(self._rate_key)
        self._acquire_slot(
            state,
            min_interval=min_interval,
            op_deadline=op_deadline,
            job_deadline=deadline_monotonic,
            on_wait_tick=on_wait_tick,
            is_cancelled=is_cancelled,
        )
        try:
            if is_cancelled is not None and is_cancelled():
                raise SourceCancelledError("Discovery request cancelled before dispatch.")
            if on_wait_tick is not None:
                on_wait_tick()
            if self._monotonic() >= op_deadline:
                raise DiscoverySourceError("Discovery source request exceeded total deadline before DNS resolution.")

            # Resolve DNS immediately before connection in a bounded tracked worker; reject if ANY returned IP is non-global.
            validated_ips = self._resolve_public_host_bounded(
                state,
                host,
                443,
                op_deadline=op_deadline,
                on_wait_tick=on_wait_tick,
                is_cancelled=is_cancelled,
            )
            if self._monotonic() >= op_deadline:
                raise DiscoverySourceError("Discovery source request exceeded total deadline during DNS resolution.")
            pinned_ip = validated_ips[0]
            pinned_url, ascii_host = format_pinned_url(endpoint, pinned_ip)

            with state.cond:
                state.last_start = self._monotonic()

            rem_before_http = op_deadline - self._monotonic()
            if rem_before_http <= 0:
                raise DiscoverySourceError("Discovery source request exceeded total deadline before HTTP connect.")

            timeout = httpx.Timeout(
                rem_before_http,
                connect=min(10.0, rem_before_http),
                read=rem_before_http,
                write=rem_before_http,
                pool=rem_before_http,
            )
            headers = {
                "Host": ascii_host,
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
            extensions = {"sni_hostname": ascii_host}
            client = httpx.Client(
                transport=self._transport,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            )
            if register_abort is not None:
                register_abort(client.close)
            try:
                with client:
                    with client.stream(
                        "POST",
                        pinned_url,
                        data={"data": query_spec.overpass_query()},
                        headers=headers,
                        extensions=extensions,
                    ) as response:
                        if is_cancelled is not None and is_cancelled():
                            raise SourceCancelledError("Discovery request cancelled after response headers.")
                        if self._monotonic() > op_deadline:
                            raise DiscoverySourceError("Discovery source response headers arrived after total deadline.")
                        if 300 <= response.status_code < 400:
                            raise SourceForbiddenError("Discovery source returned an unapproved redirect.")
                        if response.status_code in {401, 403}:
                            raise SourceForbiddenError("Discovery source denied access (HTTP 401/403).")
                        if response.status_code == 429:
                            retry_secs = parse_retry_after(
                                response.headers.get("retry-after"),
                                now_utc=self._now_utc(),
                            )
                            with state.cond:
                                now_m = self._monotonic()
                                wait_s = retry_secs if retry_secs is not None else min_interval
                                state.retry_not_before = max(state.retry_not_before or now_m, now_m + wait_s)
                            raise SourceRateLimitError(
                                "Discovery source rate-limited the request (HTTP 429).",
                                retry_after_seconds=retry_secs,
                            )
                        if response.status_code >= 500:
                            retry_secs = parse_retry_after(
                                response.headers.get("retry-after"),
                                now_utc=self._now_utc(),
                            )
                            if retry_secs is not None:
                                with state.cond:
                                    now_m = self._monotonic()
                                    state.retry_not_before = max(state.retry_not_before or now_m, now_m + retry_secs)
                            raise DiscoverySourceError(
                                f"Discovery source returned server error (HTTP {response.status_code})."
                            )
                        if response.status_code != 200:
                            raise DiscoverySourceError(
                                f"Discovery source returned unexpected HTTP {response.status_code}."
                            )
                        content_type = response.headers.get("content-type", "").lower()
                        if "json" not in content_type:
                            raise SourceSchemaError("Discovery source did not return JSON content-type.")
                        chunks = []
                        total_bytes = 0
                        for chunk in response.iter_bytes():
                            if is_cancelled is not None and is_cancelled():
                                raise SourceCancelledError("Discovery request cancelled while streaming response.")
                            if self._monotonic() > op_deadline:
                                raise DiscoverySourceError("Discovery source streaming exceeded total deadline.")
                            if on_wait_tick is not None:
                                on_wait_tick()
                            total_bytes += len(chunk)
                            if total_bytes > max_bytes:
                                raise DiscoverySourceError("Discovery source response exceeded max_response_bytes.")
                            chunks.append(chunk)
                        if self._monotonic() > op_deadline:
                            raise DiscoverySourceError("Discovery source response completed after total deadline.")
            except DiscoverySourceError:
                raise
            except (httpx.TimeoutException, TimeoutError):
                raise DiscoverySourceError("Discovery source request timed out.") from None
            except (httpx.HTTPError, OSError):
                if is_cancelled is not None and is_cancelled():
                    raise SourceCancelledError("Discovery request cancelled.") from None
                raise DiscoverySourceError("Discovery source network transport failed.") from None
        finally:
            with state.cond:
                state.in_flight = False
                state.cond.notify_all()

        if self._monotonic() > op_deadline:
            raise DiscoverySourceError("Discovery source result rejected after total deadline.")

        try:
            payload = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeError, ValueError):
            raise SourceSchemaError("Discovery source returned malformed JSON.") from None

        observed_stamp = self._now_utc().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            return parse_overpass(
                payload,
                observed_at=observed_stamp,
                policy_version=self.policy_version,
                max_elements=limit,
            )
        except RegistryError as err:
            raise SourceSchemaError(str(err)) from None


@dataclass(frozen=True)
class DiscoveryBatch:
    observations: tuple[dict, ...]
    partial: bool
    limitations: tuple[str, ...]
    attribution: str = ATTRIBUTION
    checkpoint_token: Mapping[str, object] | None = None


def parse_overpass(payload, *, observed_at, policy_version, max_elements=100):
    if type(max_elements) is not int or not 1 <= max_elements <= 100:
        raise RegistryError("Parser element limit must be between one and 100.")
    try:
        size = len(encoded(payload).encode("utf-8"))
    except (ValueError, TypeError):
        raise RegistryError("Source response is not valid JSON.") from None
    if not isinstance(payload, dict) or size > 5242880 or not isinstance(payload.get("elements"), list):
        raise RegistryError("Source response has an invalid or oversized envelope.")
    if len(payload["elements"]) > max_elements:
        raise RegistryError("Source response exceeds the reserved observation budget.")
    observations = []
    partial = bool(payload.get("remark")) or len(payload["elements"]) == max_elements
    for element in payload["elements"]:
        if not isinstance(element, dict):
            raise RegistryError("Source element must be an object.")
        kind, identifier, tags = element.get("type"), element.get("id"), element.get("tags", {})
        if kind not in {"node", "way", "relation"} or type(identifier) is not int or identifier < 1:
            raise RegistryError("Source element has no valid OSM identifier.")
        if (
            not isinstance(tags, dict)
            or len(tags) > 256
            or any(
                not isinstance(k, str) or not isinstance(v, str) or len(k) > 256 or len(v) > 2048
                for k, v in tags.items()
            )
        ):
            raise RegistryError("Source element has invalid tags.")
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
        limits = ["OSM tags are public observations, not independently verified business facts."]
        center = element if kind == "node" else element.get("center", {})
        coordinates = None
        if isinstance(center, dict):
            lat, lon = center.get("lat"), center.get("lon")
            if (
                type(lat) in {int, float}
                and type(lon) in {int, float}
                and math.isfinite(lat)
                and math.isfinite(lon)
                and -90 <= lat <= 90
                and -180 <= lon <= 180
            ):
                coordinates = {"latitude": lat, "longitude": lon}
        if coordinates is None:
            limits.append("Source supplied no usable coordinates.")
        observations.append(
            {
                "name": tags.get("name", ""),
                "source_namespace": "osm",
                "source_id": f"{kind}/{identifier}",
                "source_url": f"https://www.openstreetmap.org/{kind}/{identifier}",
                "observed_at": observed_at,
                "policy_version": policy_version,
                "attribution": ATTRIBUTION,
                "address": address,
                "website": tags.get("website", tags.get("contact:website")),
                "phone": tags.get("phone", tags.get("contact:phone")),
                "email": tags.get("email", tags.get("contact:email")),
                "coordinates": coordinates,
                "category": tags.get("amenity"),
                "limitations": limits,
            }
        )
    limitations = (
        ("Source reported a remark or reached the output cap; completeness is not established.",) if partial else ()
    )
    return DiscoveryBatch(tuple(observations), partial, limitations)
