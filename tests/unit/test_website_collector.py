import asyncio
from datetime import datetime, timedelta, timezone
import socket

import httpx
import pytest

from mi_boti.research.collector import AccessReview, ResearchError, WebsiteCollector, safe_url, extract


def review(**changes):
    values = dict(host="public.example", permission_url="https://public.example/terms", policy_version="review-v1",
                  reviewer_id="223456789012345678", expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    return AccessReview(**(values | changes))


async def resolve(host, port):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/", "http://127.0.0.1/", "https://user:pass@example.com/",
                                       "http://169.254.169.254/", "https://example.com:8080/", "https://example.com/#x",
                                       "https://[::ffff:127.0.0.1]/", "http://0x7f000001/\\x", "https://example.com/\n"])
def test_forbidden_urls(url):
    with pytest.raises(ResearchError): safe_url(url)


@pytest.mark.parametrize("case", ["success", "robots-denied", "robots-missing", "robots-html", "redirect-private", "redirect-other",
                                 "mixed-dns", "gzip", "mime", "body", "expired", "rate-limit"])
def test_collection_boundary_and_no_robots_bypass(case):
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "public.example"
        assert request.extensions["sni_hostname"] == "public.example"
        assert request.headers["accept-encoding"] == "identity"
        if request.url.path == "/robots.txt":
            if case == "robots-missing": return httpx.Response(404)
            if case == "robots-html": return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Missing</html>")
            return httpx.Response(200, headers={"content-type": "text/plain"}, text="User-agent: *\nDisallow: " + ("/" if case == "robots-denied" else "") + "\n")
        if case.startswith("redirect"):
            return httpx.Response(302, headers={"location": "http://127.0.0.1/" if case == "redirect-private" else "https://other.example/"})
        if case == "rate-limit": return httpx.Response(429, headers={"retry-after": "120"})
        if case == "gzip": return httpx.Response(200, headers={"content-type": "text/html", "content-encoding": "br"}, content=b"fake")
        if case == "mime": return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"bad")
        return httpx.Response(200, headers={"content-type": "text/html"}, content=(b"x" * 2097153 if case == "body" else b"<h1>Bookings available</h1><script>steal secrets</script>"))
    async def dns(host, port):
        answers = await resolve(host, port)
        if case == "mixed-dns": answers += [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))]
        return answers
    async def run():
        collector = WebsiteCollector("MiBoti/0.2 (+https://example.org/contact)", resolver=dns, transport=httpx.MockTransport(handler))
        policy = review(expires_at="2020-01-01T00:00:00Z") if case == "expired" else review()
        if case == "expired":
            with pytest.raises(ResearchError): await collector.collect("https://public.example/", policy, max_pages=1)
            assert not calls
            return
        result = await collector.collect("https://public.example/", policy, max_pages=1)
        assert result.state == ("SUCCEEDED" if case == "success" else "FAILED")
        if case == "success":
            assert result.pages[0].excerpt == "Bookings available"
            assert len(result.pages[0].excerpt_sha256) == 64
            assert result.requests == 2
        if case in {"robots-denied", "robots-missing", "robots-html"}: assert len(calls) == 1
        if case == "mixed-dns": assert not calls
    asyncio.run(run())


def test_text_is_bounded_and_hidden_content_is_excluded():
    text, links = extract(b'<div hidden>private</div><form>password</form><p>Public services</p><a href="/contact">Contact</a><a href="http://127.0.0.1/about">About</a>', "https://public.example/", "text/html")
    assert "private" not in text and "password" not in text
    assert links == ("https://public.example/contact",)
    assert len(extract(b"x" * 25000, "https://public.example/", "text/plain")[0]) == 20000


@pytest.mark.parametrize("case", ["ipv6", "rebind"])
def test_actual_pinned_destination_and_dns_revalidation(case):
    resolved, requested = [], []
    async def dns(host, port):
        ip = "2606:4700:4700::1111" if case == "ipv6" else "93.184.216.34" if not resolved else "127.0.0.1"
        resolved.append(ip)
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    async def handler(request):
        requested.append(request)
        assert request.url.host == ("2606:4700:4700::1111" if case == "ipv6" else "93.184.216.34")
        assert request.extensions["sni_hostname"] == "public.example"
        content = "User-agent: *\nAllow: /\n" if request.url.path == "/robots.txt" else "Public services"
        return httpx.Response(200, headers={"content-type": "text/plain"}, text=content)
    async def run():
        collector = WebsiteCollector("MiBoti/contact@example.org", resolver=dns, transport=httpx.MockTransport(handler))
        result = await collector.collect("https://public.example/", review(), max_pages=1)
        assert result.state == ("SUCCEEDED" if case == "ipv6" else "FAILED")
        assert len(requested) == (2 if case == "ipv6" else 1)
    asyncio.run(run())


def test_cancellation_keeps_dns_admission_until_resolver_finishes():
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def dns(host, port):
            entered.set()
            await release.wait()
            return await resolve(host, port)
        collector = WebsiteCollector("MiBoti/contact@example.org", resolver=dns)
        task = asyncio.create_task(collector.collect("https://public.example/", review()))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert collector.dns_slots._value == 1
        release.set()
        for _ in range(5): await asyncio.sleep(0)
        assert collector.dns_slots._value == 2
    asyncio.run(run())
