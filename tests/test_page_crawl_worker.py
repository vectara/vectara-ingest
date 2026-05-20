"""Spec tests for PageCrawlWorker — the per-process Ray actor / single-process
worker that performs the actual page indexing.

Background: PageCrawlWorker runs in its own process (Ray actor or fork). It
constructs its own Indexer at `setup()` time and is responsible for wiring
auth state into that indexer. Cookies don't survive cross-process transfer
of the parent's Indexer instance, so each worker re-derives them.

Before the fix, the Google branch of `setup()` built a Bearer-token session
that was useless for `sites.google.com` content URLs. The fix replaces it
with cookie capture from the persisted Playwright `storage_state`.
"""

import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

import requests

# Heavy optional deps that the import chain touches.
for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from crawlers.website_crawler import PageCrawlWorker


def _build_worker(google_auth_cfg=None, credentials_file=None, saml_auth_cfg=None,
                  saml_username=None, saml_password=None):
    cfg = {
        "vectara": {
            "endpoint": "https://api.vectara.io",
            "corpus_key": "k",
            "api_key": "ak",
        },
        "website_crawler": {},
    }
    if google_auth_cfg:
        cfg["website_crawler"]["google_auth"] = google_auth_cfg
        if credentials_file is not None:
            cfg["website_crawler"]["google_credentials_file"] = credentials_file
    if saml_auth_cfg:
        cfg["website_crawler"]["saml_auth"] = saml_auth_cfg
        if saml_username is not None:
            cfg["website_crawler"]["saml_username"] = saml_username
        if saml_password is not None:
            cfg["website_crawler"]["saml_password"] = saml_password
    return PageCrawlWorker(cfg, num_per_second=5)


def _fake_indexer():
    indexer = MagicMock()
    indexer.session = requests.Session()
    indexer.web_extractor = MagicMock()
    indexer.web_extractor.browser = MagicMock()
    indexer.web_extractor.browser.new_context = MagicMock(return_value=MagicMock())
    return indexer


class TestPageCrawlWorkerGoogleAuth(unittest.TestCase):

    def test_setup_injects_google_cookies_into_worker_indexer_session(self):
        worker = _build_worker(
            google_auth_cfg={"mode": "oauth_user", "storage_state_path": "/tmp/s.json"},
            credentials_file="/tmp/creds.json",
        )
        fake = _fake_indexer()
        fake.web_extractor.skip_static_prefetch = False

        with patch("crawlers.website_crawler.Indexer", return_value=fake), \
             patch("crawlers.website_crawler.normalize_vectara_endpoint", return_value="https://api.vectara.io"), \
             patch("crawlers.website_crawler.setup_logging"), \
             patch("crawlers.website_crawler.GoogleAuthManager") as MockGAM:
            MockGAM.return_value.get_authenticated_cookies.return_value = [
                {"name": "SID", "value": "sid-val", "domain": ".google.com",
                 "path": "/", "secure": True},
                {"name": "__Secure-1PSID", "value": "psid-val",
                 "domain": ".google.com", "path": "/", "secure": True},
            ]
            MockGAM.return_value.storage_state_path = "/tmp/s.json"
            worker.setup()

        self.assertEqual(
            fake.session.cookies.get("SID", domain=".google.com"), "sid-val",
        )
        self.assertEqual(
            fake.session.cookies.get("__Secure-1PSID", domain=".google.com"),
            "psid-val",
        )

    def test_setup_does_not_build_useless_bearer_session(self):
        # Pre-fix behavior: worker called get_authenticated_session() and
        # assigned the Bearer-only session as indexer.session. That session
        # is rejected by sites.google.com content URLs (docs say so) and
        # forced credentials_file to be present even for cookie-only crawls.
        worker = _build_worker(
            google_auth_cfg={"mode": "oauth_user", "storage_state_path": "/tmp/s.json"},
            credentials_file="/tmp/creds.json",
        )
        fake = _fake_indexer()

        with patch("crawlers.website_crawler.Indexer", return_value=fake), \
             patch("crawlers.website_crawler.normalize_vectara_endpoint", return_value="https://api.vectara.io"), \
             patch("crawlers.website_crawler.setup_logging"), \
             patch("crawlers.website_crawler.GoogleAuthManager") as MockGAM:
            MockGAM.return_value.get_authenticated_cookies.return_value = [
                {"name": "SID", "value": "x", "domain": ".google.com",
                 "path": "/", "secure": True},
            ]
            MockGAM.return_value.storage_state_path = "/tmp/s.json"
            worker.setup()

            MockGAM.return_value.get_authenticated_session.assert_not_called()
            MockGAM.return_value.get_authenticated_cookies.assert_called_once()


class TestPageCrawlWorkerSamlAuth(unittest.TestCase):
    """The SAML worker branch must wire auth into both `indexer.session` and
    `indexer.web_extractor` via `_apply_auth_to_indexer`. A bare session
    assignment would leave `skip_static_prefetch` off, so the unauthenticated
    static prefetch in `WebContentExtractor.fetch_page_contents` follows
    redirects to the IdP login page and short-circuits the Playwright path —
    SAML-only crawls would never see authenticated content."""

    def test_setup_routes_saml_through_apply_auth_to_indexer(self):
        worker = _build_worker(
            saml_auth_cfg={"idp_url": "https://idp.example.com"},
            saml_username="user",
            saml_password="pw",
        )
        fake = _fake_indexer()
        fake.web_extractor.skip_static_prefetch = False
        original_new_context = fake.web_extractor.browser.new_context

        saml_session_sentinel = requests.Session()

        with patch("crawlers.website_crawler.Indexer", return_value=fake), \
             patch("crawlers.website_crawler.normalize_vectara_endpoint", return_value="https://api.vectara.io"), \
             patch("crawlers.website_crawler.setup_logging"), \
             patch("crawlers.website_crawler.SAMLAuthManager") as MockSAM:
            MockSAM.return_value.get_authenticated_session.return_value = saml_session_sentinel
            worker.setup()

        # requests session wired
        self.assertIs(fake.session, saml_session_sentinel)
        # static prefetch bypassed so IdP HTML can't poison the result
        self.assertTrue(fake.web_extractor.skip_static_prefetch)
        # new_context replaced with the cookie-transferring wrapper
        self.assertIsNot(fake.web_extractor.browser.new_context, original_new_context)

    def test_setup_raises_when_saml_secrets_missing(self):
        # Guards against a regression where the secrets check is bypassed
        # before the auth wiring is attempted.
        worker = _build_worker(saml_auth_cfg={"idp_url": "https://idp.example.com"})
        fake = _fake_indexer()

        with patch("crawlers.website_crawler.Indexer", return_value=fake), \
             patch("crawlers.website_crawler.normalize_vectara_endpoint", return_value="https://api.vectara.io"), \
             patch("crawlers.website_crawler.setup_logging"):
            with self.assertRaises(ValueError):
                worker.setup()


if __name__ == "__main__":
    unittest.main()
