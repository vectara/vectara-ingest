"""Bug B regression: when auth is wired into the indexer's web_extractor,
the unauthenticated `requests.get` static prefetch in `fetch_page_contents`
must be skipped so the authenticated Playwright path actually runs.

Without this guard, Google Sites (and any other auth-required SPA) returns
~1KB of redirect-to-signin HTML which exceeds the 500-char threshold and
short-circuits the browser path entirely.
"""

import importlib.machinery
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

# Heavy native deps that the import chain touches.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())
_pw_mock = MagicMock()
_pw_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())


def _make_extractor():
    """Build a WebContentExtractor with a stub browser so `__init__` does
    not try to launch Chromium."""
    from core.web_content_extractor import WebContentExtractor

    cfg = SimpleNamespace(
        vectara=SimpleNamespace(get=lambda key, default=None: default),
    )
    fake_browser = MagicMock(name="browser")
    extractor = WebContentExtractor(cfg=cfg, browser=fake_browser)
    # Constructor sets these only when browser is None; mirror them so the
    # browser-path code doesn't trip on missing attrs.
    extractor.p = MagicMock(name="playwright_runner")
    return extractor


class TestSkipStaticPrefetchFlag(unittest.TestCase):

    def test_default_is_false(self):
        extractor = _make_extractor()
        self.assertFalse(extractor.skip_static_prefetch)

    def test_when_true_requests_get_is_not_called(self):
        extractor = _make_extractor()
        extractor.skip_static_prefetch = True

        # Make the browser path return a benign result so we exercise the
        # whole function but don't depend on Playwright internals.
        page = MagicMock()
        page.title.return_value = "ok"
        page.url = "https://sites.google.com/site/home"
        page.content.return_value = "<html></html>"
        context = MagicMock()
        context.new_page.return_value = page
        extractor.browser.new_context.return_value = context

        with patch("core.web_content_extractor.requests.get",
                   side_effect=AssertionError("static prefetch must be skipped")) as mock_get, \
             patch.object(extractor, "_extract_text_content", return_value="rendered text"), \
             patch.object(extractor, "_extract_links", return_value=[]), \
             patch.object(extractor, "_remove_elements"), \
             patch.object(extractor, "_scroll_to_bottom"):
            result = extractor.fetch_page_contents("https://sites.google.com/site/home")

        mock_get.assert_not_called()
        # Browser path was actually taken
        extractor.browser.new_context.assert_called()
        self.assertEqual(result["text"], "rendered text")

    def test_when_false_static_prefetch_runs(self):
        extractor = _make_extractor()
        # default is False — be explicit
        extractor.skip_static_prefetch = False

        # Static response with >500 chars of visible text so the static
        # branch commits and returns before any browser logic.
        fake_resp = MagicMock()
        fake_resp.headers = {"content-type": "text/html"}
        fake_resp.url = "https://example.com/page"
        fake_resp.text = "<html><body>" + ("hello world " * 100) + "</body></html>"
        fake_resp.raise_for_status = MagicMock()

        with patch("core.web_content_extractor.requests.get", return_value=fake_resp) as mock_get:
            result = extractor.fetch_page_contents("https://example.com/page")

        mock_get.assert_called_once()
        # Browser path must NOT have been invoked when static is sufficient
        extractor.browser.new_context.assert_not_called()
        self.assertGreater(len(result["text"]), 500)


class TestApplyAuthSetsSkipFlag(unittest.TestCase):
    """`_apply_auth_to_indexer` is the chokepoint that knows auth is wired
    in. It must flip `skip_static_prefetch` so per-page fetches go through
    the authenticated Playwright context, never plain `requests.get`."""

    def _fake_indexer(self):
        indexer = MagicMock()
        indexer.session = requests.Session()
        indexer.web_extractor = MagicMock()
        indexer.web_extractor.skip_static_prefetch = False
        indexer.web_extractor.browser = MagicMock()
        indexer.web_extractor.browser.new_context = MagicMock(return_value=MagicMock())
        return indexer

    def test_google_auth_sets_skip_flag(self):
        from crawlers.website_crawler import _apply_auth_to_indexer

        indexer = self._fake_indexer()
        _apply_auth_to_indexer(
            indexer,
            google_cookies=None,
            google_storage_state_path="/tmp/state.json",
        )
        self.assertTrue(indexer.web_extractor.skip_static_prefetch)

    def test_saml_session_sets_skip_flag(self):
        from crawlers.website_crawler import _apply_auth_to_indexer

        indexer = self._fake_indexer()
        _apply_auth_to_indexer(
            indexer,
            saml_session=requests.Session(),
        )
        self.assertTrue(indexer.web_extractor.skip_static_prefetch)

    def test_no_auth_leaves_flag_alone(self):
        from crawlers.website_crawler import _apply_auth_to_indexer

        indexer = self._fake_indexer()
        _apply_auth_to_indexer(indexer)
        # Should remain at its default (False) — no auth, no need to skip.
        self.assertFalse(indexer.web_extractor.skip_static_prefetch)


if __name__ == "__main__":
    unittest.main()
