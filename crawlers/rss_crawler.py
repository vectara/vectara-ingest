import logging
logger = logging.getLogger(__name__)
import time
import ray
import psutil
from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import setup_logging
import feedparser
from datetime import datetime, timedelta
from time import mktime
from omegaconf import DictConfig

class RssUrlWorker(object):
    def __init__(self, cfg: DictConfig, indexer: Indexer, source: str):
        self.indexer = indexer
        self.cfg = cfg
        self.source = source

    def setup(self):
        self.indexer.setup()
        setup_logging()

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
            succeeded = self.indexer.index_url(url, metadata=metadata)
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

    def crawl(self) -> None:
        """
        Crawl RSS feeds and upload to Vectara.
        """
        rss_pages = self.cfg.rss_crawler.rss_pages
        source = self.cfg.rss_crawler.source
        if type(rss_pages) == str:
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

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers to process {len(unique_urls)} URLs")
            # Disable browser for parallel processing
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [
                ray.remote(RssUrlWorker).remote(self.cfg, self.indexer, source)
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
        else:
            # Sequential processing (original behavior)
            rss_worker = RssUrlWorker(self.cfg, self.indexer, source)
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
            logger.info(f"RSS crawling complete: {successful} URLs successfully indexed")

        return
