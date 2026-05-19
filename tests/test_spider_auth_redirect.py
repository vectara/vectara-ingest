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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
