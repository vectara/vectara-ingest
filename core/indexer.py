import logging
import json
import html
import re
import os
from typing import Dict, Any, List, Optional
import uuid
import pandas as pd
import shutil
import warnings
import requests

import time
import unicodedata
from slugify import slugify

from omegaconf import OmegaConf
from nbconvert import HTMLExporter      # type: ignore
import nbformat
import markdown
import whisper

from html2markdown import convert

from core.summary import TableSummarizer, ImageSummarizer, get_attributes_from_text

from core.utils import (
    html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries, 
    mask_pii, safe_remove_file, url_to_filename
)
from core.extract import get_article_content
from core.doc_parser import UnstructuredDocumentParser, DoclingDocumentParser

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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
class Indexer(object):
    """
    Vectara API class.
    Args:
        endpoint (str): Endpoint for the Vectara API.
        customer_id (str): ID of the Vectara customer.
        corpus_id (int): ID of the Vectara corpus to index to.
        api_key (str): API key for the Vectara API.
    """
    def __init__(self, cfg: OmegaConf, endpoint: str, 
                 customer_id: str, corpus_id: int, corpus_key: str, api_key: str) -> None:
        self.cfg = cfg
        self.browser_use_limit = 100
        self.endpoint = endpoint
        self.customer_id = customer_id
        self.corpus_id = corpus_id
        self.corpus_key = corpus_key
        self.api_key = api_key
        self.reindex = cfg.vectara.get("reindex", False)
        self.verbose = cfg.vectara.get("verbose", False)
        self.store_docs = cfg.vectara.get("store_docs", False)
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.post_load_timeout = cfg.vectara.get("post_load_timeout", 5)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'
        self.logger = logging.getLogger()
        self.model = None
        self.whisper_model = cfg.vectara.get("whisper_model", "base")

        if 'doc_processing' not in cfg:
            cfg.doc_processing = {}
        self.summarize_tables = cfg.doc_processing.get("summarize_tables", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.use_core_indexing = cfg.doc_processing.get("use_core_indexing", False)
        self.unstructured_config = cfg.doc_processing.get("unstructured_config", 
                                                          {'chunking_strategy': 'none', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", {'chunk': False})
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        if cfg.vectara.get("openai_api_key", None) is None:
            if self.summarize_tables or self.summarize_images:
                self.logger.info("OpenAI API key not found, disabling table/image summarization")
            self.summarize_tables = False
            self.summarize_images = False
            self.extract_metadata = []

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
        Fetch content from a URL with a timeout.
        Args:
            url (str): URL to fetch.
            extract_tables (bool): Whether to extract tables from the page.
            extract_images (bool): Whether to extract images from the page.
            remove_code (bool): Whether to remove code from the HTML content.
            debug (bool): Whether to enable playwright debug logging.
        Returns:
            dict with
            - 'text': text extracted from the page
            - 'html': html of the page
            - 'title': title of the page
            - 'url': final URL of the page (if redirected)
            - 'links': list of links in the page
            - 'images': list of dictionaries with image info: [{'src': ..., 'alt': ...}, ...]
            - 'tables': list of strings representing the outerHTML of each table
        '''
        page = context = None
        text = ''
        html = ''
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

            title = page.title()
            html = page.content()

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

                {'// Remove code elements' if remove_code else ''}
                {'''
                const codeElements = document.querySelectorAll('code, pre');
                codeElements.forEach(el => {
                    content = content.replace(el.innerText, '');
                });
                ''' if remove_code else ''}

                content = content.replace(/\s{2,}/g, ' ').trim();
                return content;
            }}""")

            # Extract links
            links_script = """Array.from(document.querySelectorAll('a')).map(a => a.href)"""
            links = page.evaluate(links_script)

            # Extract tables
            if extract_tables:
                tables_script = """Array.from(document.querySelectorAll('table')).map(t => t.outerHTML)"""
                tables = page.evaluate(tables_script)

            # Extract images
            if extract_images:
                images_script = """
                Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || ''
                }))
                """
                images = page.evaluate(images_script)

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
            'html': html,
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
        body = {'customer_id': self.customer_id, 'corpus_id': self.corpus_id, 'document_id': doc_id}
        post_headers = { 
            'x-api-key': self.api_key, 
            'customer-id': str(self.customer_id), 
            'X-Source': self.x_source
        }
        response = self.session.post(
            f"https://{self.endpoint}/v1/delete-doc", data=json.dumps(body),
            verify=True, headers=post_headers)
        
        if response.status_code != 200:
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
            body = {"corpusId": self.corpus_id, "numResults": 1000}
            if page_key:  # Add page_key to the request if it's not None
                body["pageKey"] = page_key

            post_headers = { 
                'x-api-key': self.api_key, 
                'customer-id': str(self.customer_id), 
                'X-Source': self.x_source
            }
            response = self.session.post(
                f"https://{self.endpoint}/v1/list-documents", data=json.dumps(body),
                verify=True, headers=post_headers)
            if response.status_code != 200:
                self.logger.error(f"Error listing documents with status code {response.status_code}")
                return []
            res = response.json()

            # Extract URLs from documents
            for doc in res['document']:
                url = next((md['value'] for md in doc['metadata'] if md['name'] == 'url'), None)
                docs.append({'doc_id': doc['id'], 'url': url})

            # Check if we need to go further
            page_key = res.get('nextPageKey', None)    
            if not page_key:  # Break the loop if there's no next page
                break
    
        return docs

    def _index_file_v1(self, filename: str, uri: str, metadata: Dict[str, Any]) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus, using APIv1.
        Args:
            filename (str): Name of the file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if not os.path.exists(filename):
            self.logger.error(f"File {filename} does not exist")
            return False

        def get_files(filename: str, metadata: dict):
            return  {
                "file": (uri, open(filename, 'rb')),
                "doc_metadata": (None, json.dumps(metadata)),
            }  

        post_headers = { 
            'x-api-key': self.api_key,
            'customer-id': str(self.customer_id),
            'X-Source': self.x_source
        }
        response = self.session.post(
            f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}&d=True",
            files=get_files(filename, metadata), verify=True, headers=post_headers
        )
        if response.status_code == 409:
            if self.reindex:
                doc_id = response.json()['details'].split('document id')[1].split("'")[1]
                self.delete_doc(doc_id)
                response = self.session.post(
                    f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}",
                    files=get_files(filename, metadata), verify=True, headers=post_headers
                )
                if response.status_code == 200:
                    self.logger.info(f"REST upload for {uri} successful (reindex)")
                    self.store_file(filename, url_to_filename(uri))
                    return True
                else:
                    self.logger.info(f"REST upload for {uri} ({filename}) (reindex) failed with code = {response.status_code}, text = {response.text}")
                    return True
            else:
                self.logger.info(f"REST upload for {uri} failed with code {response.status_code}")
            return False
        elif response.status_code != 200:
            self.logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        self.logger.info(f"REST upload for {uri} succeesful")
        self.store_file(filename, url_to_filename(uri))
        return True

    def _index_file_v2(self, filename: str, uri: str, metadata: Dict[str, Any]) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus, using APIv2
        Args:
            filename (str): Name of the file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
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
        url = f"https://api.vectara.io/v2/corpora/{self.corpus_key}/upload_file"
        files = {
            'file': (filename.split('/')[-1], open(filename, 'rb')),
            'metadata': (None, json.dumps(metadata), 'application/json'),
        }
        if self.summarize_tables:
           files['table_extraction_config'] = (None, json.dumps({'extract_tables': True}), 'application/json')
        response = self.session.request("POST", url, headers=post_headers, files=files)

        if response.status_code == 400:
            error_msg = json.loads(html.unescape(response.text))
            if error_msg['httpCode'] == 409:
                if self.reindex:
                    match = re.search(r"document id '([^']+)'", error_msg['details'])
                    if match:
                        doc_id = match.group(1)
                    else:
                        self.logger.error(f"Failed to extract document id from error message: {error_msg}")
                        return False
                    self.delete_doc(doc_id)
                    self.logger.info(f"DEBUG 1, Reindexing, document {doc_id}, url={url}, post_headers={post_headers}")                    
                    response = self.session.request("POST", url, headers=post_headers, files=files)
                    self.logger.info(f"DEBUG 2, response code={response.status_code}")
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
            else:
                self.logger.info(f"REST upload for {uri} failed with code {response.status_code}")
                return False
            return False
        elif response.status_code != 201:
            self.logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        self.logger.info(f"REST upload for {uri} succeesful")
        self.store_file(filename, url_to_filename(uri))
        return True

    def _index_document(self, document: Dict[str, Any], use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the document dictionary

        Args:
            document (dict): Document to index.
            use_core_indexing (bool): Whether to use the core indexing API.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if use_core_indexing:
            api_endpoint = f"https://{self.endpoint}/v1/core/index"
        else:
            api_endpoint = f"https://{self.endpoint}/v1/index"

        request = {
            'customer_id': self.customer_id,
            'corpus_id': self.corpus_id,
            'document': document,
        }

        post_headers = { 
            'x-api-key': self.api_key,
            'customer-id': str(self.customer_id),
            'X-Source': self.x_source
        }
        try:
            data = json.dumps(request)
        except Exception as e:
            self.logger.info(f"Can't serialize request {request} (error {e}), skipping")   
            return False

        try:
            response = self.session.post(api_endpoint, data=data, verify=True, headers=post_headers)
        except Exception as e:
            self.logger.info(f"Exception {e} while indexing document {document['documentId']}")
            return False

        if response.status_code != 200:
            self.logger.error("REST upload failed with code %d, reason %s, text %s",
                          response.status_code,
                          response.reason,
                          response.text)
            return False

        result = response.json()
        if "status" in result and result["status"] and \
           ("ALREADY_EXISTS" in result["status"]["code"] or \
            ("CONFLICT" in result["status"]["code"] and "Indexing doesn't support updating documents" in result["status"]["statusDetail"])):
            if self.reindex:
                self.logger.info(f"Document {document['documentId']} already exists, re-indexing")
                self.delete_doc(document['documentId'])
                response = self.session.post(api_endpoint, data=json.dumps(request), verify=True, headers=post_headers)
                return True
            else:
                self.logger.info(f"Document {document['documentId']} already exists, skipping")
                return False
        if "status" in result and result["status"] and "OK" in result["status"]["code"]:
            if self.store_docs:
                with open(f"{self.store_docs_folder}/{document['documentId']}.json", "w") as f:
                    json.dump(document, f)
            return True
        
        self.logger.info(f"Indexing document {document['documentId']} failed, response = {result}")
        return False
    
    def index_url(self, url: str, metadata: Dict[str, Any], html_processing: dict = {}) -> bool:
        """
        Index a url by rendering it with scrapy-playwright, extracting paragraphs, then uploading to the Vectara corpus.
        
        Args:
            url (str): URL for where the document originated. 
            metadata (dict): Metadata for the document.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        st = time.time()
        url = url.split("#")[0]     # remove fragment, if exists

        # if file is going to download, then handle it as local file
        if self.url_triggers_download(url):
            file_path = "/tmp/" + slugify(url)
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

        # If MD, RST of IPYNB file, then we don't need playwright - can just download content directly and convert to text
        if url.lower().endswith(".md") or url.lower().endswith(".ipynb"):
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            dl_content = response.content.decode('utf-8')
            if url.lower().endswith('md'):
                html_content = markdown.markdown(dl_content)
            elif url.lower().endswith('ipynb'):
                nb = nbformat.reads(dl_content, nbformat.NO_CONVERT)    # type: ignore
                exporter = HTMLExporter()
                html_content, _ = exporter.from_notebook_node(nb)
            doc_title = url.split('/')[-1]      # no title in these files, so using file name
            text = html_to_text(html_content, self.remove_code)
            parts = [text]

        else:
            try:
                # Use Playwright to get the page content
                openai_api_key = self.cfg.vectara.get("openai_api_key", None)
                res = self.fetch_page_contents(
                    url, 
                    self.remove_code,
                    self.summarize_tables,
                    self.summarize_images,
                )
                html = res['html']
                text = res['text']
                doc_title = res['title']
                if text is None or len(text)<3:
                    return False

                # Detect language if needed
                if self.detected_language is None:
                    self.detected_language = detect_language(text)
                    self.logger.info(f"The detected language is {self.detected_language}")

                if len(self.extract_metadata)>0:
                    ex_metadata = get_attributes_from_text(
                        text,
                        metadata_questions=self.extract_metadata,
                        openai_api_key=openai_api_key
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

                if self.summarize_tables:
                    table_summarizer = TableSummarizer(openai_api_key=openai_api_key)
                    for table in res['tables']:
                        table_md = convert(table)
                        table_summary = table_summarizer.summarize_table_text(table_md)
                        if table_summary:
                            parts.append(table_summary)
                            metadatas.append({'element_type': 'table'}) 
                            if self.verbose:
                                self.logger.info(f"Table summary: {table_summary}")

                # index text and tables
                doc_id = slugify(url)
                succeeded = self.index_segments(doc_id=doc_id, texts=parts, metadatas=metadatas,
                                                doc_metadata=metadata, doc_title=doc_title)

                # index images - each image as a separate "document" in Vectara
                if self.summarize_images:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    image_summarizer = ImageSummarizer(openai_api_key=openai_api_key)
                    image_filename = 'image.png'
                    for inx,image in enumerate(res['images']):
                        image_url = image['src']
                        response = requests.get(image_url, headers=headers, stream=True)
                        if response.status_code != 200:
                            logging.info(f"Failed to retrieve image {image_url} from {url}, skipping")
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
                       doc_metadata: Dict[str, Any] = {}, doc_title: str = "", use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.

        Args:
            doc_id (str): ID of the document.
            texts (List[str]): List of segments (parts) of the document.
            titles (List[str]): List of titles for each segment.
            metadatas (List[dict]): List of metadata for each segment.
            doc_metadata (dict): Metadata for the document.
            doc_title (str): Title of the document.
            use_core_indexing (bool): Whether to use the core indexing API.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if titles is None:
            titles = ["" for _ in range(len(texts))]
        if metadatas is None:
            metadatas = [{} for _ in range(len(texts))]
        else:
            metadatas = [{k:self.normalize_value(v) for k,v in md.items()} for md in metadatas]

        document = {}
        document["documentId"] = doc_id
        if not use_core_indexing:
            if doc_title is not None and len(doc_title)>0:
                document["title"] = self.normalize_text(doc_title)
            document["section"] = [
                {"text": self.normalize_text(text), "title": self.normalize_text(title), "metadataJson": json.dumps(md)} 
                for text,title,md in zip(texts,titles,metadatas)
            ]
        else:
            if any([len(text)>16384 for text in texts]):
                self.logger.info(f"Document {doc_id} too large for Vectara core indexing, skipping")
                return False
            document["parts"] = [
                {"text": self.normalize_text(text), "metadataJson": json.dumps(md)} 
                for text,md in zip(texts,metadatas)
            ]

        if doc_metadata:
            document["metadataJson"] = json.dumps(doc_metadata)

        if self.verbose:
            self.logger.info(f"Indexing document {doc_id} with {document}")

        return self.index_document(document, use_core_indexing)

    def index_document(self, document: Dict[str, Any], use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus).
        Document is a dictionary that includes documentId, title, optionally metadataJson, and section (which is a list of segments).

        Args:
            document (dict): Document to index.
            use_core_indexing (bool): Whether to use the core indexing API.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        return self._index_document(document, use_core_indexing)

    def index_file(self, filename: str, uri: str, metadata: Dict[str, Any]) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus.
        
        Args:
            filename (str): Name of the PDF file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
        
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if not os.path.exists(filename):
            self.logger.error(f"File {filename} does not exist")
            return False
        
        # If we have a PDF file with size>50MB, or we want to use the summarize_tables option, then we parse locally and index
        # Otherwise - send to Vectara's default upload file mechanism
        openai_api_key = self.cfg.vectara.get("openai_api_key", None)
        size_limit = 50
        large_file_extensions = ['.pdf', '.html', '.htm', '.pptx', '.docx']
        if (any(uri.endswith(extension) for extension in large_file_extensions) and
           (get_file_size_in_MB(filename) >= size_limit or (self.summarize_tables and self.corpus_key is None))):            
            self.logger.info(f"Parsing file {filename}")
            if self.doc_parser == "docling":
                dp = DoclingDocumentParser(
                    verbose=self.verbose,
                    openai_api_key=openai_api_key,
                    chunk=self.docling_config['chunk'], 
                    summarize_tables=self.summarize_tables, 
                    summarize_images=self.summarize_images
                )
            else:
                dp = UnstructuredDocumentParser(
                    verbose=self.verbose,
                    openai_api_key=openai_api_key,
                    chunking_strategy=self.unstructured_config['chunking_strategy'],
                    chunk_size=self.unstructured_config['chunk_size'],
                    summarize_tables=self.summarize_tables, 
                    summarize_images=self.summarize_images, 
                )
            title, texts, metadatas, image_summaries = dp.parse(filename, uri)
            if len(self.extract_metadata)>0:
                all_text = "\n".join(texts)[:32768]
                ex_metadata = get_attributes_from_text(
                    all_text,
                    metadata_questions=self.extract_metadata,
                    openai_api_key=openai_api_key
                )
                metadata.update(ex_metadata)
            else:
                ex_metadata = {}

            # index the main document (text and tables)
            succeeded = self.index_segments(
                doc_id=slugify(uri), texts=texts, metadatas=metadatas,
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

            if self.summarize_tables or self.summarize_images:
                self.logger.info(f"For file {filename}, extracted text locally since summarize_tables/images is activated")
            else:
                self.logger.info(f"For file {filename}, extracted text locally since file size is larger than {size_limit}MB")
            return succeeded
        else:
            # Parse file content to extract images and get text content
            self.logger.info(f"Reading contents of {filename} (url={uri})")
            dp = UnstructuredDocumentParser(
                verbose=self.verbose,
                openai_api_key=openai_api_key,
                summarize_tables=False,
                summarize_images=self.summarize_images,
            )
            title, texts, metadatas, image_summaries = dp.parse(filename, uri)

            # Get metadata from text content
            if len(self.extract_metadata)>0:
                all_text = "\n".join(texts)[:32768]
                ex_metadata = get_attributes_from_text(
                    all_text,
                    metadata_questions=self.extract_metadata,
                    openai_api_key=openai_api_key
                )
                metadata.update(ex_metadata)
            else:
                ex_metadata = {}
            metadata.update(ex_metadata)

            # index the file within Vectara (use FILE UPLOAD API)
            if self.corpus_key is None:
                succeeded = self._index_file_v1(filename, uri, metadata)
                self.logger.info(f"For {uri} - uploaded via Vectara file upload API v1")
            else:
                succeeded = self._index_file_v2(filename, uri, metadata)
                self.logger.info(f"For {uri} - uploaded via Vectara file upload API v2")
            
            # If needs to summarize images - then do it locally
            if self.summarize_images and openai_api_key:
                self.logger.info(f"Parsing images from {uri}")
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
        if self.model is None:
            self.model = whisper.load_model(self.whisper_model, device="cpu")
        result = self.model.transcribe(file_path, temperature=0, verbose=False)
        text = result['segments']
        doc = {
            'documentId': slugify(file_path),
            'title': file_path,
            'section': [
                { 
                    'text': t['text'],
                } for t in text
            ]
        }
        if metadata:
            doc['metadataJson'] = json.dumps(metadata)
        self.index_document(doc)



