import logging
import os
from usp.tree import sitemap_tree_for_homepage      # type: ignore
from slugify import slugify                         # type: ignore
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
import time
from ratelimiter import RateLimiter

from crawler import Crawler

# disable USP annoying logging
logging.getLogger('usp.fetch_parse').setLevel(logging.ERROR)
logging.getLogger('usp.helpers').setLevel(logging.ERROR)

def recursive_crawl(url, depth, visited=None):
    if visited is not None:
        logging.info(f"recursive crawling: depth={depth}, visited={len(visited)}")
    if visited is None:
        visited = set()

    # Check if the depth limit has been reached or if the URL has already been visited
    if depth <= 0 or url in visited:
        return visited

    visited.add(url)
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find all anchor tags and their href attributes
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Join the base URL with the found href to get the absolute URL
            new_url = urljoin(url, href)
            # Check if the new URL has the same domain as the base URL
            if urlparse(url).netloc == urlparse(new_url).netloc:
                visited = recursive_crawl(new_url, depth - 1, visited)
    except requests.exceptions.RequestException:
        pass

    return visited

class WebsiteCrawler(Crawler):

    def crawl(self):
    
        homepage = self.cfg.website_crawler.website_homepage
        if self.cfg.website_crawler.pages_source == 'file':
            sitemap_content = open(self.cfg.website_crawler.sitemap_file, 'rt').read()
            bs = BeautifulSoup(sitemap_content, "xml")
            loc_tags = bs.find_all('loc')
            urls = [loc.get_text() for loc in loc_tags]
        elif self.cfg.website_crawler.pages_source == 'sitemap':
            tree = sitemap_tree_for_homepage(homepage)
            urls = [page.url for page in tree.all_pages()]
        elif self.cfg.website_crawler.pages_source == 'crawl':
            urls = recursive_crawl(homepage, self.cfg.website_crawler.max_depth)

        logging.info(f"Finished crawling using {self.cfg.website_crawler.pages_source}, found {len(urls)} URLs to index")

        domain = '.'.join(str(urlparse(homepage).hostname).split('.')[-2:])
        crawled_urls = set()        # sometimes pages return the same URL twice, so we need to keep track of what we crawled to avoid duplicates
        rate_limiter = RateLimiter(max_calls=2, period=1)
        for url in urls:
            if domain not in url:
                logging.info(f"Skipping {url} since it's not in the same domain as {domain}")
                continue
            if url in crawled_urls:
                logging.info(f"Skipping {url} since it was already crawled in this round")
                continue

            try:
                with rate_limiter:
                    filename = self.url_to_file(url, title=slugify(url), extraction=self.cfg.website_crawler.extraction)
            except Exception as e:
                logging.error(f"Error while processing {url}: {e}")
                continue

            try:
                metadata = {'source': 'website', 'url': url}
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
                logging.error(f"Error while indexing {url}: {e}")
        return

