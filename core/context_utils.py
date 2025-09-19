"""
Utility functions for extracting context around images in documents.
"""
from typing import List, Tuple, Optional, Any


def extract_image_context(
    elements: List[Any],
    current_idx: int,
    num_previous: int = 1,
    num_next: int = 1,
    text_extractor=None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract text context before and after an image element.
    
    Args:
        elements: List of document elements (can be different types depending on parser)
        current_idx: Index of the current image element
        num_previous: Number of previous text chunks to include (default 1)
        num_next: Number of next text chunks to include (default 1)
        text_extractor: Optional function to extract text from an element.
                       If None, will try common attributes (.text, .content, str())
    
    Returns:
        Tuple of (previous_text, next_text), either can be None if no context found
    """
    def get_text(element) -> Optional[str]:
        """Extract text from an element using various methods."""
        if text_extractor:
            return text_extractor(element)
        
        # Try common attributes
        if hasattr(element, 'text') and element.text:
            return element.text
        if hasattr(element, 'content') and element.content:
            return element.content
        if isinstance(element, str):
            return element
        if isinstance(element, dict):
            # Handle dict-based elements
            return element.get('text') or element.get('content') or element.get('value')
        
        # Try string conversion as last resort
        try:
            text = str(element)
            # Check if it's actually a string representation of the object (not useful text)
            if text and not text.startswith('<') and text != str(type(element)):
                return text
        except:
            pass
        
        return None
    
    def is_text_element(element) -> bool:
        """Check if an element contains text content."""
        # Check for type indicators
        if hasattr(element, 'type'):
            elem_type = getattr(element, 'type', '').lower()
            if 'image' in elem_type or 'table' in elem_type:
                return False
        
        if isinstance(element, dict) and 'type' in element:
            elem_type = element['type'].lower()
            if 'image' in elem_type or 'table' in elem_type:
                return False
        
        # Check if it has extractable text
        text = get_text(element)
        return text is not None and len(text.strip()) > 0
    
    # Extract previous context
    previous_texts = []
    if num_previous > 0:
        for i in range(current_idx - 1, -1, -1):
            if len(previous_texts) >= num_previous:
                break
            
            element = elements[i]
            if is_text_element(element):
                text = get_text(element)
                if text:
                    previous_texts.insert(0, text)  # Insert at beginning to maintain order
    
    # Extract next context
    next_texts = []
    if num_next > 0:
        for i in range(current_idx + 1, len(elements)):
            if len(next_texts) >= num_next:
                break
            
            element = elements[i]
            if is_text_element(element):
                text = get_text(element)
                if text:
                    next_texts.append(text)
    
    # Combine texts
    previous_text = ' '.join(previous_texts) if previous_texts else None
    next_text = ' '.join(next_texts) if next_texts else None
    
    # Truncate if too long (to avoid overwhelming the image summarizer)
    max_context_length = 1500  # characters
    if previous_text and len(previous_text) > max_context_length:
        previous_text = previous_text[:max_context_length] + '...'
    if next_text and len(next_text) > max_context_length:
        next_text = next_text[:max_context_length] + '...'
    
    return previous_text, next_text


