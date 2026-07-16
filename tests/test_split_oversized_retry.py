"""Regression tests: the split_oversized retry must fire only for oversized 400s.

index_segments retries a failed upload with split_oversized=True. split_oversized
only changes the document when a section/table exceeds MAX_SECTION_CHARS, so the
retry is worthwhile *only* when such an oversized part exists. Any other 400
(e.g. a schema error like an unrecognized field) has nothing to split and must
fail loudly instead of being silently retried into a degraded document.
"""
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from omegaconf import OmegaConf

from core.document_builder import MAX_SECTION_CHARS
from core.indexer import Indexer, _document_has_oversized_part


def _base_cfg(doc_processing: dict) -> OmegaConf:
    return OmegaConf.create({
        'vectara': {'verbose': False},
        'crawling': {'crawler_type': 'test'},
        'doc_processing': doc_processing,
    })


class TestHasOversizedPart(unittest.TestCase):
    """The pure gate helper: True only when splitting would change the document."""

    def test_short_sections_is_false(self):
        doc = {'sections': [{'text': 'short'}, {'text': 'also short'}]}
        self.assertFalse(_document_has_oversized_part(doc))

    def test_oversized_section_text_is_true(self):
        doc = {'sections': [{'text': 'a' * (MAX_SECTION_CHARS + 1)}]}
        self.assertTrue(_document_has_oversized_part(doc))

    def test_oversized_bundled_table_is_true(self):
        big_rows = [[{'text_value': 'a' * 100}] for _ in range(400)]
        doc = {'sections': [{'text': '', 'tables': [{'data': {'headers': [], 'rows': big_rows}}]}]}
        self.assertTrue(_document_has_oversized_part(doc))

    def test_image_bytes_shape_is_false(self):
        # The add_image_bytes repro shape: short image-summary sections plus the
        # core-only images/document_parts keys. Nothing is oversized -> no retry.
        doc = {
            'sections': [{'text': 'a picture of a cat'}],
            'images': [{'id': 'img0', 'image_data': {'data': 'x' * 50000}}],
            'document_parts': [{'text': 'a picture of a cat', 'image_id': 'img0'}],
        }
        self.assertFalse(_document_has_oversized_part(doc))


class TestRetryGateInIndexSegments(unittest.TestCase):
    """index_segments retries only when the rejected document has an oversized part."""

    def _make_indexer(self):
        ix = Indexer.__new__(Indexer)
        ix.cfg = _base_cfg({})
        ix.verbose = False
        ix.add_image_bytes = False
        ix.static_metadata = None
        ix._init_processors = MagicMock()
        ix._build_image_bytes_dict = MagicMock(return_value={})
        ix.delete_doc = MagicMock(return_value=True)

        # index_document always fails with a 400, like a rejected upload.
        def _fail(*args, **kwargs):
            ix._last_response_status = 400
            return False
        ix.index_document = MagicMock(side_effect=_fail)
        return ix

    def test_non_oversized_400_does_not_retry(self):
        ix = self._make_indexer()
        ok = ix.index_segments(
            doc_id="doc1",
            texts=["short body text"],
            metadatas=[{'element_type': 'text'}],
            doc_metadata={'url': 'https://example.test/p'},
            doc_title="Page",
        )
        self.assertFalse(ok)
        self.assertEqual(ix.index_document.call_count, 1)  # no retry
        ix.delete_doc.assert_not_called()

    def test_oversized_400_retries_with_split(self):
        ix = self._make_indexer()
        ok = ix.index_segments(
            doc_id="doc2",
            texts=["a" * (MAX_SECTION_CHARS + 5000)],
            metadatas=[{'element_type': 'text'}],
            doc_metadata={'url': 'https://example.test/p'},
            doc_title="Page",
        )
        self.assertFalse(ok)
        self.assertEqual(ix.index_document.call_count, 2)  # retried
        ix.delete_doc.assert_called_once()


if __name__ == "__main__":
    unittest.main()
