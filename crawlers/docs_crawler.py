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
from core.crawl_tracker import CrawlShutdownException
from core.utils import (
    create_session_with_retries, binary_extensions, RateLimiter, setup_logging,
    configure_session_for_ssl, get_docker_or_local_path, get_headers
)
from core.spider import run_link_spider_isolated
from core.indexer import Indexer
from core.indexer_utils import normalize_url_for_metadata
from core.incremental import build_manifest, plan_deletions

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
        prior_fingerprint = self.crawler.prior_fingerprints.get(normalize_url_for_metadata(url))
        logger.info(f"Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                succeeded = self.indexer.index_url(
                    url, metadata=metadata, html_processing=self.crawler.html_processing,
                    prior_fingerprint=prior_fingerprint)
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
        # Incremental reindexing state (see core/incremental.py).
        self.incremental = self.cfg.docs_crawler.get("incremental", False)
        self.source = self.cfg.docs_crawler.get("source", self.cfg.docs_crawler.docs_system)
        # {normalized_url: fingerprint} from the prior corpus state; lets index_url skip
        # an unchanged page. Populated in crawl() when incremental is enabled.
        self.prior_fingerprints = {}
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
                            not any(abs_url.lower().endswith(ext) for ext in self.extensions_to_ignore) and
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
        self.extensions_to_ignore = list({e.lower() if isinstance(e, str) else e for e in (self.cfg.docs_crawler.extensions_to_ignore + binary_extensions)})
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
            all_urls = [u for u in all_urls if u.startswith('http') and not any([u.lower().endswith(ext) for ext in self.extensions_to_ignore])]
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

        # Build the corpus manifest once when incremental skipping or deletion needs it.
        # Source-scoped in incremental mode so a shared corpus is not cross-deleted; left
        # unscoped for legacy remove_old_content to preserve its behavior.
        manifest = {}
        if self.incremental or self.cfg.docs_crawler.get("remove_old_content", False):
            manifest_source = self.indexer.source_tag if self.incremental else None
            manifest = build_manifest(self.indexer, key="url", source=manifest_source)
            logger.info(f"Loaded corpus manifest: {len(manifest)} existing documents")
        if self.incremental:
            self.prior_fingerprints = {k: e.fingerprint for k, e in manifest.items() if e.fingerprint}

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)
        # Tracks whether the crawl ran to completion; an interruption (shutdown/exception) leaves
        # it False so the deletion pass below refuses to treat a partial crawl as the full source.
        crawl_completed = False
        try:
            if ray_workers > 0:
                logger.info(f"Using {ray_workers} ray workers")
                self.indexer.p = self.indexer.browser = None
                ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
                actors = [ray.remote(UrlCrawlWorker).remote(self.indexer, self, num_per_second) for _ in range(ray_workers)]
                for a in actors:
                    a.setup.remote()
                pool = ray.util.ActorPool(actors)
                # Batch like the other crawlers so check_shutdown can interrupt mid-run and the
                # full result vector isn't buffered at once.
                batch_size = max(ray_workers * 4, 20)
                for batch_start in range(0, len(all_urls), batch_size):
                    self.check_shutdown()
                    batch = all_urls[batch_start:batch_start + batch_size]
                    list(pool.map(lambda a, u: a.process.remote(u, source=source), batch))
                # Cleanup Ray workers
                for a in actors:
                    ray.get(a.cleanup.remote())

            else:
                crawl_worker = UrlCrawlWorker(self.indexer, self, num_per_second)
                for inx, url in enumerate(all_urls):
                    self.check_shutdown()
                    if inx % 100 == 0:
                        logger.info(f"Crawling URL number {inx+1} out of {len(all_urls)}")
                    crawl_worker.process(url, source=source)
                # Cleanup worker
                crawl_worker.cleanup()
            crawl_completed = True
        except CrawlShutdownException:
            crawl_completed = False
            raise
        finally:
            # Always release Ray, even if check_shutdown() or a worker task raised mid-crawl —
            # otherwise the cluster and its worker processes leak into subsequent runs.
            if ray_workers > 0:
                ray.shutdown()

        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in the crawl list,
        # guarded by plan_deletions against a partial/interrupted crawl mass-deleting live docs.
        if self.cfg.docs_crawler.get("remove_old_content", False):
            present_keys = {normalize_url_for_metadata(u) for u in all_urls if u}
            listing_complete = crawl_completed and len(present_keys) > 0
            ratio = self.cfg.docs_crawler.get("deletion_safety_ratio", 0.5)
            to_delete, refused = plan_deletions(manifest, present_keys, listing_complete, ratio)
            removed_urls = []
            if not refused:
                to_delete_set = set(to_delete)
                for entry in manifest.values():
                    if entry.doc_id in to_delete_set:
                        if self.indexer.delete_doc(entry.doc_id) and entry.url:
                            removed_urls.append(entry.url)
            logger.info(f"Removing {len(to_delete)} docs that are not included in the crawl but are in the corpus.")
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
                    for url in sorted(removed_urls):
                        f.write(url + '\n')
