import json
import logging
import time
from typing import Dict, List, Optional
import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from omegaconf import OmegaConf
from core.utils import get_headers
from core.web_extractor_base import WebExtractorBase

logger = logging.getLogger(__name__)


class WebContentExtractor(WebExtractorBase):
    """Handles web content extraction using Playwright"""
    
    def __init__(self, cfg: OmegaConf, timeout: int = 90, post_load_timeout: int = 5, browser=None):
        super().__init__(cfg, timeout, post_load_timeout)
        # Reduce browser reuse limit to prevent memory buildup
        self.browser_use_limit = 20  # Reduced from 100
        self.browser_use_count = 0
        self.browser = browser
        self.p = None
        # Track consecutive failures for adaptive reset
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3
        
        if browser is None:
            self._setup_browser()
    
    def _ensure_browser_ready(self):
        """Ensure browser is initialized and ready"""
        if self.browser is None or self.p is None:
            self._setup_browser()
        
    def _setup_browser(self):
        """Initialize browser instance"""
        try:
            # Clean up any existing browser/playwright instance
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
            if self.p:
                try:
                    self.p.stop()
                except:
                    pass

            # Create fresh instances with better configuration
            self.p = sync_playwright().start()
            # Launch Chromium with stable configuration for Docker
            self.browser = self.p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-zygote',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=site-per-process',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--js-flags=--max-old-space-size=512',
                    '--memory-pressure-off',
                    '--max_old_space_size=512'
                ]
            )
            self.browser_use_count = 0
            self.consecutive_failures = 0  # Reset failure counter on successful setup
            logger.debug("Browser instance created successfully with memory limits")
        except Exception as e:
            logger.error(f"Failed to setup browser: {e}")
            self.browser = None
            self.p = None
            raise
        
    def _reset_browser_if_needed(self, force_reset=False):
        """Reset browser if usage limit reached or forced"""
        should_reset = (
            force_reset or 
            self.browser_use_count >= self.browser_use_limit or
            self.consecutive_failures >= self.max_consecutive_failures or
            (self.browser and not self.browser.is_connected())
        )
        
        if should_reset:
            try:
                if self.browser:
                    self.browser.close()
            except:
                pass
            
            try:
                if self.p:
                    self.p.stop()
            except:
                pass
            
            # Reinitialize browser
            self.p = None
            self.browser = None
            self._setup_browser()
            reason = "forced" if force_reset else f"after {self.browser_use_limit} uses or {self.consecutive_failures} failures"
            logger.info(f"Browser reset {reason} to avoid memory issues")
    
    def url_triggers_download(self, url: str) -> bool:
        """Check if URL triggers a download"""
        self._ensure_browser_ready()
        download_triggered = False
        context = None
        page = None
        
        try:
            # Create context with resource limits
            context = self.browser.new_context(
                # Add viewport to prevent infinite page sizes
                viewport={'width': 1920, 'height': 1080},
                # Limit resources
                ignore_https_errors=True,
                java_script_enabled=True
            )
            
            def on_download(download):
                nonlocal download_triggered
                download_triggered = True
                
            page = context.new_page()
            page.set_extra_http_headers(get_headers(self.cfg))
            page.on('download', on_download)
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)  # 30s timeout
            except Exception as e:
                logger.debug(f"Error checking download for {url}: {e}")
                pass
        except Exception as e:
            logger.error(f"Failed to check download for {url}: {e}")
        finally:
            if page:
                try:
                    page.close()
                except:
                    pass
            if context:
                try:
                    context.close()
                except:
                    pass
                    
        return download_triggered
    
    def _scroll_to_bottom(self, page, max_scroll_time=20):
        """Hybrid smart scroll with network idle + content stabilization + timeout"""
        start_time = time.time()
        stable_count = 0
        prev_height = None
        prev_content_indicators = None
        initial_wait = 500  # Start with 500ms waits
        current_wait = initial_wait
        
        logger.debug("Starting smart scroll detection")
        
        while time.time() - start_time < max_scroll_time:
            # Get multiple content indicators for stability check
            current_height = page.evaluate("document.body.scrollHeight")
            content_indicators = page.evaluate("""
                ({
                    textLength: document.body.innerText.length,
                    imageCount: document.images.length,
                    linkCount: document.links.length
                })
            """)
            
            # Check if content is stable across multiple indicators
            content_stable = (prev_height == current_height and 
                             prev_content_indicators == content_indicators)
            
            if content_stable:
                stable_count += 1
                logger.debug(f"Content stable for {stable_count} consecutive checks")
                if stable_count >= 2:  # Stable for 2 consecutive checks
                    logger.debug("Content stabilized, stopping scroll")
                    break
            else:
                stable_count = 0
                # Increase wait time if content keeps changing
                if current_wait < 2000:
                    current_wait = min(current_wait * 1.5, 2000)
                
            prev_height = current_height
            prev_content_indicators = content_indicators
            
            # Scroll to bottom
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
            # Use network idle detection with progressive timeout
            try:
                page.wait_for_load_state("networkidle", timeout=current_wait)
                logger.debug(f"Network idle detected after {current_wait}ms")
            except Exception:
                # Network idle timeout, continue with regular wait
                page.wait_for_timeout(current_wait)
                logger.debug(f"Network idle timeout, using regular wait of {current_wait}ms")
        
        total_time = time.time() - start_time
        if total_time >= max_scroll_time:
            logger.info(f"Scroll timeout reached ({max_scroll_time}s), stopping scroll")
        else:
            logger.debug(f"Smart scroll completed in {total_time:.1f}s")
    
    def _remove_elements(self, page, html_processing: dict):
        """Remove specified elements from page"""
        ids_to_remove = list(html_processing.get('ids_to_remove', []))
        classes_to_remove = list(html_processing.get('classes_to_remove', []))
        tags_to_remove = list(html_processing.get('tags_to_remove', []))

        if not ids_to_remove and not classes_to_remove and not tags_to_remove:
            return

        removal_script = """
            (function(ids, classes, tags) {
                var results = {ids: {}, classes: {}, tags: {}};
                ids.forEach(function(id) {
                    var el = document.getElementById(id);
                    results.ids[id] = !!el;
                    if (el) el.remove();
                });
                classes.forEach(function(cls) {
                    var els = document.querySelectorAll('.' + cls);
                    results.classes[cls] = els.length;
                    els.forEach(function(el) { el.remove(); });
                });
                tags.forEach(function(tag) {
                    var els = document.querySelectorAll(tag);
                    results.tags[tag] = els.length;
                    els.forEach(function(el) { el.remove(); });
                });
                return results;
            })(%s, %s, %s);
        """ % (
            json.dumps(ids_to_remove),
            json.dumps(classes_to_remove),
            json.dumps(tags_to_remove)
        )
        results = page.evaluate(removal_script)
        logger.debug("html_processing removal results: %s", results)
    
    def _extract_text_content(self, page, remove_code: bool = False) -> str:
        """Extract text content from page"""
        # Build selectors to remove as a second pass for common boilerplate
        remove_selectors = [
            'header', 'footer', 'nav', 'aside', '.sidebar', '#comments', '.advertisement'
        ]
        if remove_code:
            remove_selectors.extend(['code', 'pre'])

        return page.evaluate(f"""() => {{
            // Remove common boilerplate elements
            const selectorsToRemove = {json.dumps(remove_selectors)};
            selectorsToRemove.forEach(selector => {{
                document.querySelectorAll(selector).forEach(el => el.remove());
            }});

            // Extract text from remaining content
            let content = document.body.innerText || '';

            // Extract shadow DOM content
            function extractShadowText(root) {{
                let text = "";
                if (root.shadowRoot) {{
                    text += root.shadowRoot.textContent || '';
                    root.shadowRoot.querySelectorAll('*').forEach(child => {{
                        text += extractShadowText(child);
                    }});
                }}
                return text;
            }}

            document.querySelectorAll('*').forEach(el => {{
                content += extractShadowText(el);
            }});

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
                        const src = img.src;
                        if (!src || src.startsWith('data:') || src.startsWith('blob:')) return;
                        const w = parseInt(img.getAttribute('width') || '0');
                        const h = parseInt(img.getAttribute('height') || '0');
                        if ((w > 0 && w < 10) || (h > 0 && h < 10)) return;
                        images.push({ src: src, alt: img.alt || "" });
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

        result = {
            'text': '',
            'html': '',
            'title': '',
            'url': url,
            'links': [],
            'images': [],
            'tables': []
        }

        # Static pre-fetch: try requests.get() first. SSR pages (forums, documentation
        # sites) return clean HTML that Docling parses well. The live browser DOM is SPA-
        # structured (Angular/React elements) which Docling cannot parse into content —
        # JS-evaluating document.innerText gives rich text but page.content() gives
        # framework tags, not real HTML. We fall through to the browser only if static
        # content is sparse (<500 chars), indicating a true SPA needing JS rendering.
        try:
            from bs4 import BeautifulSoup
            static_resp = requests.get(url, headers=get_headers(self.cfg), timeout=30, allow_redirects=True)
            static_resp.raise_for_status()
            if 'text/html' in static_resp.headers.get('content-type', '').lower():
                soup = BeautifulSoup(static_resp.text, 'html.parser')
                static_text = soup.get_text(separator=' ', strip=True)
                if len(static_text.strip()) > 500:
                    result['html'] = static_resp.text
                    result['url'] = static_resp.url
                    result['title'] = soup.title.string if soup.title else ''
                    result['text'] = static_text
                    result['links'] = [a['href'] for a in soup.find_all('a', href=True)]
                    # Extract images with same filtering as the browser path
                    from urllib.parse import urljoin
                    for img_tag in soup.find_all('img'):
                        src = img_tag.get('src', '')
                        if not src or src.startswith('data:') or src.startswith('blob:'):
                            continue
                        try:
                            w = int(img_tag.get('width', '0') or '0')
                        except (ValueError, TypeError):
                            w = 0
                        try:
                            h = int(img_tag.get('height', '0') or '0')
                        except (ValueError, TypeError):
                            h = 0
                        if (w > 0 and w < 10) or (h > 0 and h < 10):
                            continue
                        result['images'].append({'src': urljoin(url, src), 'alt': img_tag.get('alt', '')})
                    logger.info(f"Static fetch used for {url}: {len(static_text)} chars")
                    logger.info(f"For crawled page {url}: images = {len(result['images'])}, "
                                f"tables = {len(result['tables'])}, links = {len(result['links'])}")
                    return result
                logger.debug(f"Static fetch for {url} too sparse ({len(static_text)} chars), falling back to browser")
        except Exception as e:
            logger.debug(f"Static pre-fetch failed for {url}, using browser: {e}")

        page = context = None
        # Cap at 90s: OS-level Chromium crash (SIGKILL) leaves websocket open, causing
        # Playwright's goto() to hang until TCP keepalive timeout (~2 min). 90s fails fast.
        nav_timeout = min(self.timeout * 1000, 90000)

        try:
            self._ensure_browser_ready()
            # Create context with resource limits
            context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True,
                java_script_enabled=True
            )
            page = context.new_page()
            page.set_extra_http_headers(get_headers(self.cfg))
            
            # Block unnecessary resources for performance and stability
            # Use a more selective approach to avoid breaking some sites
            def route_handler(route):
                try:
                    resource_type = route.request.resource_type
                    url = route.request.url
                    # Block images, fonts, and media but allow critical resources
                    if resource_type in ["image", "font", "media"]:
                        route.abort()
                    # Block known tracking/ad domains
                    elif any(domain in url for domain in ["google-analytics", "doubleclick", "facebook.com/tr"]):
                        route.abort()
                    else:
                        route.continue_()
                except Exception as e:
                    # If routing fails, continue to avoid breaking navigation
                    try:
                        route.continue_()
                    except:
                        pass
            
            page.route("**/*", route_handler)
            
            if debug:
                page.on('console', lambda msg: logger.info(f"playwright debug: {msg.text}"))
            
            logger.debug(f"Starting browser navigation to {url} (timeout={nav_timeout}ms)")
            page.goto(url, timeout=nav_timeout, wait_until="domcontentloaded")
            logger.debug(f"Navigation complete for {url}, starting post-load processing")
            page.wait_for_timeout(self.post_load_timeout * 1000)
            self._scroll_to_bottom(page)

            result['title'] = page.title()
            result['url'] = page.url

            # Remove specified elements BEFORE capturing HTML snapshot
            self._remove_elements(page, html_processing)
            result['html'] = page.content()

            # Extract content
            result['text'] = self._extract_text_content(page, remove_code)
            result['links'] = self._extract_links(page)

            if extract_tables:
                result['tables'] = self._extract_tables(page)

            if extract_images:
                result['images'] = self._extract_images(page)

        except PlaywrightTimeoutError:
            logger.info(f"Page loading timed out for {url} after {nav_timeout}ms")
            self.consecutive_failures += 1
        except Exception as e:
            logger.info(f"Page loading failed for {url} with exception '{e}'")
            self.consecutive_failures += 1
            # Force browser reset on crash-related errors
            if "crashed" in str(e).lower() or (self.browser and not self.browser.is_connected()):
                self._reset_browser_if_needed(force_reset=True)
        else:
            # Reset failure counter on success and count usage
            self.consecutive_failures = 0
            self.browser_use_count += 1
        finally:
            if page:
                try:
                    page.close()
                except:
                    pass
            if context:
                try:
                    context.close()
                except:
                    pass
            self._reset_browser_if_needed()

        # If browser also failed, log it — static pre-fetch already ran above.
        if not result['html']:
            logger.warning(f"Both static and browser fetch failed for {url}")

        logger.info(f"For crawled page {url}: images = {len(result['images'])}, "
                   f"tables = {len(result['tables'])}, links = {len(result['links'])}")
        
        return result
    
    def check_download_or_pdf(self, url: str, headers: dict = None, timeout: int = 5000):
        """Check if URL triggers download or serves PDF content directly"""
        from playwright._impl._errors import TargetClosedError, Error as PlaywrightError

        if headers is None:
            headers = get_headers(self.cfg)

        # Fast path: HEAD request to determine content-type without launching a browser.
        # This avoids Chromium crashes on heavy SPAs where the renderer dies under Docker
        # resource constraints before we ever reach fetch_page_contents.
        try:
            head = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
            ct = head.headers.get('content-type', '').lower()
            if 'text/html' in ct:
                logger.debug(f"HEAD confirmed HTML for {url}, skipping browser download check")
                return {"type": "html", "url": head.url, "response": None}
            if 'application/pdf' in ct:
                resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
                return {"type": "pdf", "url": resp.url, "content": resp.content,
                        "headers": dict(resp.headers)}
        except Exception as e:
            logger.debug(f"HEAD request failed for {url}, falling back to browser: {e}")

        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            context = None
            page = None
            try:
                self._ensure_browser_ready()
                
                # Create context and page with limits
                context = self.browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    ignore_https_errors=True,
                    java_script_enabled=True
                )
                page = context.new_page()
                page.set_extra_http_headers(headers)
                
                try:
                    # First try to catch an explicit download
                    try:
                        with page.expect_download(timeout=timeout) as dl_info:
                            response = page.goto(url, wait_until="domcontentloaded")
                        download = dl_info.value
                        # Ensure we close resources before returning
                        page.close()
                        context.close()
                        return {
                            "type": "download",
                            "url": download.url,
                            "filename": download.suggested_filename,
                            "download": download
                        }
                    except Exception as e:
                        # If it's a page crash or browser error, bubble up for retry
                        if isinstance(e, (TargetClosedError, PlaywrightError)) and "crashed" in str(e).lower():
                            self.consecutive_failures += 1
                            raise PlaywrightError(f"Page crashed: {e}")
                        if isinstance(e, TargetClosedError):
                            self.consecutive_failures += 1
                            raise
                        # No download triggered, check content type
                        response = page.goto(url, wait_until="domcontentloaded")
                        content_type = response.headers.get("content-type", "")
                        if "application/pdf" in content_type:
                            pdf_bytes = response.body()
                            # Close resources before returning
                            page.close()
                            context.close()
                            return {
                                "type": "pdf",
                                "url": response.url,
                                "content": pdf_bytes,
                                "headers": dict(response.headers)
                            }
                        else:
                            # Close resources before returning
                            page.close()
                            context.close()
                            # Success - reset failure counter
                            self.consecutive_failures = 0
                            return {"type": "html", "url": response.url, "response": response}
                finally:
                    # Cleanup already done in the try block before returns
                    pass
                    
            except (TargetClosedError, PlaywrightError) as e:
                # Clean up resources if they exist
                if page:
                    try:
                        page.close()
                    except:
                        pass
                if context:
                    try:
                        context.close()
                    except:
                        pass
                        
                if attempt < max_retries - 1:
                    logger.warning(f"Browser error during navigation to {url}: {str(e)[:100]}, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    # Force browser reset for fresh instance
                    self.consecutive_failures += 1
                    self._reset_browser_if_needed(force_reset=True)
                else:
                    logger.error(f"Failed to navigate to {url} after {max_retries} attempts: {e}")
                    raise
            except Exception as e:
                # Clean up resources for any other error
                if page:
                    try:
                        page.close()
                    except:
                        pass
                if context:
                    try:
                        context.close()
                    except:
                        pass
                logger.error(f"Unexpected error navigating to {url}: {e}")
                raise
    
    def cleanup(self):
        """Clean up browser resources"""
        # Browser cleanup without async lock
        try:
            if hasattr(self, 'browser') and self.browser is not None:
                try:
                    self.browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
                finally:
                    self.browser = None
                    
            if hasattr(self, 'p') and self.p is not None:
                try:
                    self.p.stop()
                except Exception as e:
                    logger.debug(f"Error stopping playwright: {e}")
                finally:
                    self.p = None
                    
            self.browser_use_count = 0
            self.consecutive_failures = 0
            logger.info("Browser resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")