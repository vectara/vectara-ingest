import inspect
import sys
from unittest.mock import MagicMock

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())

import pytest
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request
from scrapy.settings import Settings

from core.spider import FilterRedirectsByTypeMiddleware


def test_redirect_signature_matches_parent():
    parent_sig = inspect.signature(RedirectMiddleware._redirect)
    child_sig = inspect.signature(FilterRedirectsByTypeMiddleware._redirect)
    assert list(parent_sig.parameters) == list(child_sig.parameters)


def _make_mw():
    settings = Settings({
        "REDIRECT_ENABLED": True,
        "REDIRECT_MAX_TIMES": 20,
        "REDIRECT_PRIORITY_ADJUST": 2,
    })
    mw = FilterRedirectsByTypeMiddleware(settings)
    # Scrapy 2.14's RedirectMiddleware._redirect logs via self.crawler.spider.
    mw.crawler = MagicMock()
    return mw


def test_redirect_to_disallowed_type_is_ignored():
    mw = _make_mw()
    request = Request("http://example.com/page")
    redirected = Request("http://example.com/file.zip")
    with pytest.raises(IgnoreRequest):
        mw._redirect(redirected, request, 302)


def test_redirect_to_allowed_type_passes_through():
    mw = _make_mw()
    request = Request("http://example.com/page")
    redirected = Request("http://example.com/next")
    result = mw._redirect(redirected, request, 302)
    assert result.url == "http://example.com/next"
