from omegaconf import OmegaConf
from slugify import slugify         # type: ignore
import requests
from indexer import Indexer
from pdf_convert import PDFConverter
from trafilatura import fetch_url, extract
from bs4 import BeautifulSoup

class Crawler(object):
    """
    Base class for a crawler that indexes documents to a Vectara corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        customer_id (str): ID of the Vectara customer.
        token (str): Bearer JWT token
        corpus_id (int): ID of the Vectara corpus to index to.
    """
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        self.cfg = cfg
        self.indexer = Indexer(cfg, endpoint, customer_id, corpus_id, api_key)

    def url_to_file(self, url: str, title: str, extraction: str = "pdf", random: bool = False) -> str:
        """
        Crawl a single webpage and create a PDF file to reflect its rendered content.

        Args:
            url (str): URL of the page to crawl.
            title (str): Title to use in case HTML does not have its own title
            extraction (str): Type of extraction to perform. Can be "pdf" or "html".
        
        Returns:
            str: Name of the PDF file created.
        """        
        # first verify the URL is valid
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else title
        else:
            if response.status_code == 404:
                raise Exception(f"Error 404 - URL not found: {url}")
            elif response.status_code == 401:
                raise Exception(f"Error 403 - Unauthorized: {url}")
            elif response.status_code == 403:
                raise Exception(f"Error 403 - Access forbidden: {url}")
            elif response.status_code == 405:
                raise Exception(f"Error 405 - Method not allowed: {url}")
            else:
                raise Exception(f"Invalid URL: {url} (status code={response.status_code}, reason={response.reason})")

        # convert to PDF
        if extraction == "html":
            filename = slugify(url) + ".html"
            downloaded = fetch_url(url)
            result = extract(downloaded, include_comments=False, include_tables=True, no_fallback=True)
            if result:
                with open(filename, 'w') as f:
                    f.write(result)
            else:           
                raise Exception(f"Failed to convert {url} to HTML")
        else:
            filename = slugify(url) + ".pdf"
            if not PDFConverter(use_pdfkit=False).from_url(url, filename, title=title):
                raise Exception(f"Failed to convert {url} to PDF")

        return filename

    def crawl(self):
        raise "Not implemented"

