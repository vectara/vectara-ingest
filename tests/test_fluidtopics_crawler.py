import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

from crawlers.fluidtopics_crawler import (
    FluidtopicsCrawler,
    _clean_markup,
    _get_path,
    _safe_doc_id,
    _str_or_empty,
)


def _make_crawler(**crawler_overrides):
    cfg = OmegaConf.create({
        "vectara": {"reindex": False},
        "fluidtopics_crawler": {
            "base_url": "https://docs.example.fluidtopics.net",
            "api_key": "ft-key",
            "api_key_header": "X-Api-Key",
            "search_endpoint": "/api/search",
            "content_endpoint_template": "/api/topics/{id}",
            "page_size": 2,
            "num_per_second": 100000,
            "metadata_paths": {
                "device_family": "metadata.device_family",
                "access_tier": "acl.tier",
            },
        },
    })
    for key, value in crawler_overrides.items():
        cfg.fluidtopics_crawler[key] = value

    with patch("crawlers.fluidtopics_crawler.Crawler.__init__", return_value=None):
        crawler = FluidtopicsCrawler.__new__(FluidtopicsCrawler)
        crawler.cfg = cfg
        crawler.indexer = MagicMock()
        crawler.tracker = None
        crawler.shutdown_requested = False
        crawler.verbose = False
        FluidtopicsCrawler.__init__(crawler, cfg, "https://api.vectara.io", "corpus", "vectara-key")
    return crawler


class TestFluidTopicsHelpers(unittest.TestCase):

    def test_get_path_reads_nested_dict_and_list(self):
        data = {"a": {"b": [{"c": "value"}]}}
        self.assertEqual(_get_path(data, "a.b.0.c"), "value")
        self.assertIsNone(_get_path(data, "a.b.1.c"))

    def test_clean_markup_handles_html_and_plain_text(self):
        self.assertIn("Hello", _clean_markup("<p>Hello <b>world</b></p>"))
        self.assertEqual(_clean_markup("  Plain   text "), "Plain text")

    def test_safe_doc_id_and_str_or_empty(self):
        self.assertEqual(_safe_doc_id("Topic 123/ABC"), "Topic-123-ABC")
        self.assertEqual(_str_or_empty(None), "")
        self.assertEqual(_str_or_empty(0), "0")


class TestFluidTopicsCrawler(unittest.TestCase):

    def test_headers_support_raw_api_key(self):
        crawler = _make_crawler()
        headers = crawler._headers()
        self.assertEqual(headers["X-Api-Key"], "ft-key")

    def test_headers_support_auth_scheme(self):
        crawler = _make_crawler(api_key_header="Authorization", auth_scheme="Bearer")
        self.assertEqual(crawler._headers()["Authorization"], "Bearer ft-key")

    def test_iter_items_paginates_until_short_page(self):
        crawler = _make_crawler()
        responses = [
            {"results": [{"id": "1"}, {"id": "2"}]},
            {"results": [{"id": "3"}]},
        ]
        crawler._request = MagicMock(side_effect=responses)

        items = crawler.iter_items()

        self.assertEqual([i["id"] for i in items], ["1", "2", "3"])
        self.assertEqual(crawler._request.call_count, 2)
        self.assertEqual(crawler._request.call_args_list[0].kwargs["params"]["page"], 0)
        self.assertEqual(crawler._request.call_args_list[1].kwargs["params"]["page"], 1)

    def test_build_metadata_merges_item_and_content_paths(self):
        crawler = _make_crawler(static_metadata={"tenant": "altera"})
        item = {"id": "t1", "metadata": {"device_family": "Agilex"}}
        content = {"acl": {"tier": "public"}, "url": "https://reader/t1"}

        metadata = crawler._build_metadata(item, content, "t1", "Title")

        self.assertEqual(metadata["source"], "fluid-topics")
        self.assertEqual(metadata["document_id"], "t1")
        self.assertEqual(metadata["device_family"], "Agilex")
        self.assertEqual(metadata["access_tier"], "public")
        self.assertEqual(metadata["url"], "https://reader/t1")
        self.assertEqual(metadata["tenant"], "altera")

    def test_crawl_indexes_content(self):
        crawler = _make_crawler()
        crawler.iter_items = MagicMock(return_value=[{
            "id": "topic-1",
            "title": "Getting started",
            "metadata": {"device_family": "Agilex"},
        }])
        crawler._fetch_content_record = MagicMock(return_value={
            "content": "<topic><p>Install Quartus first.</p></topic>",
            "acl": {"tier": "public"},
        })
        crawler.indexer.index_segments = MagicMock(return_value=True)

        crawler.crawl()

        crawler.indexer.index_segments.assert_called_once()
        kwargs = crawler.indexer.index_segments.call_args.kwargs
        self.assertEqual(kwargs["doc_id"], "fluid-topics-topic-1")
        self.assertEqual(kwargs["doc_title"], "Getting started")
        self.assertIn("Install Quartus first", kwargs["texts"][0])
        self.assertEqual(kwargs["doc_metadata"]["access_tier"], "public")

    def test_crawl_skips_items_with_no_content(self):
        crawler = _make_crawler()
        crawler.iter_items = MagicMock(return_value=[{"id": "empty", "title": "Empty"}])
        crawler._fetch_content_record = MagicMock(return_value={"content": ""})
        crawler.indexer.index_segments = MagicMock(return_value=True)

        crawler.crawl()

        crawler.indexer.index_segments.assert_not_called()


class TestFluidTopicsSecretsMapping(unittest.TestCase):

    def test_fluidtopics_prefix_maps_to_crawler_config(self):
        from ingest import update_environment

        cfg = OmegaConf.create({"vectara": {}, "fluidtopics_crawler": {}})
        update_environment(cfg, "test", {
            "FLUIDTOPICS_API_KEY": "secret",
            "FLUID_TOPICS_BASE_URL": "https://docs.example.fluidtopics.net",
        })

        self.assertEqual(cfg.fluidtopics_crawler.api_key, "secret")
        self.assertEqual(cfg.fluidtopics_crawler.base_url, "https://docs.example.fluidtopics.net")


if __name__ == "__main__":
    unittest.main()
