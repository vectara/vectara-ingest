from omegaconf import OmegaConf, DictConfig
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
from typing import Set, Optional, List, Any
from core.indexer import Indexer
from core.utils import img_extensions, doc_extensions, archive_extensions
from slugify import slugify
from urllib.parse import urlparse


get_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

def url_is_relative(url: str) -> bool:
    parsed_url = urlparse(url)
    return not parsed_url.scheme and not parsed_url.netloc

def recursive_crawl(url: str, depth: int, pos_regex: List[Any], neg_regex: List[Any], 
                    indexer: Indexer, visited: Optional[Set[str]]=None, 
                    verbose: bool = False) -> Set[str]:
    """
    Recursively crawl a URL and extract all links from it.
    """    
    if visited is None:
        visited = set()

    # For archive or image - we don't extract links from them, nor are they included in the crawled URLs list
    url_without_fragment = url.split("#")[0]
    if any([url_without_fragment.endswith(ext) for ext in (archive_extensions + img_extensions)]):
        return visited

    # add the current URL
    visited.add(url)

    # for document files (like PPT, DOCX, etc) we don't extract links from the URL, but the link itself is included. 
    if any([url_without_fragment.endswith(ext) for ext in doc_extensions]):
        return visited

    # if we reached the maximum depth, stop and return the visited URLs
    if depth <= 0:
        return visited

    try:
        res = indexer.fetch_page_contents(url)
        new_urls = [urljoin(url, u) if url_is_relative(u) else u for u in res['links']]  # convert all new URLs to absolute URLs
        new_urls = [u for u in new_urls 
                    if      u not in visited and u.startswith('http') 
                    and     (len(pos_regex)==0 or any([r.match(u) for r in pos_regex]))
                    and     (len(neg_regex)==0 or (not any([r.match(u) for r in neg_regex]))) 
                   ]
        new_urls = list(set(new_urls))
        visited.update(new_urls)

        if len(new_urls) > 0:
            logging.info(f"collected {len(visited)} URLs so far")
            if verbose:
                print(f"URLs so far: {visited}")

        for new_url in new_urls:
            visited = recursive_crawl(new_url, depth-1, pos_regex, neg_regex, indexer, visited, verbose)
    except Exception as e:
        logging.error(f"Error {e} in recursive_crawl for {url}")
        pass

    return set(visited)


class Crawler(object):
    """
    Base class for a crawler that indexes documents into a Vectara corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        corpus_key (str): Key of the Vectara corpus to index to.
        api_key (str): API key to use for indexing into Vectara
    """

    def __init__(
        self,
        cfg: OmegaConf,
        endpoint: str,
        corpus_key: str,
        api_key: str,
    ) -> None:
        self.cfg: DictConfig = DictConfig(cfg)
        self.indexer = Indexer(cfg, endpoint, corpus_key, api_key)
        self.verbose = cfg.vectara.get("verbose", False)
