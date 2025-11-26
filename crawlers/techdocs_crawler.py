"""
Broadcom TechDocs Crawler

A web crawler for indexing Broadcom TechDocs content to Vectara.
Supports both sequential and Ray-based parallel processing with sitemap discovery.

"""

import json
import logging
import os
import re
import time
import traceback
import xml.etree.ElementTree as ET
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import psutil
import ray
import requests
from bs4 import BeautifulSoup
from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import RateLimiter, normalize_vectara_endpoint, setup_logging, url_matches_patterns

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Ray configuration
MAX_PENDING_TASKS = 1000  # Maximum concurrent tasks for sliding window

# Logging
SEPARATOR_WIDTH = 80  # Width of separator lines in logs

# Sitemap parsing
SITEMAP_TIMEOUT = 60  # Timeout for sitemap downloads (seconds)
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"

# Tracking files
DOCKER_HOME = "/home/vectara"  # Docker container home directory
TRACKING_SUBDIR = "techdocs"  # Subdirectory for tracking files
SUCCESS_FILE_NAME = "urls_indexed.txt"  # File to track successfully indexed URLs
FAILED_FILE_NAME = "failed_urls.txt"  # File to track failed URLs

# Default configuration values
DEFAULT_SOURCE_TAG = "techdocs"  # Default source metadata value
DEFAULT_SCRAPE_METHOD = "scrapy"  # Default scraping method


class IndexStatus(IntEnum):
    """Status codes for URL indexing operations."""

    SUCCESS = 0
    FAILURE = -1


# =============================================================================
# SITEMAP UTILITIES
# =============================================================================


def download_and_parse_sitemap(sitemap_url: str, timeout: int = SITEMAP_TIMEOUT) -> List[str]:
    """
    Download and parse an XML sitemap to extract URLs.

    This function handles both namespaced and non-namespaced sitemaps,
    automatically falling back to non-namespaced parsing if needed.

    Args:
        sitemap_url: URL to the sitemap XML file
        timeout: Request timeout in seconds

    Returns:
        List of URLs extracted from the sitemap. Returns empty list on error.

    Example:
        >>> urls = download_and_parse_sitemap("https://example.com/sitemap.xml")
        >>> print(f"Found {len(urls)} URLs")
    """
    try:
        response = requests.get(sitemap_url, timeout=timeout)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        namespace = {"ns": SITEMAP_NAMESPACE}

        # Try with namespace first (standard sitemap format)
        urls = _extract_urls_with_namespace(root, namespace)

        # Fallback to non-namespaced extraction
        if not urls:
            urls = _extract_urls_without_namespace(root)

        logger.info(f"Sitemap {sitemap_url}: extracted {len(urls)} URLs")
        return urls

    except requests.RequestException as e:
        logger.error(f"Failed to download sitemap {sitemap_url}: {e}")
        return []
    except ET.ParseError as e:
        logger.error(f"Failed to parse sitemap XML {sitemap_url}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing sitemap {sitemap_url}: {e}")
        return []


def _extract_urls_with_namespace(root: ET.Element, namespace: Dict[str, str]) -> List[str]:
    """Extract URLs from sitemap with XML namespace."""
    urls = []
    for loc in root.findall(".//ns:loc", namespace):
        if loc.text:
            urls.append(loc.text.strip())
    return urls


def _extract_urls_without_namespace(root: ET.Element) -> List[str]:
    """Extract URLs from sitemap without XML namespace."""
    urls = []
    for loc in root.findall(".//loc"):
        if loc.text:
            urls.append(loc.text.strip())
    return urls


# =============================================================================
# METADATA EXTRACTION
# =============================================================================


class MetadataExtractor:
    """
    Extracts structured metadata from Broadcom TechDocs HTML pages.

    This class handles JSON-LD metadata extraction and mapping to Vectara corpus schema.
    It provides a clean separation between HTML parsing and metadata transformation.
    """

    # Field mappings from JSON-LD to Vectara corpus schema
    SCALAR_FIELD_MAPPING = {
        "spacename": "space_name",
        "keywords": "keywords",
        "author": "author",
        "alternateName": "alternate_name",
        "language": "techdocs_language",
        "spacekey": "space_key",
        "currentpagetitle": "current_page_title",
        "name": "name",
        "siteversion": "version",
        "productname": "product",
        "searchurl": "search_url",
        "dateModified": "date_modified",
        "datePublished": "date_published",
    }

    ARRAY_FIELD_MAPPING = {
        "appname": "app_name",
        "appid": "app_id",
        "supportid": "support_id",
        "ux-context-string": "ux_context_string",
    }

    @classmethod
    def extract_from_html(cls, html_content: str) -> Dict[str, Any]:
        """
        Extract metadata from HTML content using JSON-LD structured data.

        This method parses JSON-LD script tags and extracts relevant metadata
        fields, mapping them to the Vectara corpus schema. The URL field is
        intentionally excluded to preserve the actual page URL.

        Args:
            html_content: Raw HTML content of the page

        Returns:
            Dictionary of extracted metadata fields. Returns empty dict on error.

        Note:
            The 'url' field from JSON-LD is intentionally not extracted to avoid
            overwriting the actual page URL in the metadata.
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Locate JSON-LD script tag
            jsonld_script = soup.find("script", {"type": "application/ld+json"})
            if not jsonld_script or not jsonld_script.string:
                logger.debug("No JSON-LD script tag found in HTML")
                return {}

            jsonld_data = json.loads(jsonld_script.string)
            extracted = {}

            # Extract scalar fields
            extracted.update(cls._extract_scalar_fields(jsonld_data))

            # Extract array fields (convert to comma-separated strings)
            extracted.update(cls._extract_array_fields(jsonld_data))

            # Extract hid field (only from JSON-LD, no HTML fallback)
            extracted["hid"] = jsonld_data.get("hid", "")

            logger.debug(f"Extracted {len(extracted)} metadata fields from JSON-LD")
            return extracted

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON-LD: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Unexpected error extracting metadata: {e}")
            return {}

    @classmethod
    def _extract_scalar_fields(cls, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract scalar (non-array) fields from JSON-LD."""
        extracted = {}
        for jsonld_field, corpus_field in cls.SCALAR_FIELD_MAPPING.items():
            if jsonld_field in jsonld_data:
                extracted[corpus_field] = jsonld_data[jsonld_field]
        return extracted

    @classmethod
    def _extract_array_fields(cls, jsonld_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract array fields from JSON-LD and convert to comma-separated strings."""
        extracted = {}
        for jsonld_field, corpus_field in cls.ARRAY_FIELD_MAPPING.items():
            if jsonld_field in jsonld_data:
                value = jsonld_data[jsonld_field]
                if isinstance(value, list):
                    extracted[corpus_field] = ", ".join(str(v) for v in value) if value else ""
                else:
                    extracted[corpus_field] = str(value)
        return extracted


# =============================================================================
# FILE WRITER
# =============================================================================


class FileWriter:
    """
    Handles file I/O operations for tracking successful and failed URLs.

    This class can be used directly in single-process mode or as a Ray actor
    in distributed mode for process-safe file writes. It maintains in-memory
    counts for fast progress reporting without file reads.
    """

    def __init__(self, success_file: str, failed_file: str):
        """
        Initialize the file writer.

        Args:
            success_file: Path to file for tracking successful URLs
            failed_file: Path to file for tracking failed URLs
        """
        self.success_file = success_file
        self.failed_file = failed_file
        self.success_count = 0
        self.failure_count = 0

    def record_success(self, url: str) -> None:
        """
        Record a successfully indexed URL.

        Args:
            url: The URL that was successfully indexed
        """
        try:
            with open(self.success_file, "a", encoding="utf-8") as f:
                f.write(f"{url}\n")
                f.flush()
            self.success_count += 1
        except IOError as e:
            logger.error(f"Failed to write success URL to {self.success_file}: {e}")

    def record_failure(self, url: str) -> None:
        """
        Record a failed URL.

        Args:
            url: The URL that failed to index
        """
        try:
            with open(self.failed_file, "a", encoding="utf-8") as f:
                f.write(f"{url}\n")
                f.flush()
            self.failure_count += 1
        except IOError as e:
            logger.error(f"Failed to write failed URL to {self.failed_file}: {e}")

    def get_counts(self) -> Tuple[int, int]:
        """
        Get current success and failure counts.

        Returns:
            Tuple of (success_count, failure_count)
        """
        return self.success_count, self.failure_count


# =============================================================================
# PAGE CRAWL WORKER
# =============================================================================


class PageCrawlWorker:
    """
    Worker for crawling and indexing individual TechDocs pages.

    This class handles the core indexing logic for a single URL, including
    rate limiting, metadata extraction, and error handling. It's designed to
    work both in Ray distributed environments and single-process contexts.

    Attributes:
        cfg: Full configuration dictionary
        rate_limiter: Rate limiter for API requests
        indexer: Vectara indexer instance (initialized in setup())
        html_processing: HTML processing configuration
        scrape_method: Scraping method ('scrapy' or 'playwright')
        file_writer: FileWriter instance for tracking URLs (can be Ray actor or regular class)
    """

    def __init__(self, cfg: Dict[str, Any], num_per_second: Optional[int] = None, file_writer: Optional[Any] = None, use_ray_remote: bool = False):
        """
        Initialize the page crawl worker.

        Args:
            cfg: Configuration dictionary
            num_per_second: Rate limit (requests per second). If None, no rate limiting.
            file_writer: FileWriter instance (Ray actor in distributed mode, regular class otherwise)
            use_ray_remote: If True, file_writer is a Ray actor and needs .remote() calls
        """
        self.cfg = cfg
        self.rate_limiter = RateLimiter(num_per_second) if num_per_second else None
        self.indexer: Optional[Indexer] = None

        techdocs_cfg = cfg.get("techdocs_crawler", {})
        self.html_processing = techdocs_cfg.get("html_processing", {})
        self.scrape_method = techdocs_cfg.get("scrape_method", DEFAULT_SCRAPE_METHOD)

        # FileWriter instance (can be Ray actor or regular class)
        self.file_writer = file_writer
        self.use_ray_remote = use_ray_remote

        # Metadata extractor instance
        self._metadata_extractor = MetadataExtractor()

    def setup(self) -> None:
        """
        Initialize worker resources (indexer) within the Ray process.

        This method must be called before process(). It initializes logging
        and creates the Vectara indexer with proper configuration.

        Raises:
            Exception: If indexer setup fails (e.g., missing credentials)
        """
        setup_logging()

        try:
            vectara_cfg = self.cfg.get("vectara", {})
            api_url = normalize_vectara_endpoint(vectara_cfg.get("endpoint"))
            corpus_key = vectara_cfg["corpus_key"]
            api_key = vectara_cfg["api_key"]

            self.indexer = Indexer(self.cfg, api_url, corpus_key, api_key, scrape_method=self.scrape_method)
            self.indexer.setup()

            logger.info(f"[Worker {os.getpid()}] Indexer initialized successfully")

        except KeyError as e:
            logger.error(f"[Worker {os.getpid()}] Missing required config key: {e}")
            raise
        except Exception as e:
            logger.error(f"[Worker {os.getpid()}] Failed to setup indexer: {e}")
            raise

    def cleanup(self) -> None:
        """
        Cleanup worker resources.

        Should be called when the worker is done processing to release resources.
        """
        if self.indexer is not None:
            self.indexer.cleanup()
            logger.debug(f"[Worker {os.getpid()}] Indexer cleaned up")

    def process(self, url: str, source: str = DEFAULT_SOURCE_TAG) -> int:
        """
        Process a single URL: scrape, extract metadata, and index to Vectara.

        Args:
            url: URL to process
            source: Source tag for metadata (default: "techdocs")

        Returns:
            IndexStatus.SUCCESS (0) if successful
            IndexStatus.FAILURE (-1) if failed

        Raises:
            RuntimeError: If indexer not initialized (call setup() first)
        """
        if self.indexer is None:
            error_msg = f"[Worker {os.getpid()}] Indexer not initialized. Call setup() first."
            logger.error(error_msg)
            self._track_failure(url)
            return IndexStatus.FAILURE

        metadata = {
            "source": source,
            "url": url,
            "is_public": True,
        }

        try:
            if self.rate_limiter:
                with self.rate_limiter:
                    success = self.indexer.index_url(
                        url, metadata=metadata, html_processing=self.html_processing, metadata_extractor=self._metadata_extractor.extract_from_html
                    )
            else:
                success = self.indexer.index_url(
                    url, metadata=metadata, html_processing=self.html_processing, metadata_extractor=self._metadata_extractor.extract_from_html
                )

            if success:
                self._track_success(url)
                return IndexStatus.SUCCESS
            else:
                logger.error(f"[Worker {os.getpid()}] Indexing failed for {url}")
                self._track_failure(url)
                return IndexStatus.FAILURE

        except Exception as e:
            logger.error(f"[Worker {os.getpid()}] Error indexing {url}: {e}\n" f"Traceback: {traceback.format_exc()}")
            self._track_failure(url)
            return IndexStatus.FAILURE

    def _track_success(self, url: str) -> None:
        """Record successfully indexed URL."""
        if self.use_ray_remote:
            # Ray mode: send to FileWriter actor (async, non-blocking)
            self.file_writer.record_success.remote(url)
        else:
            # Single-process mode: call directly
            self.file_writer.record_success(url)

    def _track_failure(self, url: str) -> None:
        """Record failed URL."""
        if self.use_ray_remote:
            # Ray mode: send to FileWriter actor (async, non-blocking)
            self.file_writer.record_failure.remote(url)
        else:
            # Single-process mode: call directly
            self.file_writer.record_failure(url)


# =============================================================================
# MAIN CRAWLER CLASS
# =============================================================================


class TechdocsCrawler(Crawler):
    """
    Production-grade crawler for Broadcom TechDocs documentation.

    This crawler implements a complete ETL pipeline for TechDocs content:
    1. Discovery: Fetch and parse XML sitemaps
    2. Filtering: Apply regex patterns and deduplication
    3. Processing: Extract content and metadata
    4. Indexing: Upload to Vectara corpus

    Configuration:
        See techdocs_crawler_config.yaml for full configuration options.
    """

    def __init__(self, cfg: Dict[str, Any], *args, **kwargs):
        """
        Initialize the TechDocs crawler.

        Args:
            cfg: Configuration dictionary
            *args: Additional positional arguments for parent class
            **kwargs: Additional keyword arguments for parent class
        """
        super().__init__(cfg, *args, **kwargs)
        self._setup_tracking_files()

    # -------------------------------------------------------------------------
    # Setup and Configuration
    # -------------------------------------------------------------------------

    def _setup_tracking_files(self) -> None:
        """
        Configure file paths for tracking crawled and failed URLs.

        Creates tracking directory and initializes tracking files based on
        configuration. Handles both Docker and local environments.
        """
        output_dir = self.cfg.vectara.get("output_dir", "vectara-ingest-output")

        # Determine tracking directory based on environment
        tracking_dir = self._get_tracking_directory(output_dir)
        self.tracking_dir = Path(tracking_dir)
        self.tracking_dir.mkdir(parents=True, exist_ok=True)

        # Initialize tracking file paths
        self.success_file = str(self.tracking_dir / SUCCESS_FILE_NAME)
        self.failed_file = str(self.tracking_dir / FAILED_FILE_NAME)

        # Clear tracking files if starting fresh crawl
        if self._should_clear_tracking_files():
            self._clear_tracking_files()

        logger.info(f"Tracking directory: {self.tracking_dir}")

    def _get_tracking_directory(self, output_dir: str) -> str:
        """
        Determine the tracking directory path based on environment.

        Args:
            output_dir: Configured output directory

        Returns:
            Full path to tracking directory
        """
        if os.path.isabs(output_dir):
            return os.path.join(output_dir, TRACKING_SUBDIR)

        # Check if running in Docker
        if Path(DOCKER_HOME).exists():
            return os.path.join(DOCKER_HOME, output_dir, TRACKING_SUBDIR)

        # Running locally
        return os.path.join(output_dir, TRACKING_SUBDIR)

    def _should_clear_tracking_files(self) -> bool:
        """
        Determine if tracking files should be cleared.

        Returns:
            True if files should be cleared (fresh crawl), False to preserve (resume)
        """
        is_reindex = self.cfg.vectara.get("reindex", False)
        skip_crawled = self.cfg.techdocs_crawler.get("skip_already_crawled", False)

        # Clear if reindexing OR not skipping already-crawled URLs
        return is_reindex or not skip_crawled

    def _clear_tracking_files(self) -> None:
        """Clear tracking files for a fresh crawl."""
        for filepath in [self.success_file, self.failed_file]:
            try:
                Path(filepath).write_text("", encoding="utf-8")
                logger.debug(f"Cleared tracking file: {filepath}")
            except IOError as e:
                logger.warning(f"Failed to clear tracking file {filepath}: {e}")

    def _load_already_crawled_urls(self) -> Set[str]:
        """
        Load URLs that were already successfully indexed.

        Returns:
            Set of URLs to skip. Empty set if resuming is disabled.
        """
        # Don't skip any URLs if reindexing
        if self.cfg.vectara.get("reindex", False):
            return set()

        # Don't skip URLs if feature is disabled
        if not self.cfg.techdocs_crawler.get("skip_already_crawled", False):
            return set()

        # Load from success tracking file
        success_file = Path(self.success_file)
        if not success_file.exists():
            return set()

        try:
            content = success_file.read_text(encoding="utf-8")
            crawled_urls = {line.strip() for line in content.splitlines() if line.strip()}
            logger.info(f"Loaded {len(crawled_urls)} already-crawled URLs")
            return crawled_urls

        except IOError as e:
            logger.error(f"Error loading indexed URLs from {self.success_file}: {e}")
            return set()

    def _load_failed_urls(self) -> List[str]:
        """
        Load URLs that previously failed to index.

        Returns:
            List of failed URLs. Empty list if no failed URLs exist.
        """
        failed_file = Path(self.failed_file)
        if not failed_file.exists():
            return []

        try:
            content = failed_file.read_text(encoding="utf-8")
            failed_urls = [line.strip() for line in content.splitlines() if line.strip()]
            logger.info(f"Loaded {len(failed_urls)} failed URLs for retry")
            return failed_urls

        except IOError as e:
            logger.error(f"Error loading failed URLs from {self.failed_file}: {e}")
            return []

    def _clear_failed_urls_file(self) -> None:
        """
        Clear the failed URLs tracking file before retrying.

        This ensures we only track URLs that fail again on retry,
        not URLs that were previously failed but succeed on retry.
        """
        try:
            Path(self.failed_file).write_text("", encoding="utf-8")
            logger.info(f"Cleared failed URLs file: {self.failed_file}")
        except IOError as e:
            logger.warning(f"Failed to clear failed URLs file {self.failed_file}: {e}")

    def _get_final_counts(self) -> tuple:
        """
        Get final counts of indexed and failed URLs from tracking files.

        Returns:
            Tuple of (indexed_count, failed_count)
        """
        indexed_count = 0
        failed_count = 0

        # Count indexed URLs
        success_file = Path(self.success_file)
        if success_file.exists():
            try:
                content = success_file.read_text(encoding="utf-8")
                indexed_count = len([line for line in content.splitlines() if line.strip()])
            except IOError:
                pass

        # Count failed URLs
        failed_file = Path(self.failed_file)
        if failed_file.exists():
            try:
                content = failed_file.read_text(encoding="utf-8")
                failed_count = len([line for line in content.splitlines() if line.strip()])
            except IOError:
                pass

        return indexed_count, failed_count

    # -------------------------------------------------------------------------
    # Main Crawl Logic
    # -------------------------------------------------------------------------

    def crawl(self) -> None:
        """
        Main crawl orchestration method.

        Executes the complete crawl pipeline:
        1. Discover URLs from sitemaps (or load failed URLs for retry)
        2. Filter and deduplicate
        3. Apply limits and skip already-crawled
        4. Dispatch to workers
        5. Log summary

        Raises:
            Exception: If critical errors occur during crawl
        """
        logger.info("=" * SEPARATOR_WIDTH)
        logger.info("STARTING TECHDOCS CRAWL")
        logger.info("=" * SEPARATOR_WIDTH)

        # Check if we should retry failed URLs
        reindex_failed = self.cfg.techdocs_crawler.get("reindex_failed_urls", False)

        if reindex_failed:
            # Load failed URLs for retry
            logger.info("Retry mode: Loading previously failed URLs...")
            urls_to_crawl = self._load_failed_urls()

            if not urls_to_crawl:
                logger.info("No failed URLs to retry")
                return

            logger.info(f"Loaded {len(urls_to_crawl)} failed URLs for retry")

            # Clear the failed file before retrying
            # Only URLs that fail again will be written back
            self._clear_failed_urls_file()

            # Skip URLs that have already been successfully indexed
            # (in case they succeeded in a previous retry)
            already_crawled = self._load_already_crawled_urls()
            if already_crawled:
                original_count = len(urls_to_crawl)
                urls_to_crawl = [url for url in urls_to_crawl if url not in already_crawled]
                skipped_count = original_count - len(urls_to_crawl)
                if skipped_count > 0:
                    logger.info(f"Skipping {skipped_count} URLs that were already successfully indexed")

            if not urls_to_crawl:
                logger.info("All failed URLs have already been successfully indexed")
                return

        else:
            # Normal mode: discover URLs from sitemaps
            # Pipeline stage 1: URL discovery
            all_urls = self._discover_urls_from_sitemaps()
            logger.info(f"Discovered {len(all_urls)} total URLs from sitemaps")

            # Pipeline stage 2: Filter and deduplicate
            urls_to_crawl = self._filter_and_prepare_urls(all_urls)
            logger.info(f"After filtering: {len(urls_to_crawl)} URLs")

            # Pipeline stage 3: Apply max_urls limit
            urls_to_crawl = self._apply_max_urls_limit(urls_to_crawl)

            # Pipeline stage 4: Skip already-crawled URLs
            urls_to_crawl = self._skip_already_crawled(urls_to_crawl)

        # Check if there's work to do
        if not urls_to_crawl:
            logger.info("No URLs to crawl (all URLs already processed)")
            return

        # Pipeline stage 5: Dispatch to workers
        logger.info(f"Starting crawl of {len(urls_to_crawl)} URLs...")
        self._dispatch_crawl_jobs(urls_to_crawl)

        # Log final summary
        indexed_count, failed_count = self._get_final_counts()
        logger.info("=" * SEPARATOR_WIDTH)
        logger.info("TECHDOCS CRAWL COMPLETED SUCCESSFULLY")
        logger.info(f"Indexed: {indexed_count} | Failed: {failed_count}")
        logger.info("=" * SEPARATOR_WIDTH)

    def _discover_urls_from_sitemaps(self) -> List[str]:
        """
        Download and parse all configured sitemaps to discover URLs.

        Returns:
            List of all URLs discovered from sitemaps (may contain duplicates)
        """
        sitemap_urls = self.cfg.techdocs_crawler.sitemap_urls
        pos_regex = self.cfg.techdocs_crawler.get("pos_regex", [])
        neg_regex = self.cfg.techdocs_crawler.get("neg_regex", [])

        # Compile regex patterns once
        pos_patterns = [re.compile(pattern) for pattern in pos_regex]
        neg_patterns = [re.compile(pattern) for pattern in neg_regex]

        all_urls = []
        for sitemap_url in sitemap_urls:
            # Download and parse sitemap
            urls = download_and_parse_sitemap(sitemap_url)

            # Apply regex filtering
            filtered_urls = [url for url in urls if url_matches_patterns(url, pos_patterns, neg_patterns)]

            logger.info(f"Sitemap: {sitemap_url} - " f"Found {len(urls)} URLs, {len(filtered_urls)} after filtering")

            all_urls.extend(filtered_urls)

        return all_urls

    def _filter_and_prepare_urls(self, all_urls: List[str]) -> List[str]:
        """
        Filter and deduplicate URLs.

        Args:
            all_urls: List of URLs (may contain duplicates)

        Returns:
            Deduplicated list of URLs
        """
        # Remove duplicates while preserving order
        unique_urls = list(dict.fromkeys(all_urls))

        duplicates_removed = len(all_urls) - len(unique_urls)
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate URLs")

        return unique_urls

    def _apply_max_urls_limit(self, urls: List[str]) -> List[str]:
        """
        Apply max_urls limit if configured.

        Args:
            urls: List of URLs

        Returns:
            Limited list of URLs
        """
        max_urls = self.cfg.techdocs_crawler.get("max_urls", None)
        if not max_urls or max_urls <= 0:
            return urls

        original_count = len(urls)
        limited_urls = urls[:max_urls]

        logger.info(f"max_urls limit applied: {len(limited_urls)} URLs selected " f"(limited from {original_count} total)")

        return limited_urls

    def _skip_already_crawled(self, urls: List[str]) -> List[str]:
        """
        Skip URLs that were already successfully crawled.

        Args:
            urls: List of URLs to crawl

        Returns:
            Filtered list of URLs (excluding already-crawled)
        """
        already_crawled = self._load_already_crawled_urls()
        if not already_crawled:
            return urls

        original_count = len(urls)
        remaining_urls = [url for url in urls if url not in already_crawled]
        skipped_count = original_count - len(remaining_urls)

        logger.info(f"Skipping {skipped_count} already-crawled URLs. " f"Remaining: {len(remaining_urls)}")

        return remaining_urls

    # -------------------------------------------------------------------------
    # Worker Dispatch
    # -------------------------------------------------------------------------

    def _dispatch_crawl_jobs(self, urls: List[str]) -> None:
        """
        Dispatch crawl jobs to workers (Ray or single-process).

        Args:
            urls: List of URLs to crawl (already filtered and limited)
        """
        # Get configuration
        num_per_second = self.cfg.techdocs_crawler.get("num_per_second", None)
        ray_workers = self.cfg.techdocs_crawler.get("ray_workers", 0)
        source = DEFAULT_SOURCE_TAG

        # Resolve -1 (all cores)
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)
            logger.info(f"Using all available CPU cores: {ray_workers}")

        # Dispatch to appropriate handler
        if ray_workers > 0:
            self._dispatch_to_ray_workers(urls, ray_workers, num_per_second, source)
        else:
            self._dispatch_to_single_process(urls, num_per_second, source)

    def _dispatch_to_ray_workers(self, urls: List[str], ray_workers: int, num_per_second: int, source: str) -> None:
        """
        Dispatch jobs to Ray workers for parallel processing.

        Uses a sliding window approach to prevent memory exhaustion with large URL lists.

        Args:
            urls: List of URLs to process
            ray_workers: Number of Ray worker actors
            num_per_second: Rate limit per worker
            source: Source tag for metadata
        """
        logger.info(f"Initializing Ray with {ray_workers} workers...")
        start_time = time.time()

        # Disable browser in main process (workers will create their own)
        self.indexer.p = self.indexer.browser = None

        # Configure Ray with memory limits
        self._initialize_ray(ray_workers)

        try:
            # Create and setup worker actors and file writer
            actors, file_writer = self._create_ray_actors(ray_workers, num_per_second)

            # Process URLs with sliding window
            self._process_urls_with_sliding_window(urls, actors, file_writer, source)

        finally:
            # Cleanup Ray resources
            self._cleanup_ray_actors(actors)
            ray.shutdown()
            logger.info("Ray shutdown complete")

    def _initialize_ray(self, num_workers: int) -> None:
        """
        Initialize Ray for parallel processing.

        Note: If running in Docker and experiencing /dev/shm errors,
        increase shared memory with: docker run --shm-size=8g ...

        Args:
            num_workers: Number of CPU cores to allocate
        """
        ray.init(num_cpus=num_workers, log_to_driver=True, include_dashboard=False)
        logger.info(f"Ray initialized with {num_workers} workers")

    def _create_ray_actors(self, num_actors: int, num_per_second: int) -> Tuple[List[Any], Any]:
        """
        Create and setup Ray worker actors and FileWriter actor.

        Args:
            num_actors: Number of actors to create
            num_per_second: Rate limit per actor

        Returns:
            Tuple of (list of worker actor handles, file writer actor handle)
        """
        # Create FileWriter as Ray actor for process-safe file writes
        file_writer = ray.remote(FileWriter).remote(self.success_file, self.failed_file)
        logger.info("Created FileWriter actor for process-safe tracking")

        # Create worker actors with reference to FileWriter actor
        actors = [ray.remote(PageCrawlWorker).remote(self.cfg, num_per_second, file_writer, use_ray_remote=True) for _ in range(num_actors)]

        # Setup all actors in parallel
        ray.get([actor.setup.remote() for actor in actors])
        logger.info(f"Created and initialized {num_actors} Ray worker actors")

        return actors, file_writer

    def _process_urls_with_sliding_window(self, urls: List[str], actors: List[Any], file_writer: Any, source: str) -> None:
        """
        Process URLs using a sliding window to control memory usage.

        Args:
            urls: List of URLs to process
            actors: List of Ray actor handles
            file_writer: FileWriterActor handle for getting counts
            source: Source tag for metadata

        Returns:
            None
        """
        pending_tasks = {}  # task_ref -> (index, url)
        next_submit_index = 0
        completed_count = 0
        total_urls = len(urls)

        # Fill initial window
        while next_submit_index < len(urls) and len(pending_tasks) < MAX_PENDING_TASKS:
            self._submit_task(urls, actors, next_submit_index, source, pending_tasks)
            next_submit_index += 1

        logger.info(f"Initial batch: {len(pending_tasks)} tasks submitted")

        # Process with sliding window
        while pending_tasks:
            # Wait for task completion
            ready_tasks, _ = ray.wait(list(pending_tasks.keys()), num_returns=1, timeout=None)

            # Process completed tasks
            for task_ref in ready_tasks:
                ray.get(task_ref)  # Get result but counts are tracked by FileWriterActor
                completed_count += 1

                # Remove from pending
                del pending_tasks[task_ref]

                # Log progress every 1000 URLs
                if completed_count % 1000 == 0:
                    # Get accurate counts from FileWriterActor
                    success_count, failure_count = ray.get(file_writer.get_counts.remote())
                    logger.info(f"Progress: {completed_count}/{total_urls} URLs | " f"Indexed: {success_count} | Failed: {failure_count}")

                # Submit next task
                if next_submit_index < len(urls):
                    self._submit_task(urls, actors, next_submit_index, source, pending_tasks)
                    next_submit_index += 1

        logger.info(f"All {len(urls)} URLs processed")

    def _submit_task(self, urls: List[str], actors: List[Any], index: int, source: str, pending_tasks: Dict[Any, Tuple[int, str]]) -> None:
        """
        Submit a single URL processing task to a Ray actor.

        Args:
            urls: Complete list of URLs
            actors: List of Ray actors
            index: Index of URL to submit
            source: Source tag for metadata
            pending_tasks: Dictionary to track pending tasks
        """
        url = urls[index]
        actor = actors[index % len(actors)]
        task_ref = actor.process.remote(url, source=source)
        pending_tasks[task_ref] = (index, url)

    def _cleanup_ray_actors(self, actors: List[Any]) -> None:
        """
        Cleanup Ray actor resources.

        Args:
            actors: List of Ray actor handles
        """
        try:
            ray.get([actor.cleanup.remote() for actor in actors])
            logger.info("Ray actors cleaned up")
        except Exception as e:
            logger.warning(f"Error during Ray actor cleanup: {e}")

    def _dispatch_to_single_process(self, urls: List[str], num_per_second: int, source: str) -> None:
        """
        Process URLs sequentially in a single process.

        Args:
            urls: List of URLs to process
            num_per_second: Rate limit
            source: Source tag for metadata
        """
        logger.info("Processing URLs sequentially (single process mode)")

        # Create FileWriter as regular class (not Ray actor)
        file_writer = FileWriter(self.success_file, self.failed_file)

        worker = PageCrawlWorker(self.cfg, num_per_second, file_writer)
        worker.setup()

        try:
            for url in urls:
                worker.process(url, source=source)

        finally:
            worker.cleanup()
