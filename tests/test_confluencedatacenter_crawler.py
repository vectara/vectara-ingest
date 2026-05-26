import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

# Mock only third-party deps that may be missing in the test env. Mirrors the
# approach in test_wolken_crawler.py — do NOT inject MagicMocks for `core.*`.
for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf
from furl import furl

from crawlers.confluencedatacenter_crawler import ConfluencedatacenterCrawler


def _make_crawler(confluence_cfg):
    """Build a ConfluencedatacenterCrawler with mocked dependencies."""
    cfg = {
        "vectara": {"endpoint": "https://api.vectara.io", "reindex": False},
        "confluencedatacenter": confluence_cfg,
    }
    omega_cfg = OmegaConf.create(cfg)

    with patch("crawlers.confluencedatacenter_crawler.Crawler.__init__", return_value=None):
        crawler = ConfluencedatacenterCrawler.__new__(ConfluencedatacenterCrawler)
        crawler.cfg = omega_cfg
        crawler.indexer = MagicMock()
        crawler.tracker = None
        crawler.shutdown_requested = False
        crawler.verbose = False
        crawler.base_url = furl(confluence_cfg.get("base_url", "https://conf.example.com"))
        crawler.body_view = confluence_cfg.get("body_view", "export_view")
        crawler.source = confluence_cfg.get("source", "Confluence")
        crawler.df_parser = None
        crawler.session = MagicMock()
    return crawler


class TestAuthSelection(unittest.TestCase):
    """The PAT/basic-auth selection is the behavior we are adding/pinning."""

    def test_pat_only_uses_bearer_header_and_no_auth_tuple(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_pat": "secret-pat-123",
        })
        crawler._setup_auth()
        self.assertEqual(
            crawler.confluence_headers.get("Authorization"), "Bearer secret-pat-123"
        )
        self.assertEqual(crawler.confluence_headers.get("Accept"), "application/json")
        self.assertIsNone(crawler.confluence_auth)

    def test_basic_auth_only_uses_auth_tuple_and_no_bearer(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_username": "alice",
            "confluence_datacenter_password": "pw",
        })
        crawler._setup_auth()
        self.assertNotIn("Authorization", crawler.confluence_headers)
        self.assertEqual(crawler.confluence_auth, ("alice", "pw"))

    def test_pat_wins_when_both_present_and_logs(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_pat": "secret-pat-123",
            "confluence_datacenter_username": "alice",
            "confluence_datacenter_password": "pw",
        })
        with self.assertLogs(
            "crawlers.confluencedatacenter_crawler", level="INFO"
        ) as cm:
            crawler._setup_auth()
        self.assertEqual(
            crawler.confluence_headers.get("Authorization"), "Bearer secret-pat-123"
        )
        self.assertIsNone(crawler.confluence_auth)
        # A message must explain that username/password is being ignored.
        self.assertTrue(any("username" in line.lower() for line in cm.output))

    def test_no_auth_configured_raises(self):
        crawler = _make_crawler({"base_url": "https://conf.example.com"})
        with self.assertRaises(ValueError):
            crawler._setup_auth()

    def test_token_never_logged(self):
        """The PAT must not appear in any log output."""
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_pat": "super-secret-token",
            "confluence_datacenter_username": "alice",
            "confluence_datacenter_password": "pw",
        })
        with self.assertLogs(
            "crawlers.confluencedatacenter_crawler", level="DEBUG"
        ) as cm:
            crawler._setup_auth()
        self.assertFalse(
            any("super-secret-token" in line for line in cm.output),
            "PAT must never be written to logs",
        )


class TestCrawlWiresAuthIntoRequests(unittest.TestCase):
    """Guards that crawl() actually applies the selected auth to HTTP calls."""

    def _run_crawl_capturing_get(self, crawler):
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"results": [], "_links": {}}  # no "next" -> exit
        mock_session.get.return_value = resp
        with patch(
            "crawlers.confluencedatacenter_crawler.create_session_with_retries",
            return_value=mock_session,
        ):
            crawler.crawl()
        return mock_session.get.call_args

    def test_pat_sends_bearer_header(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_cql": 'space = "TEST"',
            "confluence_datacenter_pat": "secret-pat-123",
        })
        call = self._run_crawl_capturing_get(crawler)
        self.assertEqual(call.kwargs["headers"].get("Authorization"), "Bearer secret-pat-123")
        self.assertIsNone(call.kwargs["auth"])

    def test_basic_auth_sends_auth_tuple(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_cql": 'space = "TEST"',
            "confluence_datacenter_username": "alice",
            "confluence_datacenter_password": "pw",
        })
        call = self._run_crawl_capturing_get(crawler)
        self.assertNotIn("Authorization", call.kwargs["headers"])
        self.assertEqual(call.kwargs["auth"], ("alice", "pw"))

    def test_401_response_raises_runtime_error(self):
        """A 401 on the search request must fail loudly, not silently return."""
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_cql": 'space = "TEST"',
            "confluence_datacenter_pat": "bad-pat",
        })
        mock_session = MagicMock()
        resp = MagicMock()
        resp.status_code = 401
        mock_session.get.return_value = resp
        with patch(
            "crawlers.confluencedatacenter_crawler.create_session_with_retries",
            return_value=mock_session,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                crawler.crawl()
        self.assertIn("401", str(ctx.exception))


class TestPageMetadata(unittest.TestCase):
    """Pins the metadata improvements adopted from the rewrite."""

    def _page_content(self):
        return {
            "id": "12345",
            "type": "page",
            "title": "My Page",
            "version": {"when": "2026-01-02T03:04:05Z", "number": 7},
            "space": {"id": "1", "key": "TEST", "name": "Test Space"},
            "_links": {"webui": "/display/TEST/My+Page"},
            "body": {"export_view": {"value": "<p>hello</p>"}},
        }

    def _captured_metadata(self, crawler):
        # _process_non_attachment -> indexer.index_file(file, url, metadata, doc_id)
        self.assertTrue(crawler.indexer.index_file.called)
        return crawler.indexer.index_file.call_args.args[2]

    def _process(self, content):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_pat": "pat",
            "confluence_include_attachments": False,
        })
        crawler.indexer.index_file.return_value = True
        crawler.process_content(content)
        return self._captured_metadata(crawler)

    def test_metadata_has_title_source_and_correct_last_updated_key(self):
        md = self._process(self._page_content())
        self.assertEqual(md.get("title"), "My Page")
        self.assertEqual(md.get("source"), "Confluence")
        self.assertEqual(md.get("last_updated"), "2026-01-02T03:04:05Z")
        self.assertNotIn("last_updates", md)  # the old typo must be gone

    def test_updated_by_with_legacy_keys(self):
        content = self._page_content()
        content["version"]["by"] = {"username": "jdoe", "userKey": "ff8080"}
        md = self._process(content)
        self.assertEqual(md["updated_by"], {"username": "jdoe", "userKey": "ff8080"})

    def test_updated_by_without_legacy_keys_does_not_crash(self):
        # SSO/PAT instances may return only displayName (no username/userKey).
        content = self._page_content()
        content["version"]["by"] = {"type": "known", "displayName": "Jane Doe"}
        md = self._process(content)  # must not raise KeyError
        self.assertEqual(md["updated_by"], {"displayName": "Jane Doe"})

    def test_updated_by_empty_object_omits_field(self):
        content = self._page_content()
        content["version"]["by"] = {"type": "anonymous"}
        md = self._process(content)
        self.assertNotIn("updated_by", md)


class TestAttachmentMetadata(unittest.TestCase):
    """Attachments get their own source and attachment-type metadata."""

    def _attachment_content(self):
        return {
            "id": "999",
            "type": "attachment",
            "title": "report.pdf",
            "version": {"when": "2026-01-02T03:04:05Z", "number": 1},
            "_links": {"download": "/download/attachments/123/report.pdf"},
        }

    def test_attachment_source_and_type_are_set(self):
        crawler = _make_crawler({
            "base_url": "https://conf.example.com",
            "confluence_datacenter_pat": "pat",
            "confluence_include_attachments": True,
            "include_document_attachments": True,
        })
        crawler._setup_auth()  # the download path uses confluence_headers/auth
        download = MagicMock()
        download.ok = True
        download.iter_content.return_value = [b"%PDF-1.4 fake"]
        crawler.session.get.return_value = download
        crawler.indexer.index_file.return_value = True

        crawler.process_content(self._attachment_content())

        self.assertTrue(crawler.indexer.index_file.called)
        # index_file(temp_path, url, metadata, doc_id) -> metadata is args[2]
        md = crawler.indexer.index_file.call_args.args[2]
        self.assertEqual(md.get("source"), "confluence_attachment")
        self.assertEqual(md.get("filename"), "report.pdf")
        self.assertEqual(md.get("attachment_type"), "document")


if __name__ == "__main__":
    unittest.main()
