import re
import logging
import psutil
import os

from core.crawler import Crawler
from core.utils import clean_urls, archive_extensions, img_extensions, get_file_extension, RateLimiter, setup_logging, get_urls_from_sitemap, get_docker_or_local_path
from core.indexer import Indexer
from core.spider import run_link_spider_isolated, recursive_crawl

import ray


class PageCrawlWorker(object):
    def __init__(self, indexer: Indexer, crawler: Crawler, num_per_second: int):
        self.crawler = crawler
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, url: str, source: str):
        metadata = {"source": source, "url": url}
        logging.info(f"Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                succeeded = self.indexer.index_url(url, metadata=metadata, html_processing=self.crawler.html_processing)
            if not succeeded:
                logging.info(f"Indexing failed for {url}")
            else:
                logging.info(f"Indexing {url} was successful")
        except Exception as e:
            import traceback
            logging.error(
                f"Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0

class WebsiteCrawler(Crawler):
    def crawl(self) -> None:
        base_urls = self.cfg.website_crawler.urls
        self.pos_regex = self.cfg.website_crawler.get("pos_regex", [])
        self.pos_patterns = [re.compile(r) for r in self.pos_regex]
        self.neg_regex = self.cfg.website_crawler.get("neg_regex", [])
        self.neg_patterns = [re.compile(r) for r in self.neg_regex]
        keep_query_params = self.cfg.website_crawler.get('keep_query_params', False)
        self.html_processing = self.cfg.website_crawler.get('html_processing', {})
        max_depth = self.cfg.website_crawler.get("max_depth", 3)


        if self.cfg.website_crawler.get("crawl_method", "internal") == "scrapy":
            logging.info("Using Scrapy to crawl the website")
            all_urls = run_link_spider_isolated(
                start_urls = base_urls,
                positive_regexes = self.pos_regex,
                negative_regexes = self.neg_regex,
                max_depth = max_depth,
            )
        else:
            logging.info("Using internal Vectara-ingest method to crawl the website")
            all_urls = []
            for homepage in base_urls:
                if self.cfg.website_crawler.pages_source == "sitemap":
                    urls = get_urls_from_sitemap(homepage)
                elif self.cfg.website_crawler.pages_source == "crawl":
                    urls_set = recursive_crawl(
                        homepage, max_depth, 
                        pos_patterns=self.pos_patterns, neg_patterns=self.neg_patterns,
                        indexer=self.indexer, visited=set(), verbose=self.indexer.verbose
                    )
                    urls = clean_urls(urls_set, keep_query_params)
                else:
                    logging.info(f"Unknown pages_source: {self.cfg.website_crawler.pages_source}")
                    return
                logging.info(f"Found {len(urls)} URLs on {homepage}")
                all_urls += urls

        # remove URLS that are out of our regex regime or are archives or images
        urls = [u for u in all_urls if u.startswith('http') and not any([u.endswith(ext) for ext in archive_extensions + img_extensions])]
        if self.pos_regex and len(self.pos_regex)>0:
            urls = [u for u in all_urls if any([r.match(u) for r in self.pos_patterns])]
        if self.neg_regex and len(self.neg_regex)>0:
            urls = [u for u in all_urls if not any([r.match(u) for r in self.neg_patterns])]
        urls = list(set(urls))

        # Store URLS in crawl_report if needed
        if self.cfg.website_crawler.get("crawl_report", False):
            logging.info(f"Collected {len(urls)} URLs to crawl and index. See urls_indexed.txt for a full report.")
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = '/home/vectara/env/urls_indexed.txt'
            filename = os.path.basename(docker_path)  # Extract just the filename
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
            logging.info(f"Collected {len(urls)} URLs to crawl and index.")

        # print some file types
        file_types = list(set([get_file_extension(u) for u in urls]))
        file_types = [t for t in file_types if t != ""]
        logging.info(f"Note: file types = {file_types}")

        num_per_second = max(self.cfg.website_crawler.get("num_per_second", 10), 1)
        ray_workers = self.cfg.website_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        source = self.cfg.website_crawler.get("source", "website")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(PageCrawlWorker).remote(self.indexer, self, num_per_second) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u, source=source), urls))
                
        else:
            crawl_worker = PageCrawlWorker(self.indexer, self, num_per_second)
            for inx, url in enumerate(urls):
                if inx % 100 == 0:
                    logging.info(f"Crawling URL number {inx+1} out of {len(urls)}")
                crawl_worker.process(url, source=source)

        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in the crawl list
        if self.cfg.website_crawler.get("remove_old_content", False):
            existing_docs = self.indexer._list_docs()
            docs_to_remove = [t for t in existing_docs if t['url'] and t['url'] not in urls]
            for doc in docs_to_remove:
                if doc['url']:
                    self.indexer.delete_doc(doc['id'])
            logging.info(f"Removing {len(docs_to_remove)} docs that are not included in the crawl but are in the corpus.")
            if self.cfg.website_crawler.get("crawl_report", False):
                output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
                docker_path = '/home/vectara/env/urls_removed.txt'
                filename = os.path.basename(docker_path)  # Extract just the filename
                file_path = get_docker_or_local_path(
                    docker_path=docker_path,
                    output_dir=output_dir
                )
                
                if not file_path.endswith(filename):
                    file_path = os.path.join(file_path, filename)
                    
                with open(file_path, 'w') as f:
                    for url in sorted([t['url'] for t in docs_to_remove if t['url']]):
                        f.write(url + '\n')


