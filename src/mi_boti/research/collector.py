"""Bounded, explicitly reviewed website collection; never analyzes or qualifies."""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from ..discovery.overpass import validate_public_ip, format_pinned_url
from ..domain.errors import AppError
from ..domain.values import utc_now


class ResearchError(AppError):
    code = "RESEARCH_BLOCKED"


class ResearchSafetyError(ResearchError):
    """A transport-policy violation terminates the entire collection."""


def safe_url(value):
    try:
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) <= 32 for c in value) or "\\" in value:
            raise ValueError
        p = urlsplit(value)
        host = (p.hostname or "").encode("idna").decode("ascii").lower()
        if (p.scheme not in {"http", "https"} or p.username is not None or p.password is not None
                or p.fragment or not host or p.port not in (None, 80 if p.scheme == "http" else 443)
                or host.endswith((".local", ".internal", ".localhost", ".")) or host == "localhost"):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
                raise ValueError
        else:
            validate_public_ip(host)
        return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, "")), host
    except (ValueError, UnicodeError, AppError):
        raise ResearchSafetyError("Website URL violates the public HTTP/HTTPS policy.") from None


@dataclass(frozen=True)
class AccessReview:
    """A caller-supplied review is required in addition to robots permission."""
    host: str
    permission_url: str
    policy_version: str
    reviewer_id: str
    expires_at: str

    def validate(self, now):
        try:
            _, permission_host = safe_url(self.permission_url)
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            if (permission_host != self.host or not self.policy_version.strip()
                    or not self.reviewer_id.isdigit() or expiry.tzinfo is None or expiry <= now):
                raise ValueError
        except (ValueError, AttributeError):
            raise ResearchError("A current named website-access review is required before fetching.") from None


@dataclass(frozen=True)
class PageObservation:
    source_url: str
    final_url: str
    observed_at: str
    excerpt: str
    excerpt_sha256: str
    policy_version: str
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class Collection:
    state: str
    pages: tuple[PageObservation, ...]
    requests: int
    limitations: tuple[str, ...]


class WebsiteCollector:
    """One instance per application loop; all operations share host/DNS admission.

    This staged engine has no Discord admission or database writes. Only explicit
    collect calls may use the network, and each needs a reviewed exact hostname.
    """
    def __init__(self, user_agent, *, resolver=None, transport=None, interval=2.0, limits=None):
        if not user_agent.strip() or any(c in user_agent for c in "\r\n\x00"):
            raise ResearchError("Configure a descriptive research user-agent/contact first.")
        if interval < 2:
            raise ResearchError("Website request spacing must be at least two seconds.")
        self.user_agent, self.resolver, self.transport = user_agent, resolver, transport
        self.interval = interval
        self.limits = limits or {}
        self.dispatch_check = ContextVar("research_dispatch_check", default=None)
        self.hosts = {}
        self.robots = {}
        self.dns_slots = asyncio.Semaphore(2)
        self.resolver_threads = set()
        self.resolver_guard = threading.Lock()

    async def _resolve(self, host, port):
        await self.dns_slots.acquire()
        async def resolve():
            if self.resolver:
                return await self.resolver(host, port)
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            def complete(infos, error):
                if future.done(): return
                if error: future.set_exception(error)
                else: future.set_result(infos)
            def worker():
                infos, error = None, None
                try:
                    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                except OSError:
                    error = ResearchError("Could not resolve the website hostname.")
                finally:
                    with self.resolver_guard:
                        self.resolver_threads.discard(threading.current_thread())
                try:
                    loop.call_soon_threadsafe(complete, infos, error)
                except RuntimeError:
                    pass  # Application loop closed; daemon resolver cannot delay shutdown.
            thread = threading.Thread(target=worker, name="mi-boti-research-dns", daemon=True)
            with self.resolver_guard:
                self.resolver_threads.add(thread)
            thread.start()
            return await future
        task = asyncio.create_task(resolve())
        # Retain admission until the underlying resolver actually finishes.
        def finished(done):
            self.dns_slots.release()
            if not done.cancelled(): done.exception()
        task.add_done_callback(finished)
        infos = await asyncio.shield(task)
        try:
            ips = [validate_public_ip(info[4][0]) for info in infos]
        except AppError:
            raise ResearchSafetyError("Website DNS returned a forbidden address.") from None
        if not ips: raise ResearchError("Website DNS returned no public addresses.")
        return ips[0]

    async def _request(self, url, review, budget, *, delay=2):
        url, host = safe_url(url)
        if host != review.host:
            raise ResearchSafetyError("Redirect or link leaves the reviewed website hostname.")
        check = self.dispatch_check.get()
        if check is not None and await check() is not True:
            raise ResearchError("Research dispatch authorization was denied.")
        if budget[0] <= 0: raise ResearchError("Research request budget exhausted.")
        budget[0] -= 1
        if host not in self.hosts:
            if len(self.hosts) >= 64: raise ResearchError("Website host admission is full.")
            self.hosts[host] = [asyncio.Lock(), 0.0]
        state = self.hosts[host]
        async with asyncio.timeout(min(10, self.limits.get("research.timeout_seconds", 10))):
            async with state[0]:
                await asyncio.sleep(max(0, state[1] - time.monotonic()))
                ip = await self._resolve(host, urlsplit(url).port or (443 if url.startswith("https:") else 80))
                pinned, ascii_host = format_pinned_url(url, ip)
                if check is not None:
                    if await check() is not True:
                        raise ResearchError("Research dispatch authorization was denied.")
                state[1] = time.monotonic() + max(self.interval, delay)
                async with httpx.AsyncClient(transport=self.transport, trust_env=False, follow_redirects=False, timeout=10) as client:
                    async with client.stream("GET", pinned, headers={"Host": ascii_host, "User-Agent": self.user_agent,
                                              "Accept-Encoding": "identity", "Accept": "text/html,text/plain"},
                                             extensions={"sni_hostname": ascii_host}) as response:
                        if response.status_code == 429:
                            from ..discovery.overpass import parse_retry_after
                            wait = parse_retry_after(response.headers.get("retry-after"), now_utc=datetime.now(timezone.utc))
                            state[1] = max(state[1], time.monotonic() + (wait if wait is not None else 60))
                            raise ResearchError("Website rate-limited collection; retry later.")
                        if response.status_code in {301, 302, 303, 307, 308}:
                            return response.status_code, response.headers, b""
                        if response.status_code != 200:
                            raise ResearchError("Website or robots policy was unavailable; no access bypass was attempted.")
                        if response.headers.get("content-encoding", "identity").lower() != "identity":
                            raise ResearchError("Compressed responses are not supported by this initial collector.")
                        if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in {"text/html", "text/plain"}:
                            raise ResearchError("Website returned an unsupported content type.")
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > min(2097152, self.limits.get("research.max_body_bytes", 2097152)): raise ResearchError("Website response exceeded the body limit.")
                            chunks.append(chunk)
                        return 200, response.headers, b"".join(chunks)

    async def _robots(self, url, review, budget):
        p = urlsplit(url)
        origin = urlunsplit((p.scheme, p.netloc, "", "", ""))
        cache_key = (origin, review.policy_version)
        cached = self.robots.get(cache_key)
        if cached and cached[0] > time.monotonic(): return cached[1]
        status, headers, raw = await self._request(origin + "/robots.txt", review, budget)
        if status != 200 or len(raw) > 65536:
            raise ResearchError("Robots policy is unavailable, redirected or oversized; collection is blocked.")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            raise ResearchError("Robots policy is not valid UTF-8.") from None
        if not re.search(r"(?im)^\s*user-agent\s*:", text) or "<html" in text.lower():
            raise ResearchError("Robots policy could not be interpreted; collection is blocked.")
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line: continue
            if ":" not in line: raise ResearchError("Robots policy contains an unsupported rule.")
            key, value = (part.strip() for part in line.split(":", 1))
            if key.lower() not in {"user-agent", "allow", "disallow", "crawl-delay", "request-rate", "sitemap"}:
                raise ResearchError("Robots policy contains an unsupported directive; review is required.")
            if key.lower() == "crawl-delay" and not value.isdigit():
                raise ResearchError("Robots crawl delay is not supported by this parser.")
            if key.lower() == "request-rate" and not re.fullmatch(r"[1-9][0-9]*/[1-9][0-9]*", value):
                raise ResearchError("Robots request rate is not supported by this parser.")
        robots = RobotFileParser()
        robots.parse(text.splitlines())
        self.robots = {key: value for key, value in self.robots.items() if key[0] != origin and value[0] > time.monotonic()}
        self.robots[cache_key] = (time.monotonic() + min(86400, self.limits.get("research.robots_ttl_seconds", 86400)), robots)
        return robots

    async def _page(self, url, review, budget):
        original = url
        max_redirects = min(3, self.limits.get("research.max_redirects", 3))
        for redirect in range(max_redirects + 1):
            url, host = safe_url(url)
            if host != review.host: raise ResearchSafetyError("Website redirect leaves the reviewed host.")
            robots = await self._robots(url, review, budget)
            if not robots.can_fetch(self.user_agent, url): raise ResearchError("Robots policy disallows this page.")
            delay = robots.crawl_delay(self.user_agent) or 2
            rate = robots.request_rate(self.user_agent)
            if rate: delay = max(delay, rate.seconds / rate.requests)
            status, headers, raw = await self._request(url, review, budget, delay=delay)
            if status != 200:
                if redirect == max_redirects or "location" not in headers: raise ResearchError("Website redirect limit exceeded.")
                next_url = urljoin(url, headers["location"])
                if url.startswith("https:") and not next_url.startswith("https:"):
                    raise ResearchSafetyError("HTTPS downgrade redirect is prohibited.")
                url = next_url
                continue
            text, links = extract(raw, url, headers.get("content-type", ""))
            text_limit = min(20000, self.limits.get("research.max_text_chars", 20000))
            text = text[:text_limit]
            if not text: raise ResearchError("Website contained no usable public text.")
            limitations = ("Public page excerpt; not independently verified and not proof of internal software.",)
            if len(text) >= text_limit:
                limitations += (f"The saved excerpt is capped at {text_limit} characters; additional page text may be omitted.",)
            return PageObservation(original, url, utc_now(), text, hashlib.sha256(text.encode()).hexdigest(),
                                   review.policy_version, limitations), links

    async def collect(self, url, review, *, max_pages=5, authorize=None):
        token = self.dispatch_check.set(authorize)
        try:
            return await self._collect(url, review, max_pages=max_pages)
        finally:
            self.dispatch_check.reset(token)

    async def _collect(self, url, review, *, max_pages):
        review.validate(datetime.now(timezone.utc))
        url, host = safe_url(url)
        if host != review.host or type(max_pages) is not int or not 1 <= max_pages <= 5:
            raise ResearchError("Research requires a reviewed exact host and a one-to-five-page limit.")
        budget, pages, limitations = [32], [], []
        plan = [url]
        try:
            async with asyncio.timeout(120):
                for current in plan:
                    try:
                        page, links = await self._page(current, review, budget)
                        pages.append(page)
                        if len(plan) == 1:
                            for link in links:
                                if len(plan) >= max_pages: break
                                if link not in plan: plan.append(link)
                    except ResearchSafetyError:
                        return Collection("FAILED", (), 32 - budget[0], ("Critical URL/DNS/redirect policy violation blocked collection.",))
                    except (AppError, httpx.HTTPError, TimeoutError) as error:
                        reason = str(error) if isinstance(error, AppError) else "Website request failed or timed out."
                        limitations.append(reason + " Page contents and internal systems remain unknown.")
        except TimeoutError:
            limitations.append("Collection reached its total time limit.")
        return Collection("PARTIAL" if pages and limitations else "SUCCEEDED" if pages else "FAILED", tuple(pages), 32 - budget[0], tuple(limitations))


def extract(raw, url, media_type):
    """Extract literal text only; page content never becomes execution instructions."""
    if "text/plain" in media_type:
        return raw.decode("utf-8", errors="replace")[:20000].strip(), ()
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup.select("script,style,form,template,noscript,nav,footer,[hidden],[aria-hidden='true']"):
        node.decompose()
    for node in soup.find_all(style=True):
        if node.attrs and re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", node.get("style", ""), re.I): node.decompose()
    links = []
    host = safe_url(url)[1]
    for anchor in soup.find_all("a", href=True):
        if len(links) >= 20: break
        if not re.search(r"about|service|contact|book", anchor.get_text(" ") + anchor["href"], re.I): continue
        try:
            link, link_host = safe_url(urljoin(url, anchor["href"]))
            if link_host == host: links.append(link)
        except ResearchError: pass
    return soup.get_text(" ", strip=True)[:20000], tuple(links)
