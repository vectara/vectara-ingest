import logging
import json
import os
from typing import Tuple, Dict, Any, List, Optional

import time
from slugify import slugify

from bs4 import BeautifulSoup

from omegaconf import OmegaConf
from nbconvert import HTMLExporter      # type: ignore
import nbformat
import markdown
import docutils.core

from core.utils import html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries, TableSummarizer, mask_pii
from core.extract import get_content_and_title

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from unstructured.partition.auto import partition
import unstructured as us

get_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

def _parse_local_file(filename: str, summarize_tables: bool, openai_api_key: str = None) -> Tuple[str, List[str]]:
    st = time.time()

    if filename.endswith(".pdf") and summarize_tables and openai_api_key is not None:
        try:
            from unstructured.partition.auto import partition_pdf
            elements = partition_pdf(filename, infer_table_structure=True, extract_images_in_pdf=False,
                                        strategy='hi_res', hi_res_model_name='yolox')  # use 'detectron2_onnx' for a faster model
        except ImportError:
            logging.error("Failed to import unstructured.partition.auto.partition_pdf")
            elements = partition(filename)
    else:
        elements = partition(filename)

    # get title
    titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>10]
    title = titles[0] if len(titles)>0 else 'no title'

    # get texts (and tables summaries if applicable)
    summarizer = TableSummarizer(openai_api_key) if openai_api_key is not None and summarize_tables else None
    texts = []
    for t in elements:
        if type(t)==us.documents.elements.Table and summarize_tables and openai_api_key is not None:
            texts.append(summarizer.summarize_table_text(str(t)))
        else:
            texts.append(str(t))

    logging.info(f"parsing PDF file {filename} took {time.time()-st:.2f} seconds")
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
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str, reindex: bool = True) -> None:
        self.cfg = cfg
        self.endpoint = endpoint
        self.customer_id = customer_id
        self.corpus_id = corpus_id
        self.api_key = api_key
        self.reindex = reindex
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'

        self.summarize_tables = cfg.vectara.get("summarize_tables", False)
        if cfg.vectara.get("openai_api_key", None) is None:
            if self.summarize_tables:
                logging.info("OpenAI API key not found, disabling table summarization")
            self.summarize_tables = False

        self.setup()

    def mask_pii(self, text: str) -> str:
        if self.cfg.vectara.get("mask_pii", False):
            return mask_pii(text)
        return text

    def setup(self):
        self.session = create_session_with_retries()
        # Create playwright browser so we can reuse it across all Indexer operations
        self.p = sync_playwright().start()
        self.browser = self.p.firefox.launch(headless=True)

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
        except Exception as e:
            pass

        page.close()
        context.close()
        return download_triggered

    def fetch_page_contents(self, url: str, debug: bool = False) -> Tuple[str, str, List[str]]:
        '''
        Fetch content from a URL with a timeout.
        Args:
            url (str): URL to fetch.
            debug (bool): Whether to enable playwright debug logging.
        Returns:
            content, actual url, list of links
        '''
        page = context = None
        content = ''
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
                page.on('console', lambda msg: logging.info(f"playwright debug: {msg.text})"))

            page.goto(url, timeout=self.timeout*1000, wait_until="load")
            content = page.content()
            out_url = page.url
            links_elements = page.query_selector_all("a")
            links = [link.get_attribute("href") for link in links_elements if link.get_attribute("href")]
            
        except PlaywrightTimeoutError:
            logging.info(f"Page loading timed out for {url}")
        except Exception as e:
            logging.info(f"Page loading failed for {url} with exception '{e}'")
            if not self.browser.is_connected():
                self.browser = self.p.firefox.launch(headless=True)
        finally:
            if page:
                page.close()
            if context:
                context.close()
            
        return content, out_url, links

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
            logging.error(f"Delete request failed for doc_id = {doc_id} with status code {response.status_code}, reason {response.reason}, text {response.text}")
            return False
        return True
    
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
        if os.path.exists(filename) == False:
            logging.error(f"File {filename} does not exist")
            return False

        post_headers = { 
            'x-api-key': self.api_key,
            'customer-id': str(self.customer_id),
            'X-Source': self.x_source
        }

        files: Any = {
            "file": (uri, open(filename, 'rb')),
            "doc_metadata": (None, json.dumps(metadata)),
        }  
        response = self.session.post(
            f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}&d=True",
            files=files, verify=True, headers=post_headers)

        if response.status_code == 409:
            if self.reindex:
                doc_id = response.json()['details'].split('document id')[1].split("'")[1]
                self.delete_doc(doc_id)
                response = self.session.post(
                    f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}",
                    files=files, verify=True, headers=post_headers)
                if response.status_code == 200:
                    logging.info(f"REST upload for {uri} successful (reindex)")
                    return True
                else:
                    logging.info(f"REST upload for {uri} (reindex) failed with code = {response.status_code}, text = {response.text}")
                    return True
            return False
        elif response.status_code != 200:
            logging.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        logging.info(f"REST upload for {uri} succeesful")
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
            logging.info(f"Can't serialize request {request}, skipping")   
            return False

        try:
            response = self.session.post(api_endpoint, data=data, verify=True, headers=post_headers)
        except Exception as e:
            logging.info(f"Exception {e} while indexing document {document['documentId']}")
            return False

        if response.status_code != 200:
            logging.error("REST upload failed with code %d, reason %s, text %s",
                          response.status_code,
                          response.reason,
                          response.text)
            return False

        result = response.json()
        if "status" in result and result["status"] and \
           ("ALREADY_EXISTS" in result["status"]["code"] or \
            ("CONFLICT" in result["status"]["code"] and "Indexing doesn't support updating documents" in result["status"]["statusDetail"])):
            if self.reindex:
                logging.info(f"Document {document['documentId']} already exists, re-indexing")
                self.delete_doc(document['documentId'])
                response = self.session.post(api_endpoint, data=json.dumps(request), verify=True, headers=post_headers)
                return True
            else:
                logging.info(f"Document {document['documentId']} already exists, skipping")
                return False
        if "status" in result and result["status"] and "OK" in result["status"]["code"]:
            return True
        
        logging.info(f"Indexing document {document['documentId']} failed, response = {result}")
        return False
    
    def index_url(self, url: str, metadata: Dict[str, Any]) -> bool:
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

        if self.url_triggers_download(url):
            file_path = 'tmpfile'
            response = self.session.get(url, stream=True)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192): 
                        f.write(chunk)
                logging.info(f"File downloaded successfully and saved as {file_path}")
            else:
                logging.info(f"Failed to download file. Status code: {response.status_code}")
                return False
            # parse downloaded file
            try:
                elements = partition(file_path)
                parts = [str(t) for t in elements if type(t)!=us.documents.elements.Title]
                titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>20]
                extracted_title = titles[0] if len(titles)>0 else 'unknown'
            except Exception as e:
                logging.info(f"Failed to crawl {url} - extracting content from file failed, with error {e}, skipping...")
                return False

        else:
            # If MD, RST of IPYNB file, then we don't need playwright - can just download content directly and convert to text
            if url.lower().endswith(".md") or url.lower().endswith(".rst") or url.lower().endswith(".ipynb"):
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                dl_content = response.content.decode('utf-8')
                if url.lower().endswith('rst'):
                    html_content = docutils.core.publish_string(dl_content, writer_name='html')
                elif url.lower().endswith('md'):
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
                    content, actual_url, _ = self.fetch_page_contents(url)
                    if content is None or len(content)<3:
                        return False
                    if self.detected_language is None:
                        soup = BeautifulSoup(content, 'html.parser')
                        body_text = soup.body.get_text()
                        self.detected_language = detect_language(body_text)
                        logging.info(f"The detected language is {self.detected_language}")
                    url = actual_url
                    if self.remove_boilerplate:
                        logging.info(f"Removing boilerplate from content of {url}, and extracting important text only")
                        text, extracted_title = get_content_and_title(content, url, self.detected_language, self.remove_code)
                    else:
                        extracted_title = BeautifulSoup(content, 'html.parser').title.text
                        text = html_to_text(content, self.remove_code)
                    parts = [text]
                    logging.info(f"retrieving content took {time.time()-st:.2f} seconds")
                except Exception as e:
                    import traceback
                    logging.info(f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
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
            metadatas = [{k:self.mask_pii(v) for k,v in md.items()} for md in metadatas]

        document = {}
        document["documentId"] = doc_id
        if doc_title is not None and len(doc_title)>0:
            document["title"] = self.mask_pii(doc_title)
        document["section"] = [
            {"text": self.mask_pii(text), "title": self.mask_pii(title), "metadataJson": json.dumps(md)} 
            for text,title,md in zip(texts,titles,metadatas)
        ]
        if doc_metadata:
            document["metadataJson"] = json.dumps(doc_metadata)

        logging.info(f"Indexing document {doc_id} with {document}")

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
        if os.path.exists(filename) == False:
            logging.error(f"File {filename} does not exist")
            return False

        # Parse locally and index text only in two cases:
        # 1. File size is more than 50MB (so can't upload to Vectara due to file size limit)
        # 2. the summarize_tables flag is enabled
        # In either case, if openai_api_key is valid and summarize_tables is on, we include table summary in the text

        large_file_extensions = ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.txt', '.md', '.rst', '.epub', '.html', '.htm']
        if (any(filename.endswith(extension) for extension in large_file_extensions) and
            (get_file_size_in_MB(filename) >= 50 or self.summarize_tables)):
            openai_api_key = self.cfg.vectara.get("openai_api_key", None)
            title, texts = _parse_local_file(filename, summarize_tables=self.summarize_tables, openai_api_key=openai_api_key)
            succeeded = self.index_segments(doc_id=slugify(filename), texts=texts,
                                            doc_metadata=metadata, doc_title=title)
            logging.info(f"For file {filename}, extracting text locally since file size is larger than 50MB")
            return succeeded
        else:
            # index the file within Vectara (use FILE UPLOAD API)
            return self._index_file(filename, uri, metadata)
    
