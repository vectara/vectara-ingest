"""
Unit tests for context extraction utilities.
"""
from core.context_utils import extract_image_context


class MockElement:
    """Mock element for testing."""
    def __init__(self, text=None, element_type='text'):
        self.text = text
        self.type = element_type


class TestContextExtraction:
    
    def test_extract_image_context_basic(self):
        """Test basic context extraction with default settings."""
        elements = [
            MockElement("First paragraph"),
            MockElement("Second paragraph"),
            MockElement(None, 'image'),  # Image element
            MockElement("Third paragraph"),
            MockElement("Fourth paragraph"),
        ]
        
        previous, next_text = extract_image_context(elements, 2)
        
        assert previous == "Second paragraph"
        assert next_text == "Third paragraph"
    
    def test_extract_image_context_multiple_chunks(self):
        """Test context extraction with multiple chunks."""
        elements = [
            MockElement("Para 1"),
            MockElement("Para 2"),
            MockElement("Para 3"),
            MockElement(None, 'image'),  # Image element at index 3
            MockElement("Para 4"),
            MockElement("Para 5"),
            MockElement("Para 6"),
        ]
        
        previous, next_text = extract_image_context(elements, 3, num_previous=2, num_next=2)
        
        assert previous == "Para 2 Para 3"
        assert next_text == "Para 4 Para 5"
    
    def test_extract_image_context_no_context(self):
        """Test extraction with no context requested."""
        elements = [
            MockElement("Para 1"),
            MockElement(None, 'image'),
            MockElement("Para 2"),
        ]
        
        previous, next_text = extract_image_context(elements, 1, num_previous=0, num_next=0)
        
        assert previous is None
        assert next_text is None
    
    def test_extract_image_context_at_start(self):
        """Test extraction when image is at the beginning."""
        elements = [
            MockElement(None, 'image'),  # Image at start
            MockElement("Para 1"),
            MockElement("Para 2"),
        ]
        
        previous, next_text = extract_image_context(elements, 0)
        
        assert previous is None  # No previous text
        assert next_text == "Para 1"
    
    def test_extract_image_context_at_end(self):
        """Test extraction when image is at the end."""
        elements = [
            MockElement("Para 1"),
            MockElement("Para 2"),
            MockElement(None, 'image'),  # Image at end
        ]
        
        previous, next_text = extract_image_context(elements, 2)
        
        assert previous == "Para 2"
        assert next_text is None  # No next text
    
    def test_extract_image_context_skip_non_text(self):
        """Test that non-text elements are skipped."""
        elements = [
            MockElement("Para 1"),
            MockElement(None, 'table'),  # Table - should be skipped
            MockElement("Para 2"),
            MockElement(None, 'image'),  # Image element
            MockElement(None, 'table'),  # Table - should be skipped
            MockElement("Para 3"),
        ]
        
        previous, next_text = extract_image_context(elements, 3)
        
        assert previous == "Para 2"  # Skips table
        assert next_text == "Para 3"  # Skips table
    
    def test_extract_image_context_with_dict_elements(self):
        """Test extraction with dictionary-based elements."""
        elements = [
            {'text': 'Para 1', 'type': 'text'},
            {'text': 'Para 2', 'type': 'text'},
            {'type': 'image'},
            {'text': 'Para 3', 'type': 'text'},
        ]
        
        previous, next_text = extract_image_context(elements, 2)
        
        assert previous == "Para 2"
        assert next_text == "Para 3"
    
    def test_extract_image_context_custom_extractor(self):
        """Test with custom text extractor function."""
        elements = [
            {'content': 'Para 1', 'kind': 'text'},
            {'content': 'Para 2', 'kind': 'text'},
            {'kind': 'image'},
            {'content': 'Para 3', 'kind': 'text'},
        ]
        
        def custom_extractor(elem):
            if elem.get('kind') == 'text':
                return elem.get('content')
            return None
        
        previous, next_text = extract_image_context(
            elements, 2, text_extractor=custom_extractor
        )
        
        assert previous == "Para 2"
        assert next_text == "Para 3"
    
    def test_extract_image_context_truncation(self):
        """Test that long context is truncated."""
        long_text = "x" * 2000  # Very long text
        elements = [
            MockElement(long_text),
            MockElement(None, 'image'),
            MockElement(long_text),
        ]
        
        previous, next_text = extract_image_context(elements, 1)
        
        assert len(previous) == 1503  # 1500 + "..."
        assert previous.endswith("...")
        assert len(next_text) == 1503
        assert next_text.endswith("...")
    
    def test_extract_context_empty_elements(self):
        """Test handling of empty text elements."""
        elements = [
            MockElement("Para 1"),
            MockElement(""),  # Empty text
            MockElement("   "),  # Whitespace only
            MockElement(None, 'image'),
            MockElement(""),  # Empty text
            MockElement("Para 2"),
        ]
        
        previous, next_text = extract_image_context(elements, 3)
        
        assert previous == "Para 1"  # Skips empty elements
        assert next_text == "Para 2"  # Skips empty elements
    
    def test_extract_context_all_non_text(self):
        """Test when there are no text elements."""
        elements = [
            MockElement(None, 'table'),
            MockElement(None, 'image'),
            MockElement(None, 'table'),
        ]
        
        previous, next_text = extract_image_context(elements, 1)
        
        assert previous is None
        assert next_text is None