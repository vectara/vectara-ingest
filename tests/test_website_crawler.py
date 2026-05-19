import sys
import importlib.machinery
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

# Heavy optional deps that website_crawler's import chain touches.
for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from crawlers.website_crawler import WebsiteCrawler


def _make_cfg(remove_old_content=True, crawl_report=False):
    return SimpleNamespace(
        website_crawler=SimpleNamespace(
            get=lambda key, default=None: {
                "remove_old_content": remove_old_content,
                "crawl_report": crawl_report,
            }.get(key, default)
        ),
        vectara=SimpleNamespace(get=lambda key, default=None: default),
    )


class TestRemoveOldContentEncoding(unittest.TestCase):
    """Regression tests for the urls_indexed/urls_removed encoding mismatch.

    Background: the indexer URL-decodes metadata['url'] via
    normalize_url_for_metadata before storing it, while crawled_urls comes
    directly from URL discovery and can be percent-encoded. A naive string
    comparison flagged the *same* logical URL as both indexed and removed,
    causing repeated delete/reindex churn across crawls.
    """

    def _run(self, crawled_urls, existing_docs):
        fake_indexer = MagicMock()
        fake_indexer._list_docs.return_value = existing_docs
        fake_self = SimpleNamespace(cfg=_make_cfg(), indexer=fake_indexer)
        WebsiteCrawler._remove_old_content_if_needed(fake_self, crawled_urls)
        return [c.args[0] for c in fake_indexer.delete_doc.call_args_list]

    def test_percent_encoded_discovery_matches_decoded_corpus_url(self):
        # Same logical URL, discovery percent-encoded, corpus URL-decoded.
        crawled = [
            "https://accounts.google.com/v3/signin/identifier?"
            "continue=https%3A%2F%2Fsites.google.com%2Fd%2Fabc%2Fp%2Fxyz%2Fedit"
        ]
        existing = [{
            "id": "doc1",
            "url": "https://accounts.google.com/v3/signin/identifier?"
                   "continue=https://sites.google.com/d/abc/p/xyz/edit",
        }]
        deleted = self._run(crawled, existing)
        self.assertEqual(deleted, [], "Should not delete a URL that was just indexed")

    def test_decoded_discovery_matches_decoded_corpus_url(self):
        # Both sides already decoded — must still match.
        url = "https://example.com/p?q=a b&x=1"
        deleted = self._run([url], [{"id": "doc1", "url": url}])
        self.assertEqual(deleted, [])

    def test_genuinely_missing_url_is_deleted(self):
        crawled = ["https://example.com/keep"]
        existing = [
            {"id": "keep", "url": "https://example.com/keep"},
            {"id": "gone", "url": "https://example.com/gone"},
        ]
        deleted = self._run(crawled, existing)
        self.assertEqual(deleted, ["gone"])

    def test_doc_without_url_is_ignored(self):
        # Docs without a url in metadata shouldn't get deleted.
        deleted = self._run(["https://example.com/a"], [{"id": "no-url", "url": None}])
        self.assertEqual(deleted, [])

    def test_disabled_when_remove_old_content_false(self):
        fake_indexer = MagicMock()
        fake_self = SimpleNamespace(
            cfg=_make_cfg(remove_old_content=False), indexer=fake_indexer
        )
        WebsiteCrawler._remove_old_content_if_needed(fake_self, [])
        fake_indexer._list_docs.assert_not_called()
        fake_indexer.delete_doc.assert_not_called()


def _google_auth_cfg(credentials_file=None, pages_source="crawl"):
    """Build a fake cfg that exposes a `website_crawler.google_auth` block.

    The crawler reads `google_credentials_file` as a flat attribute (stamped
    by ingest.py from `GOOGLE_CREDENTIALS_FILE`) and `google_auth` via .get().
    """
    overrides = {
        "google_auth": {"mode": "oauth_user", "storage_state_path": "/tmp/s.json"},
        "pages_source": pages_source,
    }
    website_crawler_ns = SimpleNamespace(
        get=lambda key, default=None: overrides.get(key, default),
    )
    if credentials_file is not None:
        website_crawler_ns.google_credentials_file = credentials_file
    return SimpleNamespace(website_crawler=website_crawler_ns)


class TestSetupGoogleAuth(unittest.TestCase):
    """Spec: `_setup_google_auth` captures `sites.google.com` browser cookies
    once at crawler init and stashes them on `self.google_cookies`. The old
    Bearer-token session is gone — Bearer headers are rejected by
    `sites.google.com` content URLs, so building the session was dead weight.
    """

    def test_fetches_cookies_into_google_cookies(self):
        fake_self = SimpleNamespace(
            cfg=_google_auth_cfg(credentials_file="/tmp/creds.json"),
            google_cookies=None,
        )
        with patch("crawlers.website_crawler.GoogleAuthManager") as MockGAM:
            MockGAM.return_value.get_authenticated_cookies.return_value = {
                "SID": "sid-val",
                "__Secure-1PSID": "psid-val",
            }
            WebsiteCrawler._setup_google_auth(fake_self)

        self.assertEqual(
            fake_self.google_cookies,
            {"SID": "sid-val", "__Secure-1PSID": "psid-val"},
        )
        # No Bearer session is constructed any more.
        MockGAM.return_value.get_authenticated_session.assert_not_called()

    def test_works_without_credentials_file_for_cookie_only_crawls(self):
        # Storage-state-only flow: no GOOGLE_CREDENTIALS_FILE in secrets.toml.
        fake_self = SimpleNamespace(
            cfg=_google_auth_cfg(credentials_file=None),
            google_cookies=None,
        )
        with patch("crawlers.website_crawler.GoogleAuthManager") as MockGAM:
            MockGAM.return_value.get_authenticated_cookies.return_value = {"SID": "x"}
            WebsiteCrawler._setup_google_auth(fake_self)

        self.assertEqual(fake_self.google_cookies, {"SID": "x"})
        # Manager was constructed with an empty secrets dict.
        _, kwargs = MockGAM.call_args
        secrets = kwargs.get("secrets") if "secrets" in kwargs else MockGAM.call_args.args[1]
        self.assertIsNone(secrets.get("credentials_file"))

    def test_skips_when_google_auth_block_not_configured(self):
        fake_cfg = SimpleNamespace(
            website_crawler=SimpleNamespace(get=lambda key, default=None: default),
        )
        fake_self = SimpleNamespace(cfg=fake_cfg, google_cookies=None)
        with patch("crawlers.website_crawler.GoogleAuthManager") as MockGAM:
            WebsiteCrawler._setup_google_auth(fake_self)

        self.assertIsNone(fake_self.google_cookies)
        MockGAM.assert_not_called()


class TestConfigureIndexerSession(unittest.TestCase):
    """Spec: `_configure_indexer_session` propagates auth state to BOTH the
    indexer's `requests.Session` (for HTTP fetches) and the Playwright
    `web_extractor` (for JS-rendered fetches). Without this, page content
    fetches against `sites.google.com` 302 to accounts.google.com even when
    Scrapy discovery succeeded.
    """

    def _build_fake_self(self, *, google_cookies=None, saml_session=None):
        fake_indexer = MagicMock()
        fake_indexer.session = requests.Session()
        fake_indexer.web_extractor = MagicMock()
        fake_indexer.web_extractor.browser = MagicMock()
        # original new_context returns a context whose add_cookies we can spy on
        original_context = MagicMock(name="context")
        fake_indexer.web_extractor.browser.new_context = MagicMock(return_value=original_context)
        return SimpleNamespace(
            indexer=fake_indexer,
            saml_session=saml_session,
            google_cookies=google_cookies,
        ), original_context

    def test_merges_google_cookies_into_indexer_session(self):
        fake_self, _ctx = self._build_fake_self(
            google_cookies={"SID": "sid-val", "__Secure-1PSID": "psid-val"},
        )
        WebsiteCrawler._configure_indexer_session(fake_self)

        self.assertEqual(fake_self.indexer.session.cookies.get("SID"), "sid-val")
        self.assertEqual(
            fake_self.indexer.session.cookies.get("__Secure-1PSID"), "psid-val"
        )

    def test_injects_google_cookies_into_playwright_context(self):
        fake_self, original_context = self._build_fake_self(
            google_cookies={"SID": "sid-val"},
        )
        WebsiteCrawler._configure_indexer_session(fake_self)

        # The override should have replaced new_context. Call it and confirm
        # Google cookies were forwarded to the context via add_cookies.
        new_ctx = fake_self.indexer.web_extractor.browser.new_context()
        self.assertIs(new_ctx, original_context)
        original_context.add_cookies.assert_called()
        forwarded = []
        for call in original_context.add_cookies.call_args_list:
            forwarded.extend(call.args[0])
        names = {c["name"]: c["value"] for c in forwarded}
        self.assertEqual(names.get("SID"), "sid-val")

    def test_no_auth_configured_leaves_session_alone(self):
        fake_self, _ctx = self._build_fake_self()
        WebsiteCrawler._configure_indexer_session(fake_self)

        # No cookies should land in the session.
        self.assertEqual(len(fake_self.indexer.session.cookies), 0)
        # new_context override is also not installed when nothing is configured.
        fake_self.indexer._init_processors.assert_not_called()


class TestInternalCrawlerDiscovery(unittest.TestCase):
    """Spec: when discovering URLs via the internal (non-Scrapy) path,
    sitemap_to_urls receives the indexer's merged session — which carries
    Google cookies after `_configure_indexer_session` has run. This is the
    BUG 1 fix: previously only `self.saml_session` was passed, leaving
    google_auth a silent no-op in the default crawl_method.
    """

    def test_sitemap_path_uses_indexer_session_not_saml_session(self):
        fake_indexer = MagicMock()
        fake_indexer.session = MagicMock(name="indexer_session_with_google_cookies")
        fake_indexer.verbose = False

        fake_self = SimpleNamespace(
            cfg=_google_auth_cfg(pages_source="sitemap"),
            indexer=fake_indexer,
            saml_session=MagicMock(name="saml_session"),
            pos_patterns=[],
            neg_patterns=[],
        )

        with patch("crawlers.website_crawler.sitemap_to_urls", return_value=[]) as mock_s2u:
            WebsiteCrawler._discover_urls_with_internal_crawler(
                fake_self, ["https://example.com"], max_depth=1, keep_query_params=False
            )

        mock_s2u.assert_called_once()
        _, kwargs = mock_s2u.call_args
        self.assertIs(kwargs.get("session"), fake_indexer.session)
        self.assertIsNot(kwargs.get("session"), fake_self.saml_session)


if __name__ == "__main__":
    unittest.main()
