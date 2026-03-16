import unittest
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock
from omegaconf import OmegaConf

# Mock cairosvg before it's imported by other modules
sys.modules['cairosvg'] = MagicMock()

from core.file_processor import FileProcessor


def make_cfg(**overrides):
    """Create a minimal OmegaConf config for FileProcessor."""
    base = {
        "vectara": {"verbose": False},
        "doc_processing": {
            "parse_tables": False,
            "enable_gmft": False,
            "do_ocr": False,
            "fallback_ocr": False,
            "summarize_images": False,
            "doc_parser": "docling",
            "contextual_chunking": False,
            "extract_metadata": [],
            "inline_images": True,
            "image_context": {"num_previous_chunks": 1, "num_next_chunks": 1},
        },
    }
    base["doc_processing"].update(overrides)
    return OmegaConf.create(base)


class TestParsePdfSize(unittest.TestCase):
    """Test _parse_max_pdf_size handles various config value formats."""

    def _make_fp(self, max_pdf_size):
        cfg = make_cfg(max_pdf_size=max_pdf_size)
        return FileProcessor(cfg, model_config={})

    def test_int_value(self):
        fp = self._make_fp(20)
        self.assertEqual(fp._parse_max_pdf_size(20), 20)

    def test_float_value(self):
        fp = self._make_fp(20.5)
        self.assertEqual(fp._parse_max_pdf_size(20.5), 20)

    def test_string_bare_number(self):
        fp = self._make_fp("20")
        self.assertEqual(fp._parse_max_pdf_size("20"), 20)

    def test_string_mb_uppercase(self):
        fp = self._make_fp("20MB")
        self.assertEqual(fp._parse_max_pdf_size("20MB"), 20)

    def test_string_mb_lowercase(self):
        fp = self._make_fp("20mb")
        self.assertEqual(fp._parse_max_pdf_size("20mb"), 20)

    def test_string_m_suffix(self):
        fp = self._make_fp("20M")
        self.assertEqual(fp._parse_max_pdf_size("20M"), 20)

    def test_string_with_spaces(self):
        fp = self._make_fp(" 20 MB ")
        self.assertEqual(fp._parse_max_pdf_size(" 20 MB "), 20)


class TestNeedsPdfSplitting(unittest.TestCase):
    """Test needs_pdf_splitting correctly evaluates file size vs threshold."""

    def test_non_pdf_returns_false(self):
        fp = FileProcessor(make_cfg(max_pdf_size=1), model_config={})
        self.assertFalse(fp.needs_pdf_splitting("document.docx"))

    def test_small_pdf_returns_false(self):
        """A tiny temp PDF should be well under any threshold."""
        fp = FileProcessor(make_cfg(max_pdf_size=50), model_config={})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 tiny")
            f.flush()
            try:
                self.assertFalse(fp.needs_pdf_splitting(f.name))
            finally:
                os.unlink(f.name)

    def test_large_pdf_returns_true(self):
        """A file larger than max_pdf_size should trigger splitting."""
        fp = FileProcessor(make_cfg(max_pdf_size=0), model_config={})  # 0 MB threshold
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 " + b"x" * 1024)
            f.flush()
            try:
                self.assertTrue(fp.needs_pdf_splitting(f.name))
            finally:
                os.unlink(f.name)

    def test_no_max_pdf_size_returns_false(self):
        """When max_pdf_size is not configured, splitting should not happen."""
        fp = FileProcessor(make_cfg(), model_config={})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 " + b"x" * 1024)
            f.flush()
            try:
                self.assertFalse(fp.needs_pdf_splitting(f.name))
            finally:
                os.unlink(f.name)

    def test_string_max_pdf_size_parsed(self):
        """Ensure '20MB' string config doesn't crash needs_pdf_splitting."""
        fp = FileProcessor(make_cfg(max_pdf_size="20MB"), model_config={})
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 tiny")
            f.flush()
            try:
                # Should not raise ValueError
                result = fp.needs_pdf_splitting(f.name)
                self.assertIsInstance(result, bool)
            finally:
                os.unlink(f.name)


class TestBatchPdfProcessing(unittest.TestCase):
    """Test that DoclingDocumentParser batches large PDFs by page range."""

    def _make_docling_parser(self, pdf_batch_size=500):
        """Create a DoclingDocumentParser with mocked internals."""
        from core.doc_parser import DoclingDocumentParser
        cfg = make_cfg(pdf_batch_size=pdf_batch_size)
        parser = DoclingDocumentParser(
            cfg=cfg, verbose=False, model_config={},
            parse_tables=False, enable_gmft=False,
            do_ocr=False, summarize_images=False,
            chunking_strategy='none', chunk_size=1024,
            image_scale=1.0, image_context={'num_previous_chunks': 1, 'num_next_chunks': 1},
            pdf_batch_size=pdf_batch_size,
        )
        return parser

    def _make_mock_doc(self, num_items=10, page_offset=0):
        """Create a mock Docling document with text items."""
        doc = MagicMock()
        doc.name = "test_doc"
        doc.tables = []
        items = []
        for i in range(num_items):
            item = MagicMock()
            item.text = f"Text element {page_offset + i}"
            # Only has 'text' attribute, not 'export_to_dataframe' or 'get_image'
            del item.export_to_dataframe
            del item.get_image
            prov = MagicMock()
            prov.page_no = page_offset + i + 1
            item.prov = [prov]
            items.append((item, None))
        doc.iterate_items.return_value = items
        return doc

    @patch('core.doc_parser.extract_document_title', return_value='Test PDF')
    def test_small_pdf_no_batching(self, mock_title):
        """A PDF with fewer pages than batch_size should not trigger batching."""
        parser = self._make_docling_parser(pdf_batch_size=100)

        small_doc = self._make_mock_doc(num_items=5)
        mock_converter = MagicMock()
        mock_res = MagicMock()
        mock_res.document = small_doc
        mock_converter.convert.return_value = mock_res

        # Mock _get_pdf_page_count to return 50 pages (< batch_size=100)
        with patch.object(parser, '_get_pdf_page_count', return_value=50):
            result = parser._parse_with_converter('/tmp/test.pdf', 'http://example.com', mock_converter)

        # Should call convert once without page_range
        mock_converter.convert.assert_called_once_with('/tmp/test.pdf')
        self.assertEqual(len(result.content_stream), 5)

    @patch('core.doc_parser.extract_document_title', return_value='Test PDF')
    def test_large_pdf_triggers_batching(self, mock_title):
        """A PDF with more pages than batch_size should be processed in batches."""
        parser = self._make_docling_parser(pdf_batch_size=100)

        # Create mock docs for each batch
        batch1_doc = self._make_mock_doc(num_items=3, page_offset=0)
        batch2_doc = self._make_mock_doc(num_items=3, page_offset=100)
        batch3_doc = self._make_mock_doc(num_items=2, page_offset=200)

        mock_converter = MagicMock()
        mock_results = [MagicMock(), MagicMock(), MagicMock()]
        mock_results[0].document = batch1_doc
        mock_results[1].document = batch2_doc
        mock_results[2].document = batch3_doc
        mock_converter.convert.side_effect = mock_results

        with patch.object(parser, '_get_pdf_page_count', return_value=250):
            result = parser._parse_with_converter('/tmp/test.pdf', 'http://example.com', mock_converter)

        # Should call convert 3 times with page_range
        self.assertEqual(mock_converter.convert.call_count, 3)
        calls = mock_converter.convert.call_args_list
        self.assertEqual(calls[0], unittest.mock.call('/tmp/test.pdf', page_range=(1, 100)))
        self.assertEqual(calls[1], unittest.mock.call('/tmp/test.pdf', page_range=(101, 200)))
        self.assertEqual(calls[2], unittest.mock.call('/tmp/test.pdf', page_range=(201, 250)))

        # All text from all batches should be present
        self.assertEqual(len(result.content_stream), 8)

    @patch('core.doc_parser.extract_document_title', return_value='Test PDF')
    def test_non_pdf_never_batched(self, mock_title):
        """Non-PDF files should never trigger batching regardless of size."""
        parser = self._make_docling_parser(pdf_batch_size=10)

        mock_doc = self._make_mock_doc(num_items=3)
        mock_converter = MagicMock()
        mock_res = MagicMock()
        mock_res.document = mock_doc
        mock_converter.convert.return_value = mock_res

        result = parser._parse_with_converter('/tmp/test.html', 'http://example.com', mock_converter)

        # Should call convert once without page_range
        mock_converter.convert.assert_called_once_with('/tmp/test.html')
        self.assertEqual(len(result.content_stream), 3)

    @patch('core.doc_parser.extract_document_title', return_value='Test PDF')
    def test_batch_tables_accumulated(self, mock_title):
        """Tables from all batches should be accumulated."""
        parser = self._make_docling_parser(pdf_batch_size=100)
        parser.parse_tables = True
        parser.table_summarizer = MagicMock()
        parser.table_summarizer.summarize_table_text.return_value = "summary"

        # Create batch docs with tables
        import pandas as pd
        mock_table = MagicMock()
        mock_table.export_to_dataframe.return_value = pd.DataFrame({'a': [1]})
        mock_table.prov = [MagicMock(page_no=1)]

        batch1_doc = self._make_mock_doc(num_items=2, page_offset=0)
        batch1_doc.tables = [mock_table]

        mock_table2 = MagicMock()
        mock_table2.export_to_dataframe.return_value = pd.DataFrame({'b': [2]})
        mock_table2.prov = [MagicMock(page_no=101)]

        batch2_doc = self._make_mock_doc(num_items=2, page_offset=100)
        batch2_doc.tables = [mock_table2]

        mock_converter = MagicMock()
        mock_results = [MagicMock(), MagicMock()]
        mock_results[0].document = batch1_doc
        mock_results[1].document = batch2_doc
        mock_converter.convert.side_effect = mock_results

        with patch.object(parser, '_get_pdf_page_count', return_value=150):
            result = parser._parse_with_converter('/tmp/test.pdf', 'http://example.com', mock_converter)

        # Both batches' tables should be present
        self.assertEqual(len(result.tables), 2)

    def test_pdf_batch_size_config_wired(self):
        """pdf_batch_size from config should be passed to DoclingDocumentParser."""
        cfg = make_cfg(pdf_batch_size=200)
        fp = FileProcessor(cfg, model_config={})
        parser = fp.create_document_parser(filename="test.pdf")
        self.assertEqual(parser.pdf_batch_size, 200)

    def test_pdf_batch_size_default(self):
        """Default pdf_batch_size should be 300 when not configured."""
        cfg = make_cfg()
        fp = FileProcessor(cfg, model_config={})
        parser = fp.create_document_parser(filename="test.pdf")
        self.assertEqual(parser.pdf_batch_size, 300)


if __name__ == "__main__":
    unittest.main()
