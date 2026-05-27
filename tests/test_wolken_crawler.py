import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

# Mock only third-party deps that may be missing in the test env. Do NOT inject
# MagicMocks for `core.*` modules — that pollutes sys.modules and makes the rest
# of the suite order-dependent (other tests would get the mock instead of the
# real class). `nbconvert` calls `importlib.util.find_spec("playwright")` at
# import time, so the playwright mock needs a real ModuleSpec.
for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from crawlers.wolken_crawler import WolkenCrawler, clean_html, _str_or_empty


class TestCleanHtml(unittest.TestCase):

    def test_strips_tags(self):
        self.assertEqual(clean_html("<p>Hello <b>world</b></p>"), "Hello world")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_html("  Hello   world  "), "Hello world")

    def test_empty_string(self):
        self.assertEqual(clean_html(""), "")

    def test_none(self):
        self.assertEqual(clean_html(None), "")

    def test_no_tags(self):
        self.assertEqual(clean_html("Just plain text"), "Just plain text")


def _make_crawler(**overrides):
    """Create a WolkenCrawler with mocked dependencies."""
    cfg = {
        "vectara": {
            "endpoint": "https://api.vectara.io",
            "reindex": False,
        },
        "wolken_crawler": {
            "api_endpoint": "https://api-test.wolkenservicedesk.com",
            "domain": "testdomain",
            "client_id": "test-client",
            "service_account": "svc@test.com",
            "auth_code": "Basic dGVzdA==",
            "refresh_token": "test-refresh-token",
            "batch_size": 100,
            "content_fields": ["introduction", "cause", "resolution"],
        },
    }
    cfg.update(overrides)

    from omegaconf import OmegaConf
    omega_cfg = OmegaConf.create(cfg)

    with patch("crawlers.wolken_crawler.Crawler.__init__", return_value=None):
        crawler = WolkenCrawler.__new__(WolkenCrawler)
        crawler.cfg = omega_cfg
        crawler.indexer = MagicMock()
        crawler.tracker = None
        crawler.shutdown_requested = False
        crawler.verbose = False

        crawler_cfg = omega_cfg.get("wolken_crawler", {})
        crawler.api_endpoint = crawler_cfg.get("api_endpoint", "")
        crawler.domain = crawler_cfg.get("domain", "")
        crawler.client_id = crawler_cfg.get("client_id", "")
        crawler.service_account = crawler_cfg.get("service_account", "")
        crawler.auth_code = crawler_cfg.get("auth_code", "")
        crawler.refresh_token_value = crawler_cfg.get("refresh_token", "")
        crawler.batch_size = crawler_cfg.get("batch_size", 100)
        crawler.kb_source_id = crawler_cfg.get("kb_source_id", None)
        crawler.content_fields = list(crawler_cfg.get("content_fields", []))

        crawler.access_token = "test-access-token"
        crawler.token_expires_at = 9999999999
        crawler.session = MagicMock()

    return crawler


class TestBuildArticleContent(unittest.TestCase):

    def test_extracts_configured_fields(self):
        crawler = _make_crawler()
        details = {
            "articleOtherInfo": {
                "introduction": "<p>Intro text</p>",
                "cause": "Root cause here",
                "resolution": "<b>Fix it</b>",
                "environment": "Should be ignored",
            }
        }
        sections = crawler._build_article_content(details)
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0], ("Introduction", "Intro text"))
        self.assertEqual(sections[1], ("Cause", "Root cause here"))
        self.assertEqual(sections[2], ("Resolution", "Fix it"))

    def test_fallback_to_description(self):
        crawler = _make_crawler()
        details = {
            "articleOtherInfo": {},
            "description": "Fallback description",
        }
        sections = crawler._build_article_content(details)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0], ("Description", "Fallback description"))

    def test_empty_article(self):
        crawler = _make_crawler()
        details = {"articleOtherInfo": {}}
        sections = crawler._build_article_content(details)
        self.assertEqual(sections, [])

    def test_none_fields_handled(self):
        crawler = _make_crawler()
        details = {
            "articleOtherInfo": {
                "introduction": None,
                "cause": "",
                "resolution": "Fix",
            }
        }
        sections = crawler._build_article_content(details)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0], ("Resolution", "Fix"))


class TestApiHeaders(unittest.TestCase):

    def test_returns_correct_headers(self):
        crawler = _make_crawler()
        headers = crawler._api_headers()
        self.assertEqual(headers["clientId"], "test-client")
        self.assertEqual(headers["domain"], "testdomain")
        self.assertEqual(headers["serviceAccount"], "svc@test.com")
        self.assertEqual(headers["Authorization"], "Bearer test-access-token")

    def test_refreshes_token_when_expired(self):
        crawler = _make_crawler()
        crawler.access_token = None
        crawler.token_expires_at = 0

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()
        crawler.session.post.return_value = mock_response

        headers = crawler._api_headers()
        self.assertEqual(headers["Authorization"], "Bearer new-token")
        crawler.session.post.assert_called_once()

    def test_short_lived_token_does_not_expire_immediately(self):
        """Regression: if expires_in < safety margin, the clamp must keep the token usable."""
        crawler = _make_crawler()
        crawler.access_token = None
        crawler.token_expires_at = 0

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "short-token",
            "expires_in": 60,  # less than the 120s safety margin
        }
        mock_response.raise_for_status = MagicMock()
        crawler.session.post.return_value = mock_response

        import time as _time
        before = _time.time()
        crawler._ensure_token()
        # token_expires_at must be in the future, otherwise we'd refresh on every call
        self.assertGreater(crawler.token_expires_at, before)


class TestStrOrEmpty(unittest.TestCase):

    def test_none_becomes_empty(self):
        self.assertEqual(_str_or_empty(None), "")

    def test_int_stringified(self):
        self.assertEqual(_str_or_empty(42), "42")

    def test_empty_string_passthrough(self):
        self.assertEqual(_str_or_empty(""), "")

    def test_zero_stringified(self):
        # zero is not None — must keep "0", not collapse to ""
        self.assertEqual(_str_or_empty(0), "0")


class TestMetadataNoneHandling(unittest.TestCase):
    """Regression: dict.get returns None when key exists with None value, not the default."""

    def test_null_status_id_does_not_become_string_none(self):
        crawler = _make_crawler()
        crawler.indexer.index_segments = MagicMock(return_value=True)

        def mock_get(path, params=None):
            if "categories" in path:
                return {"data": [{"catId": 1, "catName": "General"}]}
            elif "/api/kb/articles/1/" in path:
                return {"data": [{"articleId": 101, "articleTitle": "T"}]}
            elif "/api/kb/articles/101" in path:
                return {"data": {
                    "articleTitle": "T",
                    "articleOtherInfo": {
                        "introduction": "Some intro",
                        "validationStatusId": None,
                        "publishedDate": None,
                    },
                    "createdTime": None,
                    "updatedTime": None,
                    "statusId": None,
                }}
            return {"data": []}

        crawler._get = mock_get
        crawler.crawl()

        metadata = crawler.indexer.index_segments.call_args.kwargs["doc_metadata"]
        self.assertEqual(metadata["status_id"], "")
        self.assertEqual(metadata["validation_status_id"], "")
        self.assertEqual(metadata["created_time"], "")
        self.assertEqual(metadata["updated_time"], "")
        self.assertEqual(metadata["published_date"], "")
        # Sanity: nothing should be the literal string "None"
        self.assertNotIn("None", metadata.values())


class TestCrawlFlow(unittest.TestCase):

    def test_crawl_indexes_articles(self):
        crawler = _make_crawler()
        crawler.indexer.index_segments = MagicMock(return_value=True)

        # Mock _get to return categories, then articles, then details
        call_count = [0]
        def mock_get(path, params=None):
            call_count[0] += 1
            if "categories" in path:
                return {"data": [{"catId": 1, "catName": "General"}]}
            elif "/api/kb/articles/1/" in path:
                return {"data": [
                    {"articleId": 101, "articleTitle": "Test Article"},
                ]}
            elif "/api/kb/articles/101" in path:
                return {"data": {
                    "articleTitle": "Test Article",
                    "articleOtherInfo": {
                        "introduction": "Intro text",
                        "cause": "Some cause",
                        "resolution": "Fix it",
                    },
                    "createdTime": "2024-01-01",
                    "updatedTime": "2024-01-02",
                    "statusId": 2,
                }}
            return {"data": []}

        crawler._get = mock_get
        crawler.crawl()

        crawler.indexer.index_segments.assert_called_once()
        call_args = crawler.indexer.index_segments.call_args
        self.assertEqual(call_args.kwargs["doc_id"], "wolken-kb-101")
        self.assertEqual(call_args.kwargs["doc_title"], "Test Article")
        self.assertEqual(len(call_args.kwargs["texts"]), 3)

    def test_crawl_skips_indexed_ids(self):
        crawler = _make_crawler()
        crawler.tracker = MagicMock()
        crawler.tracker.get_indexed_ids.return_value = {"wolken-kb-101"}
        crawler.indexer.index_segments = MagicMock(return_value=True)

        def mock_get(path, params=None):
            if "categories" in path:
                return {"data": [{"catId": 1, "catName": "General"}]}
            elif "/api/kb/articles/1/" in path:
                return {"data": [{"articleId": 101, "articleTitle": "Already Indexed"}]}
            return {"data": []}

        crawler._get = mock_get
        crawler.crawl()

        crawler.indexer.index_segments.assert_not_called()

    def test_crawl_handles_empty_categories(self):
        crawler = _make_crawler()
        crawler.indexer.index_segments = MagicMock()

        crawler._get = lambda path, params=None: {"data": []}
        crawler.crawl()

        crawler.indexer.index_segments.assert_not_called()


class TestSecretsMapping(unittest.TestCase):

    def test_wolken_prefix_maps_to_crawler_config(self):
        """Verify WOLKEN_ prefixed secrets map to wolken_crawler config."""
        from omegaconf import OmegaConf
        from ingest import update_environment

        cfg = OmegaConf.create({
            "vectara": {},
            "wolken_crawler": {},
        })

        env_dict = {
            "WOLKEN_API_ENDPOINT": "https://api-test.wolkenservicedesk.com",
            "WOLKEN_DOMAIN": "testdomain",
            "WOLKEN_CLIENT_ID": "my-client",
        }

        update_environment(cfg, "test", env_dict)

        self.assertEqual(cfg.wolken_crawler.api_endpoint, "https://api-test.wolkenservicedesk.com")
        self.assertEqual(cfg.wolken_crawler.domain, "testdomain")
        self.assertEqual(cfg.wolken_crawler.client_id, "my-client")


if __name__ == "__main__":
    unittest.main()
