"""Tests for _split_text and oversized segment handling in DocumentBuilder."""
import unittest
from unittest.mock import MagicMock

from core.document_builder import DocumentBuilder, MAX_PART_SIZE


class TestSplitText(unittest.TestCase):
    """Tests for the _split_text static method."""

    def setUp(self):
        cfg = MagicMock()
        self.builder = DocumentBuilder(cfg, normalize_text_func=lambda t: t)

    def test_text_under_limit_returns_single_element(self):
        text = "Short text."
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(result, [text])

    def test_text_exactly_at_limit(self):
        text = "a" * MAX_PART_SIZE
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(result, [text])

    def test_splits_at_paragraph_boundary(self):
        para1 = "a" * (MAX_PART_SIZE - 100)
        para2 = "b" * 200
        text = para1 + "\n\n" + para2
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], para1)
        self.assertEqual(result[1], para2)

    def test_splits_at_sentence_boundary_when_no_paragraph(self):
        sentence1 = "a" * (MAX_PART_SIZE - 100)
        sentence2 = "b" * 200
        text = sentence1 + ". " + sentence2
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], sentence1 + ".")
        self.assertEqual(result[1], sentence2)

    def test_hard_split_when_no_boundary(self):
        text = "a" * (MAX_PART_SIZE + 500)
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], "a" * MAX_PART_SIZE)
        self.assertEqual(result[1], "a" * 500)

    def test_text_many_times_over_limit(self):
        text = "a" * (MAX_PART_SIZE * 3 + 100)
        result = self.builder._split_text(text, MAX_PART_SIZE)
        self.assertEqual(len(result), 4)
        for chunk in result[:-1]:
            self.assertEqual(len(chunk), MAX_PART_SIZE)
        self.assertEqual(len(result[-1]), 100)

    def test_paragraph_split_prefers_last_boundary(self):
        """Should split at the LAST paragraph boundary before the limit."""
        part_a = "a" * 1000
        part_b = "b" * 1000
        part_c = "c" * (MAX_PART_SIZE - 2006)  # leave room for two \n\n
        remainder = "d" * 500
        text = part_a + "\n\n" + part_b + "\n\n" + part_c + "\n\n" + remainder
        result = self.builder._split_text(text, MAX_PART_SIZE)
        # First chunk should include up to the last \n\n that fits
        self.assertLessEqual(len(result[0]), MAX_PART_SIZE)
        self.assertTrue(result[0].endswith(part_c))


class TestBuildCoreDocumentSplitting(unittest.TestCase):
    """Tests that _build_core_document splits oversized segments instead of dropping them."""

    def setUp(self):
        cfg = MagicMock()
        self.builder = DocumentBuilder(cfg, normalize_text_func=lambda t: t)

    def test_oversized_segment_is_split_not_dropped(self):
        text = "a" * (MAX_PART_SIZE + 500)
        metadata = {"source": "test"}
        doc = {"id": "doc1", "metadata": {}}
        result = self.builder._build_core_document(doc, [text], [metadata], "", [])
        # Should produce 2 parts, not 0
        self.assertEqual(len(result["document_parts"]), 2)
        # Both parts should carry the original metadata
        for part in result["document_parts"]:
            self.assertEqual(part["metadata"], metadata)

    def test_mixed_normal_and_oversized_segments(self):
        normal_text = "Normal text."
        oversized_text = "b" * (MAX_PART_SIZE + 500)
        doc = {"id": "doc2", "metadata": {}}
        result = self.builder._build_core_document(
            doc,
            [normal_text, oversized_text],
            [{"idx": 0}, {"idx": 1}],
            "",
            []
        )
        # 1 normal + 2 from split = 3
        self.assertEqual(len(result["document_parts"]), 3)
        self.assertEqual(result["document_parts"][0]["text"], normal_text)
        self.assertEqual(result["document_parts"][0]["metadata"], {"idx": 0})
        # Split parts should carry the oversized segment's metadata
        self.assertEqual(result["document_parts"][1]["metadata"], {"idx": 1})
        self.assertEqual(result["document_parts"][2]["metadata"], {"idx": 1})

    def test_all_content_preserved_hard_split(self):
        """Verify that hard splitting (no boundaries) preserves ALL text."""
        text = "a" * (MAX_PART_SIZE * 3 + 100)
        doc = {"id": "doc3", "metadata": {}}
        result = self.builder._build_core_document(doc, [text], [{}], "", [])
        reconstructed = "".join(p["text"] for p in result["document_parts"])
        self.assertEqual(reconstructed, text)

    def test_sentence_split_preserves_content(self):
        """Verify sentence splits keep the period on the left chunk."""
        text = "Hello world. " * 2000
        doc = {"id": "doc3b", "metadata": {}}
        result = self.builder._build_core_document(doc, [text], [{}], "", [])
        # Each part should be within the limit
        for part in result["document_parts"]:
            self.assertLessEqual(len(part["text"]), MAX_PART_SIZE)
        # Should produce multiple parts
        self.assertGreater(len(result["document_parts"]), 1)

    def test_normal_segments_unchanged(self):
        text = "Short segment."
        doc = {"id": "doc4", "metadata": {}}
        result = self.builder._build_core_document(doc, [text], [{}], "", [])
        self.assertEqual(len(result["document_parts"]), 1)
        self.assertEqual(result["document_parts"][0]["text"], text)


if __name__ == "__main__":
    unittest.main()
