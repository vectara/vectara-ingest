import logging
import os
from usp.tree import sitemap_tree_for_homepage      # type: ignore
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from ratelimiter import RateLimiter
from core.crawler import Crawler, recursive_crawl

# disable USP annoying logging
logging.getLogger('usp.fetch_parse').setLevel(logging.ERROR)
logging.getLogger('usp.helpers').setLevel(logging.ERROR)

from urllib.parse import urlparse

def normalize_url(url):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def is_partial_path(url_a, url_b):
    # Add 'http://' at the start of the urls if it's not present
    url_a = normalize_url(url_a)
    url_b = normalize_url(url_b)

    # Parse the urls
    parsed_a = urlparse(url_a)
    parsed_b = urlparse(url_b)

    # Remove the 'www.' if present
    parsed_a_netloc = parsed_a.netloc.replace('www.', '')
    parsed_b_netloc = parsed_b.netloc.replace('www.', '')

    # Check if the domain names match
    if parsed_a_netloc != parsed_b_netloc:
        return False

    # Check if the path of url_b is a subpath of url_a
    if not parsed_a.path.startswith(parsed_b.path):
        return False

    return True


class WebsiteCrawler(Crawler):

    def crawl(self):
    
        base_urls = self.cfg.website_crawler.urls
        crawled_urls = set()
        for homepage in base_urls:
            homepage = normalize_url(homepage)
            if self.cfg.website_crawler.pages_source == 'sitemap':
                tree = sitemap_tree_for_homepage(homepage)
                urls = [page.url for page in tree.all_pages()]
            elif self.cfg.website_crawler.pages_source == 'crawl':
                hp_domain = "{uri.netloc}".format(uri=urlparse(homepage))
                urls = recursive_crawl(homepage, self.cfg.website_crawler.max_depth, domain=hp_domain)

            if self.cfg.website_crawler.get("force_prefix", False):
                urls = [u for u in urls if is_partial_path(u, homepage)]       # ensure homepage is a substring of all URLs
    
            logging.info(f"Finished crawling using {homepage}, found {len(urls)} URLs to index")

            rate_limiter = RateLimiter(max_calls=1, period=self.cfg.website_crawler.delay)
            for url in urls:
                if url in crawled_urls:
                    logging.info(f"Skipping {url} since it was already crawled in this round")
                    continue

                extraction = self.cfg.website_crawler.extraction
                metadata = {'source': 'website', 'url': url}
                if extraction == 'pdf':
                    try:
                        with rate_limiter:
                            filename = self.url_to_file(url, title=None)
                    except Exception as e:
                        logging.error(f"Error while processing {url}: {e}")
                        continue
                    try:
                        succeeded = self.indexer.index_file(filename, uri=url, metadata=metadata)
                        if not succeeded:
                            logging.info(f"Indexing failed for {url}, deleting document from corpus, then trying to index again")
                            doc_id = url
                            self.indexer.delete_doc(doc_id)   # doc_id is the URL itself
                            self.indexer.index_file(filename, uri=url, metadata=metadata)
                        if os.path.exists(filename):
                            os.remove(filename)
                        crawled_urls.add(url)
                    except Exception as e:
                        import traceback
                        logging.error(f"Error while indexing {url}: {e}, traceback={traceback.format_exc()}")
                else:   # use index_url which does not go through PDF
                    with rate_limiter:
                        succeeded = self.indexer.index_url(url, metadata=metadata)
                    if not succeeded:
                        logging.info(f"Indexing failed for {url}, deleting document from corpus, then trying to index again")
                        doc_id = url
                        self.indexer.delete_doc(doc_id)   # doc_id is the URL itself
                        self.indexer.index_url(url, metadata=metadata)
                    crawled_urls.add(url)
            return
