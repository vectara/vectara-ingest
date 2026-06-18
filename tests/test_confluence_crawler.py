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

from crawlers.confluence_crawler import append_links, append_labels


BASE = "https://example.atlassian.net/wiki"


def _links(**overrides):
    links = {
        "base": BASE,
        "editui": "/pages/edit/123",
        "webui": "/spaces/SP/pages/123",
        "edituiv2": "/edit-v2/123",
        "tinyui": "/x/abc",
    }
    links.update(overrides)
    return {k: v for k, v in links.items() if v is not None}


class TestAppendLinks(unittest.TestCase):
    # Regression: append_links indexed _links['editui'/'webui'/'edituiv2'/
    # 'tinyui'/'base'] directly; any missing key raised KeyError and killed
    # processing of the page.

    def test_all_links_present(self):
        metadata = {}
        append_links(metadata, {"_links": _links()})
        self.assertEqual(metadata["links"]["editui"], f"{BASE}/pages/edit/123")
        self.assertEqual(set(metadata["links"]),
                         {"editui", "webui", "edituiv2", "tinyui"})

    def test_missing_link_key_is_skipped(self):
        metadata = {}
        append_links(metadata, {"_links": _links(edituiv2=None)})
        self.assertEqual(set(metadata["links"]), {"editui", "webui", "tinyui"})

    def test_missing_base_is_noop(self):
        metadata = {}
        append_links(metadata, {"_links": _links(base=None)})
        self.assertNotIn("links", metadata)

    def test_missing_links_object_is_noop(self):
        metadata = {}
        append_links(metadata, {})
        self.assertNotIn("links", metadata)


class TestAppendLabels(unittest.TestCase):
    # Regression: append_labels indexed label['label'/'name'/'id'] directly;
    # a label missing any field raised KeyError.

    def test_labels_extracted(self):
        metadata = {}
        page = {"metadata": {"labels": [
            {"label": "global:doc", "name": "doc", "id": "1"},
            {"label": "global:api", "name": "api", "id": "2"},
        ]}}
        append_labels(metadata, page)
        self.assertEqual(metadata["label_names"], ["doc", "api"])
        self.assertEqual(metadata["label_ids"], ["1", "2"])

    def test_label_with_missing_fields_does_not_crash(self):
        metadata = {}
        page = {"metadata": {"labels": [{"name": "doc"}]}}
        append_labels(metadata, page)
        self.assertEqual(metadata["label_names"], ["doc"])
        self.assertEqual(metadata["labels"], [""])
        self.assertEqual(metadata["label_ids"], [""])

    def test_no_metadata_is_noop(self):
        metadata = {}
        append_labels(metadata, {})
        self.assertNotIn("labels", metadata)


if __name__ == "__main__":
    unittest.main()
