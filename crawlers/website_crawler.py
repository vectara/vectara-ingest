import re
import logging
import psutil
import os

from core.crawler import Crawler
from core.utils import (
    clean_urls, archive_extensions, img_extensions, get_file_extension, RateLimiter, 
    setup_logging, get_docker_or_local_path, url_matches_patterns
)
from core.indexer import Indexer
from core.spider import run_link_spider_isolated, recursive_crawl, sitemap_to_urls
from crawlers.auth.saml_manager import SAMLAuthManager

import ray

logger = logging.getLogger(__name__)


class PageCrawlWorker(object):
    def __init__(self, indexer: Indexer, crawler: Crawler, num_per_second: int, saml_session=None):
        self.crawler = crawler
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)
        self.saml_session = saml_session

    def setup(self):
        self.indexer.setup()
        # If we have a SAML session, configure the indexer to use it
        if self.saml_session:
            self.indexer.session = self.saml_session
        setup_logging()

    def process(self, url: str, source: str):
        metadata = {"source": source, "url": url}
        logger.info(f"Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                # If we have a SAML session, pass cookies to the indexer
                succeeded = self.indexer.index_url(url, metadata=metadata, html_processing=self.crawler.html_processing)
            if not succeeded:
                logger.info(f"Indexing failed for {url}")
            else:
                logger.info(f"Indexing {url} was successful")
        except Exception as e:
            import traceback
            logger.error(
                f"Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0

class WebsiteCrawler(Crawler):
    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        self.saml_session = None
        self._setup_saml_auth()
    
    def _setup_saml_auth(self):
        """Initialize SAML authentication if configured"""
        saml_config = self.cfg.website_crawler.get("saml_auth")
        if not saml_config:
            return
            
        logger.info("SAML authentication configured, initializing...")
        
        try:
            # The secrets are already loaded into the config by ingest.py
            # Extract the required secrets for SAML authentication
            secrets_dict = {}
            
            # Get username and password from the website_crawler config
            # These should have been loaded from secrets.toml by ingest.py
            if hasattr(self.cfg.website_crawler, 'saml_username') and hasattr(self.cfg.website_crawler, 'saml_password'):
                secrets_dict['username'] = self.cfg.website_crawler.saml_username
                secrets_dict['password'] = self.cfg.website_crawler.saml_password
            else:
                raise Exception("SAML authentication requires 'SAML_USERNAME' and 'SAML_PASSWORD' in secrets.toml")
            
            # Initialize SAML auth manager
            saml_manager = SAMLAuthManager(saml_config, secrets_dict)
            
            # Get authenticated session
            self.saml_session = saml_manager.get_authenticated_session()
            logger.info("SAML authentication successful")
            
        except Exception as e:
            logger.error(f"SAML authentication failed: {e}")
            raise
    
    def _transfer_session_cookies_to_context(self, context, session):
        """Transfer cookies from requests session to Playwright context"""
        if not session or not hasattr(session, 'cookies'):
            return
            
        for cookie in session.cookies:
            cookie_dict = {
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain or '',
                'path': cookie.path or '/',
            }
            
            # Add optional cookie attributes if present
            if hasattr(cookie, 'secure') and cookie.secure:
                cookie_dict['secure'] = True
            if hasattr(cookie, 'expires') and cookie.expires:
                cookie_dict['expires'] = cookie.expires
                
            try:
                context.add_cookies([cookie_dict])
                logger.debug(f"Added cookie {cookie.name} to Playwright context")
            except Exception as e:
                logger.warning(f"Failed to add cookie {cookie.name}: {e}")

    def crawl(self) -> None:
        base_urls = self.cfg.website_crawler.urls
        self.pos_regex = self.cfg.website_crawler.get("pos_regex", [])
        self.pos_patterns = [re.compile(r) for r in self.pos_regex]
        self.neg_regex = self.cfg.website_crawler.get("neg_regex", [])
        self.neg_patterns = [re.compile(r) for r in self.neg_regex]
        keep_query_params = self.cfg.website_crawler.get('keep_query_params', False)
        self.html_processing = self.cfg.website_crawler.get('html_processing', {})
        max_depth = self.cfg.website_crawler.get("max_depth", 3)

        # Configure indexer to use SAML session if available
        if self.saml_session and hasattr(self.indexer, 'session'):
            self.indexer.session = self.saml_session
            logger.info("Configured indexer to use SAML authenticated session")
        
        # Override web extractor's context creation to include SAML cookies
        if self.saml_session:
            # Initialize web extractor to ensure it exists
            self.indexer._init_processors()
            
            if hasattr(self.indexer, 'web_extractor') and self.indexer.web_extractor:
                original_new_context = self.indexer.web_extractor.browser.new_context
                
                def new_context_with_auth(*args, **kwargs):
                    context = original_new_context(*args, **kwargs)
                    self._transfer_session_cookies_to_context(context, self.saml_session)
                    return context
                    
                self.indexer.web_extractor.browser.new_context = new_context_with_auth
                logger.info("Configured web extractor to use SAML authenticated cookies")

        # In website_crawler.py - prevent scrapy with SAML
        if self.cfg.website_crawler.get("crawl_method", "internal") == "scrapy" and self.saml_session:
            logger.warning("Scrapy is not fully compatible with SAML authentication. Using internal crawler instead.")
            crawl_method = "internal"

        if self.cfg.website_crawler.get("crawl_method", "internal") == "scrapy":
            logger.info("Using Scrapy to crawl the website")
            all_urls = run_link_spider_isolated(
                start_urls = base_urls,
                positive_regexes = self.pos_regex,
                negative_regexes = self.neg_regex,
                max_depth = max_depth,
            )
        else:
            logger.info("Using internal Vectara-ingest method to crawl the website")
            all_urls = []
            for homepage in base_urls:
                if self.cfg.website_crawler.pages_source == "sitemap":
                    # Pass SAML session for authenticated sitemap access
                    urls = sitemap_to_urls(homepage, session=self.saml_session)
                    urls = [
                        url for url in urls 
                        if url.startswith('http') and url_matches_patterns(url, self.pos_patterns, self.neg_patterns)
                    ]
                elif self.cfg.website_crawler.pages_source == "crawl":
                    urls_set = recursive_crawl(
                        homepage, max_depth,
                        pos_patterns=self.pos_patterns, neg_patterns=self.neg_patterns,
                        indexer=self.indexer, visited=set(), verbose=self.indexer.verbose
                    )
                    urls = clean_urls(urls_set, keep_query_params)
                else:
                    logger.info(f"Unknown pages_source: {self.cfg.website_crawler.pages_source}")
                    return
                logger.info(f"Found {len(urls)} URLs on {homepage}")
                all_urls += urls

        # remove URLS that are out of our regex regime or are archives or images
        urls = [
            u for u in all_urls 
            if u.startswith('http') and not any([u.endswith(ext) for ext in archive_extensions + img_extensions])
            and url_matches_patterns(u, self.pos_patterns, self.neg_patterns)
        ]
        urls = list(set(urls))

        # Store URLS in crawl_report if needed
        if self.cfg.website_crawler.get("crawl_report", False):
            logger.info(f"Collected {len(urls)} URLs to crawl and index. See urls_indexed.txt for a full report.")
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
            logger.info(f"Collected {len(urls)} URLs to crawl and index.")

        # print some file types
        file_types = list(set([get_file_extension(u) for u in urls]))
        file_types = [t for t in file_types if t != ""]
        logger.info(f"Note: file types = {file_types}")

        num_per_second = max(self.cfg.website_crawler.get("num_per_second", 10), 1)
        ray_workers = self.cfg.website_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        source = self.cfg.website_crawler.get("source", "website")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            # Pass SAML session to workers
            actors = [ray.remote(PageCrawlWorker).remote(self.indexer, self, num_per_second, self.saml_session) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u, source=source), urls))

        else:
            crawl_worker = PageCrawlWorker(self.indexer, self, num_per_second, self.saml_session)
            crawl_worker.setup()
            for inx, url in enumerate(urls):
                if inx % 100 == 0:
                    logger.info(f"Crawling URL number {inx+1} out of {len(urls)}")
                crawl_worker.process(url, source=source)

        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in the crawl list
        if self.cfg.website_crawler.get("remove_old_content", False):
            existing_docs = self.indexer._list_docs()
            docs_to_remove = [t for t in existing_docs if t['url'] and t['url'] not in urls]
            for doc in docs_to_remove:
                if doc['url']:
                    self.indexer.delete_doc(doc['id'])
            logger.info(f"Removing {len(docs_to_remove)} docs that are not included in the crawl but are in the corpus.")
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
