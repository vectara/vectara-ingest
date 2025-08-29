"""
Base class for web content extractors.
Allows choosing between different extraction backends via configuration.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)


class WebExtractorBase(ABC):
    """Abstract base class for web content extractors"""
    
    def __init__(self, cfg: OmegaConf, timeout: int = 90, post_load_timeout: int = 5):
        self.cfg = cfg
        self.timeout = timeout
        self.post_load_timeout = post_load_timeout
    
    @abstractmethod
    def fetch_page_contents(
        self,
        url: str,
        extract_tables: bool = False,
        extract_images: bool = False,
        remove_code: bool = False,
        html_processing: Optional[dict] = None,
        debug: bool = False
    ) -> Dict:
        """
        Fetch content from URL.
        
        Returns:
            dict with 'text', 'html', 'title', 'url', 'links', 'images', 'tables'
        """
        pass
    
    @abstractmethod
    def check_download_or_pdf(self, url: str, headers: dict, timeout: int = 5000) -> Dict:
        """Check if URL triggers download or serves PDF content directly"""
        pass
    
    @abstractmethod
    def url_triggers_download(self, url: str) -> bool:
        """Check if URL triggers a download"""
        pass
    
    @abstractmethod
    def cleanup(self):
        """Clean up resources"""
        pass


def create_web_extractor(cfg: OmegaConf, scrape_method: str = None, **kwargs) -> WebExtractorBase:
    """
    Factory function to create a web content extractor based on configuration.
    
    Args:
        cfg: Configuration object
        scrape_method: Override extraction method ('playwright' or 'scrapy')
        **kwargs: Additional arguments for the specific backend
        
    Returns:
        WebExtractorBase instance
    """
    # Use provided scrape_method or default to playwright for backward compatibility
    backend = (scrape_method or 'playwright').lower()
    
    if backend == "playwright":
        from core.web_content_extractor import WebContentExtractor
        return WebContentExtractor(cfg, **kwargs)
    
    elif backend == "scrapy":
        from core.scrapy_content_extractor import ScrapyContentExtractor
        return ScrapyContentExtractor(cfg, **kwargs)
    
    else:
        raise ValueError(f"Unknown scrape_method: {backend}. Supported: playwright, scrapy")