"""Tests for ScrapyContentExtractor html_processing key names."""

import unittest
from unittest.mock import patch, MagicMock
from core.scrapy_content_extractor import ScrapyContentExtractor


class TestScrapyHtmlProcessing(unittest.TestCase):
    """Verify that ScrapyContentExtractor uses the canonical html_processing keys:
    ids_to_remove, classes_to_remove, tags_to_remove."""

    def _make_extractor(self):
        """Create a ScrapyContentExtractor with a minimal mock config."""
        cfg = MagicMock()
        with patch.object(ScrapyContentExtractor, '__init__', lambda self, *a, **kw: None):
            ext = ScrapyContentExtractor.__new__(ScrapyContentExtractor)
            ext.timeout = 10
            ext.session = MagicMock()
            ext.headers = {}
        return ext

    def _fetch(self, extractor, html, html_processing):
        """Helper: mock a GET response with the given HTML and call fetch_page_contents."""
        resp = MagicMock()
        resp.text = html
        resp.url = "http://example.com"
        resp.raise_for_status = MagicMock()
        extractor.session.get.return_value = resp
        return extractor.fetch_page_contents(
            "http://example.com",
            html_processing=html_processing,
        )

    def test_classes_to_remove(self):
        html = '<html><body><div class="ad">Ad</div><p>Content</p></body></html>'
        ext = self._make_extractor()
        result = self._fetch(ext, html, {'classes_to_remove': ['ad']})
        self.assertNotIn('Ad', result['text'])
        self.assertIn('Content', result['text'])

    def test_tags_to_remove(self):
        # Use <section> — not in the hardcoded removal list, so only html_processing can strip it
        html = '<html><body><section>Section</section><p>Content</p></body></html>'
        ext = self._make_extractor()
        result = self._fetch(ext, html, {'tags_to_remove': ['section']})
        self.assertNotIn('Section', result['text'])
        self.assertIn('Content', result['text'])

    def test_ids_to_remove(self):
        html = '<html><body><div id="banner">Banner</div><p>Content</p></body></html>'
        ext = self._make_extractor()
        result = self._fetch(ext, html, {'ids_to_remove': ['banner']})
        self.assertNotIn('Banner', result['text'])
        self.assertIn('Content', result['text'])

    def test_combined_processing(self):
        html = (
            '<html><body>'
            '<div id="hdr">Header</div>'
            '<div class="ad">Ad</div>'
            '<nav>Nav</nav>'
            '<p>Content</p>'
            '</body></html>'
        )
        ext = self._make_extractor()
        result = self._fetch(ext, html, {
            'ids_to_remove': ['hdr'],
            'classes_to_remove': ['ad'],
            'tags_to_remove': ['nav'],
        })
        self.assertNotIn('Header', result['text'])
        self.assertNotIn('Ad', result['text'])
        self.assertNotIn('Nav', result['text'])
        self.assertIn('Content', result['text'])


if __name__ == '__main__':
    unittest.main()
