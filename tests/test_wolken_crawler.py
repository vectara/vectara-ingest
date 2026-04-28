import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock heavy dependencies before importing the crawler
for mod in [
    "cairosvg", "whisper", "pdf2image",
    "playwright", "playwright.sync_api",
    "core.summary", "core.indexer", "core.web_content_extractor",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from crawlers.wolken_crawler import WolkenCrawler, clean_html


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
        from omegaconf import OmegaConf, DictConfig
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
