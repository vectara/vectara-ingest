from omegaconf import OmegaConf, DictConfig
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
from typing import Set, Optional, List, Any
from core.indexer import Indexer
from core.pdf_convert import PDFConverter
from core.utils import binary_extensions, doc_extensions
from slugify import slugify

import asyncio
from playwright.sync_api import sync_playwright

get_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

            
def recursive_crawl(url: str, depth: int, url_regex: List[Any], indexer: Indexer, visited: Optional[Set[str]]=None) -> Set[str]:
    if depth <= 0:
        return set() if visited is None else set(visited)

    if visited is None:
        visited = set()

    # For binary files - we don't extract links from them, nor are they included in the crawled URLs list
    # for document files (like PPT, DOCX, etc) we don't extract links from the, but they ARE included in the crawled URLs list
    url_without_fragment = url.split("#")[0]
    if any([url_without_fragment.endswith(ext) for ext in binary_extensions]):
        return visited
    visited.add(url)
    if any([url_without_fragment.endswith(ext) for ext in doc_extensions]):
        return visited

    try:
        _, _, new_urls = indexer.fetch_page_contents(url)
        logging.info(f"DEBUG A: new_urls = {new_urls}")
        new_urls = [u for u in new_urls if u not in visited and u.startswith('http') and (len(url_regex)==0 or any([r.match(u) for r in url_regex]))]
        new_urls = list(set(new_urls))
        logging.info(f"DEBUG B: new_urls = {new_urls}")
        visited.update(new_urls)
        for new_url in new_urls:
            visited = recursive_crawl(new_url, depth-1, url_regex, indexer, visited)
    except Exception as e:
        logging.info(f"Error {e} in recursive_crawl for {url}")
        pass

    return set(visited)


class Crawler(object):
    """
    Base class for a crawler that indexes documents into a Vectara corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        customer_id (str): ID of the Vectara customer.
        corpus_id (int): ID of the Vectara corpus to index to.
        api_key (str): API key to use for indexing into Vectara
    """

    def __init__(
        self,
        cfg: OmegaConf,
        endpoint: str,
        customer_id: str,
        corpus_id: int,
        api_key: str,
    ) -> None:
        self.cfg: DictConfig = DictConfig(cfg)
        reindex = self.cfg.vectara.get("reindex", False)
        self.indexer = Indexer(cfg, endpoint, customer_id, corpus_id, api_key, reindex)

    def url_to_file(self, url: str, title: str) -> str:
        """
        Crawl a single webpage and create a PDF file to reflect its rendered content.

        Args:
            url (str): URL of the page to crawl.
            title (str): Title to use in case HTML does not have its own title.

        Returns:
            str: Name of the PDF file created.
        """
        # first verify the URL is valid
        response = requests.get(url, headers=get_headers)
        if response.status_code != 200:
            if response.status_code == 404:
                raise Exception(f"Error 404 - URL not found: {url}")
            elif response.status_code == 401:
                raise Exception(f"Error 403 - Unauthorized: {url}")
            elif response.status_code == 403:
                raise Exception(f"Error 403 - Access forbidden: {url}")
            elif response.status_code == 405:
                raise Exception(f"Error 405 - Method not allowed: {url}")
            else:
                raise Exception(
                    f"Invalid URL: {url} (status code={response.status_code}, reason={response.reason})"
                )

        if title is None or len(title)==0:
            soup = BeautifulSoup(response.text, "html.parser")
            title = str(soup.title)

        # convert to local file (PDF)
        filename = slugify(url) + ".pdf"
        if not PDFConverter(use_pdfkit=False).from_url(url, filename, title=title):
            raise Exception(f"Failed to convert {url} to PDF")

        return filename

    def crawl(self) -> None:
        raise Exception("Not implemented")
