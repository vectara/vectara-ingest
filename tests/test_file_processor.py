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


if __name__ == "__main__":
    unittest.main()
