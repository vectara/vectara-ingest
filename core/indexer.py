import logging
import json
import re
import os
import time
import warnings
import unicodedata
from typing import Dict, Any, List, Optional, Sequence
import shutil
from datetime import datetime

import uuid
import pandas as pd
import requests

from slugify import slugify

from omegaconf import OmegaConf
from nbconvert import HTMLExporter  # type: ignore
import nbformat
import markdown
import whisper
import hashlib

from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from core.summary import TableSummarizer, ImageSummarizer, get_attributes_from_text
from core.models import get_api_key
from core.utils import (
    html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries,
    mask_pii, safe_remove_file, url_to_filename, df_cols_to_headers, html_table_to_header_and_rows,
    get_file_path_from_url, create_row_items, configure_session_for_ssl, get_docker_or_local_path
)
from core.extract import get_article_content
from core.doc_parser import UnstructuredDocumentParser, DoclingDocumentParser, LlamaParseDocumentParser, \
    DocupandaDocumentParser
from core.contextual import ContextualChunker
from pypdf import PdfReader, PdfWriter
import tempfile

# Suppress FutureWarning related to torch.load
warnings.filterwarnings("ignore", category=FutureWarning, module="whisper")
warnings.filterwarnings("ignore", category=UserWarning, message="FP16 is not supported on CPU; using FP32 instead")

get_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# helper function to add table_extraction and chunking_strategy to payload
def _get_chunking_config(
        cfg: OmegaConf,
    ) -> Optional[Dict]:
    if cfg.vectara.get("chunking_strategy", "sentence") == "fixed":
        chunk_size = cfg.vectara.get("chunk_size", 512)
        return {
            "type": "max_chars_chunking_strategy",
            "max_chars_per_chunk": chunk_size
        }
    return None

def _extract_last_modified(url: str, html: str) -> dict:
    """
    Extracts the last modified date from HTML content.
    Strategies, in order:
      1. <meta http-equiv="last-modified" | name="last-modified">
      2. <time datetime="…">
      3. Regex search for ISO or "Month Day, Year"
      4. Fallback to MD5 hash of the HTML
    """
    result = {'url': url, 'detection_method': None}
    soup = BeautifulSoup(html, 'html.parser')

    # 1) META tags
    for attr in ('http-equiv', 'name'):
        tag = soup.find('meta', attrs={attr: lambda v: v and v.lower()=='last-modified'})
        if tag and tag.get('content'):
            try:
                dt = parsedate_to_datetime(tag['content'])
            except Exception:
                continue
            result.update(last_modified=dt, detection_method='meta')
            return result

    # 2) <time datetime="…">
    times = []
    for time_tag in soup.find_all('time', datetime=True):
        dt_str = time_tag['datetime'].strip()
        for parser in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                dt = parser(dt_str)
                times.append(dt)
                break
            except Exception:
                continue
    if times:
        result.update(last_modified=max(times), detection_method='time')
        return result

    # 3) Regex search
    text = soup.get_text(" ", strip=True)
    patterns = [
        # ISO-8601, no capture group so findall → full match
        r'\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?\b',
        # Month Day, Year using a non-capturing group for the month
        r'\b(?:January|February|March|April|May|June|July|'
        r'August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b',
    ]
    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            dt_str = m.group(0)
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%B %d, %Y"):
                try:
                    dt = parsedate_to_datetime(dt_str) if 'T' in dt_str or '-' in dt_str else datetime.strptime(dt_str, fmt)
                    candidates.append(dt)
                    break
                except Exception:
                    continue

    if candidates:
        result.update(last_modified=max(candidates), detection_method='regex')
        return result

    # 4) Fallback to hash
    result.update(content_hash=hashlib.md5(html.encode('utf-8')).hexdigest(),
                  detection_method='hash')
    return result

class Indexer:
    """
    Vectara API class.
    Args:
        api_url (str): Url for the Vectara API.
        corpus_key (str): Key of the Vectara corpus to index to.
        api_key (str): API key for the Vectara API.
    """

    def __init__(self, cfg: OmegaConf, api_url: str,
                 corpus_key: str, api_key: str) -> None:
        self.cfg = cfg
        self.browser_use_limit = 100
        self.api_url = api_url
        self.corpus_key = corpus_key
        self.api_key = api_key
        self.reindex = cfg.vectara.get("reindex", False)
        self.create_corpus = cfg.vectara.get("create_corpus", False)
        self.verbose = cfg.vectara.get("verbose", False)
        self.store_docs = cfg.vectara.get("store_docs", False)
        self.output_dir = cfg.vectara.get("output_dir", "vectara_ingest_output")
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.post_load_timeout = cfg.vectara.get("post_load_timeout", 5)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'
        self.logger = logging.getLogger()
        self.whisper_model = None
        self.whisper_model_name = cfg.vectara.get("whisper_model", "base")
        self.static_metadata = cfg.get('metadata', None)

        if 'doc_processing' not in cfg:
            cfg.doc_processing = {}
        self.parse_tables = cfg.doc_processing.get("parse_tables", cfg.doc_processing.get("summarize_tables",
                                                                                          False))  # backward compatibility
        self.enable_gmft = cfg.doc_processing.get("enable_gmft", False)
        self.do_ocr = cfg.doc_processing.get("do_ocr", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.process_locally = cfg.doc_processing.get("process_locally", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.use_core_indexing = cfg.doc_processing.get("use_core_indexing", False)
        self.unstructured_config = cfg.doc_processing.get("unstructured_config",
                                                          {'chunking_strategy': 'by_title', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", {'chunking_strategy': 'none'})
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        self.contextual_chunking = cfg.doc_processing.get("contextual_chunking", False)

        if ('model' in self.cfg.doc_processing or 
            ('model_config' not in self.cfg.doc_processing and 'model' not in self.cfg.doc_processing)):
            logging.warning(
                "doc_processing.model will no longer be supported in a future release. Use doc_processing.model_config instead.")

            provider = self.cfg.doc_processing.get("model", "openai")
            pcfg = {
                'provider': provider,
                'model_name': self.cfg.doc_processing.get("model_name", "gpt-4o"),
                'base_url': self.cfg.doc_processing.get("base_url",
                                                        "https://api.openai.com/v1") if provider == 'openai' else \
                    self.cfg.doc_processing.get("base_url", "https://api.anthropic.com/"),
            }
            mcfg = {
                'text': pcfg,
                'vision': pcfg,
            }  # By default use the same model for text and image processing
            OmegaConf.update(self.cfg, "doc_processing.model_config", mcfg, merge=False)

        self.model_config = self.cfg.doc_processing.get("model_config", {})
        text_api_key = get_api_key(self.model_config.get('text', {}).get('provider', None), cfg)
        vision_api_key = get_api_key(self.model_config.get('vision', {}).get('provider', None), cfg)

        if self.parse_tables and text_api_key is None and self.process_locally:
            self.parse_tables = False
            self.logger.warning("Table summarization enabled but model API key not found, disabling table summarization")

        if self.summarize_images and vision_api_key is None:
            self.summarize_images = False
            self.logger.warning(
                "Image summarization (doc_processing.summarize_images) enabled but model API key not found, disabling image summarization")

        if self.contextual_chunking and text_api_key is None:
            self.contextual_chunking = False
            self.logger.warning("Contextual chunking enabled but model API key not found, disabling contextual chunking")

        if self.extract_metadata and text_api_key is None:
            self.extract_metadata = []
            self.logger.warning(
                "Metadata extraction (doc_processing.extract_metadata) enabled but model API key not found, disabling metadata extraction")

        logging.info(f"Vectara API Url = '{self.api_url}'")

        self.setup()

    def normalize_text(self, text: str) -> str:
        if pd.isnull(text) or len(text) == 0:
            return text
        if self.cfg.vectara.get("mask_pii", False):
            text = mask_pii(text)
        text = unicodedata.normalize('NFD', text)
        return text

    def normalize_value(self, v):
        if isinstance(v, str):
            return self.normalize_text(v)
        else:
            return v

    def setup(self, use_playwright: bool = True) -> None:
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.vectara)

        # Create playwright browser so we can reuse it across all Indexer operations
        if use_playwright:
            self.p = sync_playwright().start()
            self.browser = self.p.firefox.launch(headless=True)
            self.browser_use_count = 0
        if self.store_docs:
            uuid_suffix = f"indexed_docs_{str(uuid.uuid4())}"
            docker_env_path = '/home/vectara/env'
            
            self.store_docs_folder = get_docker_or_local_path(
                docker_path=os.path.join(docker_env_path, uuid_suffix),
                output_dir=os.path.join(self.output_dir, uuid_suffix),
                should_delete_existing=True
            )

    def store_file(self, filename: str, orig_filename) -> None:
        if self.store_docs:
            dest_path = f"{self.store_docs_folder}/{orig_filename}"
            shutil.copyfile(filename, dest_path)

    def url_triggers_download(self, url: str) -> bool:
        download_triggered = False
        context = self.browser.new_context()

        # Define the event listener for download
        def on_download(download):
            nonlocal download_triggered
            download_triggered = True

        page = context.new_page()
        page.set_extra_http_headers(get_headers)
        page.on('download', on_download)
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception:
            pass

        page.close()
        context.close()
        return download_triggered

    def fetch_page_contents(
            self,
            url: str,
            extract_tables: bool = False,
            extract_images: bool = False,
            remove_code: bool = False,
            html_processing: dict = None,
            debug: bool = False
    ) -> dict:
        '''
        Fetch content from a URL with a timeout, including content from the Shadow DOM.
        Args:
            url (str): URL to fetch.
            extract_tables (bool): Whether to extract tables from the page.
            extract_images (bool): Whether to extract images from the page.
            remove_code (bool): Whether to remove code from the HTML content.
            html_processing (dict): Dict with optional lists:
                - 'ids_to_remove': list of element IDs to remove
                - 'classes_to_remove': list of class names to remove
                - 'tags_to_remove': list of tag names to remove
            debug (bool): Whether to enable playwright debug logging.
        Returns:
            dict with
            - 'text': text extracted from the page (including Shadow DOM)
            - 'html': html of the page
            - 'title': title of the page
            - 'url': final URL of the page (if redirected)
            - 'links': list of links in the page (including Shadow DOM)
            - 'images': list of dictionaries with image info: [{'src': ..., 'alt': ...}, ...]
            - 'tables': list of strings representing the outerHTML of each table
        '''
        page = context = None
        text = ''
        html_content = ''
        title = ''
        links = []
        out_url = url
        images = []
        tables = []

        if html_processing is None:
            html_processing = {}
        ids_to_remove = list(html_processing.get('ids_to_remove', []))
        classes_to_remove = list(html_processing.get('classes_to_remove', []))
        tags_to_remove = list(html_processing.get('tags_to_remove', []))

        try:
            context = self.browser.new_context()
            page = context.new_page()
            page.set_extra_http_headers(get_headers)
            page.route("**/*", lambda route: route.abort()
            if route.request.resource_type == "image"
            else route.continue_()
                       )
            if debug:
                page.on('console', lambda msg: self.logger.info(f"playwright debug: {msg.text})"))

            page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            page.wait_for_timeout(self.post_load_timeout * 1000)  # Wait additional time to handle AJAX
            self._scroll_to_bottom(page)
            html_content = page.content()

            title = page.title()
            out_url = page.url

            # Remove specified elements in-page before extraction
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

            text = page.evaluate(f"""() => {{
                let content = Array.from(document.body.childNodes)
                    .map(node => node.textContent || "")
                    .join(" ")
                    .trim();
                
                const elementsToRemove = [
                    'header',
                    'footer',
                    'nav',
                    'aside',
                    '.sidebar',
                    '#comments',
                    '.advertisement'
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
                
                return content.replace(/\s{2,}/g, ' ').trim();
            }}""")

            # Extract links (direct and in shadow DOM)
            links = page.evaluate("""
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

            # Extract tables
            if extract_tables:
                tables = page.evaluate("""
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

            # Extract images
            if extract_images:
                images = page.evaluate("""
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


        except PlaywrightTimeoutError:
            self.logger.info(f"Page loading timed out for {url} after {self.timeout} seconds")
        except Exception as e:
            self.logger.info(f"Page loading failed for {url} with exception '{e}'")
            if not self.browser.is_connected():
                self.browser = self.p.firefox.launch(headless=True)
        finally:
            if page:
                page.close()
            if context:
                context.close()
            self.browser_use_count += 1
            if self.browser_use_count >= self.browser_use_limit:
                self.browser.close()
                self.browser = self.p.firefox.launch(headless=True)
                self.browser_use_count = 0
                self.logger.info(f"browser reset after {self.browser_use_limit} uses to avoid memory issues")

        self.logger.info(f"For crawled page {url}: images = {len(images)}, tables = {len(tables)}, links = {len(links)}")

        return {
            'text': text,
            'html': html_content,
            'title': title,
            'url': out_url,
            'links': links,
            'images': images,
            'tables': tables
        }

    def _scroll_to_bottom(self, page, pause=2000):
        """
        Scroll down the page until no new content is loaded. Useful for pages that load content on scroll.
        :param page: Playwright page object.
        :param pause: Time in milliseconds to wait after each scroll.
        """
        prev_height = None
        while True:
            current_height = page.evaluate("document.body.scrollHeight")
            if prev_height == current_height:
                break
            prev_height = current_height
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(pause)

    def _does_doc_exist(self, doc_id: str) -> bool:
        """
        Check if a document exists in the Vectara corpus.

        Args:
            doc_id (str): ID of the document to check.

        Returns:
            bool: True if the document exists, False otherwise.
        """
        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }
        response = self.session.get(
            f"{self.api_url}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            headers=post_headers)
        return response.status_code == 200

    # delete document; returns True if successful, False otherwise
    def delete_doc(self, doc_id: str) -> bool:
        """
        Delete a document from the Vectara corpus.

        Args:
            url (str): URL of the page to delete.
            doc_id (str): ID of the document to delete.

        Returns:
            bool: True if the delete was successful, False otherwise.
        """
        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }

        response = self.session.delete(
            f"{self.api_url}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            headers=post_headers)

        if response.status_code != 204:
            self.logger.error(
                f"Delete request failed for doc_id = {doc_id} with status code {response.status_code}, reason {response.reason}, text {response.text}")
            return False
        return True

    def _list_docs(self) -> List[Dict[str, str]]:
        """
        List documents in the corpus.
        Returns:
            list of [docId, URL] for each document in the corpus
            URL taken from metadata if exists, otherwise it'd be None
        """
        page_key = None  # Initialize page_key as None
        docs = []

        # Loop until there's no next page
        while True:
            params = {"limit": 100}
            if page_key:  # Add page_key to the request if it's not None
                params["page_key"] = page_key

            post_headers = {
                'x-api-key': self.api_key,
                'X-Source': self.x_source
            }
            response = self.session.get(
                f"{self.api_url}/v2/corpora/{self.corpus_key}/documents",
                headers=post_headers, params=params)
            if response.status_code != 200:
                self.logger.error(f"Error listing documents with status code {response.status_code}")
                return []
            res = response.json()

            # Extract URLs from documents
            for doc in res.get('documents', []):
                url = doc['metadata']['url'] if 'url' in doc['metadata'] else None
                docs.append({'id': doc['id'], 'url': url})

            response_metadata = res.get('metadata', None)
            # Check if we need to go further
            if not response_metadata or not response_metadata['page_key']:  # Break the loop if there's no next page
                break
            else:
                page_key = response_metadata['page_key']

        return docs

    def _index_file(self, filename: str, uri: str, metadata: Dict[str, Any], id: str = None) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus, using APIv2
        Args:
            filename (str): Name of the file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
            id (str, optional): Document id for the uploaded document.
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if not os.path.exists(filename):
            self.logger.error(f"File {filename} does not exist")
            return False

        if self.static_metadata:
            metadata.update({k: v for k, v in self.static_metadata.items() if k not in metadata})

        post_headers = {
            'Accept': 'application/json',
            'x-api-key': self.api_key,
        }
        url = f"{self.api_url}/v2/corpora/{self.corpus_key}/upload_file"

        upload_filename = id if id is not None else filename.split('/')[-1]
        
        files = {
            'file': (upload_filename, open(filename, 'rb')),
            'metadata': (None, json.dumps(metadata), 'application/json'),
        }

        if self.parse_tables and filename.endswith('.pdf'):
            files['table_extraction_config'] = (None, json.dumps({'extract_tables': True}), 'application/json')
        chunking_config = _get_chunking_config(self.cfg)
        if chunking_config:
            files['chunking_strategy'] = (None, json.dumps(chunking_config), 'application/json')

        response = self.session.request("POST", url, headers=post_headers, files=files)
        if response.status_code == 409:
            if self.reindex:
                match = re.search(r"document id '([^']+)'", response.text)
                if match:
                    doc_id = match.group(1)
                else:
                    self.logger.error(f"Failed to extract document id from error message: {response.text}")
                    return False
                self.delete_doc(doc_id)
                new_files = {
                    'file': (upload_filename, open(filename, 'rb')),
                    'metadata': (None, json.dumps(metadata), 'application/json'),
                }
                if self.parse_tables and filename.endswith('.pdf'):
                    new_files['table_extraction_config'] = (None, json.dumps({'extract_tables': True}), 'application/json')
                chunking_config = _get_chunking_config(self.cfg)
                if chunking_config:
                    new_files['chunking_strategy'] = (None, json.dumps(chunking_config), 'application/json')

                response = self.session.request("POST", url, headers=post_headers, files=new_files)
                if response.status_code == 201:
                    self.logger.info(f"REST upload for {uri} successful (reindex)")
                    self.store_file(filename, url_to_filename(uri))
                    return True
                else:
                    self.logger.info(
                        f"REST upload for {uri} ({doc_id}) (reindex) failed with code = {response.status_code}, text = {response.text}")
                    return True
            else:
                self.logger.info(f"document {uri} already indexed, skipping")
                return False
        elif response.status_code != 201:
            self.logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        self.logger.info(f"REST upload for {uri} ({upload_filename}) successful")
        self.store_file(filename, url_to_filename(uri))
        return True

    def index_document(self, document: Dict[str, Any], use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the document dictionary

        Args:
            document (dict): Document to index.
            use_core_indexing (bool): Whether to use the core indexing API.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        api_endpoint = f"{self.api_url}/v2/corpora/{self.corpus_key}/documents"
        doc_exists = self._does_doc_exist(document['id'])
        if doc_exists:
            if self.reindex:
                self.logger.info(f"Document {document['id']} already exists, deleting then reindexing")
                self.delete_doc(document['id'])
            else:
                self.logger.info(f"Document {document['id']} already exists, skipping")
                return False


        if self.static_metadata:
            metadata = None
            if 'metadata' in document:
                metadata = document['metadata']
            else:
                metadata = {}
                document['metadata'] = metadata
            metadata.update({k: v for k, v in self.static_metadata.items() if k not in metadata})


        if use_core_indexing:
            document['type'] = 'core'
        else:
            document['type'] = 'structured'

        if not self.use_core_indexing:
            chunking_config = _get_chunking_config(self.cfg)
            if chunking_config:
                document['chunking_strategy'] = chunking_config

        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }
        try:
            data = json.dumps(document)
        except Exception as e:
            self.logger.info(f"Can't serialize document {document} (error {e}), skipping")
            return False

        try:
            response = self.session.post(api_endpoint, data=data, headers=post_headers)
        except Exception as e:
            self.logger.info(f"Exception {e} while indexing document {document['id']}")
            return False

        if response.status_code != 201:
            self.logger.error("REST upload failed with code %d, reason %s, text %s",
                              response.status_code,
                              response.reason,
                              response.text)
            return False

        if self.store_docs:
            with open(f"{self.store_docs_folder}/{document['id']}.json", "w") as f:
                json.dump(document, f)
        return True

    def index_url(self, url: str, metadata: Dict[str, Any], html_processing: dict = None) -> bool:
        """
        Index a url by rendering it with scrapy-playwright, extracting paragraphs, then uploading to the Vectara corpus.
        
        Args:
            url (str): URL for where the document originated. 
            metadata (dict): Metadata for the document.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        succeeded = False
        if html_processing is None:
            html_processing = {}
        st = time.time()
        url = url.split("#")[0]  # remove fragment, if exists

        # if file is going to download, then handle it as local file
        if self.url_triggers_download(url):
            os.makedirs("/tmp", exist_ok=True)
            url_file_path = get_file_path_from_url(url)
            if not url_file_path:
                self.logger.info(f"Failed to extract file path from URL {url}, skipping...")
                return False
            file_path = os.path.join("/tmp/" + url_file_path)
            response = self.session.get(url, headers=get_headers, stream=True)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                self.logger.info(f"File downloaded successfully and saved as {file_path}")
                res = self.index_file(file_path, url, metadata)
                safe_remove_file(file_path)
                return res
            else:
                self.logger.info(f"Failed to download file. Status code: {response.status_code}")
                return False

        # If MD or IPYNB file, then we don't need playwright - can just download content directly and convert to text
        if url.lower().endswith(".md") or url.lower().endswith(".ipynb"):
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            dl_content = response.content.decode('utf-8')
            if url.lower().endswith('md'):
                html_content = markdown.markdown(dl_content)
            elif url.lower().endswith('ipynb'):
                nb = nbformat.reads(dl_content, as_version=4)
                exporter = HTMLExporter()
                html_content, _ = exporter.from_notebook_node(nb)
            doc_title = url.split('/')[-1]  # no title in these files, so using file name
            text = html_to_text(html_content, self.remove_code)
            parts = [text]

        else:
            try:
                # Use Playwright to get the page content
                res = self.fetch_page_contents(
                    url=url,
                    extract_tables=self.parse_tables,
                    extract_images=self.summarize_images,
                    remove_code=self.remove_code,
                    html_processing=html_processing,
                )
                html = res['html']
                text = res['text']
                doc_title = res['title']
                if text is None or len(text) < 3:
                    return False

                # Extract the last modified date from the HTML content.
                ext_res = _extract_last_modified(url, html)
                last_modified = ext_res.get('last_modified', None)
                if last_modified:
                    metadata['last_updated'] = last_modified.strftime("%Y-%m-%d")

                # Detect language if needed
                if self.detected_language is None:
                    self.detected_language = detect_language(text)
                    self.logger.info(f"The detected language is {self.detected_language}")

                if len(self.extract_metadata) > 0:
                    ex_metadata = get_attributes_from_text(
                        self.cfg,
                        text,
                        metadata_questions=self.extract_metadata,
                        model_config=self.model_config.text
                    )
                    metadata.update(ex_metadata)
                else:
                    ex_metadata = {}

                #
                # By default, 'text' is extracted above.
                # If remove_boilerplate is True, then use it directly
                # If no boilerplate remove but need to remove code, then we need to use html_to_text
                #
                if self.remove_boilerplate:
                    url = res['url']
                    if self.verbose:
                        self.logger.info(
                            f"Removing boilerplate from content of {url}, and extracting important text only")
                    text, doc_title = get_article_content(html, url, self.detected_language, self.remove_code)
                else:
                    text = html_to_text(html, self.remove_code, html_processing)

                parts = [text]
                metadatas = [{'element_type': 'text'}]

                vec_tables = []
                if self.parse_tables and 'tables' in res:
                    if 'text' not in self.model_config:
                        self.logger.warning("Table summarization is enabled but no text model is configured, skipping table summarization")
                    else:
                        if self.verbose:
                            self.logger.info(f"Found {len(res['tables'])} tables in {url}")
                        table_summarizer = TableSummarizer(
                            cfg=self.cfg,
                            table_model_config=self.model_config.text,
                        )
                        for table in res['tables']:
                            table_summary = table_summarizer.summarize_table_text(table)
                            if table_summary:
                                if self.verbose:
                                    self.logger.info(f"Table summary: {table_summary[:500]}...")
                                cols, rows = html_table_to_header_and_rows(table)
                                cols_not_empty = any(col for col in cols)
                                rows_not_empty = any(any(cell for cell in row) for row in rows)
                                if cols_not_empty or rows_not_empty:
                                    vec_tables.append({'headers': cols, 'rows': rows, 'summary': table_summary})

                # index text and tables
                doc_id = slugify(url)
                succeeded = self.index_segments(doc_id=doc_id, texts=parts, metadatas=metadatas, tables=vec_tables,
                                                doc_metadata=metadata, doc_title=doc_title)

                # index images - each image as a separate "document" in Vectara
                if self.summarize_images:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    image_summarizer = ImageSummarizer(
                        cfg=self.cfg,
                        image_model_config=self.model_config.vision
                    )
                    image_filename = 'image.png'
                    if 'images' in res:
                        if self.verbose:
                            self.logger.info(f"Found {len(res['images'])} images in {url}")
                        for inx, image in enumerate(res['images']):
                            image_url = image['src']
                            response = requests.get(image_url, headers=headers, stream=True)
                            if response.status_code != 200:
                                self.logger.info(f"Failed to retrieve image {image_url} from {url}, skipping")
                                continue
                            with open(image_filename, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            image_summary = image_summarizer.summarize_image(image_filename, image_url, None)
                            if image_summary:
                                text = image_summary
                                metadata = {'element_type': 'image', 'url': url}
                                if ex_metadata:
                                    metadata.update(ex_metadata)
                                if self.verbose:
                                    self.logger.info(f"Image summary: {image_summary[:500]}...")
                                doc_id = slugify(url) + "_image_" + str(inx)
                                succeeded = self.index_segments(doc_id=doc_id, texts=[image_summary],
                                                                metadatas=metadatas,
                                                                doc_metadata=metadata, doc_title=doc_title,
                                                                use_core_indexing=True)
                            else:
                                self.logger.info(f"Failed to retrieve image {image['src']}")
                                continue

                self.logger.info(f"retrieving content took {time.time() - st:.2f} seconds")
            except Exception as e:
                import traceback
                self.logger.info(
                    f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
                return False

        return succeeded

    def index_segments(self, doc_id: str, texts: List[str], titles: Optional[List[str]] = None,
                       metadatas: Optional[List[Dict[str, Any]]] = None,
                       doc_metadata: Dict[str, Any] = None, doc_title: str = "",
                       tables: Optional[Sequence[Dict[str, Any]]] = None,
                       use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.

        Args:
            doc_id (str): ID of the document.
            texts (List[str]): List of segments (parts) of the document.
            titles (List[str]): List of titles for each segment.
            metadatas (List[dict]): List of metadata for each segment.
            doc_metadata (dict): Metadata for the document.
            doc_title (str): Title of the document.
            tables (List[dict]): List of tables. Each table is a dictionary with 'headers', 'rows', and 'summary'.
            use_core_indexing (bool): Whether to use the core indexing API.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if ''.join(texts).strip() == '':
            self.logger.info(f"Document {doc_id} has no content, skipping")
            return False

        if titles is None:
            titles = ["" for _ in range(len(texts))]
        if doc_metadata is None:
            doc_metadata = {}
        if metadatas is None:
            metadatas = [{} for _ in range(len(texts))]
        else:
            metadatas = [{k: self.normalize_value(v) for k, v in md.items()} for md in metadatas]

        document = {}
        document["id"] = (
            doc_id if len(doc_id) < 128 
            else doc_id[:128] + "-" + hashlib.sha256(doc_id.encode('utf-8')).hexdigest()[:16]
        )

        # Create tables structure
        tables_array = []
        if tables:
            for inx, table in enumerate(tables):
                table_dict = {
                    'id': 'table_' + str(inx),
                    'title': table.get('title', ''),
                    'data': {
                        'headers': [
                            [
                                {'text_value': str(col)}
                                for col in header
                            ] for header in table['headers']
                        ],
                        'rows': [
                            create_row_items(row) for row in table['rows']
                        ]
                    },
                    'description': table['summary']
                }
                tables_array.append(table_dict)

        if not use_core_indexing:
            if doc_title is not None and len(doc_title) > 0:
                document["title"] = self.normalize_text(doc_title)
            document["sections"] = [
                {"text": self.normalize_text(text), "title": self.normalize_text(title), "metadata": md}
                for text, title, md in zip(texts, titles, metadatas)
            ]
            if tables:
                document["sections"].append(
                    {"text": '', "title": '', "metadata": {}, "tables": tables_array}
                )
        else:
            if any((len(text) > 16384 for text in texts)):
                self.logger.info(f"Document {doc_id} too large for Vectara core indexing, skipping")
                return False
            document["document_parts"] = [
                {"text": self.normalize_text(text), "metadata": md}
                for text, md in zip(texts, metadatas)
            ]
            if tables:
                document["tables"] = tables_array

        if doc_metadata:
            document["metadata"] = doc_metadata

        if self.verbose:
            self.logger.info(f"Indexing document {doc_id} with json {str(document)[:500]}...")

        return self.index_document(document, use_core_indexing)

    def index_file(self, filename: str, uri: str, metadata: Dict[str, Any], id: str = None) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus.
        
        Args:
            filename (str): Name of the PDF file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
            id (str, optional): Document id for the uploaded document.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if not os.path.exists(filename):
            self.logger.error(f"File {filename} does not exist")
            return False

        # If we have a PDF/HTML/PPT/DOCX file with size>50MB, or we want to use the parse_tables option, then we parse locally and index
        max_chars = 128000  # all_text is limited to 128,000 characters
        large_file_extensions = ['.pdf', '.html', '.htm', '.pptx', '.docx']
        filesize_mb = get_file_size_in_MB(filename)

        if (any(uri.endswith(extension) for extension in large_file_extensions) and
                (self.contextual_chunking or self.summarize_images or self.enable_gmft)
        ):
            self.process_locally = True

        #
        # Case A: using the file-upload API
        # Used when we don't need to process the file locally, and we don't need to parse tables from non-PDF files
        #
        if not self.process_locally and (
                (self.parse_tables and filename.lower().endswith('.pdf')) or not self.parse_tables):
            self.logger.info(f"For {uri} - Uploading via Vectara file upload API")
            if len(self.extract_metadata) > 0 or self.summarize_images:
                self.logger.info(f"Reading contents of {filename} (url={uri})")
                dp = UnstructuredDocumentParser(
                    cfg=self.cfg,
                    verbose=self.verbose,
                    model_config=self.cfg.doc_processing.model_config,
                    parse_tables=False, enable_gmft=False,
                    summarize_images=self.summarize_images,
                )
                title, texts, _, images = dp.parse(filename, uri)

            # Get metadata attribute values from text content (if defined)
            ex_metadata = {}
            if len(self.extract_metadata) > 0:
                if 'text' not in self.model_config:
                    self.logger.warning("Metadata field extraction is enabled but no text model is configured, skipping")
                else:
                    all_text = "\n".join([t[0] for t in texts])[:max_chars]
                    ex_metadata = get_attributes_from_text(
                        self.cfg,
                        all_text,
                        metadata_questions=self.extract_metadata,
                        model_config=self.model_config.text
                    )
                    metadata.update(ex_metadata)
            metadata.update(ex_metadata)
            metadata['file_name'] = filename.split('/')[-1]

            max_pdf_size = int(self.cfg.doc_processing.get('max_pdf_size', 50))
            pages_per_pdf = int(self.cfg.doc_processing.get('pages_per_pdf', 100))

            if filesize_mb > max_pdf_size:
                pdf_reader = PdfReader(filename)
                total_pages = len(pdf_reader.pages)
                logging.info(
                    f"{filename} is {filesize_mb} which is larger than {max_pdf_size} mb with {total_pages} pages. Splitting into {pages_per_pdf} page chunks.")
                error_count = 0
                for i in range(0, total_pages, pages_per_pdf):
                    pdf_writer = PdfWriter()
                    pdf_part_metadata = {
                        "start_page": i,
                        "end_page": min(i + pages_per_pdf, total_pages)
                    }
                    for j in range(i, min(i + pages_per_pdf, total_pages)):
                        pdf_writer.add_page(pdf_reader.pages[j])
                    pdf_part_id = f"{metadata['file_name']}-{i}"

                    pdf_part_metadata.update(metadata)
                    with tempfile.NamedTemporaryFile(suffix=".pdf", mode='wb', delete=False) as f:
                        pdf_writer.write(f)
                        f.flush()
                        f.close()
                        try:
                            part_success = self._index_file(f.name, uri, pdf_part_metadata, pdf_part_id)
                            if not part_success:
                                error_count += 1
                        finally:
                            if os.path.exists(f.name):
                                os.remove(f.name)
                    succeeded = error_count == 0
            else:
                # index the file within Vectara (use FILE UPLOAD API)
                succeeded = self._index_file(filename, uri, metadata, id)

            # If indicated, summarize images - and upload each image summary as a single doc
            if self.summarize_images and images:
                self.logger.info(f"Extracted {len(images)} images from {uri}")
                for inx, image in enumerate(images):
                    image_summary = image[0]
                    metadata = image[1]
                    if ex_metadata:
                        metadata.update(ex_metadata)
                    doc_id = slugify(uri) + "_image_" + str(inx)
                    succeeded &= self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=[metadata],
                                                     doc_metadata=metadata, doc_title=title, use_core_indexing=True)
            return succeeded

        #
        # Case B: Process locally and upload to Vectara
        #
        self.logger.info(f"Parsing file {filename} locally")
        if self.contextual_chunking:
            self.logger.info(f"Applying contextual chunking for {filename}")
            dp = UnstructuredDocumentParser(
                cfg=self.cfg,
                verbose=self.verbose,
                model_config=self.model_config,
                chunking_strategy='by_title',
                chunk_size=1024,
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images,
            )
        elif self.doc_parser == "llama_parse" or self.doc_parser == "llama" or self.doc_parser == "llama-parse":
            dp = LlamaParseDocumentParser(
                cfg=self.cfg,
                verbose=self.verbose,
                model_config=self.model_config,
                llama_parse_api_key=self.cfg.get("llama_cloud_api_key", None),
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images
            )
        elif self.doc_parser == "docupanda":
            dp = DocupandaDocumentParser(
                cfg=self.cfg,
                verbose=self.verbose,
                model_config=self.model_config,
                docupanda_api_key=self.cfg.get("docupanda_api_key", None),
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images
            )
        elif self.doc_parser == "docling":
            dp = DoclingDocumentParser(
                cfg=self.cfg,
                verbose=self.verbose,
                model_config=self.model_config,
                chunking_strategy=self.docling_config.get('chunking_strategy', 'none'),
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                do_ocr=self.do_ocr,
                summarize_images=self.summarize_images,
                image_scale=self.docling_config.get('image_scale', 2.0),
            )
        else:
            dp = UnstructuredDocumentParser(
                cfg=self.cfg,
                verbose=self.verbose,
                model_config=self.cfg.doc_processing.model_config,
                chunking_strategy=self.unstructured_config.get('chunking_strategy', 'by_title'),
                chunk_size=self.unstructured_config.get('chunk_size', 1024),
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images,
            )

        try:
            title, texts, tables, images = dp.parse(filename, uri)
        except Exception as e:
            self.logger.info(f"Failed to parse {filename} with error {e}")
            return False

        # Get metadata attribute values from text content (if defined)
        if len(self.extract_metadata) > 0:
            all_text = "\n".join([t[0] for t in texts])[:max_chars]
            ex_metadata = get_attributes_from_text(
                self.cfg,
                all_text,
                metadata_questions=self.extract_metadata,
                model_config=self.model_config.text
            )
            metadata.update(ex_metadata)
        else:
            ex_metadata = {}

        # prepare tables
        def generate_vec_tables(tables):
            for df, summary, table_title, table_metadata in tables:
                cols = df_cols_to_headers(df)
                rows = df.fillna('').values.tolist()
                del df
                if len(rows) > 0 and len(cols) > 0:
                    yield {'headers': cols, 'rows': rows, 'summary': summary, 'title': table_title,
                           'metadata': table_metadata}

        # Index text portions
        # Apply contextual chunking if indicated, otherwise just the text directly.
        if self.contextual_chunking:
            chunks = [t[0] for t in texts]
            all_text = "\n".join(chunks)
            cc = ContextualChunker(
                cfg=self.cfg,
                contextual_model_config=self.model_config.text,
                whole_document=all_text
            )
            contextual_chunks = cc.parallel_transform(chunks)
            succeeded = self.index_segments(
                doc_id=slugify(uri),
                texts=contextual_chunks, metadatas=[t[1] for t in texts],
                tables=generate_vec_tables(tables),
                doc_metadata=metadata, doc_title=title,
                use_core_indexing=True
            )
        else:
            succeeded = self.index_segments(
                doc_id=slugify(uri),
                texts=[t[0] for t in texts], metadatas=[t[1] for t in texts],
                tables=generate_vec_tables(tables),
                doc_metadata=metadata, doc_title=title,
                use_core_indexing=self.use_core_indexing
            )

            # index the images - one per document
        image_success = []
        for inx, image in enumerate(images):
            image_summary = image[0]
            image_metadata = image[1]
            image_metadata.update(metadata)
            image_metadata['url'] = uri
            if ex_metadata:
                image_metadata.update(ex_metadata)
            doc_id = slugify(uri) + "_image_" + str(inx)
            try:
                img_okay = self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=[image_metadata],
                                               doc_metadata=image_metadata, doc_title=title, use_core_indexing=True)
                image_success.append(img_okay)
            except Exception as e:
                self.logger.info(f"Failed to index image {metadata.get('src', 'no image name')} with error {e}")
                image_success.append(False)
        self.logger.info(f"Indexed {len(images)} images from {filename} with {sum(image_success)} successes")
        return succeeded

    def index_media_file(self, file_path, metadata=None):
        """
        Index a media file (audio or video) by transcribing it with Whisper and uploading it to the Vectara corpus.
        
        Args:
            file_path (str): Path to the media file.
            metadata (dict): Metadata for the document.

        Returns:
            bool: True if the upload was successful, False
        """
        logging.info(
            f"Transcribing file {file_path} with Whisper model of size {self.whisper_model} (this may take a while)")
        if self.whisper_model is None:
            self.whisper_model = whisper.load_model(self.whisper_model, device="cpu")
        result = self.whisper_model.transcribe(file_path, temperature=0, verbose=False)
        text = result['segments']
        doc = {
            'id': slugify(file_path),
            'title': file_path,
            'sections': [
                {
                    'text': t['text'],
                } for t in text
            ]
        }
        if metadata:
            doc['metadata'] = metadata
        self.index_document(doc)
