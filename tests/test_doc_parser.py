import unittest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

# Mock cairosvg before it's imported by other modules
sys.modules['cairosvg'] = MagicMock()


class TestDocumentTitleExtraction(unittest.TestCase):
    """Test cases for document title extraction functionality across PDF, DOCX, and PPTX formats"""
    
    def test_pdf_title_extraction_from_metadata(self):
        """Test that PDF metadata title is extracted when available"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # Mock PdfReader and metadata
            mock_reader = Mock()
            mock_metadata = Mock()
            mock_metadata.title = "Test PDF Title from Metadata"
            mock_reader.metadata = mock_metadata
            mock_pdf_reader_class.return_value = mock_reader
            
            # Import and test the helper function
            from core.doc_parser import extract_document_title
            
            filename = "test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Verify the behavior
            self.assertEqual(doc_title, "Test PDF Title from Metadata")
            mock_pdf_reader_class.assert_called_once_with(filename)
    
    def test_pdf_title_extraction_with_whitespace(self):
        """Test that PDF title with whitespace is properly trimmed"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # Mock PdfReader with title containing whitespace
            mock_reader = Mock()
            mock_metadata = Mock()
            mock_metadata.title = "  \t  PDF Title With Whitespace  \n  "
            mock_reader.metadata = mock_metadata
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Verify title was trimmed
            self.assertEqual(doc_title, "PDF Title With Whitespace")
    
    def test_pdf_title_extraction_empty_metadata(self):
        """Test fallback when PDF metadata title is empty"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # Mock PdfReader with empty title
            mock_reader = Mock()
            mock_metadata = Mock()
            mock_metadata.title = ""  # Empty title
            mock_reader.metadata = mock_metadata
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            filename = "my_test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Should remain empty for fallback to filename
            self.assertEqual(doc_title, "")
    
    def test_pdf_title_extraction_none_metadata(self):
        """Test fallback when PDF metadata title is None"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # Mock PdfReader with None title
            mock_reader = Mock()
            mock_metadata = Mock()
            mock_metadata.title = None
            mock_reader.metadata = mock_metadata
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Should remain empty for fallback to filename
            self.assertEqual(doc_title, "")
    
    def test_pdf_title_extraction_no_metadata(self):
        """Test fallback when PDF has no metadata"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # Mock PdfReader with no metadata
            mock_reader = Mock()
            mock_reader.metadata = None
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Should remain empty for fallback to filename
            self.assertEqual(doc_title, "")
    
    def test_pdf_title_extraction_error_handling(self):
        """Test error handling when PDF reading fails"""
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            # PdfReader raises exception
            mock_pdf_reader_class.side_effect = Exception("PDF processing error")
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.pdf"
            doc_title = extract_document_title(filename)
            
            # Should remain empty after exception
            self.assertEqual(doc_title, "")
    
    def test_filename_fallback_logic(self):
        """Test filename fallback formatting logic"""
        test_cases = [
            ("my_test_document.pdf", "My Test Document"),
            ("research-paper-2024.pdf", "Research Paper 2024"),
            ("simple_file.pdf", "Simple File"),
            ("complex-file_name.pdf", "Complex File Name"),
            ("no-extension", "No Extension"),
        ]
        
        for filename, expected_title in test_cases:
            basename = os.path.basename(filename)
            doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            self.assertEqual(doc_title, expected_title, f"Failed for filename: {filename}")
    
    def test_docx_title_extraction_from_metadata(self):
        """Test that DOCX document title is extracted when available"""
        with patch('docx.Document') as mock_document_class:
            # Mock Document and core_properties
            mock_doc = Mock()
            mock_core_props = Mock()
            mock_core_props.title = "Test DOCX Title from Properties"
            mock_doc.core_properties = mock_core_props
            mock_document_class.return_value = mock_doc
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.docx"
            doc_title = extract_document_title(filename)
            
            # Verify the behavior
            self.assertEqual(doc_title, "Test DOCX Title from Properties")
            mock_document_class.assert_called_once_with(filename)
    
    def test_pptx_title_extraction_from_metadata(self):
        """Test that PPTX presentation title is extracted when available"""
        with patch('pptx.Presentation') as mock_presentation_class:
            # Mock Presentation and core_properties
            mock_prs = Mock()
            mock_core_props = Mock()
            mock_core_props.title = "Test PPTX Title from Properties"
            mock_prs.core_properties = mock_core_props
            mock_presentation_class.return_value = mock_prs
            
            from core.doc_parser import extract_document_title
            
            filename = "test_presentation.pptx"
            doc_title = extract_document_title(filename)
            
            # Verify the behavior
            self.assertEqual(doc_title, "Test PPTX Title from Properties")
            mock_presentation_class.assert_called_once_with(filename)
    
    def test_docx_title_extraction_import_error(self):
        """Test DOCX title extraction when python-docx is not available"""
        with patch('docx.Document') as mock_document_class:
            # Mock ImportError when trying to import docx.Document
            mock_document_class.side_effect = ImportError("No module named 'docx'")
            
            from core.doc_parser import extract_document_title
            
            filename = "test_document.docx"
            doc_title = extract_document_title(filename)
            
            # Should return empty string when library not available
            self.assertEqual(doc_title, "")
    
    def test_pptx_title_extraction_import_error(self):
        """Test PPTX title extraction when python-pptx is not available"""
        with patch('pptx.Presentation') as mock_presentation_class:
            # Mock ImportError when trying to import pptx.Presentation
            mock_presentation_class.side_effect = ImportError("No module named 'pptx'")
            
            from core.doc_parser import extract_document_title
            
            filename = "test_presentation.pptx"
            doc_title = extract_document_title(filename)
            
            # Should return empty string when library not available
            self.assertEqual(doc_title, "")
    
    def test_html_files_return_empty(self):
        """Test that HTML files return empty string (per user requirement)"""
        from core.doc_parser import extract_document_title
        
        html_files = ["test.html", "test.htm"]
        
        for filename in html_files:
            with self.subTest(filename=filename):
                doc_title = extract_document_title(filename)
                self.assertEqual(doc_title, "", f"HTML file {filename} should return empty title for filename fallback")
    
    def test_unsupported_files_return_empty(self):
        """Test that unsupported files return empty string"""
        from core.doc_parser import extract_document_title
        
        unsupported_files = ["test.txt", "test.csv", "test.json"]
        
        for filename in unsupported_files:
            with self.subTest(filename=filename):
                doc_title = extract_document_title(filename)
                self.assertEqual(doc_title, "", f"Unsupported file {filename} should return empty title")


class TestIntegratedTitleExtraction(unittest.TestCase):
    """Integration tests for title extraction in complete flow"""
    
    def test_pdf_priority_over_title_elements_unstructured(self):
        """Test that PDF metadata takes priority over Title elements in UnstructuredDocumentParser"""
        # This test verifies the complete logic flow for PDFs:
        # PDF metadata > filename (no Title element fallback for PDFs)
        
        filename = "research_paper.pdf"
        
        # Case 1: PDF has metadata title
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            mock_reader = Mock()
            mock_metadata = Mock()
            mock_metadata.title = "Advanced AI Research"
            mock_reader.metadata = mock_metadata
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            # Simulate PDF title extraction logic using helper
            doc_title = extract_document_title(filename)
            
            # Fallback to filename if no title found
            if not doc_title:
                basename = os.path.basename(filename)
                doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            
            # Should use PDF metadata title, not filename
            self.assertEqual(doc_title, "Advanced AI Research")
    
    def test_complete_title_extraction_flow(self):
        """Test the complete title extraction flow with all fallbacks"""
        
        # Test with PDF that has no metadata - should use filename
        with patch('pypdf.PdfReader') as mock_pdf_reader_class:
            mock_reader = Mock()
            mock_reader.metadata = None
            mock_pdf_reader_class.return_value = mock_reader
            
            from core.doc_parser import extract_document_title
            
            filename = "my_research_paper.pdf"
            doc_title = extract_document_title(filename)
            
            # Fallback to filename if no title found
            if not doc_title:
                basename = os.path.basename(filename)
                doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            
            # Should use formatted filename
            self.assertEqual(doc_title, "My Research Paper")


class TestFetchImageBytes(unittest.TestCase):
    """Tests for _fetch_image_bytes — content-type validation and header forwarding."""

    def _make_response(self, status_code: int, content_type: str, content: bytes = b""):
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.headers = {'content-type': content_type}
        mock_resp.content = content
        return mock_resp

    def test_returns_bytes_for_image_png(self):
        """Valid image/png response returns content."""
        from core.doc_parser import _fetch_image_bytes
        img_bytes = b"\x89PNG\r\n\x1a\n"
        with patch('requests.get', return_value=self._make_response(200, 'image/png', img_bytes)) as mock_get:
            result = _fetch_image_bytes("http://example.com/img.png")
        self.assertEqual(result, img_bytes)
        mock_get.assert_called_once()

    def test_returns_bytes_for_image_jpeg(self):
        """Valid image/jpeg response returns content."""
        from core.doc_parser import _fetch_image_bytes
        img_bytes = b"\xff\xd8\xff"
        with patch('requests.get', return_value=self._make_response(200, 'image/jpeg; charset=utf-8', img_bytes)):
            result = _fetch_image_bytes("http://example.com/img.jpg")
        self.assertEqual(result, img_bytes)

    def test_rejects_html_content_type(self):
        """HTTP 200 with text/html (e.g. a login redirect) must return None."""
        from core.doc_parser import _fetch_image_bytes
        html_bytes = b"<html><body>Please log in</body></html>"
        with patch('requests.get', return_value=self._make_response(200, 'text/html', html_bytes)):
            result = _fetch_image_bytes("http://example.com/attachment")
        self.assertIsNone(result)

    def test_rejects_empty_content_type(self):
        """Response with no content-type header must return None."""
        from core.doc_parser import _fetch_image_bytes
        with patch('requests.get', return_value=self._make_response(200, '', b"some bytes")):
            result = _fetch_image_bytes("http://example.com/img")
        self.assertIsNone(result)

    def test_rejects_non_200_status(self):
        """Non-200 status codes must return None."""
        from core.doc_parser import _fetch_image_bytes
        for status in (403, 404, 500):
            with self.subTest(status=status):
                with patch('requests.get', return_value=self._make_response(status, 'image/png', b"data")):
                    result = _fetch_image_bytes("http://example.com/img.png")
                self.assertIsNone(result)

    def test_returns_none_on_exception(self):
        """Network exception must return None without raising."""
        from core.doc_parser import _fetch_image_bytes
        with patch('requests.get', side_effect=Exception("connection refused")):
            result = _fetch_image_bytes("http://example.com/img.png")
        self.assertIsNone(result)

    def test_passes_headers_to_request(self):
        """Supplied headers must be forwarded to requests.get."""
        from core.doc_parser import _fetch_image_bytes
        headers = {'User-Agent': 'test-agent', 'Cookie': 'session=abc123'}
        with patch('requests.get', return_value=self._make_response(200, 'image/png', b"x")) as mock_get:
            _fetch_image_bytes("http://example.com/img.png", headers=headers)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs['headers'], headers)

    def test_default_headers_is_empty_dict(self):
        """When no headers supplied, requests.get receives an empty dict."""
        from core.doc_parser import _fetch_image_bytes
        with patch('requests.get', return_value=self._make_response(200, 'image/png', b"x")) as mock_get:
            _fetch_image_bytes("http://example.com/img.png")
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs['headers'], {})


if __name__ == '__main__':
    unittest.main()