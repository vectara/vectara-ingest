import logging
import json
import re
import os
import time
import warnings
import unicodedata
from typing import Dict, Any, List, Optional
import shutil
from datetime import datetime

import uuid
import pandas as pd
import requests

from slugify import slugify

from omegaconf import OmegaConf
from nbconvert import HTMLExporter      # type: ignore
import nbformat
import markdown
import whisper

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from core.summary import TableSummarizer, ImageSummarizer, get_attributes_from_text
from core.utils import (
    html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries,
    mask_pii, safe_remove_file, url_to_filename, df_cols_to_headers, html_table_to_header_and_rows,
    get_file_path_from_url, create_row_items
)
from core.extract import get_article_content
from core.doc_parser import UnstructuredDocumentParser, DoclingDocumentParser, LlamaParseDocumentParser
from core.contextual import ContextualChunker

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

def extract_last_modified_from_html(html: str) -> Optional[str]:
    """
    Extract the last modified date from HTML meta tags.
    Looks for meta tags with property "article:modified_time" or name "last-modified".
    
    Args:
        html (str): HTML content of the page.
        
    Returns:
        Optional[str]: The extracted date string or None if not found.
    """
    # Define regex patterns to match meta tags
    pattern = re.compile(
        r'<meta\s+(?=[^>]*(?:property|name)\s*=\s*["\'](?:article:modified_time|last-modified)["\'])'
        r'[^>]*content\s*=\s*["\']([^"\']+)["\']',
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(html)
    return match.group(1) if match else None

class Indexer:
    """
    Vectara API class.
    Args:
        endpoint (str): Endpoint for the Vectara API.
        corpus_key (str): Key of the Vectara corpus to index to.
        api_key (str): API key for the Vectara API.
    """
    def __init__(self, cfg: OmegaConf, endpoint: str,
                 corpus_key: str, api_key: str) -> None:
        self.cfg = cfg
        self.browser_use_limit = 100
        self.endpoint = endpoint
        self.corpus_key = corpus_key
        self.api_key = api_key
        self.reindex = cfg.vectara.get("reindex", False)
        self.create_corpus = cfg.vectara.get("create_corpus", False)
        self.verbose = cfg.vectara.get("verbose", False)
        self.store_docs = cfg.vectara.get("store_docs", False)
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.post_load_timeout = cfg.vectara.get("post_load_timeout", 5)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'
        self.logger = logging.getLogger()
        self.whisper_model = None
        self.whisper_model_name = cfg.vectara.get("whisper_model", "base")

        if 'doc_processing' not in cfg:
            cfg.doc_processing = {}
        self.parse_tables = cfg.doc_processing.get("parse_tables", cfg.doc_processing.get("summarize_tables", False)) # backward compatibility
        self.enable_gmft = cfg.doc_processing.get("enable_gmft", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.process_locally = cfg.doc_processing.get("process_locally", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.use_core_indexing = cfg.doc_processing.get("use_core_indexing", False)
        self.unstructured_config = cfg.doc_processing.get("unstructured_config",
                                                          {'chunking_strategy': 'by_title', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", {'chunking_strategy': 'none'})
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        self.contextual_chunking = cfg.doc_processing.get("contextual_chunking", False)

        self.model_name = self.cfg.doc_processing.get("model_name", "openai")
        self.model_api_key = self.cfg.vectara.get("openai_api_key", None) if self.model_name=='openai' else \
            self.cfg.vectara.get("anthropic_api_key", None)

        if self.model_api_key is None:
            if self.parse_tables or self.summarize_images:
                self.logger.info(f"Model ({self.model_name}) API key not found, disabling table/image summarization")
            self.parse_tables = False
            self.summarize_images = False
            self.extract_metadata = []
            self.contextual_chunking = False

        self.setup()

    def normalize_text(self, text: str) -> str:
        if pd.isnull(text) or len(text)==0:
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
        # Create playwright browser so we can reuse it across all Indexer operations
        if use_playwright:
            self.p = sync_playwright().start()
            self.browser = self.p.firefox.launch(headless=True)
            self.browser_use_count = 0
        if self.store_docs:
            self.store_docs_folder = '/home/vectara/env/indexed_docs_' + str(uuid.uuid4())
            if os.path.exists(self.store_docs_folder):
                shutil.rmtree(self.store_docs_folder)
            os.makedirs(self.store_docs_folder)

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
            debug: bool = False
        ) -> dict:
        '''
        Fetch content from a URL with a timeout, including content from the Shadow DOM.
        Args:
            url (str): URL to fetch.
            extract_tables (bool): Whether to extract tables from the page.
            extract_images (bool): Whether to extract images from the page.
            remove_code (bool): Whether to remove code from the HTML content.
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

            page.goto(url, timeout=self.timeout*1000, wait_until="domcontentloaded")
            page.wait_for_timeout(self.post_load_timeout*1000)  # Wait additional time to handle AJAX
            self._scroll_to_bottom(page)
            html_content = page.content()

            title = page.title()
            out_url = page.url

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
            f"https://{self.endpoint}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            verify=True, headers=post_headers)
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
            f"https://{self.endpoint}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            verify=True, headers=post_headers)

        if response.status_code != 204:
            self.logger.error(f"Delete request failed for doc_id = {doc_id} with status code {response.status_code}, reason {response.reason}, text {response.text}")
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
                f"https://{self.endpoint}/v2/corpora/{self.corpus_key}/documents",
                verify=True, headers=post_headers, params=params)
            if response.status_code != 200:
                self.logger.error(f"Error listing documents with status code {response.status_code}")
                return []
            res = response.json()

            # Extract URLs from documents
            for doc in res['documents']:
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

        post_headers = {
            'Accept': 'application/json',
            'x-api-key': self.api_key,
        }
        url = f"https://{self.endpoint}/v2/corpora/{self.corpus_key}/upload_file"

        upload_filename = id if id is not None else filename.split('/')[-1]

        files = {
            'file': (upload_filename, open(filename, 'rb')),
            'metadata': (None, json.dumps(metadata), 'application/json'),
        }
        if self.parse_tables and filename.lower().endswith('.pdf'):
           files['table_extraction_config'] = (None, json.dumps({'extract_tables': True}), 'application/json')
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
                response = self.session.request("POST", url, headers=post_headers, files=files)
                if response.status_code == 201:
                    self.logger.info(f"REST upload for {uri} successful (reindex)")
                    self.store_file(filename, url_to_filename(uri))
                    return True
                else:
                    self.logger.info(f"REST upload for {uri} ({doc_id}) (reindex) failed with code = {response.status_code}, text = {response.text}")
                    return True
            else:
                self.logger.info(f"document {uri} already indexed, skipping")
                return False
        elif response.status_code != 201:
            self.logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        self.logger.info(f"REST upload for {uri} successful")
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
        api_endpoint = f"https://{self.endpoint}/v2/corpora/{self.corpus_key}/documents"
        doc_exists = self._does_doc_exist(document['id'])
        if doc_exists:
            if self.reindex:
                self.logger.info(f"Document {document['id']} already exists, deleting then reindexing")
                self.delete_doc(document['id'])
            else:
                self.logger.info(f"Document {document['id']} already exists, skipping")
                return False

        if use_core_indexing:
            document['type'] = 'core'
        else:
            document['type'] = 'structured'

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
            response = self.session.post(api_endpoint, data=data, verify=True, headers=post_headers)
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
        url = url.split("#")[0]     # remove fragment, if exists

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
            doc_title = url.split('/')[-1]      # no title in these files, so using file name
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
                )
                html = res['html']
                text = res['text']
                doc_title = res['title']
                if text is None or len(text)<3:
                    return False

                # Extract the last modified date from the HTML content.
                last_modified = extract_last_modified_from_html(html)
                if not last_modified:
                    # If not found in HTML, try using an HTTP HEAD request.
                    response = self.session.head(url, headers=get_headers)
                    last_modified = response.headers.get("Last-Modified")

                if last_modified:
                    try:
                        # Attempt to parse the date if it follows a common HTTP format.
                        # Example format: "Wed, 21 Oct 2015 07:28:00 GMT"
                        last_modified_dt = datetime.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z")
                        metadata["last_updated"] = last_modified_dt.strftime("%Y-%m-%d")
                    except ValueError:
                        # If parsing fails, store the raw value.
                        metadata["last_updated"] = last_modified
                else:
                    self.logger.info(f"Last modified date not found for {url}")

                # Detect language if needed
                if self.detected_language is None:
                    self.detected_language = detect_language(text)
                    self.logger.info(f"The detected language is {self.detected_language}")

                if len(self.extract_metadata)>0:
                    ex_metadata = get_attributes_from_text(
                        text,
                        metadata_questions=self.extract_metadata,
                        model_name=self.model_name,
                        model_api_key=self.model_api_key
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
                        self.logger.info(f"Removing boilerplate from content of {url}, and extracting important text only")
                    text, doc_title = get_article_content(html, url, self.detected_language, self.remove_code)
                else:
                    text = html_to_text(html, self.remove_code, html_processing)

                parts = [text]
                metadatas = [{'element_type': 'text'}]

                vec_tables = []
                if self.parse_tables:
                    table_summarizer = TableSummarizer(model_name=self.model_name, model_api_key=self.model_api_key)
                    for table in res['tables']:
                        table_summary = table_summarizer.summarize_table_text(table)
                        if table_summary:
                            if self.verbose:
                                self.logger.info(f"Table summary: {table_summary}")
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
                    image_summarizer = ImageSummarizer(model_name=self.model_name, model_api_key=self.model_api_key)
                    image_filename = 'image.png'
                    for inx,image in enumerate(res['images']):
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
                            metadata = {'element_type': 'image'}
                            if ex_metadata:
                                metadata.update(ex_metadata)
                            if self.verbose:
                                self.logger.info(f"Image summary: {image_summary}")
                            doc_id = slugify(url) + "_image_" + str(inx)
                            succeeded = self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=metadatas,
                                                            doc_metadata=metadata, doc_title=doc_title)
                        else:
                            self.logger.info(f"Failed to retrieve image {image['src']}")
                            continue

                self.logger.info(f"retrieving content took {time.time()-st:.2f} seconds")
            except Exception as e:
                import traceback
                self.logger.info(f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
                return False
        
        return succeeded

    def index_segments(self, doc_id: str, texts: List[str], titles: Optional[List[str]] = None, metadatas: Optional[List[Dict[str, Any]]] = None,
                       doc_metadata: Dict[str, Any] = None, doc_title: str = "", 
                       tables: Optional[List[Dict[str, Any]]] = None,
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
        if titles is None:
            titles = ["" for _ in range(len(texts))]
        if doc_metadata is None:
            doc_metadata = {}
        if metadatas is None:
            metadatas = [{} for _ in range(len(texts))]
        else:
            metadatas = [{k:self.normalize_value(v) for k,v in md.items()} for md in metadatas]

        document = {}
        document["id"] = doc_id

        # Create tables structure
        tables_array = []
        if tables:
            for inx,table in enumerate(tables):
                table_dict = {
                    'id': 'table_' + str(inx),
                    'title': table.get('title', ''),
                    'data': {
                        'headers': [
                            create_row_items(h) for h in table['headers']
                        ],
                        'rows': [
                            create_row_items(row) for row in table['rows']
                        ]
                    },
                    'description': table['summary']
                }
                tables_array.append(table_dict)

        if not use_core_indexing:
            if doc_title is not None and len(doc_title)>0:
                document["title"] = self.normalize_text(doc_title)
            document["sections"] = [
                {"text": self.normalize_text(text), "title": self.normalize_text(title), "metadata": md} 
                for text,title,md in zip(texts,titles,metadatas)
            ]
            if tables:
                document["sections"].append(
                    {"text": '', "title": '', "metadata": {}, "tables": tables_array}
                )
        else:
            if any((len(text)>16384 for text in texts)):
                self.logger.info(f"Document {doc_id} too large for Vectara core indexing, skipping")
                return False
            document["document_parts"] = [
                {"text": self.normalize_text(text), "metadata": md} 
                for text,md in zip(texts,metadatas)
            ]
            if tables:
                document["tables"] = tables_array

        if doc_metadata:
            document["metadata"] = doc_metadata

        if self.verbose:
            self.logger.info(f"Indexing document {doc_id} with {document}")

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
        size_limit = 50
        max_chars = 128000   # all_text is limited to 128,000 characters
        large_file_extensions = ['.pdf', '.html', '.htm', '.pptx', '.docx']
        
        if (any(uri.endswith(extension) for extension in large_file_extensions) and
            (get_file_size_in_MB(filename) >= size_limit or self.contextual_chunking or
             self.summarize_images or self.enable_gmft)
        ):
            self.process_locally = True

        #
        # Case A: using the file-upload API
        # Used when we don't need to process the file locally, and we don't need to parse tables from non-PDF files
        #
        if not self.process_locally and ((self.parse_tables and filename.lower().endswith('.pdf')) or not self.parse_tables):
            self.logger.info(f"For {uri} - Uploading via Vectara file upload API")
            if len(self.extract_metadata)>0 or self.summarize_images:
                self.logger.info(f"Reading contents of {filename} (url={uri})")
                dp = DoclingDocumentParser(
                    verbose=self.verbose,
                    model_name=self.model_name, model_api_key=self.model_api_key,
                    parse_tables=False,
                    enable_gmft=False,
                    summarize_images=self.summarize_images,
                )
                title, texts, metadatas, _, image_summaries = dp.parse(filename, uri)

            # Get metadata attribute values from text content (if defined)
            if len(self.extract_metadata)>0:
                all_text = "\n".join(texts)[:max_chars]
                ex_metadata = get_attributes_from_text(
                    all_text,
                    metadata_questions=self.extract_metadata,
                    model_name=self.model_name, model_api_key=self.model_api_key,
                )
                metadata.update(ex_metadata)
            else:
                ex_metadata = {}
            metadata.update(ex_metadata)

            # index the file within Vectara (use FILE UPLOAD API)
            succeeded = self._index_file(filename, uri, metadata, id)
            
            # If indicated, summarize images - and upload each image summary as a single doc
            if self.summarize_images and image_summaries:
                self.logger.info(f"Extracted {len(image_summaries)} images from {uri}")
                for inx,image_summary in enumerate(image_summaries):
                    if image_summary:
                        metadata = {'element_type': 'image'}
                        if ex_metadata:
                            metadata.update(ex_metadata)
                        doc_id = slugify(uri) + "_image_" + str(inx)
                        succeeded &= self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=metadatas,
                                                            doc_metadata=metadata, doc_title=title)
            return succeeded

        #
        # Case B: Process locally and upload to Vectara
        #
        self.logger.info(f"Parsing file {filename} locally")
        if self.contextual_chunking:
            self.logger.info(f"Applying contextual chunking for {filename}")
            dp = DoclingDocumentParser(
                verbose=self.verbose,
                model_name=self.model_name, model_api_key=self.model_api_key,
                chunking_strategy='hybrid',
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images
            )
        elif self.doc_parser == "llama_parse" or self.doc_parser == "llama" or self.doc_parser == "llama-parse":
            dp = LlamaParseDocumentParser(
                verbose=self.verbose,
                model_name=self.model_name, model_api_key=self.model_api_key,
                llama_parse_api_key=self.cfg.get("llama_cloud_api_key", None),
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images
            )
        elif self.doc_parser == "docling":
            dp = DoclingDocumentParser(
                verbose=self.verbose,
                model_name=self.model_name, model_api_key=self.model_api_key,
                chunking_strategy=self.docling_config.get('chunking_stragety', 'none'), 
                parse_tables=self.parse_tables,
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images
            )
        else:
            dp = UnstructuredDocumentParser(
                verbose=self.verbose,
                model_name=self.model_name, model_api_key=self.model_api_key,
                chunking_strategy=self.unstructured_config['chunking_strategy'],
                chunk_size=self.unstructured_config['chunk_size'],
                parse_tables=self.parse_tables, 
                enable_gmft=self.enable_gmft,
                summarize_images=self.summarize_images, 
            )

        try:
            title, texts, metadatas, tables, image_summaries = dp.parse(filename, uri)
        except Exception as e:
            self.logger.info(f"Failed to parse {filename} with error {e}")
            return False

        # docling has a bug with some HTML files where it doesn't extract text properly
        # in this case, we just extract the text directly from file, and do simple chunking.
        if self.doc_parser == "docling" and len(texts)==0 and (len(tables)>0 or len(image_summaries)>0):
            with open(filename, 'r') as f:
                html_content = f.read()
                text = html_to_text(html_content, remove_code=self.remove_code)
                chunk_size = 1024
                texts = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
            
        # Get metadata attribute values from text content (if defined)
        if len(self.extract_metadata)>0:
            all_text = "\n".join(texts)[:max_chars]
            ex_metadata = get_attributes_from_text(
                all_text,
                metadata_questions=self.extract_metadata,
                model_name=self.model_name, model_api_key=self.model_api_key,
            )
            metadata.update(ex_metadata)
        else:
            ex_metadata = {}

        # prepare tables
        vec_tables = []
        for [df, summary, table_title] in tables:
            cols = df_cols_to_headers(df)
            rows = df.fillna('').to_numpy().tolist()
            if len(rows)>0 and len(cols)>0:
                vec_tables.append({'headers': cols, 'rows': rows, 'summary': summary, 'title': table_title})

        # Index text portions
        # Apply contextual chunking if indicated, otherwise just the text directly.
        if self.contextual_chunking:
            all_text = "\n".join(texts)[:max_chars]
            cc = ContextualChunker(model_name=self.model_name, model_api_key=self.model_api_key, whole_document=all_text)
            texts = cc.parallel_transform(texts)
            succeeded = self.index_segments(
                doc_id=slugify(uri), texts=texts, metadatas=metadatas, tables=vec_tables,
                doc_metadata=metadata, doc_title=title,
                use_core_indexing=True
            )
        else:
            self.logger.info(f"DEBUG - extracted {len(texts)} text segments from {filename}, and {len(vec_tables)} tables")
            succeeded = self.index_segments(
                doc_id=slugify(uri), texts=texts, metadatas=metadatas, tables=vec_tables,
                doc_metadata=metadata, doc_title=title,
                use_core_indexing=self.use_core_indexing
            )            

        # index the images - one per document
        for inx,image_summary in enumerate(image_summaries):
            if image_summary:
                metadata = {'element_type': 'image'}
                if ex_metadata:
                    metadata.update(ex_metadata)
                doc_id = slugify(uri) + "_image_" + str(inx)
                succeeded &= self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=metadatas,
                                                 doc_metadata=metadata, doc_title=title)

        self.logger.info(f"For file {filename}, extracted text locally")
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
        logging.info(f"Transcribing file {file_path} with Whisper model of size {self.whisper_model} (this may take a while)")
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



