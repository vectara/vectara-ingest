import logging
import json
import os
from typing import Tuple, Dict, Any, List, Optional
import uuid
import pandas as pd

import time
from slugify import slugify
import unicodedata

from omegaconf import OmegaConf
from nbconvert import HTMLExporter      # type: ignore
import nbformat
import markdown

from core.utils import html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries, TableSummarizer, mask_pii, safe_remove_file
from core.extract import get_article_content

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

get_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

def _parse_local_file(filename: str, uri: str, summarize_tables: bool = False, openai_api_key: str = None) -> Tuple[str, List[str]]:
    import unstructured as us
    from unstructured.partition.pdf import partition_pdf
    from unstructured.partition.html import partition_html

    logger = logging.getLogger()
    st = time.time()
    if uri.endswith('.pdf'):
        if summarize_tables and openai_api_key is not None:
                elements = partition_pdf(filename=filename, infer_table_structure=True, extract_images_in_pdf=False,
                                        strategy='hi_res', hi_res_model_name='yolox')  # use 'detectron2_onnx' for a faster model
        else:
            elements = partition_pdf(filename, strategy='fast')
    elif uri.endswith('.html') or uri.endswith('.htm'):
        elements = partition_html(filename=filename)
    else:
        logger.info(f"data from {uri} is not HTML or PDF")
        return '', []

    titles = [str(x) for x in elements if type(x) in [us.documents.elements.Title, us.documents.html.HTMLTitle] and len(str(x))>10]
    title = titles[0] if len(titles)>0 else 'no title'

    # get texts (and tables summaries if applicable)
    summarizer = TableSummarizer(openai_api_key) if openai_api_key is not None and summarize_tables else None
    texts = []
    for t in elements:
        if ((type(t)==us.documents.elements.Table or type(t)==us.documents.html.HTMLTable) and 
            summarize_tables and openai_api_key is not None):
            texts.append(summarizer.summarize_table_text(str(t)))
        else:
            texts.append(str(t))
    logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")
    return title, texts

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
                 customer_id: str, corpus_id: int, api_key: str) -> None:
        self.cfg = cfg
        self.browser_use_limit = 100
        self.endpoint = endpoint
        self.customer_id = customer_id
        self.corpus_id = corpus_id
        self.api_key = api_key
        self.reindex = cfg.vectara.get("reindex", False)
        self.verbose = cfg.vectara.get("verbose", False)
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.post_load_timeout = cfg.vectara.get("post_load_timeout", 5)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'
        self.logger = logging.getLogger()

        self.summarize_tables = cfg.vectara.get("summarize_tables", False)
        if cfg.vectara.get("openai_api_key", None) is None:
            if self.summarize_tables:
                self.logger.info("OpenAI API key not found, disabling table summarization")
            self.summarize_tables = False

        self.setup()

    def normalize_text(self, text: str) -> str:
        if pd.isnull(text) or len(text)==0:
            return text
        if self.cfg.vectara.get("mask_pii", False):
            text = mask_pii(text)
        text = unicodedata.normalize('NFD', text)
        return text

    def setup(self, use_playwright: bool = True) -> None:
        self.session = create_session_with_retries()
        # Create playwright browser so we can reuse it across all Indexer operations
        if use_playwright:
            self.p = sync_playwright().start()
            self.browser = self.p.firefox.launch(headless=True)
            self.browser_use_count = 0
        self.tmp_file = 'tmp_' + str(uuid.uuid4())

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

    def fetch_page_contents(self, url: str, remove_code: bool = False, debug: bool = False) -> dict:
        '''
        Fetch content from a URL with a timeout.
        Args:
            url (str): URL to fetch.
            remove_code (bool): Whether to remove code from the HTML content.
            debug (bool): Whether to enable playwright debug logging.
        Returns:
            dict with
            - 'text': text extracted from the page
            - 'html': html of the page
            - 'url': final URL of the page (if redirect)
            - 'links': list of links in the page
        '''
        page = context = None
        text = ''
        html = ''
        title = ''
        links = []
        out_url = url
        try:
            context = self.browser.new_context()
            page = context.new_page()
            page.set_extra_http_headers(get_headers)
            page.route("**/*", lambda route: route.abort()  # do not load images as they are unnecessary for our purpose
                if route.request.resource_type == "image" 
                else route.continue_() 
            ) 
            if debug:
                page.on('console', lambda msg: self.logger.info(f"playwright debug: {msg.text})"))

            page.goto(url, timeout=self.timeout*1000, wait_until="domcontentloaded")
            page.wait_for_timeout(self.post_load_timeout*1000)  # Wait an additional time to handle AJAX or animations
            links_script = """Array.from(document.querySelectorAll('a')).map(a => a.href)"""
            links = page.evaluate(links_script)
            title = page.title()
            html = page.content()
            out_url = page.url
            text = page.evaluate(f"""() => {{
                // Extract main text content
                let content = document.body.innerText;
                
                // Remove common boilerplate elements
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
                codeElements.forEach(el => {{
                    content = content.replace(el.innerText, '');
                }});
                ''' if remove_code else ''}
                
                // Remove extra whitespace
                content = content.replace(/\\s+/g, ' ').trim();
                
                return content;
            }}""")

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
            'text': text, 'html': html, 'title': title,
            'url': out_url, 'links': links
        }

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

    def _index_file(self, filename: str, uri: str, metadata: Dict[str, Any]) -> bool:
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
                    return True
                else:
                    self.logger.info(f"REST upload for {uri} ({filename}) (reindex) failed with code = {response.status_code}, text = {response.text}")
                    return True
            return False
        elif response.status_code != 200:
            self.logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        self.logger.info(f"REST upload for {uri} succeesful")
        return True

    def _index_document(self, document: Dict[str, Any]) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the document dictionary
        """
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
            file_path = self.tmp_file
            response = self.session.get(url, headers=get_headers, stream=True)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192): 
                        f.write(chunk)
                self.logger.info(f"File downloaded successfully and saved as {file_path}")
                res =  self.index_file(file_path, url, metadata)
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
            extracted_title = url.split('/')[-1]      # no title in these files, so using file name
            text = html_to_text(html_content, self.remove_code)
            parts = [text]

        else:
            try:
                # Use Playwright to get the page content
                res = self.fetch_page_contents(url, self.remove_code)
                html = res['html']
                text = res['text']
                extracted_title = res['title']

                if text is None or len(text)<3:
                    return False

                # Detect language if needed
                if self.detected_language is None:
                    self.detected_language = detect_language(text)
                    self.logger.info(f"The detected language is {self.detected_language}")

                #
                # By default, 'text' is extracted above.
                # If remove_boilerplate is True, then use it directly
                # If no boilerplate remove but need to remove code, then we need to use html_to_text
                #
                if self.remove_boilerplate:
                    url = res['url']
                    if self.verbose:
                        self.logger.info(f"Removing boilerplate from content of {url}, and extracting important text only")
                    text, extracted_title = get_article_content(html, url, self.detected_language, self.remove_code)
                else:
                    text = html_to_text(html, self.remove_code, html_processing)

                parts = [text]
                self.logger.info(f"retrieving content took {time.time()-st:.2f} seconds")
            except Exception as e:
                import traceback
                self.logger.info(f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
                return False
        
        doc_id = slugify(url)
        succeeded = self.index_segments(doc_id=doc_id, texts=parts,
                                        doc_metadata=metadata, doc_title=extracted_title)
        return succeeded

    def index_segments(self, doc_id: str, texts: List[str], titles: Optional[List[str]] = None, metadatas: Optional[List[Dict[str, Any]]] = None, 
                       doc_metadata: Dict[str, Any] = {}, doc_title: str = "") -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        """
        if titles is None:
            titles = ["" for _ in range(len(texts))]
        if metadatas is None:
            metadatas = [{} for _ in range(len(texts))]
        else:
            metadatas = [{k:self.normalize_text(v) for k,v in md.items()} for md in metadatas]

        document = {}
        document["documentId"] = doc_id
        if doc_title is not None and len(doc_title)>0:
            document["title"] = self.normalize_text(doc_title)
        document["section"] = [
            {"text": self.normalize_text(text), "title": self.normalize_text(title), "metadataJson": json.dumps(md)} 
            for text,title,md in zip(texts,titles,metadatas)
        ]
        if doc_metadata:
            document["metadataJson"] = json.dumps(doc_metadata)

        if self.verbose:
            self.logger.info(f"Indexing document {doc_id} with {document}")

        return self.index_document(document)

    def index_document(self, document: Dict[str, Any]) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus).
        Document is a dictionary that includes documentId, title, optionally metadataJson, and section (which is a list of segments).
        """
        return self._index_document(document)

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
        
        # If we have a PDF fiel with size>50MB, or we want to use the summarize_tables option, then we parse locally and index
        # Otherwise - send to Vectara's default upload fiel mechanism
        size_limit = 50
        large_file_extensions = ['.pdf', '.html', '.htm']
        if (any(uri.endswith(extension) for extension in large_file_extensions) and
           (get_file_size_in_MB(filename) >= size_limit or self.summarize_tables)):
            openai_api_key = self.cfg.vectara.get("openai_api_key", None)
            title, texts = _parse_local_file(filename, uri, self.summarize_tables, openai_api_key)
            succeeded = self.index_segments(doc_id=slugify(uri), texts=texts,
                                            doc_metadata=metadata, doc_title=title)
            if self.summarize_tables:
                self.logger.info(f"For file {filename}, extracting text locally since summarize_tables is activated")
            else:
                self.logger.info(f"For file {filename}, extracting text locally since file size is larger than {size_limit}MB")
            return succeeded
        else:
            # index the file within Vectara (use FILE UPLOAD API)
            return self._index_file(filename, uri, metadata)
    
