import os
from core.crawler import Crawler
from git import Repo
import logging
from pathlib import Path
import fnmatch
from omegaconf import OmegaConf
from markdown import markdown
from bs4 import BeautifulSoup
import requests
from slugify import slugify
import json
from urllib.parse import urljoin, urlparse
import re

class DocusaurusCrawler(Crawler):    
    def _get_links(self, page_url):
        """Crawls a single page in a docusaurus documentation site and return URLs that show on this page

        Args:
            page_url: The URL of the page to crawl.

        Returns:
            A list of URLs extracted from the page
        """

        response = requests.get(page_url)
        soup = BeautifulSoup(response.content, "html.parser")

        # Find all anchor tags and their href attributes
        urls = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.startswith("#"):
                continue
            new_url = urljoin(page_url, href)
            if new_url in self.crawled or new_url in self.ignored:
                continue
            if not any([r.match(new_url) for r in self.domain_regex]):
                self.ignored.add(new_url)
                continue
            urls.append(new_url)
        return urls

    def crawl_urls(self, urls: list):
        new_urls = []
        for url in urls:
            if url in self.crawled or url in self.ignored:
                continue
            self.indexer.index_url(url, metadata={'url': url, 'source': 'docusaurus'})
            self.crawled.add(url)
            new_urls.extend(self._get_links(url))

        new_urls = list(set(new_urls)-self.crawled-self.ignored)
        self.crawl_urls(new_urls)

    def crawl(self):
        self.crawled = set()
        self.ignored = set()
        self.site_url = self.cfg.docusaurus_crawler.docs_homepage
        self.domain_regex = [re.compile(r) for r in self.cfg.docusaurus_crawler.url_regex]
        if self.site_url.endswith('/'):
            self.site_url = self.site_url[:-1]
        self.crawl_urls([self.site_url])
