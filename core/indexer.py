import logging
import json
import os
from slugify import slugify         # type: ignore
import time
from core.utils import create_session_with_retries

from goose3 import Goose

from omegaconf import OmegaConf
from nbconvert import HTMLExporter
import nbformat
import markdown
import docutils.core
from core.utils import html_to_text

from unstructured.partition.auto import partition
import unstructured as us
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


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
        self.timeout = 30

        # setup requests session and mount adapter to retry requests
        self.session = create_session_with_retries()

        # create playwright browser so we can reuse it across all Indexer operations
        self.p = sync_playwright().start()
        self.browser = self.p.firefox.launch(headless=True)

    def fetch_content_with_timeout(self, url: str, timeout: int = 30):
        '''
        Fetch content from a URL with a timeout.
        Args:
            url (str): URL to fetch.
            timeout (int, optional): Timeout in seconds. Defaults to 30.
        Returns:
            str: Content from the URL.
        '''
        page = context = None
        try:
            context = self.browser.new_context()
            page = context.new_page()
            page.route("**/*", lambda route: route.abort()  # do not load images as they are unnecessary for our purpose
                if route.request.resource_type == "image" 
                else route.continue_() 
            ) 
            page.goto(url, timeout=timeout*1000)
            content = page.content()
            out_url = page.url
        except PlaywrightTimeoutError:
            logging.info(f"Page loading timed out for {url}")
            return '', ''
        except Exception as e:
            logging.info(f"Page loading failed for {url} with exception '{e}'")
            content = ''
            out_url = ''
            if not self.browser.is_connected():
                self.browser = self.p.firefox.launch(headless=True)
        finally:
            if context:
                context.close()
            if page:
                page.close()
            
        return out_url, content

    # delete document; returns True if successful, False otherwise
    def delete_doc(self, doc_id: str):
        """
        Delete a document from the Vectara corpus.

        Args:
            url (str): URL of the page to delete.
            doc_id (str): ID of the document to delete.

        Returns:
            bool: True if the delete was successful, False otherwise.
        """
        body = {'customer_id': self.customer_id, 'corpus_id': self.corpus_id, 'document_id': doc_id}
        post_headers = { 'x-api-key': self.api_key, 'customer-id': str(self.customer_id) }
        response = self.session.post(
            f"https://{self.endpoint}/v1/delete-doc", data=json.dumps(body),
            verify=True, headers=post_headers)
        
        if response.status_code != 200:
            logging.error(f"Delete request failed for doc_id = {doc_id} with status code {response.status_code}, reason {response.reason}, text {response.text}")
            return False
        return True
    
    def index_file(self, filename: str, uri: str, metadata: dict) -> bool:
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
        }

        files = { "file": (uri, open(filename, 'rb')), "doc_metadata": json.dumps(metadata) }
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
                    logging.info(f"REST upload for {uri} succeesful (reindex)")
                    return True
                else:
                    logging.info(f"REST upload for {uri} failed with code = {response.status_code}, text = {response.text}")
                    return True
            return False
        elif response.status_code != 200:
            logging.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
            return False

        logging.info(f"REST upload for {uri} succeesful")
        return True

    def index_url(self, url: str, metadata: dict) -> bool:
        """
        Index a url by rendering it with scrapy-playwright, extracting paragraphs, then uploading to the Vectara corpus.
        Args:
            url (str): URL for where the document originated. 
            metadata (dict): Metadata for the document.
        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        st = time.time()
        try:
            headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            }
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            if response.status_code != 200:
                logging.info(f"Page {url} is unavailable ({response.status_code})")
                return False
            else:
                content_type = str(response.headers["Content-Type"])
        except Exception as e:
            logging.info(f"Failed to crawl {url} to get content_type, skipping...")
            return False
        
        # read page content: everything is translated into various segments (variable "elements") so that we can use index_segment()
        # If PDF then use partition from  "unstructured.io" to extract the content
        if content_type == 'application/pdf' or url.endswith(".pdf"):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                fname = 'tmp.pdf'
                with open(fname, 'wb') as f:
                    f.write(response.content)
                elements = partition(fname)
                parts = [str(t) for t in elements if type(t)!=us.documents.elements.Title]
                titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>20]
                title = titles[0] if len(titles)>0 else 'unknown'
            except Exception as e:
                logging.info(f"Failed to crawl {url} to get PDF content with error {e}, skipping...")
                return False

        # If MD, RST of IPYNB file, then we don't need playwright - can just download content directly and convert to text
        elif url.endswith(".md") or url.endswith(".rst") or url.lower().endswith(".ipynb"):
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            dl_content = response.content
            if url.endswith('rst'):
                html_content = docutils.core.publish_string(dl_content, writer_name='html')
            elif url.endswith('md'):
                html_content = markdown.markdown(dl_content)
            elif url.lower().endswith('ipynb'):
                nb = nbformat.reads(dl_content, nbformat.NO_CONVERT)
                exporter = HTMLExporter()
                html_content, _ = exporter.from_notebook_node(nb)
            title = url.split('/')[-1]      # no title in these files, so using file name
            text = html_to_text(html_content)
            parts = [text]

        # for everything else, use PlayWright as we may want it to render JS on the page before reading the content
        else:
            try:
                actual_url, html_content = self.fetch_content_with_timeout(url)
                if html_content is None or len(html_content)<3:
                    return False
                url = actual_url
                article = Goose().extract(raw_html=html_content)
                title = article.title
                text = article.cleaned_text
                parts = [text]
                logging.info(f"retrieving content took {time.time()-st:.2f} seconds")
            except Exception as e:
                import traceback
                logging.info(f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
                return False

        succeeded = self.index_segments(doc_id=slugify(url), parts=parts, metadatas=[{}]*len(parts), 
                                        doc_metadata=metadata, title=title)
        if succeeded:
            return True
        else:
            return False

    def index_segments(self, doc_id: str, parts: list, metadatas: list, doc_metadata: dict = None, title: str = None) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        """
        document = {}
        document["documentId"] = doc_id
        if title:
            document["title"] = title
        document["section"] = [{"text": part, "metadataJson": json.dumps(md)} for part,md in zip(parts,metadatas)]
        if doc_metadata:
            document["metadataJson"] = json.dumps(doc_metadata)
        return self.index_document(document)
    
    def index_document(self, document: dict) -> bool:
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

