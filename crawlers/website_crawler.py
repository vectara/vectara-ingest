import re
import requests
import logging
import psutil
import os

from core.crawler import Crawler
from core.utils import (
    clean_urls, archive_extensions, img_extensions, get_file_extension, RateLimiter, 
    setup_logging, get_docker_or_local_path, url_matches_patterns, normalize_vectara_endpoint
)
from core.indexer import Indexer
from core.spider import run_link_spider_isolated, recursive_crawl, sitemap_to_urls
from crawlers.auth.saml_manager import SAMLAuthManager

import ray

logger = logging.getLogger(__name__)


class PageCrawlWorker(object):
    def __init__(self, cfg: dict, num_per_second: int):
        self.cfg = cfg
        self.rate_limiter = RateLimiter(num_per_second)
        self.indexer = None
        self.session = None
        website_crawler_cfg = self.cfg.get('website_crawler', {})
        self.html_processing = website_crawler_cfg.get('html_processing', {})
        self.saml_config = website_crawler_cfg.get('saml_auth')
        self.scrape_method = website_crawler_cfg.get('scrape_method', 'playwright')

    def setup(self):
        """
        Initializes the worker's resources (Indexer, Session) within the Ray process.
        This method MUST be called before `process`.
        """
        setup_logging()
    
        vectara_cfg = self.cfg.get('vectara', {})
        api_url = normalize_vectara_endpoint(vectara_cfg.get('endpoint'))
        corpus_key = vectara_cfg['corpus_key']
        api_key = vectara_cfg['api_key']
        
        self.indexer = Indexer(self.cfg, api_url, corpus_key, api_key, scrape_method=self.scrape_method)
        self.indexer.setup()

        # Initialize SAML session if configured
        if self.saml_config:
            worker_pid = os.getpid()
            logging.info(f"[Worker {worker_pid}] SAML authentication is enabled. Initializing SAMLAuthManager.")
            
            # Extract SAML secrets from the config (they should be loaded by ingest.py)
            saml_secrets = {}
            website_crawler_cfg = self.cfg.get('website_crawler', {})
            if 'saml_username' in website_crawler_cfg and 'saml_password' in website_crawler_cfg:
                saml_secrets['username'] = website_crawler_cfg['saml_username']
                saml_secrets['password'] = website_crawler_cfg['saml_password']
            else:
                raise ValueError("SAML authentication requires 'SAML_USERNAME' and 'SAML_PASSWORD' in secrets.toml")
            
            try:
                from crawlers.auth.saml_manager import SAMLAuthManager
                auth_manager = SAMLAuthManager(config=self.saml_config, secrets=saml_secrets)
                self.session = auth_manager.get_authenticated_session()
                logging.info(f"[Worker {worker_pid}] SAML authentication successful.")
                
                # Assign the authenticated session to the indexer
                self.indexer.session = self.session
                logging.info(f"[Worker {worker_pid}] Authenticated session assigned to indexer.")
                
            except Exception as e:
                logging.error(f"[Worker {worker_pid}] Fatal SAML authentication failure: {e}")
                raise
        else:
            logging.info(f"[Worker {os.getpid()}] SAML not configured. Using standard session.")
            # Indexer will use its default session
    
    def cleanup(self):
        """Cleanup resources when worker is done"""
        if hasattr(self, 'indexer'):
            self.indexer.cleanup()

    def process(self, url: str, source: str):
        if not self.indexer:
            logging.error(f"[Worker {os.getpid()}] Indexer not set up. Call setup() before process().")
            return -1
            
        metadata = {"source": source, "url": url}
        logging.info(f"[Worker {os.getpid()}] Crawling and indexing {url}")
        try:
            with self.rate_limiter:
                succeeded = self.indexer.index_url(url, metadata=metadata, html_processing=self.html_processing)
            if not succeeded:
                logging.info(f"[Worker {os.getpid()}] Indexing failed for {url}")
            else:
                logging.info(f"[Worker {os.getpid()}] Indexing {url} was successful")
        except Exception as e:
            import traceback
            logging.error(
                f"[Worker {os.getpid()}] Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
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
            secrets_dict = self._get_saml_secrets()
            saml_manager = SAMLAuthManager(saml_config, secrets_dict)
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

    def _get_saml_secrets(self):
        """Extract SAML secrets from config (loaded from secrets.toml)."""
        if hasattr(self.cfg.website_crawler, 'saml_username') and hasattr(self.cfg.website_crawler, 'saml_password'):
            return {
                'username': self.cfg.website_crawler.saml_username,
                'password': self.cfg.website_crawler.saml_password
            }
        else:
            raise Exception("SAML authentication requires 'SAML_USERNAME' and 'SAML_PASSWORD' in secrets.toml")

    def _get_scrapy_saml_cookies(self):
        """
        Get SAML authentication cookies using SAMLAuthManager's Playwright method.
        Returns cookies that can be used with Scrapy for fast crawling.
        """
        saml_config = self.cfg.website_crawler.get("saml_auth")
        if not saml_config:
            return None
            
        try:
            secrets_dict = self._get_saml_secrets()
            saml_manager = SAMLAuthManager(saml_config, secrets_dict)
            return saml_manager.get_authenticated_cookies()
            
        except Exception as e:
            logger.error(f"Failed to get SAML cookies: {e}")
            return None

    def crawl(self) -> None:
        """Main crawl orchestration method."""
        # 1. Configuration and setup
        self._configure_indexer_session()
        
        # 2. Discover all URLs using the chosen method
        all_urls = self._discover_urls()

        # 3. Filter and prepare the final URL list
        urls_to_crawl = self._filter_and_prepare_urls(all_urls)

        # 4. Dispatch the jobs to workers (Ray or single process)
        self._dispatch_crawl_jobs(urls_to_crawl)

        # 5. Handle post-crawl cleanup
        self._remove_old_content_if_needed(urls_to_crawl)

    def _configure_indexer_session(self):
        """Configure indexer to use SAML session if available."""
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

    def _discover_urls(self) -> list:
        """
        Discover URLs using the chosen crawl method.
        Returns list of discovered URLs.
        """
        base_urls = self.cfg.website_crawler.urls
        self.pos_regex = self.cfg.website_crawler.get("pos_regex", [])
        self.pos_patterns = [re.compile(r) for r in self.pos_regex]
        self.neg_regex = self.cfg.website_crawler.get("neg_regex", [])
        self.neg_patterns = [re.compile(r) for r in self.neg_regex]
        keep_query_params = self.cfg.website_crawler.get('keep_query_params', False)
        self.html_processing = self.cfg.website_crawler.get('html_processing', {})
        max_depth = self.cfg.website_crawler.get("max_depth", 3)

        # Determine crawl method and handle SAML compatibility
        crawl_method = self.cfg.website_crawler.get("crawl_method", "internal")
        scrapy_cookies = None
        
        # Try SAML authentication for Scrapy if configured
        if crawl_method == "scrapy" and self.cfg.website_crawler.get("saml_auth"):
            logger.info("SAML detected with Scrapy - attempting Playwright-based SAML authentication")
            scrapy_cookies = self._get_scrapy_saml_cookies()
            
            if scrapy_cookies:
                logger.info(f"Playwright-based SAML successful! Using Scrapy with {len(scrapy_cookies)} cookies")
            else:
                logger.warning("Playwright-based SAML failed. Falling back to internal crawler with requests-based SAML.")
                crawl_method = "internal"
        
        # Execute crawling based on method
        if crawl_method == "scrapy":
            return self._discover_urls_with_scrapy(base_urls, max_depth, scrapy_cookies)
        else:
            return self._discover_urls_with_internal_crawler(base_urls, max_depth, keep_query_params)

    def _discover_urls_with_scrapy(self, base_urls: list, max_depth: int, scrapy_cookies: dict) -> list:
        """Discover URLs using Scrapy crawler."""
        logger.info("Using Scrapy to crawl the website")
        
        # Prepare extra settings for Scrapy with cookies
        extra_settings = {}
        if scrapy_cookies:
            extra_settings.update({
                'COOKIES_ENABLED': True,
                'COOKIES_DEBUG': True
            })
            logger.info("Configuring Scrapy with SAML cookies")
        
        return run_link_spider_isolated(
            start_urls=base_urls,
            positive_regexes=self.pos_regex,
            negative_regexes=self.neg_regex,
            max_depth=max_depth,
            extra_settings=extra_settings,
            cookies=scrapy_cookies
        )

    def _discover_urls_with_internal_crawler(self, base_urls: list, max_depth: int, keep_query_params: bool) -> list:
        """Discover URLs using internal Vectara-ingest crawler."""
        logger.info("Using internal Vectara-ingest method to crawl the website")
        all_urls = []
        pages_source = self.cfg.website_crawler.pages_source
        
        for homepage in base_urls:
            urls = []
            
            # Get URLs based on pages_source method
            if pages_source == "sitemap":
                # Pass SAML session for authenticated sitemap access
                urls = sitemap_to_urls(homepage, session=self.saml_session)
                urls = [
                    url for url in urls 
                    if url.startswith('http') and url_matches_patterns(url, self.pos_patterns, self.neg_patterns)
                ]
            elif pages_source == "crawl":
                urls_set = recursive_crawl(
                    homepage, max_depth,
                    pos_patterns=self.pos_patterns, neg_patterns=self.neg_patterns,
                    indexer=self.indexer, visited=set(), verbose=self.indexer.verbose
                )
                urls = clean_urls(urls_set, keep_query_params)
            else:
                logger.info(f"Unknown pages_source: {pages_source}")
                continue
            
            logger.info(f"Found {len(urls)} URLs on {homepage}")
            all_urls.extend(urls)
            
        return all_urls

    def _filter_and_prepare_urls(self, all_urls: list) -> list:
        """
        Filter URLs by extensions and patterns, deduplicate, and generate crawl report.
        Returns the final list of URLs to crawl.
        """
        # Filter and deduplicate URLs
        excluded_extensions = archive_extensions + img_extensions
        urls = [
            url for url in all_urls 
            if (url.startswith('http') and 
                not any(url.endswith(ext) for ext in excluded_extensions) and
                url_matches_patterns(url, self.pos_patterns, self.neg_patterns))
        ]
        urls = list(set(urls))

        # Store URLS in crawl_report if needed
        if self.cfg.website_crawler.get("crawl_report", False):
            logger.info(f"Collected {len(urls)} URLs to crawl and index. See urls_indexed.txt for a full report.")
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/urls_indexed.txt'
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

        # Print some file types
        file_types = list(set([get_file_extension(u) for u in urls]))
        file_types = [t for t in file_types if t != ""]
        logger.info(f"Note: file types = {file_types}")
        
        return urls

    def _dispatch_crawl_jobs(self, urls: list):
        """
        Dispatch crawl jobs to Ray workers or process sequentially.
        """
        num_per_second = max(self.cfg.website_crawler.get("num_per_second", 10), 1)
        ray_workers = self.cfg.website_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        source = self.cfg.website_crawler.get("source", "website")

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            self._dispatch_to_ray_workers(urls, ray_workers, num_per_second, source)
        else:
            self._dispatch_to_single_process(urls, num_per_second, source)

    def _dispatch_to_ray_workers(self, urls: list, ray_workers: int, num_per_second: int, source: str):
        """Dispatch jobs to Ray workers for parallel processing."""
        logger.info(f"Using {ray_workers} ray workers")
        self.indexer.p = self.indexer.browser = None
        ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
        
        # Create workers with serializable config
        actors = [ray.remote(PageCrawlWorker).remote(
            self.cfg,
            num_per_second
        ) for _ in range(ray_workers)]
        ray.get([a.setup.remote() for a in actors])
        pool = ray.util.ActorPool(actors)
        _ = list(pool.map(lambda a, u: a.process.remote(u, source=source), urls))
        # Cleanup Ray workers
        for a in actors:
            ray.get(a.cleanup.remote())
        ray.shutdown()

    def _dispatch_to_single_process(self, urls: list, num_per_second: int, source: str):
        """Process URLs sequentially in a single process."""
        crawl_worker = PageCrawlWorker(
            self.cfg,
            num_per_second
        )
        crawl_worker.setup()
        for inx, url in enumerate(urls):
            if inx % 100 == 0:
                logger.info(f"Crawling URL number {inx+1} out of {len(urls)}")
            crawl_worker.process(url, source=source)
        # Cleanup worker
        crawl_worker.cleanup()

    def _remove_old_content_if_needed(self, crawled_urls: list):
        """
        Remove old content from corpus if remove_old_content is enabled.
        """
        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in the crawl list
        if not self.cfg.website_crawler.get("remove_old_content", False):
            return
        
        existing_docs = self.indexer._list_docs()
        docs_to_remove = [t for t in existing_docs if t['url'] and t['url'] not in crawled_urls]
        for doc in docs_to_remove:
            if doc['url']:
                self.indexer.delete_doc(doc['id'])
        logger.info(f"Removed {len(docs_to_remove)} docs that are not included in the crawl but are in the corpus.")
        
        if self.cfg.website_crawler.get("crawl_report", False):
            output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/urls_removed.txt'
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
