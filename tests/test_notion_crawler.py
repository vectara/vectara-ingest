"""Notion crawler deletion-safety tests.

Regression: a transient blocks-fetch failure (rate limit, flaky API) must leave the page in
the "present at source" set — the page still exists in Notion, we just failed to read it.
Otherwise `remove_old_content: true` deletes a live page from the corpus.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault('cairosvg', MagicMock())
sys.modules.setdefault('notion_client', MagicMock())

from omegaconf import OmegaConf

from crawlers.notion_crawler import NotionCrawler


def _cfg():
    return OmegaConf.create({
        "notion_crawler": {
            "notion_api_key": "k",
            "remove_old_content": True,
            "incremental": False,
            # 0 so the (separately tested) ratio guard does not mask the per-page behavior.
            "deletion_safety_ratio": 0.0,
            "crawl_report": False,
        },
        "vectara": {},
    })


def _page(page_id):
    return {
        "id": page_id,
        "url": f"https://notion.so/{page_id}",
        "properties": {"title": {"type": "title", "title": [{"plain_text": page_id}]}},
    }


def _corpus_doc(doc_id):
    return {"id": doc_id, "url": f"https://notion.so/{doc_id}", "source": "notion",
            "fingerprint": None, "content_hash": None, "config_sig": None,
            "last_updated": None, "parent_doc_id": None}


class TestNotionFetchFailureNotDeleted(unittest.TestCase):
    def _crawler(self, indexer):
        crawler = NotionCrawler.__new__(NotionCrawler)
        crawler.cfg = _cfg()
        crawler.incremental = False
        crawler.source = "notion"
        crawler.tracker = None
        crawler.check_shutdown = MagicMock()
        crawler.notion_api_key = "k"
        crawler.indexer = indexer
        return crawler

    def test_fetch_failure_page_survives_deletion_pass(self):
        # Two pages in Notion and in the corpus; fetching p_fail's blocks raises. Only a page
        # actually gone from Notion may be deleted — p_fail must survive.
        indexer = MagicMock()
        indexer.source_tag = "notion"
        indexer._list_docs.return_value = [_corpus_doc("p_ok"), _corpus_doc("p_fail")]
        indexer.was_skipped.return_value = False
        indexer.delete_doc.return_value = True

        def _blocks_list(page_id):
            if page_id == "p_fail":
                raise RuntimeError("rate limited")
            return {"results": [{"type": "paragraph",
                                 "paragraph": {"rich_text": [{"plain_text": "hello"}]}}]}

        notion = MagicMock()
        notion.blocks.children.list.side_effect = _blocks_list
        crawler = self._crawler(indexer)

        with patch("crawlers.notion_crawler.Client", return_value=notion), \
             patch("crawlers.notion_crawler.list_all_pages",
                   return_value=[_page("p_ok"), _page("p_fail")]):
            crawler.crawl()

        indexer.delete_doc.assert_not_called()

    def test_page_gone_from_source_is_deleted(self):
        # Sanity check the deletion pass still works: a corpus doc absent from Notion is removed.
        indexer = MagicMock()
        indexer.source_tag = "notion"
        indexer._list_docs.return_value = [_corpus_doc("p_ok"), _corpus_doc("p_gone")]
        indexer.was_skipped.return_value = False
        indexer.delete_doc.return_value = True

        notion = MagicMock()
        notion.blocks.children.list.return_value = {
            "results": [{"type": "paragraph",
                         "paragraph": {"rich_text": [{"plain_text": "hello"}]}}]}
        crawler = self._crawler(indexer)

        with patch("crawlers.notion_crawler.Client", return_value=notion), \
             patch("crawlers.notion_crawler.list_all_pages", return_value=[_page("p_ok")]):
            crawler.crawl()

        indexer.delete_doc.assert_called_once_with("p_gone")


if __name__ == "__main__":
    unittest.main()
