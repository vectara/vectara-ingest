import re
import logging
import psutil
import os
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from core.crawler import Crawler
from core.utils import (
    RateLimiter, setup_logging, get_docker_or_local_path,
    url_matches_patterns, normalize_vectara_endpoint
)
from core.indexer import Indexer
from scrapy import Spider, Request
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
import requests

import ray

logger = logging.getLogger(__name__)


def extract_jsonld_metadata(url: str) -> Dict[str, Any]:
    """
    Extract JSON-LD metadata from the TechDocs page.

    Extracts and maps fields to match corpus schema:
    - techdocs_language (from jsonLD.language)
    - product (from jsonLD.productname)
    - version (from jsonLD.siteversion)
    - space_name (from jsonLD.spacename)
    - current_page_title (from jsonLD.currentpagetitle)
    - url (from jsonLD.url)
    - hid (from meta tag or data-hid attribute)

    Args:
        url: URL of the page to extract metadata from

    Returns:
        Dictionary with extracted metadata fields
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the JSON-LD script tag
        jsonld_script = soup.find('script', {'type': 'application/ld+json'})

        if not jsonld_script:
            logger.warning(f"No JSON-LD script found for {url}")
            return {}

        # Parse JSON-LD
        jsonld_data = json.loads(jsonld_script.string)

        # Extract and map fields to match corpus schema
        metadata = {}

        # Map JSON-LD fields to corpus schema field names
        field_mapping = {
            'language': 'techdocs_language',
            'productname': 'product',
            'siteversion': 'version',
            'spacename': 'space_name',
            'currentpagetitle': 'current_page_title',
            'url': 'url',
        }

        for jsonld_field, corpus_field in field_mapping.items():
            if jsonld_field in jsonld_data:
                value = jsonld_data[jsonld_field]
                if value:  # Only add non-empty values
                    metadata[corpus_field] = str(value)

        # Extract hid field from page
        hid_meta = soup.find('meta', {'name': 'hid'}) or soup.find('meta', {'property': 'hid'})
        if hid_meta and hid_meta.get('content'):
            metadata['hid'] = hid_meta.get('content')
        else:
            # Look for data-hid attribute in any element
            hid_element = soup.find(attrs={'data-hid': True})
            if hid_element:
                metadata['hid'] = hid_element.get('data-hid')
            else:
                metadata['hid'] = ''

        logger.debug(f"Extracted {len(metadata)} metadata fields from {url}")
        return metadata

    except Exception as e:
        logger.error(f"Error extracting JSON-LD metadata from {url}: {e}")
        return {}


class TechDocsSpider(Spider):
    """Scrapy spider for crawling techdocs pages."""
    name = 'techdocs'

    def __init__(self, start_urls: List[str], pos_patterns: List[re.Pattern],
                 neg_patterns: List[re.Pattern], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls
        self.pos_patterns = pos_patterns
        self.neg_patterns = neg_patterns
        self.discovered_urls = set()

    def start_requests(self):
        for url in self.start_urls:
            yield Request(url, callback=self.parse, dont_filter=True)

    def parse(self, response: Response):
        """Parse the page and extract the URL."""
        url = response.url

        # Filter by patterns
        if url_matches_patterns(url, self.pos_patterns, self.neg_patterns):
            self.discovered_urls.add(url)
            logger.debug(f"Discovered URL: {url}")


def download_and_parse_sitemap(sitemap_url: str) -> List[str]:
    """
    Download an XML sitemap and extract all URLs from it.

    Args:
        sitemap_url: URL to the sitemap XML file

    Returns:
        List of URLs found in the sitemap
    """
    try:
        logger.info(f"Downloading sitemap from {sitemap_url}")
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)

        # Handle namespace in sitemap
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        # Extract all <loc> elements
        urls = []
        for loc in root.findall('.//ns:loc', namespace):
            if loc.text:
                urls.append(loc.text.strip())

        # Also try without namespace (some sitemaps don't use it)
        if not urls:
            for loc in root.findall('.//loc'):
                if loc.text:
                    urls.append(loc.text.strip())

        logger.info(f"Extracted {len(urls)} URLs from sitemap {sitemap_url}")
        return urls

    except Exception as e:
        logger.error(f"Error downloading/parsing sitemap {sitemap_url}: {e}")
        return []


def run_techdocs_spider_isolated(start_urls: List[str], positive_regexes: List[str],
                                   negative_regexes: List[str]) -> List[str]:
    """
    Run the Scrapy spider in isolated process mode to collect URLs.

    Args:
        start_urls: List of URLs to scrape
        positive_regexes: List of regex patterns for URLs to include
        negative_regexes: List of regex patterns for URLs to exclude

    Returns:
        List of discovered URLs
    """
    logger.info(f"Running techdocs spider with {len(start_urls)} URLs")

    pos_patterns = [re.compile(r) for r in positive_regexes]
    neg_patterns = [re.compile(r) for r in negative_regexes]

    process = CrawlerProcess(settings={
        'LOG_LEVEL': 'INFO',
        'USER_AGENT': 'Mozilla/5.0 (compatible; VectaraTechDocsCrawler/1.0)',
        'ROBOTSTXT_OBEY': True,
        'CONCURRENT_REQUESTS': 16,
        'DOWNLOAD_DELAY': 0.5,
        'COOKIES_ENABLED': False,
    })

    spider = TechDocsSpider(
        start_urls=start_urls,
        pos_patterns=pos_patterns,
        neg_patterns=neg_patterns
    )

    process.crawl(spider)
    process.start()

    discovered = list(spider.discovered_urls)
    logger.info(f"Spider discovered {len(discovered)} URLs")
    return discovered


class PageCrawlWorker(object):
    """Worker for crawling and indexing individual pages."""

    def __init__(self, cfg: dict, num_per_second: int, success_file: str = None, failed_file: str = None):
        self.cfg = cfg
        self.rate_limiter = RateLimiter(num_per_second)
        self.indexer = None
        techdocs_cfg = self.cfg.get('techdocs_crawler', {})
        self.html_processing = techdocs_cfg.get('html_processing', {})
        self.scrape_method = techdocs_cfg.get('scrape_method', 'playwright')
        self.success_file = success_file
        self.failed_file = failed_file

    def setup(self):
        """Initialize the worker's resources (Indexer) within the Ray process."""
        setup_logging()

        vectara_cfg = self.cfg.get('vectara', {})
        api_url = normalize_vectara_endpoint(vectara_cfg.get('endpoint'))
        corpus_key = vectara_cfg['corpus_key']
        api_key = vectara_cfg['api_key']

        self.indexer = Indexer(self.cfg, api_url, corpus_key, api_key, scrape_method=self.scrape_method)
        self.indexer.setup()

    def cleanup(self):
        """Cleanup resources when worker is done."""
        if hasattr(self, 'indexer'):
            self.indexer.cleanup()

    def _append_to_file(self, filepath: str, url: str):
        """Thread-safe append URL to file."""
        if filepath:
            try:
                with open(filepath, 'a') as f:
                    f.write(url + '\n')
                    f.flush()
            except Exception as e:
                logging.error(f"Failed to write URL to {filepath}: {e}")

    def process(self, url: str, source: str):
        """Process a single URL: scrape and index it."""
        if not self.indexer:
            logging.error(f"[Worker {os.getpid()}] Indexer not set up. Call setup() before process().")
            self._append_to_file(self.failed_file, url)
            return -1

        # Start with basic metadata
        metadata = {
            "source": source,
            "url": url,
            "is_public": True  # TechDocs are public documentation
        }

        # Extract JSON-LD metadata from the page
        # Note: This will fetch the page once to extract metadata
        # The indexer will fetch it again for content extraction
        # This is acceptable for now to get rich metadata
        try:
            logging.info(f"[Worker {os.getpid()}] Extracting metadata from {url}")
            jsonld_metadata = extract_jsonld_metadata(url)
            if jsonld_metadata:
                metadata.update(jsonld_metadata)
                logging.info(f"[Worker {os.getpid()}] Extracted {len(jsonld_metadata)} metadata fields from {url}")
            else:
                logging.warning(f"[Worker {os.getpid()}] No JSON-LD metadata found for {url}")
        except Exception as e:
            logging.warning(f"[Worker {os.getpid()}] Failed to extract JSON-LD metadata from {url}: {e}")

        logging.info(f"[Worker {os.getpid()}] Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                succeeded = self.indexer.index_url(url, metadata=metadata, html_processing=self.html_processing)
            if not succeeded:
                logging.info(f"[Worker {os.getpid()}] Indexing failed for {url}")
                self._append_to_file(self.failed_file, url)
                return -1
            else:
                logging.info(f"[Worker {os.getpid()}] Indexing {url} was successful")
                self._append_to_file(self.success_file, url)
                return 0
        except Exception as e:
            import traceback
            logging.error(
                f"[Worker {os.getpid()}] Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
            )
            self._append_to_file(self.failed_file, url)
            return -1


class TechdocsCrawler(Crawler):
    """
    Crawler for Broadcom TechDocs that processes sitemap XML files.
    """

    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        self._setup_tracking_files()

    def _setup_tracking_files(self):
        """Setup file paths for tracking crawled and failed URLs."""
        output_dir = self.cfg.vectara.get("output_dir", "vectara-ingest-output")
        docker_path = f'/home/vectara/{output_dir}/techdocs'

        self.tracking_dir = get_docker_or_local_path(
            docker_path=docker_path,
            output_dir=os.path.join(output_dir, "techdocs")
        )

        # Create directory if it doesn't exist
        os.makedirs(self.tracking_dir, exist_ok=True)

        self.success_file = os.path.join(self.tracking_dir, "crawled_urls.txt")
        self.failed_file = os.path.join(self.tracking_dir, "failed_urls.txt")

        logger.info(f"Tracking files: success={self.success_file}, failed={self.failed_file}")

    def _load_already_crawled_urls(self) -> set:
        """Load URLs that were already successfully crawled."""
        crawled_urls = set()
        if os.path.exists(self.success_file):
            try:
                with open(self.success_file, 'r') as f:
                    for line in f:
                        url = line.strip()
                        if url:
                            crawled_urls.add(url)
                logger.info(f"Loaded {len(crawled_urls)} already-crawled URLs from {self.success_file}")
            except Exception as e:
                logger.error(f"Error loading crawled URLs: {e}")
        return crawled_urls

    def crawl(self) -> None:
        """Main crawl orchestration method."""
        # 1. Discover all URLs from sitemaps
        all_urls = self._discover_urls_from_sitemaps()

        # 2. Filter and prepare the final URL list
        urls_to_crawl = self._filter_and_prepare_urls(all_urls)

        # 3. Load already-crawled URLs and skip them
        already_crawled = self._load_already_crawled_urls()
        if already_crawled:
            original_count = len(urls_to_crawl)
            urls_to_crawl = [url for url in urls_to_crawl if url not in already_crawled]
            skipped_count = original_count - len(urls_to_crawl)
            logger.info(f"Skipping {skipped_count} already-crawled URLs. Remaining: {len(urls_to_crawl)}")

        # 4. Dispatch the jobs to workers (Ray or single process)
        self._dispatch_crawl_jobs(urls_to_crawl)

        # 5. Handle post-crawl cleanup
        self._remove_old_content_if_needed(urls_to_crawl)

    def _discover_urls_from_sitemaps(self) -> List[str]:
        """
        Download and parse all sitemap URLs to extract page URLs.

        Returns:
            List of all URLs discovered from sitemaps
        """
        sitemap_urls = self.cfg.techdocs_crawler.sitemap_urls
        self.pos_regex = self.cfg.techdocs_crawler.get("pos_regex", [])
        self.pos_patterns = [re.compile(r) for r in self.pos_regex]
        self.neg_regex = self.cfg.techdocs_crawler.get("neg_regex", [])
        self.neg_patterns = [re.compile(r) for r in self.neg_regex]

        logger.info(f"Processing {len(sitemap_urls)} sitemap(s)")

        all_urls = []
        for sitemap_url in sitemap_urls:
            urls = download_and_parse_sitemap(sitemap_url)

            # Filter URLs by patterns
            filtered_urls = [
                url for url in urls
                if url_matches_patterns(url, self.pos_patterns, self.neg_patterns)
            ]

            logger.info(f"Sitemap {sitemap_url}: {len(urls)} total, {len(filtered_urls)} after filtering")
            all_urls.extend(filtered_urls)

        logger.info(f"Total URLs discovered from all sitemaps: {len(all_urls)}")
        return all_urls

    def _filter_and_prepare_urls(self, all_urls: List[str]) -> List[str]:
        """
        Filter and deduplicate URLs, and generate crawl report.

        Args:
            all_urls: List of URLs to filter

        Returns:
            Final list of URLs to crawl
        """
        # Deduplicate
        urls = list(set(all_urls))

        logger.info(f"After deduplication: {len(urls)} unique URLs")

        # Store URLs in crawl_report if needed
        if self.cfg.techdocs_crawler.get("crawl_report", False):
            logger.info(f"Collected {len(urls)} URLs to crawl and index. See urls_indexed.txt for a full report.")
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/urls_indexed.txt'
            filename = os.path.basename(docker_path)
            file_path = get_docker_or_local_path(
                docker_path=docker_path,
                output_dir=output_dir
            )

            if not file_path.endswith(filename):
                file_path = os.path.join(file_path, filename)

            with open(file_path, 'w') as f:
                for url in sorted(urls):
                    f.write(url + '\n')
        else:
            logger.info(f"Collected {len(urls)} URLs to crawl and index.")

        return urls

    def _dispatch_crawl_jobs(self, urls: List[str]):
        """
        Dispatch crawl jobs to Ray workers or process sequentially.

        Args:
            urls: List of URLs to crawl
        """
        num_per_second = max(self.cfg.techdocs_crawler.get("num_per_second", 10), 1)
        ray_workers = self.cfg.techdocs_crawler.get("ray_workers", 0)
        source = self.cfg.techdocs_crawler.get("source", "techdocs")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            self._dispatch_to_ray_workers(urls, ray_workers, num_per_second, source)
        else:
            self._dispatch_to_single_process(urls, num_per_second, source)

    def _dispatch_to_ray_workers(self, urls: List[str], ray_workers: int, num_per_second: int, source: str):
        """Dispatch jobs to Ray workers for parallel processing."""
        logger.info(f"Using {ray_workers} ray workers")
        self.indexer.p = self.indexer.browser = None
        ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)

        # Create workers with tracking file paths
        actors = [ray.remote(PageCrawlWorker).remote(
            self.cfg,
            num_per_second,
            self.success_file,
            self.failed_file
        ) for _ in range(ray_workers)]
        ray.get([a.setup.remote() for a in actors])
        pool = ray.util.ActorPool(actors)
        _ = list(pool.map(lambda a, u: a.process.remote(u, source=source), urls))

        # Cleanup Ray workers
        for a in actors:
            ray.get(a.cleanup.remote())
        ray.shutdown()

    def _dispatch_to_single_process(self, urls: List[str], num_per_second: int, source: str):
        """Process URLs sequentially in a single process."""
        import time

        # Apply max_urls limit if configured
        max_urls = self.cfg.techdocs_crawler.get("max_urls", None)
        total_urls_in_sitemap = len(urls)
        if max_urls and max_urls > 0:
            urls = urls[:max_urls]
            logger.info(f"Limited to first {max_urls} URLs (out of {total_urls_in_sitemap} total)")

        crawl_worker = PageCrawlWorker(
            self.cfg,
            num_per_second,
            self.success_file,
            self.failed_file
        )
        crawl_worker.setup()

        success_count = 0
        failed_count = 0
        start_time = time.time()

        for inx, url in enumerate(urls):
            if inx % 100 == 0 and inx > 0:
                elapsed = time.time() - start_time
                avg_time_per_url = elapsed / inx
                remaining_urls = len(urls) - inx
                estimated_remaining = avg_time_per_url * remaining_urls

                logger.info(f"Crawling URL {inx+1}/{len(urls)} - Success: {success_count}, Failed: {failed_count}")
                logger.info(f"  Average: {avg_time_per_url:.2f}s/URL, Elapsed: {elapsed/60:.1f}min, ETA: {estimated_remaining/60:.1f}min")

            result = crawl_worker.process(url, source=source)
            if result == 0:
                success_count += 1
            else:
                failed_count += 1

        # Cleanup worker
        crawl_worker.cleanup()

        # Calculate final metrics
        total_time = time.time() - start_time
        avg_time_per_url = total_time / len(urls) if len(urls) > 0 else 0

        logger.info(f"\n{'='*80}")
        logger.info(f"CRAWL METRICS SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"Total URLs crawled: {len(urls)}")
        logger.info(f"Success: {success_count} ({success_count/len(urls)*100:.1f}%)")
        logger.info(f"Failed: {failed_count} ({failed_count/len(urls)*100:.1f}%)")
        logger.info(f"Total time: {total_time/60:.2f} minutes ({total_time/3600:.2f} hours)")
        logger.info(f"Average time per URL: {avg_time_per_url:.2f} seconds")
        logger.info(f"Throughput: {len(urls)/total_time*60:.1f} URLs/minute")

        # Projections for different scales
        if total_urls_in_sitemap > len(urls):
            logger.info(f"\n{'='*80}")
            logger.info(f"PROJECTIONS (based on current performance)")
            logger.info(f"{'='*80}")

            # Projection for all URLs in sitemap
            estimated_sitemap_time = avg_time_per_url * total_urls_in_sitemap
            logger.info(f"All sitemap URLs ({total_urls_in_sitemap:,} URLs):")
            logger.info(f"  Estimated time: {estimated_sitemap_time/3600:.1f} hours ({estimated_sitemap_time/86400:.1f} days)")

            # Projection for 2 million URLs
            estimated_2m_time = avg_time_per_url * 2_000_000
            logger.info(f"2 Million URLs:")
            logger.info(f"  Estimated time: {estimated_2m_time/3600:.1f} hours ({estimated_2m_time/86400:.1f} days)")

            # With parallelization
            cpu_count = psutil.cpu_count(logical=True)
            estimated_2m_parallel = estimated_2m_time / cpu_count
            logger.info(f"2 Million URLs (with {cpu_count} parallel workers):")
            logger.info(f"  Estimated time: {estimated_2m_parallel/3600:.1f} hours ({estimated_2m_parallel/86400:.1f} days)")

        logger.info(f"{'='*80}")
        logger.info(f"Success URLs saved to: {self.success_file}")
        logger.info(f"Failed URLs saved to: {self.failed_file}")
        logger.info(f"{'='*80}\n")

    def _remove_old_content_if_needed(self, crawled_urls: List[str]):
        """
        Remove old content from corpus if remove_old_content is enabled.

        Args:
            crawled_urls: List of URLs that were crawled
        """
        if not self.cfg.techdocs_crawler.get("remove_old_content", False):
            return

        existing_docs = self.indexer._list_docs()
        docs_to_remove = [t for t in existing_docs if t['url'] and t['url'] not in crawled_urls]
        for doc in docs_to_remove:
            if doc['url']:
                self.indexer.delete_doc(doc['id'])
        logger.info(f"Removed {len(docs_to_remove)} docs that are not included in the crawl but are in the corpus.")

        if self.cfg.techdocs_crawler.get("crawl_report", False):
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/urls_removed.txt'
            filename = os.path.basename(docker_path)
            file_path = get_docker_or_local_path(
                docker_path=docker_path,
                output_dir=output_dir
            )

            if not file_path.endswith(filename):
                file_path = os.path.join(file_path, filename)

            with open(file_path, 'w') as f:
                for url in sorted([t['url'] for t in docs_to_remove if t['url']]):
                    f.write(url + '\n')
