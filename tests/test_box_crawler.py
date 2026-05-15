import logging
import sys
import unittest
from unittest.mock import MagicMock

# box_crawler imports many heavy optional dependencies at module load time.
# They are all present in requirements.txt (so CI imports the real modules),
# but stub any that are missing so the units under test can be imported and
# exercised in a lean environment. setdefault never shadows an installed module.
for _optional in (
    "psutil", "boxsdk", "slugify", "omegaconf", "nbconvert", "nbformat",
    "markdown", "whisper", "PIL", "cairosvg", "openai", "anthropic", "magic",
    "pandas", "bs4", "langdetect", "goose3", "goose3.text", "justext",
    "pdf2image", "unstructured", "unstructured.partition",
    "unstructured.partition.pdf", "unstructured.partition.html",
    "unstructured.partition.pptx", "unstructured.partition.docx",
    "nest_asyncio", "llama_parse", "gmft", "gmft.pdf_bindings", "gmft.auto",
    "nltk", "pypdf",
):
    sys.modules.setdefault(_optional, MagicMock())

from crawlers.box_crawler import BoxCrawler


class FakeItem:
    def __init__(self, item_id, name, item_type, modified_at="2026-01-01T00:00:00Z", size=10):
        self.id = item_id
        self.name = name
        self.type = item_type
        self.modified_at = modified_at
        self.size = size


class FakeFolder:
    """Stand-in for a boxsdk Folder. `get()` returns folder metadata,
    `get_items()` yields children. Either raises when `fail` is set, mirroring
    a Box Shield 403 on the folder listing."""

    def __init__(self, fid, name, items, fail=False):
        self.id = fid
        self.name = name
        self._items = items
        self.fail = fail

    def get(self, fields=None):
        if self.fail:
            raise RuntimeError("403 Forbidden: forbidden_by_policy")
        return self

    def get_items(self, fields=None):
        if self.fail:
            raise RuntimeError("403 Forbidden: forbidden_by_policy")
        return list(self._items)


class FakeBoxClient:
    def __init__(self, folders):
        self._folders = {str(fid): folder for fid, folder in folders.items()}

    def folder(self, fid):
        return self._folders[str(fid)]


def _make_crawler(client=None, recursive=True, file_extensions=None):
    """Construct a BoxCrawler without running its real __init__."""
    crawler = BoxCrawler.__new__(BoxCrawler)
    crawler.client = client
    crawler.recursive = recursive
    crawler.file_extensions = file_extensions or []
    return crawler


class TestGetAllBoxFiles(unittest.TestCase):
    """`_get_all_box_files` must report whether the listing was complete so the
    caller never mistakes a Box outage for a folder full of deletions."""

    def test_all_folders_listed_marks_complete(self):
        client = FakeBoxClient({
            "ROOT": FakeFolder("ROOT", "root", [
                FakeItem("D1", "a.pdf", "file"),
                FakeItem("D2", "b.pdf", "file"),
            ]),
        })
        files, listing_complete = _make_crawler(client)._get_all_box_files(["ROOT"])
        self.assertTrue(listing_complete)
        self.assertEqual(set(files.keys()), {"D1", "D2"})

    def test_top_level_folder_failure_marks_incomplete(self):
        client = FakeBoxClient({"ROOT": FakeFolder("ROOT", "root", [], fail=True)})
        files, listing_complete = _make_crawler(client)._get_all_box_files(["ROOT"])
        self.assertFalse(listing_complete)
        self.assertEqual(files, {})

    def test_subfolder_failure_marks_incomplete_but_keeps_parent_files(self):
        client = FakeBoxClient({
            "ROOT": FakeFolder("ROOT", "root", [
                FakeItem("D1", "a.pdf", "file"),
                FakeItem("SUB", "sub", "folder"),
            ]),
            "SUB": FakeFolder("SUB", "sub", [FakeItem("D2", "b.pdf", "file")], fail=True),
        })
        files, listing_complete = _make_crawler(client)._get_all_box_files(["ROOT"])
        self.assertFalse(listing_complete)
        self.assertEqual(set(files.keys()), {"D1"})

    def test_one_failed_folder_among_several_marks_incomplete(self):
        client = FakeBoxClient({
            "OK": FakeFolder("OK", "ok", [FakeItem("D1", "a.pdf", "file")]),
            "BAD": FakeFolder("BAD", "bad", [], fail=True),
        })
        files, listing_complete = _make_crawler(client)._get_all_box_files(["OK", "BAD"])
        self.assertFalse(listing_complete)
        self.assertEqual(set(files.keys()), {"D1"})

    def test_failed_folder_logs_error(self):
        client = FakeBoxClient({"ROOT": FakeFolder("ROOT", "root", [], fail=True)})
        with self.assertLogs(level=logging.ERROR) as cm:
            _make_crawler(client)._get_all_box_files(["ROOT"])
        self.assertTrue(any("Error crawling folder ROOT" in line for line in cm.output))


class TestIncrementalDeleteGuard(unittest.TestCase):
    """The deletion pass must run only when the Box listing was complete.
    A 403 on the folder listing must never cascade into mass deletion."""

    def _make(self):
        crawler = BoxCrawler.__new__(BoxCrawler)
        crawler.hours_back = "24h"
        crawler.tracker = MagicMock()
        crawler.tracker.get_indexed_file_ids.return_value = set()
        crawler._delete_removed_from_vectara = MagicMock()
        return crawler

    def test_delete_skipped_when_listing_incomplete(self):
        crawler = self._make()
        crawler._get_all_box_files = MagicMock(return_value=({}, False))
        crawler._crawl_incremental(["296961383989"])
        crawler._delete_removed_from_vectara.assert_not_called()

    def test_delete_runs_when_listing_complete(self):
        crawler = self._make()
        crawler._get_all_box_files = MagicMock(return_value=({}, True))
        crawler._crawl_incremental(["296961383989"])
        crawler._delete_removed_from_vectara.assert_called_once_with({})

    def test_incomplete_listing_logs_skip_warning(self):
        crawler = self._make()
        crawler._get_all_box_files = MagicMock(return_value=({}, False))
        with self.assertLogs(level=logging.WARNING) as cm:
            crawler._crawl_incremental(["296961383989"])
        self.assertTrue(any("Skipping deletion pass" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
