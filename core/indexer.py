import logging
import json
import os
from omegaconf import OmegaConf
from slugify import slugify         # type: ignore
import requests

import asyncio
from unstructured.partition.html import partition_html
from unstructured.partition.pdf import partition_pdf
import unstructured as us

from nbconvert import HTMLExporter
import nbformat
import markdown
import docutils.core
from core.utils import html_to_text

from readability import Document
from playwright.async_api import async_playwright 

async def fetch_content_with_timeout(url, timeout=30):
    '''
    Fetch content from a URL with a timeout.

    Args:
        url (str): URL to fetch.
        timeout (int, optional): Timeout in seconds. Defaults to 30.

    Returns:
        str: Content from the URL.
    '''
    async with async_playwright() as playwright:
        browser = await playwright.firefox.launch()
        page = await browser.new_page()
        try:
            # goto page
            await asyncio.wait_for(page.goto(url), timeout=timeout)
            content = await page.content()
        except asyncio.TimeoutError:
            logging.info(f"Page loading timed out for {url}")
            content = None
        finally:
            await page.close()
            await browser.close()
        return content

def get_content_type_and_status(url: str):
    '''
    Get the content type and status code for a URL.

    Args:
        url (str): URL to fetch.

    Returns:
        tuple: status code and content_type
    '''
    headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return response.status_code, ''
    else:
        return response.status_code, str(response.headers["Content-Type"])

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

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=5)
        self.session.mount('http://', adapter)

    def _check_response(self, response) -> bool:
        if response.status_code != 200:
            logging.error("REST upload failed with code %d, reason %s, text %s",
                        response.status_code,
                        response.reason,
                        response.text)
            return False
        else:
            return True
        
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
        try:
            status_code, content_type = get_content_type_and_status(url)
        except Exception as e:
            logging.info(f"Failed to crawl {url} to get content_type and status_code, skipping...")
            return False
        
        if status_code != 200:
            logging.info(f"Page {url} is unavailable ({status_code})")
            return False

        # read page content: everything is translated into various segments (variable "elements") so that we can use index_segment()
        # If PDF then use partition_pdf from  "unstructured.io" to extract the content
        if content_type == 'application/pdf':
            response = self.session.get(url)
            response.raise_for_status()
            fname = 'tmp.pdf'
            with open(fname, 'wb') as f:
                f.write(response.content)
            elements = partition_pdf(fname, strategy='auto')
            text = ' '.join(str(t) for t in elements if type(t)!=us.documents.elements.Title)
            titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>20]
            title = titles[0] if len(titles)>0 else 'unknown'

        # If MD, RST of IPYNB file, then we don't need playwright - can just download content directly and convert to text
        elif url.endswith(".md") or url.endswith(".rst") or url.lower().endswith(".ipynb"):
            response = self.session.get(url)
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
        # for everything else, use PlayWright as we may want it to render JS on the page before reading the content
        else:
            try:
                html_content = asyncio.run(fetch_content_with_timeout(url))
            except Exception as e:
                logging.info(f"Failed to crawl {url}, skipping due to error {e}")
                return False
            if html_content is None:
                return False
            doc = Document(html_content)
            title = doc.title()
            text = html_to_text(doc.summary())

        succeeded = self.index_segments(doc_id=slugify(url), parts=[text], metadata=metadata, title=title)
        if succeeded:
            logging.info(f"Indexing for {url} succeesful")
            return True
        else:
            logging.info(f"Did not index {url}")
            return False

    def index_segments(self, doc_id: str, parts: list, metadata: dict, title: str = None) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        """
        document = {}
        document["documentId"] = doc_id
        document["title"] = title
        document["section"] = [{"text": part} for part in parts]
        document["metadataJson"] = json.dumps(metadata)
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

        result = response.json()
        if "status" in result and result["status"] and "ALREADY_EXISTS" in result["status"]["code"]:
            if self.reindex:
                logging.info(f"Document {document['documentId']} already exists, re-indexing")
                self.delete_doc(document['documentId'])
                response = self.session.post(api_endpoint, data=json.dumps(request), verify=True, headers=post_headers)
            else:
                logging.info(f"Document {document['documentId']} already exists, skipping")
                return False

        return self._check_response(response)
