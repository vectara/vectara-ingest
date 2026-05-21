"""Discovery-side guard: spider must not extract links from IdP sign-in
pages it lands on after a cross-domain redirect.
"""

import sys
from unittest.mock import MagicMock

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())

import pytest
from scrapy.http import HtmlResponse, Request

from core.spider import LinkSpider, recursive_crawl


_IDP_SIGNIN_HTML = b"""
<html><body>
  <form action="/signin"><input name="user"></form>
  <a href="https://accounts.google.com/signin/v2/usernamerecovery">Forgot?</a>
  <a href="https://accounts.google.com/lifecycle/steps/signup/name">Create account</a>
  <a href="https://support.google.com/accounts/answer/2917834">Learn more</a>
</body></html>
"""


def _make_spider():
    return LinkSpider(
        start_urls=["https://sites.google.com/d/abc/p/xyz/edit"],
        positive_regexes=[".*"],
        negative_regexes=[],
        max_depth=2,
    )


def test_linkspider_drops_links_when_redirected_to_google_signin():
    spider = _make_spider()
    original = "https://sites.google.com/d/abc/p/xyz/edit"
    landed = "https://accounts.google.com/v3/signin/identifier?continue=..."
    request = Request(landed, meta={"depth": 0, "redirect_urls": [original]})
    response = HtmlResponse(url=landed, request=request, body=_IDP_SIGNIN_HTML)

    items = list(spider.parse(response))
    assert items == [], "Spider must not yield URLs or follow links from an IdP landing page"


def test_linkspider_drops_direct_link_to_idp_host():
    """Regression: when an authenticated page body contains a direct link to
    an IdP host (e.g. accounts.google.com/SignOutOptions), Scrapy should
    follow neither yield the URL nor crawl deeper into it. Previously this
    leaked into urls_indexed.txt because auth_redirect_reason only fires on
    a netloc change during the same fetch."""
    spider = _make_spider()
    # The response URL is itself on the IdP host — no prior redirect.
    landed = "https://accounts.google.com/SignOutOptions?continue=https://sites.google.com/..."
    request = Request(landed, meta={"depth": 0})
    response = HtmlResponse(url=landed, request=request, body=_IDP_SIGNIN_HTML)

    items = list(spider.parse(response))
    assert items == [], "Spider must drop IdP-host responses, not yield them"


def test_linkspider_does_not_follow_idp_links_from_authenticated_page():
    """Regression: an authenticated page may include account-management
    links (sign out, switch account). Those point to accounts.google.com
    and should not be followed even though the response itself is fine."""
    spider = _make_spider()
    url = "https://sites.google.com/d/abc/p/xyz/edit"
    request = Request(url, meta={"depth": 0})
    body = (
        b'<html><body>'
        b'<a href="https://accounts.google.com/SignOutOptions">Sign out</a>'
        b'<a href="/page2">Next</a>'
        b'</body></html>'
    )
    response = HtmlResponse(url=url, request=request, body=body)

    items = list(spider.parse(response))
    follow_urls = [i.url for i in items if isinstance(i, Request)]
    assert "https://sites.google.com/page2" in follow_urls
    assert not any("accounts.google.com" in u for u in follow_urls)


def test_linkspider_processes_normal_response():
    spider = _make_spider()
    url = "https://sites.google.com/d/abc/p/xyz/edit"
    request = Request(url, meta={"depth": 0})
    body = b'<html><body><a href="/page2">Next</a></body></html>'
    response = HtmlResponse(url=url, request=request, body=body)

    items = list(spider.parse(response))
    # Should yield the page itself plus the follow-up request for /page2.
    urls_yielded = [i.get("url") for i in items if isinstance(i, dict)]
    requests_yielded = [i.url for i in items if isinstance(i, Request)]
    assert url in urls_yielded
    assert "https://sites.google.com/page2" in requests_yielded


def test_recursive_crawl_drops_discovery_on_idp_redirect():
    indexer = MagicMock()
    # Simulate Playwright following the redirect to an IdP page that still
    # contains some "links" we definitely should NOT enqueue.
    indexer.fetch_page_contents.return_value = {
        "url": "https://accounts.google.com/v3/signin/identifier?continue=...",
        "links": [
            "https://accounts.google.com/signin/v2/usernamerecovery",
            "https://accounts.google.com/lifecycle/steps/signup/name",
        ],
        "text": "Sign in", "html": "<html></html>", "title": "Sign in",
    }
    visited = recursive_crawl(
        "https://sites.google.com/d/abc/p/xyz/edit",
        depth=2, pos_patterns=[], neg_patterns=[], indexer=indexer,
    )
    # The seed URL itself is still recorded (it's what the caller asked us
    # to start from), but none of the IdP links should be picked up.
    assert visited == {"https://sites.google.com/d/abc/p/xyz/edit"}


def test_linkspider_start_forwards_cookie_list_with_attributes():
    """Bug A regression: when cookies are passed as a list-of-dicts (the
    format Scrapy needs to enforce per-cookie domain scoping for `__Host-*`
    and other host-bound Google cookies), `start()` must forward the list
    verbatim to each Scrapy Request — no flattening, no attribute loss."""
    import asyncio

    cookies = [
        {"name": "SID", "value": "sid", "domain": ".google.com",
         "path": "/", "secure": True},
        {"name": "__Host-1PLSID", "value": "psid",
         "domain": "accounts.google.com", "path": "/", "secure": True},
    ]
    spider = LinkSpider(
        start_urls=["https://sites.google.com/site/home"],
        positive_regexes=[".*"],
        negative_regexes=[],
        max_depth=1,
        cookies=cookies,
    )

    async def _collect():
        return [r async for r in spider.start()]

    requests_yielded = asyncio.run(_collect())
    assert len(requests_yielded) == 1
    req = requests_yielded[0]
    # Scrapy Request stores the raw cookies kwarg until CookieMiddleware
    # consumes it. We assert structural equality so the test stays robust
    # against Scrapy internals.
    assert req.cookies == cookies
    # Per-cookie attributes are still present (i.e. nothing was flattened
    # to a {name: value} dict along the way).
    by_name = {c["name"]: c for c in req.cookies}
    assert by_name["__Host-1PLSID"]["domain"] == "accounts.google.com"
    assert by_name["__Host-1PLSID"]["secure"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
