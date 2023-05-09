import logging
import requests
import json
import os
from omegaconf import OmegaConf

class Indexer(object):
    """
    Vectara API class.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        customer_id (str): ID of the Vectara customer.
        corpus_id (int): ID of the Vectara corpus to index to.
        api_key (str): API key for the Vectara API.
    """
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        self.cfg = cfg
        self.endpoint = endpoint
        self.customer_id = customer_id
        self.corpus_id = corpus_id
        self.api_key = api_key

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
        logging.info(f"Deleting document {doc_id} from corpus {self.corpus_id}")
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
            f"https://{self.endpoint}/upload?c={self.customer_id}&o={self.corpus_id}&d=true",
            files=files, verify=True, headers=post_headers)

        if response.status_code == 200:
            logging.info(f"REST upload for {uri} succeesful")
            return True
        if response.status_code == 409:
            logging.info(f"REST upload for {uri} failed with code {response.status_code} (document already indexed)")
            return False

        logging.error(f"REST upload for {uri} failed with code {response.status_code}")
        return False

    def index_document(self, document: dict):
        """
        Index a document (by uploading it to the Vectara corpus) from the document dictionary
        """
        request = {
            'customer_id': self.customer_id,
            'corpus_id': self.corpus_id,
            'document': document,
        }
        post_headers = { 
            'x-api-key': self.api_key,
            'customer-id': str(self.customer_id),
        }
        response = requests.post(
            f"https://{self.endpoint}/v1/index",
            data=json.dumps(request),
            verify=True,
            headers=post_headers)

        if response.status_code != 200:
            logging.error("REST upload failed with code %d, reason %s, text %s",
                        response.status_code,
                        response.reason,
                        response.text)
            return response, False
        return response, True


    def index_segments(self, doc_id: str, parts: list, metadata: dict, title: str = None):
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        """
        document = {}
        document["document_id"] = doc_id
        document["title"] = title
        sections = []
        logging.info(f"Indexing {len(parts)} segments")
        for part in parts:
            section = {}
            section["text"] = part
            sections.append(section)
        document["section"] = sections
        document["metadataJson"] = json.dumps(metadata)
        return self.index_document(document)
    