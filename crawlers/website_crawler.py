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
from core.indexer_utils import normalize_url_for_metadata
from core.spider import run_link_spider_isolated, recursive_crawl, sitemap_to_urls
from crawlers.auth.saml_manager import SAMLAuthManager
from crawlers.auth.google_manager import GoogleAuthManager

import ray

logger = logging.getLogger(__name__)


def _transfer_session_to_context(context, session):
    """Forward cookies from a `requests.Session` to a Playwright context."""
    if not session or not hasattr(session, 'cookies'):
        return
    for cookie in session.cookies:
        attrs = {
            'name': cookie.name,
            'value': cookie.value,
            'domain': cookie.domain or '',
            'path': cookie.path or '/',
        }
        if getattr(cookie, 'secure', False):
            attrs['secure'] = True
        if getattr(cookie, 'expires', None):
            attrs['expires'] = cookie.expires
        try:
            context.add_cookies([attrs])
        except Exception as e:
            logger.warning(f"Failed to add cookie {cookie.name} to Playwright context: {e}")


def _apply_auth_to_indexer(
    indexer,
    saml_session=None,
    google_cookies=None,
    google_storage_state_path=None,
):
    """Propagate auth to an Indexer so both `session` (requests) and
    `web_extractor` (Playwright) issue authenticated fetches.

    Used by `WebsiteCrawler._configure_indexer_session` (parent process,
    discovery-side indexer) and by `PageCrawlWorker.setup` (per-worker
    indexer in Ray actor or single-process mode).

    For Google auth, the Playwright context is loaded from the captured
    `storage_state` JSON. Re-injecting individual cookies via `add_cookies`
    fails for Google's `__Host-*` / `__Secure-*` cookies (CDP rejects the
    batch because `__Host-` cookies must be sent without a Domain attribute
    and `__Secure-` cookies require `Secure=true`). Playwright's
    `storage_state` path preserves the original cookie attributes verbatim.
    """
    if saml_session and hasattr(indexer, 'session'):
        indexer.session = saml_session
        logger.info("Configured indexer to use SAML authenticated session")

    if google_cookies and hasattr(indexer, 'session') and indexer.session is not None:
        # Use create_cookie + set_cookie so each cookie retains its
        # domain/path/secure scoping in the requests cookie jar. A flat
        # `cookies.update({name: value})` would attach every Google cookie
        # to every host the session talks to, leaking host-bound cookies
        # (`__Host-*`) to wrong domains on redirects.
        for c in google_cookies:
            cookie = requests.cookies.create_cookie(
                name=c["name"],
                value=c["value"],
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
                secure=bool(c.get("secure", False)),
            )
            indexer.session.cookies.set_cookie(cookie)
        logger.info(
            f"Merged {len(google_cookies)} Google session cookies into indexer session"
        )

    if not (saml_session or google_storage_state_path):
        return

    indexer._init_processors()
    if hasattr(indexer, 'web_extractor') and indexer.web_extractor:
        original_new_context = indexer.web_extractor.browser.new_context

        def new_context_with_auth(*args, **kwargs):
            if google_storage_state_path:
                kwargs.setdefault('storage_state', google_storage_state_path)
            context = original_new_context(*args, **kwargs)
            if saml_session:
                _transfer_session_to_context(context, saml_session)
            return context

        indexer.web_extractor.browser.new_context = new_context_with_auth
        # Auth is wired in via Playwright `storage_state` / per-context cookie
        # transfer. Tell the extractor to skip the unauthenticated `requests.get`
        # prefetch in `fetch_page_contents` — without this, the prefetch follows
        # redirects to the IdP sign-in page (~1KB of HTML, >500 chars) and
        # short-circuits the authenticated browser path entirely.
        indexer.web_extractor.skip_static_prefetch = True
        logger.info("Configured web extractor to inject authenticated cookies")


class PageCrawlWorker(object):
    def __init__(self, cfg: dict, num_per_second: int):
        self.cfg = cfg
        self.rate_limiter = RateLimiter(num_per_second)
        self.indexer = None
        self.session = None
        website_crawler_cfg = self.cfg.get('website_crawler', {})
        self.html_processing = website_crawler_cfg.get('html_processing', {})
        self.saml_config = website_crawler_cfg.get('saml_auth')
        self.google_config = website_crawler_cfg.get('google_auth')
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
                auth_manager = SAMLAuthManager(config=self.saml_config, secrets=saml_secrets)
                self.session = auth_manager.get_authenticated_session()
                logging.info(f"[Worker {worker_pid}] SAML authentication successful.")

                # Wire SAML into both requests.Session and Playwright web_extractor
                # via the shared helper. A bare `indexer.session = self.session`
                # would leave `skip_static_prefetch` off, so the unauthenticated
                # static prefetch in `WebContentExtractor.fetch_page_contents`
                # would follow redirects to the IdP and short-circuit the
                # authenticated browser path before it ran.
                _apply_auth_to_indexer(self.indexer, saml_session=self.session)
                logging.info(
                    f"[Worker {worker_pid}] SAML session wired into indexer (requests + Playwright)."
                )

            except Exception as e:
                logging.error(f"[Worker {worker_pid}] Fatal SAML authentication failure: {e}")
                raise
        else:
            logging.info(f"[Worker {os.getpid()}] SAML not configured. Using standard session.")
            # Indexer will use its default session

        # Initialize Google authenticated cookies if configured (independent of SAML).
        # A Bearer-token API session is NOT useful here: sites.google.com content
        # URLs reject Bearer auth (only browser cookies work). We capture cookies
        # from the persisted storage_state and inject them into both the indexer's
        # requests.Session and its Playwright web_extractor.
        if self.google_config:
            worker_pid = os.getpid()
            logging.info(f"[Worker {worker_pid}] Google authentication enabled. Capturing storage_state cookies.")

            google_secrets = {}
            website_crawler_cfg = self.cfg.get('website_crawler', {})
            if 'google_credentials_file' in website_crawler_cfg:
                google_secrets['credentials_file'] = website_crawler_cfg['google_credentials_file']

            try:
                google_manager = GoogleAuthManager(config=self.google_config, secrets=google_secrets)
                google_cookies = google_manager.get_authenticated_cookies()
                _apply_auth_to_indexer(
                    self.indexer,
                    google_cookies=google_cookies,
                    google_storage_state_path=google_manager.storage_state_path,
                )
                logging.info(
                    f"[Worker {worker_pid}] Captured {len(google_cookies)} Google session cookies."
                )
            except Exception as e:
                logging.error(f"[Worker {worker_pid}] Fatal Google authentication failure: {e}")
                raise
    
    def cleanup(self):
        """Cleanup resources when worker is done"""
        if hasattr(self, 'indexer'):
            self.indexer.cleanup()

    # Return codes from process(). PageCrawlWorker runs in a Ray actor, so
    # the dispatch side can't read `self.indexer.last_skip_reason` directly —
    # we encode the outcome in the integer return value instead.
    RESULT_INDEXED = 0
    RESULT_FAILED = 1
    RESULT_AUTH_REQUIRED = 2

    def process(self, url: str, source: str):
        if not self.indexer:
            logging.error(f"[Worker {os.getpid()}] Indexer not set up. Call setup() before process().")
            return self.RESULT_FAILED

        metadata = {"source": source, "url": url}
        logging.info(f"[Worker {os.getpid()}] Crawling and indexing {url}")
        succeeded = False
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
            return self.RESULT_FAILED
        if succeeded:
            return self.RESULT_INDEXED
        if getattr(self.indexer, "last_skip_reason", None):
            return self.RESULT_AUTH_REQUIRED
        return self.RESULT_FAILED

class WebsiteCrawler(Crawler):
    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        self.saml_session = None
        self.google_cookies = None
        self.google_storage_state_path = None
        self._setup_saml_auth()
        self._setup_google_auth()

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

    def _get_saml_secrets(self):
        """Extract SAML secrets from config (loaded from secrets.toml)."""
        if hasattr(self.cfg.website_crawler, 'saml_username') and hasattr(self.cfg.website_crawler, 'saml_password'):
            return {
                'username': self.cfg.website_crawler.saml_username,
                'password': self.cfg.website_crawler.saml_password
            }
        raise ValueError("SAML authentication requires 'SAML_USERNAME' and 'SAML_PASSWORD' in secrets.toml")

    def _setup_google_auth(self):
        """Capture `sites.google.com` session cookies once at crawler init.

        These cookies are the only thing that authenticates requests against
        `sites.google.com` content URLs — Bearer tokens are rejected there.
        They are injected into both the indexer's `requests.Session` and its
        Playwright `web_extractor` by `_configure_indexer_session`, and also
        forwarded to Scrapy in the discovery path via `_discover_urls`.

        `GOOGLE_CREDENTIALS_FILE` is optional here: it is only consumed when
        someone calls `GoogleAuthManager.get_authenticated_session()` for
        Drive / Sites API access. Cookie-only crawls do not need it.
        """
        google_config = self.cfg.website_crawler.get("google_auth")
        if not google_config:
            return

        logger.info("Google authentication configured, capturing storage_state cookies...")
        secrets_dict = {}
        if hasattr(self.cfg.website_crawler, 'google_credentials_file'):
            secrets_dict['credentials_file'] = self.cfg.website_crawler.google_credentials_file

        try:
            google_manager = GoogleAuthManager(google_config, secrets_dict)
            self.google_cookies = google_manager.get_authenticated_cookies()
            self.google_storage_state_path = google_manager.storage_state_path
            logger.info(
                f"Captured {len(self.google_cookies)} Google session cookies."
            )
        except Exception as e:
            logger.error(f"Google authentication failed: {e}")
            raise

    def _get_scrapy_saml_cookies(self):
        """
        Get SAML authentication cookies using SAMLAuthManager's Playwright method.
        Returns a list of `{name, value}` dicts in the shape Scrapy expects.
        Domain/secure attributes are absent because SAMLAuthManager flattens
        cookies at capture time — Scrapy will treat them as host-bound to
        each request URL, which is correct for single-IdP SAML flows.
        """
        saml_config = self.cfg.website_crawler.get("saml_auth")
        if not saml_config:
            return None

        try:
            secrets_dict = self._get_saml_secrets()
            saml_manager = SAMLAuthManager(saml_config, secrets_dict)
            flat = saml_manager.get_authenticated_cookies()
            if not flat:
                return None
            return [{"name": k, "value": v} for k, v in flat.items()]

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
        """Propagate SAML session and/or Google cookies to the indexer's
        `requests.Session` and Playwright `web_extractor`."""
        _apply_auth_to_indexer(
            self.indexer,
            saml_session=self.saml_session,
            google_cookies=self.google_cookies,
            google_storage_state_path=self.google_storage_state_path,
        )

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

        # Determine crawl method and handle SAML / Google auth for Scrapy.
        # Cookies are passed as a list of dicts (`{name, value, domain, path,
        # secure}`) so Scrapy's CookieMiddleware can enforce per-cookie
        # scoping on redirects — `__Host-*` and other host-bound Google
        # cookies must not leak to `sites.google.com` from `accounts.google.com`.
        crawl_method = self.cfg.website_crawler.get("crawl_method", "internal")
        scrapy_cookies: list = []

        if crawl_method == "scrapy" and self.cfg.website_crawler.get("saml_auth"):
            logger.info("SAML detected with Scrapy - attempting Playwright-based SAML authentication")
            saml_cookies = self._get_scrapy_saml_cookies()
            if saml_cookies:
                scrapy_cookies.extend(saml_cookies)
                logger.info(f"Playwright-based SAML successful! Got {len(saml_cookies)} cookies")
            else:
                logger.warning(
                    "Playwright-based SAML failed. Falling back to internal crawler with requests-based SAML."
                )
                crawl_method = "internal"

        if crawl_method == "scrapy" and self.cfg.website_crawler.get("google_auth"):
            logger.info("Google auth detected with Scrapy - forwarding captured session cookies")
            if self.google_cookies:
                scrapy_cookies.extend(self.google_cookies)
                logger.info(f"Loaded {len(self.google_cookies)} Google session cookies")
            else:
                # Google cookies are required to crawl sites.google.com. Without
                # them, every Scrapy request 302s into accounts.google.com and we
                # discover 0 URLs. Surface this loudly rather than silently
                # producing an empty crawl.
                raise RuntimeError(
                    "Google authentication is configured but no session cookies were obtained. "
                    "Run `python -m crawlers.auth.google_bootstrap --output <path>` to capture a Google session."
                )

        # Pass None instead of an empty list so the spider keeps default
        # behavior for crawls that have no auth configured.
        scrapy_cookies = scrapy_cookies or None
        
        # Execute crawling based on method
        if crawl_method == "scrapy":
            return self._discover_urls_with_scrapy(base_urls, max_depth, scrapy_cookies)
        else:
            return self._discover_urls_with_internal_crawler(base_urls, max_depth, keep_query_params)

    def _discover_urls_with_scrapy(self, base_urls: list, max_depth: int, scrapy_cookies: list) -> list:
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
        pages_source = self.cfg.website_crawler.get("pages_source", "crawl")
        
        for homepage in base_urls:
            urls = []
            
            # Get URLs based on pages_source method
            if pages_source == "sitemap":
                # `indexer.session` carries both SAML and Google cookies after
                # `_configure_indexer_session` has run, so sitemap fetches work
                # against authenticated origins regardless of which auth is set.
                urls = sitemap_to_urls(homepage, session=self.indexer.session)
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
                not any(url.lower().endswith(ext) for ext in excluded_extensions) and
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
        # Pre-filter already-indexed URLs for crash recovery / resume (skip when reindex=True)
        if self.tracker and not self.cfg.vectara.get("reindex", False):
            indexed = self.tracker.get_indexed_ids()
            before = len(urls)
            urls = [u for u in urls if u not in indexed]
            logger.info(f"Skipping {before - len(urls)} already-indexed URLs ({len(urls)} remaining)")

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
        # Stop Playwright from URL discovery to close its asyncio event loop
        # This allows workers to create fresh Playwright instances without conflicts
        if hasattr(self.indexer, 'web_extractor') and self.indexer.web_extractor:
            if hasattr(self.indexer.web_extractor, 'p') and self.indexer.web_extractor.p:
                try:
                    self.indexer.web_extractor.p.stop()
                    logger.info("Stopped Playwright from URL discovery phase")
                except Exception as e:
                    logger.warning(f"Failed to stop Playwright: {e}")
        self.indexer.web_extractor = None
        ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
        
        # Create workers with serializable config
        actors = [ray.remote(PageCrawlWorker).remote(
            self.cfg,
            num_per_second
        ) for _ in range(ray_workers)]
        ray.get([a.setup.remote() for a in actors])
        pool = ray.util.ActorPool(actors)
        batch_size = max(ray_workers * 4, 20)
        for batch_start in range(0, len(urls), batch_size):
            self.check_shutdown()
            batch = urls[batch_start:batch_start + batch_size]
            results = list(pool.map(lambda a, u: a.process.remote(u, source=source), batch))
            if self.tracker:
                for url, result in zip(batch, results):
                    if result == PageCrawlWorker.RESULT_INDEXED:
                        self.tracker.track_indexed(url, url=url)
                    elif result == PageCrawlWorker.RESULT_AUTH_REQUIRED:
                        self.tracker.track_auth_required(url, url=url)
                    else:
                        self.tracker.track_failed(url, url=url)
            logger.info(f"Processed {min(batch_start + batch_size, len(urls))}/{len(urls)} URLs")
        # Cleanup Ray workers
        for a in actors:
            ray.get(a.cleanup.remote())
        ray.shutdown()

    def _dispatch_to_single_process(self, urls: list, num_per_second: int, source: str):
        """Process URLs sequentially in a single process."""
        # Stop Playwright from URL discovery to close its asyncio event loop
        # This allows worker to create fresh Playwright instance without conflicts
        if hasattr(self.indexer, 'web_extractor') and self.indexer.web_extractor:
            if hasattr(self.indexer.web_extractor, 'p') and self.indexer.web_extractor.p:
                try:
                    self.indexer.web_extractor.p.stop()
                    logger.info("Stopped Playwright from URL discovery phase")
                except Exception as e:
                    logger.warning(f"Failed to stop Playwright: {e}")
        self.indexer.web_extractor = None

        crawl_worker = PageCrawlWorker(
            self.cfg,
            num_per_second
        )
        crawl_worker.setup()
        for inx, url in enumerate(urls):
            self.check_shutdown()
            if inx % 100 == 0:
                logger.info(f"Crawling URL number {inx+1} out of {len(urls)}")
            result = crawl_worker.process(url, source=source)
            if self.tracker:
                if result == PageCrawlWorker.RESULT_INDEXED:
                    self.tracker.track_indexed(url, url=url)
                elif result == PageCrawlWorker.RESULT_AUTH_REQUIRED:
                    self.tracker.track_auth_required(url, url=url)
                else:
                    self.tracker.track_failed(url, url=url)
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
        # Normalize both sides: the indexer stores metadata['url'] after
        # normalize_url_for_metadata (URL-decoded), but crawled_urls comes
        # straight from URL discovery and may still be percent-encoded.
        # Without this, encoded discovery URLs would never match decoded
        # stored URLs and would be flagged for deletion every crawl.
        crawled_set = {normalize_url_for_metadata(u) for u in crawled_urls if u}
        docs_to_remove = [
            t for t in existing_docs
            if t['url'] and normalize_url_for_metadata(t['url']) not in crawled_set
        ]
        for doc in docs_to_remove:
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
