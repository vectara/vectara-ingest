"""
Wolken KB Crawler

Crawls Knowledge Base articles from Wolken ServiceDesk using the public KB REST API
and indexes them into Vectara.

API docs: https://developer-beta.wolkensoftware.com/kb/docs.html

Flow:
1. Authenticate via refresh_token to get access_token
2. Fetch KB categories (paginated)
3. For each category, fetch articles (paginated)
4. For each article, fetch full details and index into Vectara
"""

import logging
import re
import time

import requests
from core.crawler import Crawler

logger = logging.getLogger(__name__)


def clean_html(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class WolkenCrawler(Crawler):

    def __init__(self, cfg, endpoint, corpus_key, api_key):
        super().__init__(cfg, endpoint, corpus_key, api_key)

        crawler_cfg = cfg.get("wolken_crawler", {})

        self.api_endpoint = crawler_cfg.get("api_endpoint", "")
        self.domain = crawler_cfg.get("domain", "")
        self.client_id = crawler_cfg.get("client_id", "")
        self.service_account = crawler_cfg.get("service_account", "")
        self.auth_code = crawler_cfg.get("auth_code", "")
        self.refresh_token_value = crawler_cfg.get("refresh_token", "")

        self.batch_size = crawler_cfg.get("batch_size", 100)
        self.kb_source_id = crawler_cfg.get("kb_source_id", None)

        # Content fields to extract from articleOtherInfo
        self.content_fields = crawler_cfg.get("content_fields", [
            "introduction", "cause", "environment", "resolution", "additionalInfo"
        ])

        self.access_token = None
        self.token_expires_at = 0
        self.session = requests.Session()

    def _ensure_token(self):
        """Refresh the access token if expired or missing."""
        if self.access_token and time.time() < self.token_expires_at:
            return

        url = f"{self.api_endpoint}/wolken-secure/oauth/token"
        headers = {
            "Authorization": self.auth_code,
            "domain": self.domain,
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token_value,
        }

        response = self.session.post(url, headers=headers, data=data, timeout=30)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data.get("access_token")
        if not self.access_token:
            raise ValueError("No access_token in response")

        expires_in = int(token_data.get("expires_in", 3600))
        self.token_expires_at = time.time() + expires_in - 120
        logger.info("Access token obtained (expires_in=%s)", expires_in)

    def _api_headers(self) -> dict:
        """Return headers for authenticated KB API calls."""
        self._ensure_token()
        return {
            "clientId": self.client_id,
            "domain": self.domain,
            "serviceAccount": self.service_account,
            "Authorization": f"Bearer {self.access_token}",
            "accept": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        """Make an authenticated GET request to the Wolken KB API."""
        url = f"{self.api_endpoint}/wolken-secure{path}"
        response = self.session.get(url, headers=self._api_headers(), params=params, timeout=60)

        if response.status_code == 401:
            logger.warning("Got 401, refreshing token and retrying")
            self.access_token = None
            response = self.session.get(url, headers=self._api_headers(), params=params, timeout=60)

        response.raise_for_status()
        return response.json()

    def _get_categories(self) -> list:
        """Fetch all KB categories with pagination."""
        categories = []
        offset = 0
        limit = self.batch_size

        while True:
            params = {}
            if self.kb_source_id is not None:
                params["kbSourceId"] = self.kb_source_id

            result = self._get(f"/api/kb/categories/{limit}/{offset}", params=params)
            data = result.get("data", [])
            if not data:
                break

            if isinstance(data, dict):
                categories.append(data)
                break
            categories.extend(data)

            if len(data) < limit:
                break
            offset += limit

        logger.info("Found %d KB categories", len(categories))
        return categories

    def _get_articles_for_category(self, cat_id: int) -> list:
        """Fetch all articles for a given category with pagination."""
        articles = []
        offset = 0
        limit = self.batch_size

        while True:
            result = self._get(f"/api/kb/articles/{cat_id}/{limit}/{offset}")
            data = result.get("data", [])
            if not data:
                break

            if isinstance(data, dict):
                articles.append(data)
                break
            articles.extend(data)

            if len(data) < limit:
                break
            offset += limit

        return articles

    def _get_article_details(self, article_id: int) -> dict:
        """Fetch full article details by ID."""
        result = self._get(f"/api/kb/articles/{article_id}")
        data = result.get("data", {})
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data if isinstance(data, dict) else {}

    def _build_article_content(self, details: dict) -> list:
        """
        Extract content sections from article details.
        Returns list of (section_title, section_text) tuples.
        """
        other_info = details.get("articleOtherInfo", {}) or {}
        sections = []

        field_titles = {
            "introduction": "Introduction",
            "cause": "Cause",
            "environment": "Environment",
            "resolution": "Resolution",
            "additionalInfo": "Additional Info",
            "internalNotes": "Internal Notes",
        }

        for field in self.content_fields:
            raw = other_info.get(field, "") or ""
            text = clean_html(raw)
            if text:
                title = field_titles.get(field, field.replace("_", " ").title())
                sections.append((title, text))

        # Fallback: use description or summary if no content fields found
        if not sections:
            desc = clean_html(details.get("description", "") or "")
            if desc:
                sections.append(("Description", desc))
            summary = clean_html(details.get("summary", "") or "")
            if summary:
                sections.append(("Summary", summary))

        return sections

    def crawl(self) -> None:
        """Main crawl loop: categories → articles → details → index."""
        categories = self._get_categories()

        indexed_ids = set()
        if self.tracker and not self.cfg.vectara.get("reindex", False):
            indexed_ids = self.tracker.get_indexed_ids()

        total_indexed = 0
        total_failed = 0
        total_skipped = 0

        for cat in categories:
            cat_id = cat.get("catId")
            cat_name = cat.get("catName", "Unknown")
            if not cat_id:
                continue

            logger.info("Fetching articles for category '%s' (id=%s)", cat_name, cat_id)
            articles = self._get_articles_for_category(cat_id)
            logger.info("Found %d articles in category '%s'", len(articles), cat_name)

            for article in articles:
                self.check_shutdown()

                article_id = article.get("articleId")
                article_title = article.get("articleTitle", "Untitled")
                if not article_id:
                    continue

                doc_id = f"wolken-kb-{article_id}"

                if doc_id in indexed_ids:
                    total_skipped += 1
                    continue

                try:
                    details = self._get_article_details(article_id)
                    if not details:
                        logger.warning("No details for article %s, skipping", article_id)
                        total_failed += 1
                        if self.tracker:
                            self.tracker.track_failed(doc_id, title=article_title, error="No details returned")
                        continue

                    title = details.get("articleTitle", article_title)
                    content_sections = self._build_article_content(details)

                    if not content_sections:
                        logger.info("Article %s has no content, skipping", article_id)
                        total_skipped += 1
                        if self.tracker:
                            self.tracker.track_skipped(doc_id, title=title, reason="No content")
                        continue

                    # Build metadata
                    other_info = details.get("articleOtherInfo", {}) or {}
                    metadata = {
                        "source": "wolken_kb",
                        "article_id": str(article_id),
                        "category": cat_name,
                        "created_time": details.get("createdTime", ""),
                        "updated_time": details.get("updatedTime", ""),
                        "status_id": str(details.get("statusId", "")),
                        "validation_status_id": str(other_info.get("validationStatusId", "")),
                        "published_date": other_info.get("publishedDate", ""),
                    }

                    # Build article URL if available
                    url_name = details.get("articleUrlName", "")
                    if url_name:
                        metadata["url"] = url_name

                    texts = [text for _, text in content_sections]
                    titles = [section_title for section_title, _ in content_sections]

                    succeeded = self.indexer.index_segments(
                        doc_id=doc_id,
                        texts=texts,
                        titles=titles,
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
                    logger.warning("Failed to process article %s: %s", article_id, e)
                    total_failed += 1
                    if self.tracker:
                        self.tracker.track_failed(doc_id, title=article_title, error=str(e))

        logger.info(
            "Wolken KB crawl complete: indexed=%d, failed=%d, skipped=%d",
            total_indexed, total_failed, total_skipped,
        )
