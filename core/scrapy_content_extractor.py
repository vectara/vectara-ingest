"""
Scrapy-based web content extractor implementation.
More stable for large-scale crawling but doesn't handle JavaScript.
"""

import logging
import requests
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from omegaconf import OmegaConf

from core.web_extractor_base import WebExtractorBase
from core.utils import get_headers

logger = logging.getLogger(__name__)


class ScrapyContentExtractor(WebExtractorBase):
    """Web content extraction using requests+BeautifulSoup - stable and simple"""

    def __init__(self, cfg: OmegaConf, timeout: int = 90, post_load_timeout: int = 5):
        super().__init__(cfg, timeout, post_load_timeout)
        # Handle missing vectara config gracefully for testing
        try:
            self.headers = get_headers(cfg)
        except:
            self.headers = {"User-Agent": "Mozilla/5.0 (compatible; ScrapyContentExtractor)"}

        # Create session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _convert_links_to_markdown(self, soup: BeautifulSoup, base_url: str) -> None:
        """
        Convert all anchor tags to markdown format: [text](URL)
        Modifies the soup in-place.

        Args:
            soup: BeautifulSoup object to process
            base_url: Base URL for resolving relative links
        """
        for link in soup.find_all('a'):
            href = link.get('href', '')
            text = link.get_text(strip=True)

            if href:
                # Convert relative URLs to absolute
                absolute_url = urljoin(base_url, href)

                # Format as markdown
                if text:
                    markdown_link = f"[{text}]({absolute_url})"
                else:
                    # If no text, just use the URL
                    markdown_link = f"[{absolute_url}]({absolute_url})"

                # Replace the link with markdown text
                link.replace_with(markdown_link)
            elif text:
                # Link has no href, just keep the text
                link.replace_with(text)

    def fetch_page_contents(
        self,
        url: str,
        extract_tables: bool = False,
        extract_images: bool = False,
        remove_code: bool = False,
        html_processing: Optional[dict] = None,
        debug: bool = False
    ) -> Dict:
        """Synchronous fetch using requests+BeautifulSoup"""
        result = {
            'text': '',
            'html': '',
            'title': '',
            'url': url,
            'links': [],
            'images': [],
            'tables': []
        }
        
        try:
            # Make the request
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Store response data
            result['html'] = response.text
            result['url'] = response.url
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title_tag = soup.find('title')
            result['title'] = title_tag.text.strip() if title_tag else ''

            # Apply HTML processing rules
            if html_processing:
                # Remove specified classes
                for class_name in html_processing.get('remove_classes', []):
                    for element in soup.find_all(class_=class_name):
                        element.decompose()

                # Remove specified tags
                for tag in html_processing.get('remove_tags', []):
                    for element in soup.find_all(tag):
                        element.decompose()

            # Remove unwanted elements
            for selector in ['script', 'style', 'header', 'footer', 'nav', 'aside']:
                for element in soup.find_all(selector):
                    element.decompose()

            if remove_code:
                for tag in ['code', 'pre']:
                    for element in soup.find_all(tag):
                        element.decompose()

            # Determine content source: either from target_tag/target_class or default (entire document)
            target_tag = html_processing.get('target_tag') if html_processing else None
            target_class = html_processing.get('target_class') if html_processing else None
            content_source = soup  # Default to entire document

            if target_tag:
                # Try to find the specified tag
                target_element = soup.find(target_tag)
                if target_element:
                    content_source = target_element

                    # If target_class is also specified, find it within the target_tag
                    if target_class:
                        class_element = target_element.find(class_=target_class)
                        if class_element:
                            content_source = class_element
            elif target_class:
                # If only target_class is specified (no target_tag)
                class_element = soup.find(class_=target_class)
                if class_element:
                    content_source = class_element

            # Remove duplicate title heading if requested
            # Often pages have <title> tag and then <h1> with same text, causing duplication
            if html_processing and html_processing.get('remove_title_heading', False):
                if result['title']:
                    # Find first h1 in content
                    first_h1 = content_source.find('h1')
                    if first_h1:
                        h1_text = first_h1.get_text(strip=True)
                        # If h1 matches title, remove it
                        if h1_text == result['title']:
                            first_h1.decompose()

            # Extract links BEFORE converting to markdown
            for link in content_source.find_all('a', href=True):
                absolute_url = urljoin(str(response.url), link['href'])
                result['links'].append(absolute_url)
            result['links'] = list(set(result['links']))  # Remove duplicates

            # Preserve links in markdown format if requested
            if html_processing and html_processing.get('preserve_links', False):
                self._convert_links_to_markdown(content_source, str(response.url))

            # Extract text from content source
            result['text'] = ' '.join(content_source.get_text().split())
            
            # Extract tables
            if extract_tables:
                result['tables'] = [str(table) for table in soup.find_all('table')]
            
            # Extract images
            if extract_images:
                for img in soup.find_all('img'):
                    img_src = urljoin(str(response.url), img.get('src', ''))
                    result['images'].append({
                        'src': img_src,
                        'alt': img.get('alt', '')
                    })
                    
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
        
        logger.info(f"For crawled page {url}: images = {len(result['images'])}, "
                   f"tables = {len(result['tables'])}, links = {len(result['links'])}")
        
        return result
    
    def check_download_or_pdf(self, url: str, headers: dict = None, timeout: int = 5000) -> Dict:
        """Check if URL triggers download or serves PDF content directly using HEAD request"""
        if headers is None:
            headers = self.headers
        try:
            # First try HEAD request to check content type
            response = self.session.head(url, headers=headers, timeout=timeout/1000)
            content_type = response.headers.get('content-type', '').lower()
            content_disposition = response.headers.get('content-disposition', '').lower()
            
            # Check if it's a download
            if 'attachment' in content_disposition:
                filename = None
                if 'filename=' in content_disposition:
                    parts = content_disposition.split('filename=')
                    if len(parts) > 1:
                        filename = parts[1].strip('"').strip("'")
                
                # Create a mock download object compatible with playwright's interface
                class ScrapyDownload:
                    def __init__(self, url, session, headers):
                        self.url = url
                        self.suggested_filename = filename
                        self._session = session
                        self._headers = headers
                    
                    def save_as(self, path):
                        """Download and save the file to the specified path"""
                        response = self._session.get(self.url, headers=self._headers, stream=True)
                        response.raise_for_status()
                        with open(path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                
                return {
                    "type": "download",
                    "url": str(response.url),
                    "filename": filename,
                    "download": ScrapyDownload(str(response.url), self.session, headers),
                    "headers": dict(response.headers)
                }
            
            # Check if it's a PDF
            if 'application/pdf' in content_type:
                # Fetch the actual content
                get_response = self.session.get(url, headers=headers, timeout=timeout/1000)
                pdf_bytes = get_response.content
                return {
                    "type": "pdf",
                    "url": str(get_response.url),
                    "content": pdf_bytes,
                    "headers": dict(get_response.headers)
                }
            
            # Otherwise it's HTML
            return {"type": "html", "url": str(response.url), "headers": dict(response.headers)}
                
        except requests.Timeout:
            logger.warning(f"Timeout checking {url}")
            return {"type": "html", "url": url, "headers": {}}
        except Exception as e:
            logger.error(f"Error checking {url}: {e}")
            return {"type": "html", "url": url, "headers": {}}
    
    def url_triggers_download(self, url: str) -> bool:
        """Check if URL triggers a download using HEAD request"""
        result = self.check_download_or_pdf(url, self.headers)
        return result.get("type") == "download"
    
    def cleanup(self):
        """Clean up session resources"""
        if hasattr(self, 'session'):
            self.session.close()