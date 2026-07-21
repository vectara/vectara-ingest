import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

# Stub heavy/optional deps pulled in via core.crawler/core.indexer.
for mod in ["Bio", "cairosvg", "whisper", "pdf2image", "pydub"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

from crawlers.pmc_crawler import PmcCrawler

ARTICLE_XML = """<pmc-articleset><article>
<article-title>A paper</article-title>
<pub-date><year>2024</year><month>1</month><day>1</day></pub-date>
</article></pmc-articleset>"""


def make_crawler():
    crawler = PmcCrawler.__new__(PmcCrawler)
    crawler.cfg = OmegaConf.create({"pmc_crawler": {}})
    crawler.indexer = MagicMock()
    crawler.rate_limiter = MagicMock()
    crawler.crawled_pmc_ids = set()
    crawler.session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.text = ARTICLE_XML
    crawler.session.get.return_value = response
    return crawler


class TestPmcPaperIndexing(unittest.TestCase):

    def test_pdf_url_uses_current_pmc_domain(self):
        # Regression: www.ncbi.nlm.nih.gov/pmc/... now 301s to
        # pmc.ncbi.nlm.nih.gov; the crawler must use the current domain.
        crawler = make_crawler()
        with patch("crawlers.pmc_crawler.get_top_n_papers",
                   return_value=["123"]):
            crawler.index_papers_by_topic("topic", 1)

        crawler.indexer.index_url.assert_called_once()
        indexed_url = crawler.indexer.index_url.call_args.args[0]
        self.assertEqual(
            indexed_url, "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/")

    def test_index_url_failure_is_logged(self):
        # Regression: index_url's return value was discarded, so per-paper
        # indexing failures were completely silent.
        crawler = make_crawler()
        crawler.indexer.index_url.return_value = False
        with patch("crawlers.pmc_crawler.get_top_n_papers",
                   return_value=["123"]):
            with self.assertLogs("crawlers.pmc_crawler", level="WARNING") as cm:
                crawler.index_papers_by_topic("topic", 1)
        self.assertTrue(any("123" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
