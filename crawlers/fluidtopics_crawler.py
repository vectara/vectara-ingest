"""
Fluid Topics crawler.

Crawls documents/topics from a Fluid Topics tenant using a configurable REST API
shape and indexes the extracted content into Vectara as structured documents.

The Fluid Topics APIs and response schemas can vary by tenant/version. This
crawler therefore keeps the source API endpoints, JSON paths, auth header, and
metadata mapping configurable instead of hard-coding one customer's tenant
contract.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl, html_to_text

logger = logging.getLogger(__name__)


_MISSING = object()


def _str_or_empty(value: Any) -> str:
    """Stringify metadata values without turning None into the literal 'None'."""
    return "" if value is None else str(value)


def _safe_doc_id(value: Any) -> str:
    """Create a stable Vectara document id fragment."""
    text = _str_or_empty(value).strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-")
    return text or "unknown"


def _get_path(data: Any, path: Optional[str], default: Any = None) -> Any:
    """Read a dotted path from nested dict/list data.

    Supports simple paths such as `metadata.version` and list indexes such as
    `results.0.id`. Returns `default` if any segment is missing.
    """
    if not path:
        return default
    current = data
    for part in str(path).split("."):
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else _MISSING
        else:
            return default
        if current is _MISSING:
            return default
    return current


def _get_first_path(data: Any, paths: List[str], default: Any = None) -> Any:
    for path in paths:
        value = _get_path(data, path, _MISSING)
        if value is not _MISSING and value is not None and value != "":
            return value
    return default


def _clean_markup(text: Any) -> str:
    """Convert Fluid Topics HTML/DITA/XML-ish content to plain text."""
    if text is None:
        return ""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False)
    text = str(text)
    if not text.strip():
        return ""
    try:
        if "<" in text and ">" in text:
            return html_to_text(text).strip()
    except Exception:
        logger.debug("html_to_text failed; falling back to BeautifulSoup", exc_info=True)
    if "<" in text and ">" in text:
        return BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


class FluidtopicsCrawler(Crawler):
    """Configurable crawler for Fluid Topics tenants."""

    DEFAULT_ITEM_PATHS = ["results", "items", "topics", "documents", "data", "content"]
    DEFAULT_ID_PATHS = ["id", "khubId", "contentId", "topicId", "mapId", "document_id"]
    DEFAULT_TITLE_PATHS = ["title", "name", "label", "metadata.title"]
    DEFAULT_CONTENT_PATHS = ["content", "body", "html", "text", "xml", "dita", "data.content", "data.body"]
    DEFAULT_URL_PATHS = ["url", "htmlUrl", "readerUrl", "metadata.url"]

    def __init__(self, cfg, endpoint, corpus_key, api_key):
        super().__init__(cfg, endpoint, corpus_key, api_key)
        crawler_cfg = cfg.get("fluidtopics_crawler", {})

        self.base_url = crawler_cfg.get("base_url", "").rstrip("/")
        if not self.base_url:
            raise ValueError("fluidtopics_crawler.base_url is required")

        self.api_key = crawler_cfg.get("api_key", "")
        if not self.api_key:
            raise ValueError("fluidtopics_crawler.api_key is required")

        self.api_key_header = crawler_cfg.get("api_key_header", "X-FluidTopics-Api-Key")
        self.auth_scheme = crawler_cfg.get("auth_scheme", "")
        self.search_endpoint = crawler_cfg.get("search_endpoint", "/api/search")
        self.content_endpoint_template = crawler_cfg.get("content_endpoint_template", "/api/topics/{id}")

        self.query = crawler_cfg.get("query", "*")
        self.query_param = crawler_cfg.get("query_param", "q")
        self.extra_params = dict(crawler_cfg.get("params", {}) or {})
        self.since_param = crawler_cfg.get("since_param", None)
        self.since = crawler_cfg.get("since", None)

        self.page_param = crawler_cfg.get("page_param", "page")
        self.page_size_param = crawler_cfg.get("page_size_param", "limit")
        self.page_size = int(crawler_cfg.get("page_size", 100))
        self.start_page = int(crawler_cfg.get("start_page", 0))
        self.max_pages = crawler_cfg.get("max_pages", None)
        self.next_page_path = crawler_cfg.get("next_page_path", None)

        self.items_path = crawler_cfg.get("items_path", None)
        self.id_paths = list(crawler_cfg.get("id_paths", self.DEFAULT_ID_PATHS))
        self.title_paths = list(crawler_cfg.get("title_paths", self.DEFAULT_TITLE_PATHS))
        self.content_paths = list(crawler_cfg.get("content_paths", self.DEFAULT_CONTENT_PATHS))
        self.url_paths = list(crawler_cfg.get("url_paths", self.DEFAULT_URL_PATHS))
        self.metadata_paths = dict(crawler_cfg.get("metadata_paths", {}) or {})
        self.static_metadata = dict(crawler_cfg.get("static_metadata", {}) or {})
        self.source = crawler_cfg.get("source", "fluid-topics")
        self.num_per_second = max(int(crawler_cfg.get("num_per_second", 5)), 1)

        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, crawler_cfg)

    def _headers(self) -> Dict[str, str]:
        value = f"{self.auth_scheme} {self.api_key}".strip() if self.auth_scheme else self.api_key
        return {
            self.api_key_header: value,
            "Accept": "application/json, text/html, application/xml, text/xml;q=0.9, */*;q=0.8",
        }

    def _url(self, endpoint: str) -> str:
        return urljoin(f"{self.base_url}/", endpoint.lstrip("/"))

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self._url(endpoint)
        response = self.session.get(url, headers=self._headers(), params=params, timeout=60)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
            logger.warning("Fluid Topics rate limited %s; sleeping %ss", url, wait)
            time.sleep(wait)
            response = self.session.get(url, headers=self._headers(), params=params, timeout=60)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            return response.json()
        try:
            return response.json()
        except Exception:
            return response.text

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []

        paths = [self.items_path] if self.items_path else self.DEFAULT_ITEM_PATHS
        for path in paths:
            items = _get_path(payload, path, None)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return []

    def iter_items(self) -> List[Dict[str, Any]]:
        """Fetch all item records from the configured search/list endpoint."""
        items: List[Dict[str, Any]] = []
        page = self.start_page
        pages_fetched = 0

        while True:
            params = dict(self.extra_params)
            if self.query_param and self.query is not None:
                params[self.query_param] = self.query
            if self.page_param:
                params[self.page_param] = page
            if self.page_size_param:
                params[self.page_size_param] = self.page_size
            if self.since_param and self.since:
                params[self.since_param] = self.since

            payload = self._request(self.search_endpoint, params=params)
            batch = self._extract_items(payload)
            if not batch:
                break

            items.extend(batch)
            pages_fetched += 1
            if self.max_pages is not None and pages_fetched >= int(self.max_pages):
                break

            next_page = _get_path(payload, self.next_page_path, None) if self.next_page_path else None
            if next_page is not None:
                page = next_page
            else:
                if len(batch) < self.page_size:
                    break
                page += 1

        return items

    def _content_endpoint(self, item: Dict[str, Any], item_id: str) -> str:
        values = {k: v for k, v in item.items() if isinstance(k, str)}
        values.update({"id": item_id, "document_id": item_id})
        return self.content_endpoint_template.format_map(_DefaultFormatDict(values))

    def _fetch_content_record(self, item: Dict[str, Any], item_id: str) -> Any:
        if not self.content_endpoint_template:
            return item
        return self._request(self._content_endpoint(item, item_id))

    def _extract_text(self, item: Dict[str, Any], content_record: Any) -> str:
        candidates = [content_record, item]
        for candidate in candidates:
            if isinstance(candidate, str):
                text = _clean_markup(candidate)
                if text:
                    return text
            for path in self.content_paths:
                value = _get_path(candidate, path, None)
                text = _clean_markup(value)
                if text:
                    return text
        return ""

    def _build_metadata(self, item: Dict[str, Any], content_record: Any, item_id: str, title: str) -> Dict[str, Any]:
        merged = item.copy()
        if isinstance(content_record, dict):
            merged.update(content_record)

        metadata = {
            "source": self.source,
            "document_id": _str_or_empty(item_id),
        }
        if title:
            metadata["title"] = title

        url = _get_first_path(merged, self.url_paths, None)
        if url:
            metadata["url"] = _str_or_empty(url)

        default_paths = {
            "device_family": "metadata.device_family",
            "content_type": "metadata.content_type",
            "version": "metadata.version",
            "access_tier": "metadata.access_tier",
            "publication_date": "metadata.publication_date",
        }
        for key, path in {**default_paths, **self.metadata_paths}.items():
            value = _get_path(merged, path, None)
            if value is not None:
                metadata[key] = value

        metadata.update(self.static_metadata)
        return metadata

    def crawl(self) -> None:
        items = self.iter_items()
        logger.info("Found %d Fluid Topics items", len(items))

        indexed_ids = set()
        if self.tracker and not self.cfg.vectara.get("reindex", False):
            indexed_ids = self.tracker.get_indexed_ids()

        delay = 1.0 / self.num_per_second
        total_indexed = 0
        total_failed = 0
        total_skipped = 0

        for item in items:
            self.check_shutdown()
            item_id = _get_first_path(item, self.id_paths, None)
            if item_id is None:
                logger.warning("Skipping Fluid Topics item with no configured id path: %s", item)
                total_skipped += 1
                continue

            doc_id = f"fluid-topics-{_safe_doc_id(item_id)}"
            title = _str_or_empty(_get_first_path(item, self.title_paths, item_id))

            if doc_id in indexed_ids:
                total_skipped += 1
                continue

            try:
                content_record = self._fetch_content_record(item, _str_or_empty(item_id))
                text = self._extract_text(item, content_record)
                if not text:
                    logger.info("Fluid Topics item %s has no extractable text, skipping", item_id)
                    total_skipped += 1
                    if self.tracker:
                        self.tracker.track_skipped(doc_id, title=title, reason="No content")
                    continue

                metadata = self._build_metadata(item, content_record, _str_or_empty(item_id), title)
                succeeded = self.indexer.index_segments(
                    doc_id=doc_id,
                    texts=[text],
                    titles=[title] if title else None,
                    doc_metadata=metadata,
                    doc_title=title,
                )

                if succeeded:
                    total_indexed += 1
                    if self.tracker:
                        self.tracker.track_indexed(doc_id, title=title)
                else:
                    total_failed += 1
                    if self.tracker:
                        self.tracker.track_failed(doc_id, title=title, error="Indexing failed")
            except Exception as e:
                logger.warning("Failed to process Fluid Topics item %s: %s", item_id, e)
                total_failed += 1
                if self.tracker:
                    self.tracker.track_failed(doc_id, title=title, error=str(e))

            if delay > 0:
                time.sleep(delay)

        logger.info(
            "Fluid Topics crawl complete: indexed=%d failed=%d skipped=%d",
            total_indexed, total_failed, total_skipped,
        )


class _DefaultFormatDict(dict):
    """Keep unknown endpoint-template placeholders visible instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"
