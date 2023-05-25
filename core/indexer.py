import logging
import requests
import json
import os
from omegaconf import OmegaConf
from slugify import slugify         # type: ignore
from bs4 import BeautifulSoup

import asyncio
from unstructured.partition.html import partition_html
from unstructured.partition.pdf import partition_pdf
import unstructured as us

from playwright.async_api import async_playwright 

async def fetch_content_with_timeout(url, timeout: int = 20):
    async with async_playwright() as playwright:
        browser = await playwright.firefox.launch()
        page = await browser.new_page()
        try:
            await asyncio.wait_for(page.goto(url), timeout=timeout)
            content = await page.content()
        except asyncio.TimeoutError:
            logging.info(f"Page loading timed out for {url}")
            content = None
        await browser.close()
    return content

def get_content_type_and_status(url: str):
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
        self.chunk_min_len = 50
        self.chunk_max_len = 2500   # targeting roughly 500 words

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
        response = requests.post(
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
        response = requests.post(
            f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}&d=True",
            files=files, verify=True, headers=post_headers)

        if response.status_code == 409:
            if self.reindex:
                doc_id = response.json()['details'].split('document id')[1].split("'")[1]
                self.delete_doc(doc_id)
                response = requests.post(
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
            logging.error(f"REST upload for {uri} failed with code {response.status_code}")
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

        # read page content using playwright
        if content_type == 'application/pdf':
            response = requests.get(url)
            response.raise_for_status()
            fname = 'tmp.pdf'
            with open(fname, 'wb') as f:
                f.write(response.content)
            elements = partition_pdf(fname, strategy='auto')
            titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>20]
            title = titles[0] if len(titles)>0 else 'unknown'
            elements = [str(e) for e in elements if type(e)==us.documents.elements.NarrativeText]
        else:
            try:
                content = asyncio.run(fetch_content_with_timeout(url))
            except Exception as e:
                logging.info(f"Failed to crawl {url}, skipping due to error {e}")
                return False
            if content is None:
                return False
            soup = BeautifulSoup(content, 'html.parser')
            title = soup.title.string if soup.title else 'No Title'
            elements = partition_html(text=content)
            elements = [str(e) for e in elements if type(e)==us.documents.elements.NarrativeText]

        succeeded = self.index_segments(doc_id=slugify(url), parts=elements, metadata=metadata, title=title)
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
        response = requests.post(api_endpoint, data=data, verify=True, headers=post_headers)

        result = response.json()
        if "status" in result and result["status"] and "ALREADY_EXISTS" in result["status"]["code"]:
            if self.reindex:
                logging.info(f"Document {document['documentId']} already exists, re-indexing")
                self.delete_doc(document['documentId'])
                response = requests.post(api_endpoint, data=json.dumps(request), verify=True, headers=post_headers)
            else:
                logging.info(f"Document {document['documentId']} already exists, skipping")
                return False

        return self._check_response(response)
