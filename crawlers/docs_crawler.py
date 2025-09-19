from bs4 import BeautifulSoup
import psutil
import time
import logging
logger = logging.getLogger(__name__)
import re
from typing import Tuple, Set
from collections import deque
from urllib.parse import urljoin, urlparse
import os

from core.crawler import Crawler
from core.utils import (
    create_session_with_retries, binary_extensions, RateLimiter, setup_logging,
    configure_session_for_ssl, get_docker_or_local_path, get_headers
)
from core.spider import run_link_spider_isolated
from core.indexer import Indexer

import ray

class UrlCrawlWorker(object):
    def __init__(self, indexer: Indexer, crawler: Crawler, num_per_second: int):
        self.indexer = indexer
        self.crawler = crawler
        self.rate_limiter = RateLimiter(num_per_second)

    def setup(self):
        self.indexer.setup()
        setup_logging()
    
    def cleanup(self):
        """Cleanup resources when worker is done"""
        if hasattr(self, 'indexer'):
            self.indexer.cleanup()

    def process(self, url: str, source: str):
        if url is None:
            logger.info("URL is None, skipping")
            return -1
        metadata = {"source": source, "url": url}
        logger.info(f"Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                succeeded = self.indexer.index_url(url, metadata=metadata, html_processing=self.crawler.html_processing)
            if not succeeded:
                logger.warning(f"Indexing failed for {url}")
            else:
                logger.info(f"Indexing {url} was successful")
        except Exception as e:
            import traceback
            logger.error(
                f"Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0

class DocsCrawler(Crawler):
    
    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        # Get scrape_method from docs_crawler config if available
        scrape_method = self.cfg.docs_crawler.get('scrape_method')
        if scrape_method:
            # Recreate indexer with the scrape_method
            from core.indexer import Indexer
            endpoint = args[0] if args else kwargs.get('endpoint')
            corpus_key = args[1] if len(args) > 1 else kwargs.get('corpus_key')
            api_key = args[2] if len(args) > 2 else kwargs.get('api_key')
            self.indexer = Indexer(cfg, endpoint, corpus_key, api_key, scrape_method=scrape_method)

    def concat_url_and_href(self, url: str, href: str) -> str:
        if href.startswith('http'):
            return href
        else:
            if 'index.html?' in href:
                href = href.replace('index.html?', '/')     # special fix for Spark docs
            joined = urljoin(url, href)
            return joined

    def get_url_content(self, url: str) -> Tuple[str, BeautifulSoup]:
        response = self.session.get(url, headers=get_headers(self.cfg))
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
            logger.warning(f"429 on {url}, sleeping for {wait}s")
            time.sleep(wait)
            response = self.session.get(url, headers=get_headers(self.cfg))
        if response.status_code != 200:
            logger.warning(f"Failed to crawl {url}, response code is {response.status_code}")
            return None, None

        # check for refresh redirect
        soup = BeautifulSoup(response.content, 'html.parser')
        meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
        if meta_refresh:
            href = meta_refresh['content'].split('url=')[-1]            # type: ignore
            url = self.concat_url_and_href(url, href)
            response = self.session.get(url, headers=get_headers(self.cfg))
            if response.status_code != 200:
                logger.warning(f"Failed to crawl redirect {url}, response code is {response.status_code}")
                return None, None

        page_content = BeautifulSoup(response.content, 'lxml')
        return url, page_content

    def collect_urls(self, base_url: str, num_per_second: int) -> None:
        new_urls = deque([base_url])
        rate_limiter = RateLimiter(num_per_second)
        # Crawl each URL in the queue
        while len(new_urls):
            n_urls = len(self.crawled_urls)
            if n_urls>0 and n_urls%100==0:
                logger.info(f"Currently have {n_urls} urls identified")

            # pop the left-most URL from new_urls
            url = new_urls.popleft()

            try:
                with rate_limiter:
                    url, page_content = self.get_url_content(url)
                if url is None:
                    continue
                self.crawled_urls.add(url)

                # Find all the new URLs in the page's content and add them into the queue
                if page_content:
                    for link in page_content.find_all('a'):
                        href = link.get('href')
                        if href is None:
                            continue
                        abs_url = self.concat_url_and_href(url, href)
                        if (abs_url.startswith(("http://", "https://")) and len(urlparse(abs_url).fragment) == 0 and
                            not any(abs_url.endswith(ext) for ext in self.extensions_to_ignore) and
                            any(r.search(abs_url) for r in self.pos_regex) and             # match any of the positive regexes
                            not any([r.search(abs_url) for r in self.neg_regex])):         # don't match any of the negative regexes
                            if abs_url not in self.crawled_urls and abs_url not in new_urls:
                                new_urls.append(abs_url)
                        else:
                            self.ignored_urls.add(abs_url)

            except Exception as e:
                import traceback
                logger.warning(f"Error crawling {url}: {e}, traceback={traceback.format_exc()}")
                continue

    def crawl(self) -> None:
        self.crawled_urls: Set[str] = set()
        self.ignored_urls: Set[str] = set()
        self.extensions_to_ignore = list(set(self.cfg.docs_crawler.extensions_to_ignore + binary_extensions))
        self.pos_regex = [re.compile(r) for r in self.cfg.docs_crawler.get("pos_regex", [])]
        self.neg_regex = [re.compile(r) for r in self.cfg.docs_crawler.get("neg_regex", [])]
        self.html_processing = self.cfg.docs_crawler.get('html_processing', {})

        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.docs_crawler)

        source = self.cfg.docs_crawler.docs_system
        ray_workers = self.cfg.docs_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        num_per_second = max(self.cfg.docs_crawler.get("num_per_second", 10), 1)

        if self.cfg.docs_crawler.get("crawl_method", "internal") == "scrapy":
            logger.info("Using Scrapy for crawling the docs")
            all_urls = run_link_spider_isolated(
                start_urls = self.cfg.docs_crawler.base_urls,
                positive_regexes = self.cfg.docs_crawler.get("pos_regex", []),
                negative_regexes = self.cfg.docs_crawler.get("neg_regex", []),
                max_depth = self.cfg.docs_crawler.get("max_depth", 3),
            )
            all_urls = [u for u in all_urls if u.startswith('http') and not any([u.endswith(ext) for ext in self.extensions_to_ignore])]
        else:
            logger.info("Using internal mechanism for crawling the docs")
            all_urls = []
            for base_url in self.cfg.docs_crawler.base_urls:
                self.collect_urls(base_url, num_per_second=num_per_second)
            all_urls = list(self.crawled_urls)
        all_urls = list(set(all_urls))      # final deduplication

        logger.info(f"Found {len(all_urls)} urls in {self.cfg.docs_crawler.base_urls}")
        if self.cfg.docs_crawler.get("crawl_report", False):
            logger.info(f"Collected {len(all_urls)} URLs to crawl and index. See urls_indexed.txt for a full report.")
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/urls_indexed.txt'
            filename = os.path.basename(docker_path)  # Extract just the filename
            file_path = get_docker_or_local_path(
                docker_path=docker_path,
                output_dir=output_dir
            )

            # If we're using a local path, make sure the filename is included
            if not file_path.endswith(filename):
                file_path = os.path.join(file_path, filename)

            with open(file_path, 'w') as f:
                for url in sorted(all_urls):
                    f.write(url + '\n')
        else:
            logger.info(f"Collected {len(all_urls)} URLs to crawl and index.")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)
        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(UrlCrawlWorker).remote(self.indexer, self, num_per_second) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u, source=source), all_urls))
            # Cleanup Ray workers
            for a in actors:
                ray.get(a.cleanup.remote())
            ray.shutdown()

        else:
            crawl_worker = UrlCrawlWorker(self.indexer, self, num_per_second)
            for inx, url in enumerate(all_urls):
                if inx % 100 == 0:
                    logger.info(f"Crawling URL number {inx+1} out of {len(all_urls)}")
                crawl_worker.process(url, source=source)
            # Cleanup worker
            crawl_worker.cleanup()

        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in the crawl list
        if self.cfg.docs_crawler.get("remove_old_content", False):
            existing_docs = self.indexer._list_docs()
            docs_to_remove = [t for t in existing_docs if t['url'] and t['url'] not in all_urls]
            for doc in docs_to_remove:
                if doc['url']:
                    self.indexer.delete_doc(doc['id'])
            logger.info(f"Removing {len(docs_to_remove)} docs that are not included in the crawl but are in the corpus.")
            if self.cfg.docs_crawler.get("crawl_report", False):
                output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
                docker_path = f'/home/vectara/{output_dir}/urls_removed.txt'
                filename = os.path.basename(docker_path)  # Extract just the filename
                file_path = get_docker_or_local_path(
                    docker_path=docker_path,
                    output_dir=output_dir
                )

                # If we're using a local path, make sure the filename is included
                if not file_path.endswith(filename):
                    file_path = os.path.join(file_path, filename)

                with open(file_path, 'w') as f:
                    for url in sorted([t['url'] for t in docs_to_remove if t['url']]):
                        f.write(url + '\n')
