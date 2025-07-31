import json
import logging
import time
from typing import Dict, List, Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from omegaconf import OmegaConf
from core.utils import get_headers

logger = logging.getLogger(__name__)


class WebContentExtractor:
    """Handles web content extraction using Playwright"""
    
    def __init__(self, cfg: OmegaConf, timeout: int = 90, post_load_timeout: int = 5, browser=None):
        self.cfg = cfg
        self.timeout = timeout
        self.post_load_timeout = post_load_timeout
        self.browser_use_limit = 100
        self.browser_use_count = 0
        self.browser = browser
        self.p = None
        
        if browser is None:
            self._setup_browser()
        
    def _setup_browser(self):
        """Initialize browser instance"""
        self.p = sync_playwright().start()
        self.browser = self.p.firefox.launch(headless=True)
        
    def _reset_browser_if_needed(self):
        """Reset browser if usage limit reached"""
        if self.browser_use_count >= self.browser_use_limit:
            self.browser.close()
            self.browser = self.p.firefox.launch(headless=True)
            self.browser_use_count = 0
            logger.info(f"Browser reset after {self.browser_use_limit} uses to avoid memory issues")
    
    def url_triggers_download(self, url: str) -> bool:
        """Check if URL triggers a download"""
        download_triggered = False
        context = self.browser.new_context()
        
        def on_download(download):
            nonlocal download_triggered
            download_triggered = True
            
        page = context.new_page()
        page.set_extra_http_headers(get_headers(self.cfg))
        page.on('download', on_download)
        
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            pass
        finally:
            page.close()
            context.close()
            
        return download_triggered
    
    def _scroll_to_bottom(self, page, pause=2000):
        """Scroll down page until no new content loads"""
        prev_height = None
        while True:
            current_height = page.evaluate("document.body.scrollHeight")
            if prev_height == current_height:
                break
            prev_height = current_height
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(pause)
    
    def _remove_elements(self, page, html_processing: dict):
        """Remove specified elements from page"""
        ids_to_remove = list(html_processing.get('ids_to_remove', []))
        classes_to_remove = list(html_processing.get('classes_to_remove', []))
        tags_to_remove = list(html_processing.get('tags_to_remove', []))
        
        removal_script = """
            (function(ids, classes, tags) {
                ids.forEach(function(id) {
                    var el = document.getElementById(id);
                    if (el) el.remove();
                });
                classes.forEach(function(cls) {
                    document.querySelectorAll('.' + cls).forEach(function(el) { el.remove(); });
                });
                tags.forEach(function(tag) {
                    document.querySelectorAll(tag).forEach(function(el) { el.remove(); });
                });
            })(%s, %s, %s);
        """ % (
            json.dumps(ids_to_remove),
            json.dumps(classes_to_remove),
            json.dumps(tags_to_remove)
        )
        page.evaluate(removal_script)
    
    def _extract_text_content(self, page, remove_code: bool = False) -> str:
        """Extract text content from page"""
        return page.evaluate(f"""() => {{
            let content = Array.from(document.body.childNodes)
                .map(node => node.textContent || "")
                .join(" ")
                .trim();
            
            const elementsToRemove = [
                'header', 'footer', 'nav', 'aside', '.sidebar', '#comments', '.advertisement'
            ];
            
            elementsToRemove.forEach(selector => {{
                const elements = document.querySelectorAll(selector);
                elements.forEach(el => {{
                    content = content.replace(el.innerText, '');
                }});
            }});
            
            function extractShadowText(root) {{
                let text = "";
                if (root.shadowRoot) {{
                    root.shadowRoot.childNodes.forEach(node => {{
                        text += node.textContent + " ";
                        text += extractShadowText(node);
                    }});
                }}
                return text;
            }}
            
            document.querySelectorAll("*").forEach(el => {{
                content += extractShadowText(el);
            }});
            
            {'// Remove code elements' if remove_code else ''}
            {'''
            const codeElements = document.querySelectorAll('code, pre');
            codeElements.forEach(el => {
                content = content.replace(el.innerText, '');
            });
            ''' if remove_code else ''}
            
            return content.replace(/\\s{{2,}}/g, ' ').trim();
        }}""")
    
    def _extract_links(self, page) -> List[str]:
        """Extract links from page including shadow DOM"""
        return page.evaluate("""
            () => {
                let links = [];
                
                function extractLinks(root) {
                    root.querySelectorAll('a').forEach(a => {
                        if (a.href) links.push(a.href);
                    });
                    root.querySelectorAll('*').forEach(el => {
                        if (el.shadowRoot) {
                            extractLinks(el.shadowRoot);
                        }
                    });
                }
                
                extractLinks(document);
                return [...new Set(links)];
            }
        """)
    
    def _extract_tables(self, page) -> List[str]:
        """Extract tables from page including shadow DOM"""
        return page.evaluate("""
            () => {
                let tables = [];
                
                function extractTables(root) {
                    root.querySelectorAll("table").forEach(t => {
                        tables.push(t.outerHTML);
                    });
                    root.querySelectorAll("*").forEach(el => {
                        if (el.shadowRoot) {
                            extractTables(el.shadowRoot);
                        }
                    });
                }
                
                extractTables(document);
                return tables;
            }
        """)
    
    def _extract_images(self, page) -> List[Dict[str, str]]:
        """Extract images from page including shadow DOM"""
        return page.evaluate("""
            () => {
                let images = [];
                
                function extractImages(root) {
                    root.querySelectorAll("img").forEach(img => {
                        images.push({ src: img.src, alt: img.alt || "" });
                    });
                    root.querySelectorAll("*").forEach(el => {
                        if (el.shadowRoot) {
                            extractImages(el.shadowRoot);
                        }
                    });
                }
                
                extractImages(document);
                return images;
            }
        """)
    
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
        Fetch content from URL with timeout, including Shadow DOM content.
        
        Returns:
            dict with 'text', 'html', 'title', 'url', 'links', 'images', 'tables'
        """
        if html_processing is None:
            html_processing = {}
            
        page = context = None
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
            context = self.browser.new_context()
            page = context.new_page()
            page.set_extra_http_headers(get_headers(self.cfg))
            
            # Block image loading for performance
            page.route("**/*", lambda route: route.abort()
                      if route.request.resource_type == "image"
                      else route.continue_())
            
            if debug:
                page.on('console', lambda msg: logger.info(f"playwright debug: {msg.text}"))
            
            page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(self.post_load_timeout * 1000)
            self._scroll_to_bottom(page)
            
            result['html'] = page.content()
            result['title'] = page.title()
            result['url'] = page.url
            
            # Remove specified elements
            self._remove_elements(page, html_processing)
            
            # Extract content
            result['text'] = self._extract_text_content(page, remove_code)
            result['links'] = self._extract_links(page)
            
            if extract_tables:
                result['tables'] = self._extract_tables(page)
            
            if extract_images:
                result['images'] = self._extract_images(page)
                
        except PlaywrightTimeoutError:
            logger.info(f"Page loading timed out for {url} after {self.timeout} seconds")
        except Exception as e:
            logger.info(f"Page loading failed for {url} with exception '{e}'")
            if not self.browser.is_connected():
                self.browser = self.p.firefox.launch(headless=True)
        finally:
            if page:
                page.close()
            if context:
                context.close()
            self.browser_use_count += 1
            self._reset_browser_if_needed()
        
        logger.info(f"For crawled page {url}: images = {len(result['images'])}, "
                   f"tables = {len(result['tables'])}, links = {len(result['links'])}")
        
        return result
    
    def cleanup(self):
        """Clean up browser resources"""
        if hasattr(self, 'browser') and self.p is not None:
            self.browser.close()
        if hasattr(self, 'p') and self.p is not None:
            self.p.stop()