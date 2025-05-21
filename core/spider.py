import re
from typing import Set, Optional, List, Any
import logging
import multiprocessing
from urllib.parse import urlparse, urljoin

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy import signals
from scrapy.signalmanager import dispatcher
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.exceptions import IgnoreRequest

from core.indexer import Indexer
from core.utils import img_extensions, doc_extensions, archive_extensions

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _url_is_relative(url: str) -> bool:
    parsed_url = urlparse(url)
    return not parsed_url.scheme and not parsed_url.netloc

def recursive_crawl(url: str, depth: int, 
                    pos_patterns: List[re.Pattern], neg_patterns: List[re.Pattern], 
                    indexer: Indexer, visited: Optional[Set[str]]=None, 
                    verbose: bool = False) -> Set[str]:
    """
    Recursively crawl a URL and extract all links from it.
    """    
    if visited is None:
        visited = set()

    parsed_url = urlparse(url)
    current_path_lower = parsed_url.path.lower()
    
    if any([current_path_lower.endswith(ext) for ext in (archive_extensions + img_extensions)]):
        return visited
    
    # add the current URL
    visited.add(url)

    # for document files (like PPT, DOCX, etc) we don't extract links from the URL, but the link itself is included. 
    if any([current_path_lower.endswith(ext) for ext in doc_extensions]):
        return visited

    # if we reached the maximum depth, stop and return the visited URLs
    if depth <= 0:
        return visited

    try:
        res = indexer.fetch_page_contents(url)
        new_urls = [urljoin(url, u) if _url_is_relative(u) else u for u in res['links']]  # convert all new URLs to absolute URLs
        new_urls = [u for u in new_urls 
                    if      u not in visited and u.startswith('http') 
                    and     (len(pos_patterns)==0 or any([r.match(u) for r in pos_patterns]))
                    and     (len(neg_patterns)==0 or (not any([r.match(u) for r in neg_patterns]))) 
                   ]
        new_urls = list(set(new_urls))
        new_urls = [u for u in new_urls if not any([u.endswith(ext) for ext in archive_extensions + img_extensions])]
        visited.update(new_urls)

        if len(new_urls) > 0:
            logger.info(f"collected {len(visited)} URLs so far")
            if verbose:
                logger.info(f"URLs so far: {visited}")

        for new_url in new_urls:
            visited = recursive_crawl(new_url, depth-1, pos_patterns, neg_patterns, indexer, visited, verbose)
    except Exception as e:
        logger.error(f"Error {e} in recursive_crawl for {url}")
        pass

    return set(visited)

DISALLOWED_REDIRECT_EXTENSIONS = tuple(
    ext.lower() for ext in (doc_extensions + archive_extensions + img_extensions)
)
class FilterRedirectsByTypeMiddleware(RedirectMiddleware):

    def _redirect(self, redirected, request, spider, reason):
        redirect_to_url = redirected.url
        should_ignore_this_redirect = False

        try:
            parsed_redirect_to_url = urlparse(redirect_to_url)
            path_lower = parsed_redirect_to_url.path.lower()

            if path_lower.endswith(DISALLOWED_REDIRECT_EXTENSIONS):
                spider.logger.info(
                    f"REDIRECT_FILTER: Ignoring redirect from '{request.url}' to disallowed file type: '{redirect_to_url}'"
                )
                should_ignore_this_redirect = True
        except Exception as e:
            # This block now only catches truly unexpected errors during your *checking logic* (e.g., urlparse failure)
            spider.logger.error(
                f"REDIRECT_FILTER: Unexpected error during file type check for redirect from '{request.url}' to '{redirect_to_url}': {e}. "
                f"Allowing redirect to proceed by default to avoid breaking other functionalities."
            )

        if should_ignore_this_redirect:
            raise IgnoreRequest(f"Redirect target '{redirect_to_url}' is a disallowed file type; original request '{request.url}' will be ignored.")
        else:
            return super()._redirect(redirected, request, spider, reason)

class LinkSpider(scrapy.Spider):
    name = "link_spider"

    def __init__(
        self,
        start_urls: list[str],
        positive_regexes: list[str],
        negative_regexes: list[str],
        max_depth: int = 1,
        *args, **kwargs
    ):
        """
        start_urls: list of URLs, e.g. '["https://example.com","https://foo.com"]'
        positive_regexes: list of strings, e.g. '["^https?://.*foo","bar$"]'
        negative_regexes: list of strings, e.g. '["/logout","/private"]'
        max_depth: integer, how many hops from any start_url
        """
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls
        self.max_depth = int(max_depth)
        try:
            self.positive_patterns = [re.compile(r) for r in positive_regexes]
            self.negative_patterns = [re.compile(r) for r in negative_regexes]
        except re.error as e:
            logger.error(f"Invalid regex pattern provided: {e.pattern} - {e.msg}")
            raise ValueError(f"Invalid regex pattern: {e.pattern} - {e.msg}") from e
    
    def is_valid_by_regex(self, url: str) -> bool:
        if any(p.match(url) for p in self.negative_patterns):
            return False
        
        if not self.positive_patterns:  # If no positive patterns are defined
            return True                

        return any(p.match(url) for p in self.positive_patterns)

    def should_follow(self, url: str) -> bool:
        parsed_url = urlparse(url)
        path_lower = parsed_url.path.lower()

        if any([path_lower.endswith(ext) for ext in (doc_extensions + archive_extensions + img_extensions)]):
            return False

        if not parsed_url.scheme.lower() in ['http', 'https']:
            return False
        return self.is_valid_by_regex(url)

    def parse(self, response):
        extract_links = True
        parsed_response_url = urlparse(response.url)
        response_path_lower = parsed_response_url.path.lower() # Get lowercase path

        if any([response_path_lower.endswith(ext) for ext in (archive_extensions + img_extensions)]):
            return
        
        # For document files, yield the URL but do not attempt to extract links.
        if any([response_path_lower.endswith(ext) for ext in doc_extensions]):
            extract_links = False
            
        # 1) If this URL itself is valid, yield it
        if self.is_valid_by_regex(response.url):
            yield {'url': response.url}

        # 2) If we haven’t reached max_depth, extract links and follow
        depth = response.meta.get('depth', 0)
        if depth < self.max_depth and extract_links:
            for href in response.css('a::attr(href)').getall():
                next_url = response.urljoin(href)
                if self.should_follow(next_url):
                    yield scrapy.Request(
                        next_url,
                        callback=self.parse,
                        meta={'depth': depth + 1},
                    )

def run_link_spider(
    start_urls:       List[str],
    positive_regexes: List[str],
    negative_regexes: List[str],
    max_depth:        int = 1,
    extra_settings:   dict | None = None,
) -> List[str]:
    """
    Blocking, in-process runner that:
     - silences Scrapy
     - hooks into item_scraped
     - returns the list of {'url': ...} items your spider yields
    """
    results: List[str] = []

    def _item_scraped_callback(item, response, spider):
        if 'url' in item:
            results.append(item['url'])
        else:
            logger.debug(f"WORKER WARNING (Signal): Item scraped without 'url' key: {item}")

    try:
        dispatcher.connect(_item_scraped_callback, signal=signals.item_scraped)
    
        middleware_path = f"{FilterRedirectsByTypeMiddleware.__module__}.{FilterRedirectsByTypeMiddleware.__name__}"

        # These settings should be respected by the CrawlerProcess
        process_settings = {
            'ROBOTSTXT_OBEY': False,
            'CONCURRENT_REQUESTS': 4,
            'LOG_ENABLED': False,
            'LOG_LEVEL': 'WARNING',
            'LOG_STDOUT': False,
            'DOWNLOAD_TIMEOUT': 10,
            'STATS_CLASS': 'scrapy.statscollectors.DummyStatsCollector',
            'DUPEFILTER_DEBUG': True,
            'DOWNLOADER_MIDDLEWARES': {
                # Disable the default RedirectMiddleware
                'scrapy.downloadermiddlewares.redirect.RedirectMiddleware': None,
                # Enable your custom one at the same default priority (or adjust as needed)
                middleware_path: 600,
            }
        }

        if extra_settings:
            if 'DOWNLOADER_MIDDLEWARES' in extra_settings and 'DOWNLOADER_MIDDLEWARES' in process_settings:
                process_settings['DOWNLOADER_MIDDLEWARES'].update(extra_settings.pop('DOWNLOADER_MIDDLEWARES'))
            process_settings.update(extra_settings)

        # Create the process with these settings
        process = CrawlerProcess(settings=process_settings)
        scrapy_logger_instance = logging.getLogger('scrapy')
        scrapy_logger_instance.setLevel(logging.WARNING) # FORCE the level to WARNING

        process.crawl(
            LinkSpider,
            start_urls       = start_urls,
            positive_regexes = positive_regexes,
            negative_regexes = negative_regexes,
            max_depth        = max_depth,
        )

        process.start() # This is a blocking call

    except Exception as e:
        logger.warning(f"WORKER ERROR: An exception occurred during run_link_spider: {e}")
    finally:
        try:
            dispatcher.disconnect(_item_scraped_callback, signal=signals.item_scraped)
        except Exception as e:
            logger.warning(f"WORKER WARNING: Failed to disconnect signal handler: {e}")

    results = list(set(results))
    logger.info(f"LinkSpider finished. Found {len(results)} unique URLs.")
    return results


def run_link_spider_isolated(
    start_urls: list[str],
    positive_regexes: List[str],
    negative_regexes: List[str],
    max_depth: int = 1,
    extra_settings: dict | None = None,
) -> list[str]:
    """
    Launches run_link_spider(...) in a fresh Python process so that
    Scrapy's reactor.run() and logging never collide with the main loop.
    """    
    def _worker(queue):
        import logging
        logging.getLogger('scrapy').setLevel(logging.WARNING)
        logging.getLogger('scrapy.core.engine').setLevel(logging.WARNING)
        logging.getLogger('twisted').setLevel(logging.WARNING)
        try:
            results = run_link_spider(
                start_urls=start_urls,
                positive_regexes=positive_regexes,
                negative_regexes=negative_regexes,
                max_depth=max_depth,
                extra_settings=extra_settings,
            )
            logger.debug(f"WORKER: run_link_spider finished. Results: {results}")
            queue.put((results, None))
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.debug(f"WORKER: Exception in run_link_spider: {e}\n{error_details}")
            queue.put((None, e))

    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=_worker, args=(queue,))
    p.start()
    results, error = queue.get()
    p.join()
    p.close()

    if error:
        raise error
    return results if results is not None else []

if __name__ == "__main__":
    def main():
        urls = run_link_spider_isolated(
            start_urls=['https://vectara.com'],
            positive_regexes=['.*vectara.com.*'],
            max_depth=2,
        )
        print("Valid URLs:", urls)

    main()