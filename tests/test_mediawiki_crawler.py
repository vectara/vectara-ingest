import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from crawlers.mediawiki_crawler import MediawikiCrawler


PAGE_EXTRACT = "This is the article body text."


def _session_returning(*json_payloads):
    """A mock session whose successive .get() calls return the given JSON payloads."""
    session = MagicMock()
    responses = []
    for payload in json_payloads:
        r = MagicMock()
        r.json.return_value = payload
        responses.append(r)
    session.get.side_effect = responses
    return session


class TestFetchPageAndLinks(unittest.TestCase):
    # Regression: the revisions condition was inverted, so revision metadata
    # was never extracted (or crashed when revisions were missing).

    def test_revision_metadata_extracted_when_present(self):
        info = {"query": {"pages": {"1": {
            "extract": PAGE_EXTRACT,
            "fullurl": "https://wiki.example.org/wiki/Foo",
            "touched": "2024-05-01T00:00:00Z",
            "revisions": [{"user": "alice", "timestamp": "2024-06-01T12:00:00Z"}],
        }}}}
        links = {"query": {"pages": {"1": {"links": [{"ns": 0, "title": "Bar"}]}}}}
        session = _session_returning(info, links)

        crawler = MediawikiCrawler.__new__(MediawikiCrawler)
        doc, link_titles = crawler._fetch_page_and_links(
            session, "https://wiki.example.org/api.php", "Foo")

        self.assertEqual(doc["metadata"]["last_edit_user"], "alice")
        self.assertEqual(doc["metadata"]["last_edit_time"], "2024-06-01T12:00:00Z")
        self.assertEqual(link_titles, ["Bar"])

    def test_fallback_when_revisions_missing(self):
        info = {"query": {"pages": {"1": {
            "extract": PAGE_EXTRACT,
            "fullurl": "https://wiki.example.org/wiki/Foo",
            "touched": "2024-05-01T00:00:00Z",
        }}}}
        links = {"query": {"pages": {"1": {}}}}
        session = _session_returning(info, links)

        crawler = MediawikiCrawler.__new__(MediawikiCrawler)
        doc, _ = crawler._fetch_page_and_links(
            session, "https://wiki.example.org/api.php", "Foo")

        self.assertEqual(doc["metadata"]["last_edit_user"], "unknown")
        self.assertEqual(doc["metadata"]["last_edit_time"], "2024-05-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
