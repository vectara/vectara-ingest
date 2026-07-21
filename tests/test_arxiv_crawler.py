import sys
import importlib.machinery
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

# Stub heavy/optional deps pulled in via core.crawler/core.indexer.
for mod in ["arxiv", "cairosvg", "whisper", "pdf2image", "pydub"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

from crawlers.arxiv_crawler import ArxivCrawler


class TestArxivClientApi(unittest.TestCase):

    def test_crawl_uses_client_results(self):
        # Regression: arxiv 2.x+ removed Search.results(); papers must be
        # fetched via arxiv.Client().results(search) or the crawler silently
        # indexes nothing.
        result = MagicMock()
        result.entry_id = "http://arxiv.org/abs/2401.00001v1"
        result.published.date.return_value = date(2024, 1, 1)
        result.pdf_url = "https://arxiv.org/pdf/2401.00001v1"
        result.title = "A paper"
        result.authors = ["A. Author"]
        result.summary = "An abstract"

        mock_arxiv = MagicMock()
        mock_arxiv.Client.return_value.results.return_value = iter([result])

        crawler = ArxivCrawler.__new__(ArxivCrawler)
        crawler.cfg = OmegaConf.create({
            "arxiv_crawler": {
                "n_papers": 1,
                "query_terms": ["llm"],
                "start_year": 2020,
                "arxiv_category": "cs",
                "sort_by": "date",
            },
        })
        crawler.indexer = MagicMock()

        with patch("crawlers.arxiv_crawler.arxiv", mock_arxiv), \
             patch("crawlers.arxiv_crawler.create_session_with_retries",
                   return_value=MagicMock()), \
             patch("crawlers.arxiv_crawler.configure_session_for_ssl"):
            crawler.crawl()

        crawler.indexer.index_url.assert_called_once()
        indexed_url = crawler.indexer.index_url.call_args.args[0]
        self.assertEqual(indexed_url, "https://arxiv.org/pdf/2401.00001v1.pdf")

    def _make_crawler(self):
        crawler = ArxivCrawler.__new__(ArxivCrawler)
        crawler.cfg = OmegaConf.create({
            "arxiv_crawler": {
                "n_papers": 1,
                "query_terms": ["llm"],
                "start_year": 2020,
                "arxiv_category": "cs",
                "sort_by": "date",
            },
        })
        crawler.indexer = MagicMock()
        return crawler

    def test_crawl_raises_when_query_fails_before_any_results(self):
        # Regression: an upstream failure before any results were fetched must
        # not be swallowed — otherwise ingest marks the crawl completed even
        # though it never reached arXiv.
        mock_arxiv = MagicMock()
        mock_arxiv.Client.return_value.results.side_effect = RuntimeError("arxiv down")

        crawler = self._make_crawler()
        with patch("crawlers.arxiv_crawler.arxiv", mock_arxiv), \
             patch("crawlers.arxiv_crawler.create_session_with_retries",
                   return_value=MagicMock()), \
             patch("crawlers.arxiv_crawler.configure_session_for_ssl"):
            with self.assertRaises(RuntimeError):
                crawler.crawl()

        crawler.indexer.index_url.assert_not_called()

    def test_crawl_continues_with_partial_results_on_midstream_failure(self):
        # A failure after some results were fetched should still index what
        # we have (existing behavior).
        result = MagicMock()
        result.entry_id = "http://arxiv.org/abs/2401.00001v1"
        result.published.date.return_value = date(2024, 1, 1)
        result.pdf_url = "https://arxiv.org/pdf/2401.00001v1"
        result.title = "A paper"
        result.authors = ["A. Author"]
        result.summary = "An abstract"

        def one_then_fail(search):
            yield result
            raise RuntimeError("connection dropped")

        mock_arxiv = MagicMock()
        mock_arxiv.Client.return_value.results.side_effect = one_then_fail

        crawler = self._make_crawler()
        with patch("crawlers.arxiv_crawler.arxiv", mock_arxiv), \
             patch("crawlers.arxiv_crawler.create_session_with_retries",
                   return_value=MagicMock()), \
             patch("crawlers.arxiv_crawler.configure_session_for_ssl"):
            crawler.crawl()

        crawler.indexer.index_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
