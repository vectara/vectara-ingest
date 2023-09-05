import logging
import time
from core.crawler import Crawler
import feedparser
from datetime import datetime, timedelta
from time import mktime

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

        logging.info(f"Found {len(urls)} URLs to index from the last {self.cfg.rss_crawler.days_past} days ({source})")

        crawled_urls = set()        # sometimes same url (with diff title) may appear twice, so we keep track of crawled pages to avoid duplication.
        for url,title,pub_date in urls:
            if url in crawled_urls:
                logging.info(f"Skipping {url} since it was already crawled in this round")
                continue
            
            # index document into Vectara
            try:
                if pub_date:
                    pub_date_int = int(str(pub_date.timestamp()).split('.')[0])
                else:
                    pub_date_int = 0        # unknown published date
                    pub_date = 'unknown'
                crawl_date_int = int(str(today.timestamp()).split('.')[0])
                metadata = {
                    'source': source, 'url': url, 'title': title, 
                    'pub_date': str(pub_date), 'pub_date_int': pub_date_int,
                    'crawl_date': str(today),
                    'crawl_date_int': crawl_date_int
                }
                succeeded = self.indexer.index_url(url, metadata=metadata)
                if succeeded:
                    logging.info(f"Successfully indexed {url}")
                    crawled_urls.add(url)
                else:
                    logging.info(f"Indexing failed for {url}")
            except Exception as e:
                logging.error(f"Error while indexing {url}: {e}")
            time.sleep(delay_in_secs)

        return

