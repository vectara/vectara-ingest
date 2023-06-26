from core.crawler import Crawler
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin, urlparse
import re
from collections import deque

from core.utils import create_session_with_retries

class DocusaurusCrawler(Crawler):    

    def get_urls(self, base_urls):
        new_urls = deque(base_urls)
        crawled_urls = set()
        ignored_urls = set()
        session = create_session_with_retries()

        # Crawl each URL in the queue
        while len(new_urls):
            # Dequeue a URL from new_urls
            url = new_urls.popleft()
            
            try:
                response = session.get(url)
                if response.status_code != 200:
                    continue
                page_content = BeautifulSoup(response.content, 'lxml')
                crawled_urls.add(url)

                # Find all the new URLs in the page's content and add them into the queue
                for link in page_content.find_all('a'):
                    href = link.get('href')
                    if href is None:
                        continue
                    abs_url = urljoin(url, href)
                    if (abs_url in ignored_urls or urlparse(abs_url).fragment or                   # don't crawl if this points to a fragment (#)
                        any([abs_url.endswith(ext) for ext in self.extensions_to_ignore])):     # don't crawl specified extensions
                           ignored_urls.add(abs_url)
                           continue
                    if abs_url not in crawled_urls and abs_url not in new_urls:
                        # Ensure the URL is not None and it is a child URL under any of the base_urls
                        if any(base_url in abs_url for base_url in base_urls):
                            new_urls.append(abs_url)
            except:
                continue

        return crawled_urls

    def crawl(self):
        self.extensions_to_ignore = list(set(self.cfg.docusaurus_crawler.extensions_to_ignore + ["gif", "jpeg", "jpg", "mp3", "mp4", "png", "svg"]))
        all_urls = self.get_urls(self.cfg.docusaurus_crawler.base_urls)

        url_regex = [re.compile(r) for r in self.cfg.docusaurus_crawler.url_regex]
        for url in set(all_urls):
            if any([r.match(url) for r in url_regex]):
                self.indexer.index_url(url, metadata={'url': url, 'source': 'docusaurus'})
                logging.info(f"Docusarus Crawler: finished indexing {url}")
            else:
                logging.info(f"Docusarus Crawler: skipping {url} since it does not match any of the regexes")
