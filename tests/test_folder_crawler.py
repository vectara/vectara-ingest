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

from crawlers.folder_crawler import _doc_id_for_file


class TestDocIdForFile(unittest.TestCase):
    """Regression tests for the folder_crawler doc_id derivation.

    Background: prior to this fix, `doc_id = slugify(file_name)` collided
    across distinct file paths because python-slugify collapses '/', '.',
    ' ', and '-' all into a single separator. The collision caused unrelated
    files to overwrite each other on reindex.
    """

    def test_distinct_paths_with_colliding_slugs_get_distinct_ids(self):
        # These all slugify to 'a-b-txt' under python-slugify defaults.
        colliding = ["a/b.txt", "a-b.txt", "a b.txt", "a.b.txt"]
        ids = [_doc_id_for_file(name) for name in colliding]
        self.assertEqual(len(ids), len(set(ids)),
                         f"Expected unique ids for distinct paths, got {ids}")

    def test_nested_vs_flat_path_collision(self):
        # Real-world shape: a nested doc next to a legacy flat sibling.
        self.assertNotEqual(
            _doc_id_for_file("docs/api/v1.md"),
            _doc_id_for_file("docs-api-v1.md"),
        )

    def test_id_is_stable_across_calls(self):
        # Stability is the whole point of the original fix in 5e6c977 —
        # re-indexing must produce the same id so the existing document
        # is updated in place rather than duplicated.
        name = "some/folder/file.pdf"
        self.assertEqual(_doc_id_for_file(name), _doc_id_for_file(name))

    def test_id_contains_readable_slug_prefix(self):
        # The slug prefix is what keeps logs and the admin UI scannable.
        doc_id = _doc_id_for_file("docs/api/v1.md")
        self.assertTrue(doc_id.startswith("docs-api-v1-md-"),
                        f"expected readable slug prefix, got {doc_id}")

    def test_unicode_file_name(self):
        # Should not raise on non-ASCII paths.
        a = _doc_id_for_file("café/menü.pdf")
        b = _doc_id_for_file("cafe/menu.pdf")
        self.assertIsInstance(a, str)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
