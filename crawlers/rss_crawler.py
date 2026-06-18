import logging
logger = logging.getLogger(__name__)
import time
import ray
import psutil
from core.crawler import Crawler
from core.indexer import Indexer
from core.indexer_utils import normalize_url_for_metadata
from core.incremental import build_manifest, plan_deletions, source_is_newer
from core.utils import setup_logging
import feedparser
from datetime import datetime, timedelta
from time import mktime
from omegaconf import DictConfig

class RssUrlWorker(object):
    def __init__(self, cfg: DictConfig, indexer: Indexer, source: str, prior_fingerprints: dict = None):
        self.indexer = indexer
        self.cfg = cfg
        self.source = source
        # {normalized_url: fingerprint} from the prior corpus state; lets index_url skip an
        # unchanged entry after fetching. Empty unless incremental is enabled.
        self.prior_fingerprints = prior_fingerprints or {}

    def setup(self):
        self.indexer.setup()
        setup_logging()
    
    def cleanup(self):
        """Cleanup resources when worker is done"""
        if hasattr(self, 'indexer'):
            self.indexer.cleanup()

    def process(self, url_data: tuple):
        url, title, pub_date = url_data
        try:
            # index document into Vectara
            if pub_date:
                pub_date_int = int(str(pub_date.timestamp()).split('.')[0])
            else:
                pub_date_int = 0        # unknown published date
                pub_date = 'unknown'
            
            today = datetime.now().replace(microsecond=0)
            crawl_date_int = int(str(today.timestamp()).split('.')[0])
            metadata = {
                'source': self.source, 'url': url, 'title': title,
                'pub_date': str(pub_date), 'pub_date_int': pub_date_int,
                'crawl_date': str(today),
                'crawl_date_int': crawl_date_int
            }
            prior_fingerprint = self.prior_fingerprints.get(normalize_url_for_metadata(url))
            succeeded = self.indexer.index_url(url, metadata=metadata, prior_fingerprint=prior_fingerprint)
            if succeeded:
                logger.info(f"Successfully indexed {url}")
                return 1
            else:
                logger.info(f"Indexing failed for {url}")
                return 0
        except Exception as e:
            logger.error(f"Error while indexing {url}: {e}")
            return -1

class RssCrawler(Crawler):
    
    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        # Incremental reindexing state (see core/incremental.py).
        self.incremental = self.cfg.rss_crawler.get("incremental", False)
        # Get scrape_method from rss_crawler config if available
        scrape_method = self.cfg.rss_crawler.get('scrape_method')
        if scrape_method:
            # Recreate indexer with the scrape_method
            from core.indexer import Indexer
            endpoint = args[0] if args else kwargs.get('endpoint')
            corpus_key = args[1] if len(args) > 1 else kwargs.get('corpus_key')
            api_key = args[2] if len(args) > 2 else kwargs.get('api_key')
            self.indexer = Indexer(cfg, endpoint, corpus_key, api_key, scrape_method=scrape_method)

    def crawl(self) -> None:
        """
        Crawl RSS feeds and upload to Vectara.
        """
        rss_pages = self.cfg.rss_crawler.rss_pages
        source = self.cfg.rss_crawler.source
        if isinstance(rss_pages, str):
            rss_pages = [rss_pages]
        delay_in_secs = self.cfg.rss_crawler.delay
        ray_workers = self.cfg.rss_crawler.get("ray_workers", 0)
        today = datetime.now().replace(microsecond=0)
        days_ago = today - timedelta(days=self.cfg.rss_crawler.days_past)

        # collect all URLs from the RSS feeds
        urls = []
        for rss_page in rss_pages:
            feed = feedparser.parse(rss_page)
            for entry in feed.entries:
                if "published_parsed" not in entry:
                    urls.append([entry.link, entry.title, None])
                    continue
                entry_date = datetime.fromtimestamp(mktime(entry.published_parsed))
                if entry_date >= days_ago and entry_date <= today:
                    urls.append([entry.link, entry.title, entry_date])

        # Remove duplicates while preserving order
        unique_urls = []
        seen_urls = set()
        for url, title, pub_date in urls:
            if url not in seen_urls:
                unique_urls.append((url, title, pub_date))
                seen_urls.add(url)
            else:
                logger.debug(f"Skipping duplicate URL {url}")
        logger.info(f"After deduplication, we have found {len(unique_urls)} URLs to index from the last {self.cfg.rss_crawler.days_past} days ({source})")

        # Incremental reindexing: build the corpus manifest once, source-scoped, then use it
        # for a Layer-1 pre-fetch skip (pub_date not newer than what we last indexed) and to
        # pass prior fingerprints to the workers (Layer-2 post-fetch skip).
        remove_old_content = self.cfg.rss_crawler.get("remove_old_content", False)
        manifest = {}
        prior_fingerprints = {}
        # Every feed entry in the window is "present at source" for the deletion diff.
        present_keys = {normalize_url_for_metadata(u) for u, _t, _p in unique_urls}
        if self.incremental or remove_old_content:
            manifest = build_manifest(self.indexer, key="url",
                                      source=(source if self.incremental else None))
            logger.info(f"Loaded corpus manifest: {len(manifest)} existing documents")
        if self.incremental and manifest:
            prior_fingerprints = {k: e.fingerprint for k, e in manifest.items() if e.fingerprint}
            kept = []
            skipped = 0
            for url, title, pub_date in unique_urls:
                entry = manifest.get(normalize_url_for_metadata(url))
                if entry and entry.last_updated and not source_is_newer(pub_date, entry.last_updated):
                    skipped += 1
                    continue
                kept.append((url, title, pub_date))
            unique_urls = kept
            if skipped:
                logger.info(f"Incremental: skipped {skipped} unchanged entries via pub_date "
                            f"({len(unique_urls)} remaining to index)")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        crawl_completed = False
        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers to process {len(unique_urls)} URLs")
            # Disable browser for parallel processing
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [
                ray.remote(RssUrlWorker).remote(self.cfg, self.indexer, source, prior_fingerprints)
                for _ in range(ray_workers)
            ]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            results = list(pool.map(lambda a, u: a.process.remote(u), unique_urls))
            
            # Log summary
            successful = sum(1 for r in results if r == 1)
            failed = sum(1 for r in results if r == 0)
            errors = sum(1 for r in results if r == -1)
            logger.info(f"RSS crawling complete: {successful} successful, {failed} failed, {errors} errors")
            
            # Cleanup Ray workers
            for a in actors:
                ray.get(a.cleanup.remote())
            ray.shutdown()
        else:
            # Sequential processing (original behavior)
            rss_worker = RssUrlWorker(self.cfg, self.indexer, source, prior_fingerprints)
            rss_worker.setup()
            successful = 0
            for inx, url_data in enumerate(unique_urls):
                if (inx + 1) % 10 == 0:
                    logger.info(f"Processing URL {inx+1} out of {len(unique_urls)}")
                result = rss_worker.process(url_data)
                if result == 1:
                    successful += 1
                if delay_in_secs > 0:
                    time.sleep(delay_in_secs)
            # Cleanup worker
            rss_worker.cleanup()
            logger.info(f"RSS crawling complete: {successful} URLs successfully indexed")
        crawl_completed = True

        # Delete corpus docs not present in the current feed window — opt-in via
        # remove_old_content (NOT auto-enabled by incremental). Note: RSS only sees the last
        # `days_past` days, so this removes any corpus doc older than the window. Enable it only
        # if you want the corpus to mirror the current feed rather than accumulate history.
        if remove_old_content:
            listing_complete = crawl_completed and len(present_keys) > 0
            ratio = self.cfg.rss_crawler.get("deletion_safety_ratio", 0.5)
            to_delete, refused = plan_deletions(manifest, present_keys, listing_complete, ratio)
            if not refused:
                to_delete_set = set(to_delete)
                for entry in manifest.values():
                    if entry.doc_id in to_delete_set:
                        self.indexer.delete_doc(entry.doc_id)
                logger.info(f"Removed {len(to_delete)} docs that are no longer present in the RSS feeds.")

        return
