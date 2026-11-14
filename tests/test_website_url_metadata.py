"""Spec tests for website_crawler.url_metadata: per-URL-pattern metadata.

Each rule is {pattern, metadata}. Patterns use re.match (like pos_regex). The first
matching rule's metadata is added to the page's document metadata; later rules are
ignored. Pages matching no rule get no extra metadata. `source` and `url` are set by
the crawler and cannot be overridden by a rule.
"""

import sys
import importlib.machinery
import re
import unittest
from unittest.mock import MagicMock

from omegaconf import OmegaConf

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from crawlers.website_crawler import PageCrawlWorker  # noqa: E402

RULES = [
    {"pattern": r"^https://example\.com/de/", "metadata": {"lang": "de"}},
    {"pattern": r"^https://example\.com/ja/", "metadata": {"lang": "ja", "region": "apac"}},
    {"pattern": r".*", "metadata": {"lang": "en"}},
]


def _worker(rules):
    cfg = OmegaConf.create({"vectara": {}, "website_crawler": {"url_metadata": rules}})
    worker = PageCrawlWorker(cfg, num_per_second=100)
    worker.indexer = MagicMock()
    worker.indexer.index_url.return_value = True
    worker.indexer.last_fetch_status = 200
    worker.indexer.last_throttled = False
    worker.indexer.was_skipped.return_value = False
    return worker


def _indexed_metadata(worker, url):
    worker.process(url, source="website")
    return worker.indexer.index_url.call_args.kwargs["metadata"]


class TestUrlMetadata(unittest.TestCase):

    def test_first_matching_rule_wins(self):
        w = _worker(RULES)
        self.assertEqual(_indexed_metadata(w, "https://example.com/de/about")["lang"], "de")
        md = _indexed_metadata(w, "https://example.com/ja/x")
        self.assertEqual((md["lang"], md["region"]), ("ja", "apac"))
        # The catch-all also matches /de/ but comes later, so /de/ stays "de".
        self.assertEqual(_indexed_metadata(w, "https://example.com/pricing")["lang"], "en")

    def test_no_match_adds_nothing(self):
        w = _worker(RULES[:2])
        md = _indexed_metadata(w, "https://example.com/pricing")
        self.assertEqual(md, {"source": "website", "url": "https://example.com/pricing"})

    def test_pattern_uses_match_not_search(self):
        w = _worker([{"pattern": "de/", "metadata": {"lang": "de"}}])
        self.assertNotIn("lang", _indexed_metadata(w, "https://example.com/de/about"))

    def test_rule_cannot_override_source_or_url(self):
        w = _worker([{"pattern": ".*", "metadata": {"source": "x", "url": "y", "lang": "fr"}}])
        md = _indexed_metadata(w, "https://example.com/a")
        self.assertEqual(md, {"source": "website", "url": "https://example.com/a", "lang": "fr"})

    def test_rule_metadata_not_shared_across_pages(self):
        w = _worker([{"pattern": ".*", "metadata": {"lang": "en"}}])
        _indexed_metadata(w, "https://example.com/a")["sitemap_lastmod"] = "mutated"
        self.assertNotIn("sitemap_lastmod", _indexed_metadata(w, "https://example.com/b"))

    def test_metadata_is_plain_dict_with_nested_values(self):
        w = _worker([{"pattern": ".*", "metadata": {"tags": ["a", "b"]}}])
        md = _indexed_metadata(w, "https://example.com/a")
        self.assertEqual(md["tags"], ["a", "b"])
        self.assertIs(type(md["tags"]), list)

    def test_no_rules_configured(self):
        cfg = OmegaConf.create({"vectara": {}, "website_crawler": {}})
        w = PageCrawlWorker(cfg, num_per_second=100)
        self.assertEqual(w.url_metadata, [])

    def test_empty_url_metadata_key(self):
        cfg = OmegaConf.create({"vectara": {}, "website_crawler": {"url_metadata": None}})
        self.assertEqual(PageCrawlWorker(cfg, num_per_second=100).url_metadata, [])

    def test_invalid_pattern_fails_at_construction(self):
        with self.assertRaises(re.error):
            _worker([{"pattern": "(", "metadata": {"lang": "de"}}])


if __name__ == "__main__":
    unittest.main()
