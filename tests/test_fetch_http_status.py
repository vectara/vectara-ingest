"""Regression: pages that come back with an HTTP error must not be indexed.

The static pre-fetch swallowed HTTP errors at DEBUG and the browser path ignored the
status of page.goto(), so a site's 429 page was indexed as if it were the real
document, replacing the good copy in the corpus while the run logged success.
"""

import importlib.machinery
import logging
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests

# Heavy native deps that the import chain touches.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())
_pw_mock = MagicMock()
_pw_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf  # noqa: E402

from core.indexer import Indexer  # noqa: E402
from crawlers.website_crawler import PageCrawlWorker, WebsiteCrawler  # noqa: E402

URL = "https://docs.example.com/guide/page.html"
BODY = "Too many requests"


def _make_extractor(goto_status=200, goto_error=None):
    """WebContentExtractor whose stub browser reports `goto_status` for navigation."""
    from core.web_content_extractor import WebContentExtractor

    cfg = SimpleNamespace(
        vectara=SimpleNamespace(get=lambda key, default=None: default)
    )
    extractor = WebContentExtractor(cfg=cfg, browser=MagicMock(name="browser"))
    extractor.p = MagicMock(name="playwright_runner")
    extractor._scroll_to_bottom = MagicMock()
    page = extractor.browser.new_context.return_value.new_page.return_value
    page.goto.side_effect = goto_error
    page.goto.return_value = None if goto_status is None else SimpleNamespace(status=goto_status)
    page.title.return_value = "Title"
    page.url = URL
    page.content.return_value = f"<html><body>{BODY}</body></html>"
    page.evaluate.return_value = []
    return extractor


def _http_error(status, headers=None):
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    return response


def _fetch(extractor, static_status=None, headers=None):
    """Run fetch_page_contents with the static pre-fetch failing with `static_status`."""
    if static_status is None:
        side_effect = requests.ConnectionError("no static")
    else:
        side_effect = None
    response = _http_error(static_status or 200, headers)
    with patch(
        "core.web_content_extractor.requests.get",
        side_effect=side_effect,
        return_value=response,
    ), patch("core.web_content_extractor.PlaywrightTimeoutError", TimeoutError):
        return extractor.fetch_page_contents(URL)


class TestExtractorReportsStatus(unittest.TestCase):

    def test_browser_error_status_is_reported(self):
        result = _fetch(_make_extractor(goto_status=429))
        self.assertEqual(result["status_code"], 429)

    def test_browser_success_after_static_429_is_not_an_error(self):
        result = _fetch(_make_extractor(goto_status=200), static_status=429)
        self.assertEqual(result["status_code"], 200)

    def test_static_429_kept_when_browser_also_fails(self):
        extractor = _make_extractor(goto_error=RuntimeError("browser gone"))
        result = _fetch(extractor, static_status=429)
        self.assertEqual(result["status_code"], 429)

    def test_no_browser_response_does_not_report_stale_static_status(self):
        result = _fetch(_make_extractor(goto_status=None), static_status=429)
        self.assertIsNone(result["status_code"])

    def test_static_429_logs_warning_with_retry_after(self):
        with self.assertLogs("core.web_content_extractor", logging.WARNING) as logs:
            _fetch(
                _make_extractor(goto_status=200),
                static_status=429,
                headers={"Retry-After": "60"},
            )
        output = "\n".join(logs.output)
        self.assertIn("429", output)
        self.assertIn("Retry-After: 60", output)


class TestIndexerSkipsErrorPages(unittest.TestCase):

    def _make_indexer(self, status):
        ix = Indexer.__new__(Indexer)
        ix.cfg = OmegaConf.create({"vectara": {"verbose": False}, "doc_processing": {}})
        ix.incremental = False
        ix.add_image_bytes = False
        ix.summarize_images = False
        ix.process_locally = False
        ix.remove_boilerplate = False
        ix.parse_tables = False
        ix.remove_code = False
        ix.detected_language = "en"
        ix.extract_metadata = []
        ix.timeout = 90
        ix.last_skip_reason = None
        ix.verbose = False
        ix.model_config = MagicMock()
        ix.file_processor = MagicMock()
        ix.file_processor.inline_images = True
        ix.url_triggers_download = MagicMock(return_value=False)
        ix.check_download_or_pdf = MagicMock(return_value={"type": "page"})
        ix.fetch_page_contents = MagicMock(return_value={
            "text": BODY, "html": f"<p>{BODY}</p>", "title": "t", "url": URL,
            "images": [], "tables": [], "links": [], "status_code": status,
        })
        ix.index_segments = MagicMock(return_value=True)
        return ix

    def test_error_statuses_are_not_indexed(self):
        for status in (403, 404, 429, 503):
            with self.subTest(status=status):
                ix = self._make_indexer(status)
                self.assertFalse(ix.index_url(URL, metadata={"url": URL}))
                ix.index_segments.assert_not_called()
                self.assertEqual(ix.last_fetch_status, status)
                self.assertIn(str(status), ix.last_error)

    def test_ok_and_unknown_statuses_are_indexed(self):
        for status in (200, None):
            with self.subTest(status=status):
                ix = self._make_indexer(status)
                self.assertTrue(ix.index_url(URL, metadata={"url": URL}))
                ix.index_segments.assert_called_once()

    def test_status_does_not_leak_into_next_url(self):
        ix = self._make_indexer(429)
        ix.index_url(URL, metadata={"url": URL})
        ix.fetch_page_contents.return_value["status_code"] = 200
        ix.index_url(URL, metadata={"url": URL})
        self.assertEqual(ix.last_fetch_status, 200)


class TestRateLimitReporting(unittest.TestCase):

    def _worker(self, succeeded, status):
        worker = PageCrawlWorker.__new__(PageCrawlWorker)
        worker.indexer = MagicMock()
        worker.indexer.index_url.return_value = succeeded
        worker.indexer.was_skipped.return_value = False
        worker.indexer.last_skip_reason = None
        worker.indexer.last_fetch_status = status
        worker.sitemap_lastmods = {}
        worker.prior_fingerprints = {}
        worker.html_processing = {}
        worker.rate_limiter = MagicMock()
        return worker

    def test_worker_reports_429_as_rate_limited(self):
        result = self._worker(False, 429).process(URL, source="web")
        self.assertEqual(result, PageCrawlWorker.RESULT_RATE_LIMITED)

    def test_worker_reports_other_errors_as_failed(self):
        result = self._worker(False, 503).process(URL, source="web")
        self.assertEqual(result, PageCrawlWorker.RESULT_FAILED)

    def test_rate_limited_page_is_tracked_as_failed(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.tracker = MagicMock()
        crawler._track_result(URL, PageCrawlWorker.RESULT_RATE_LIMITED)
        crawler.tracker.track_failed.assert_called_once()
        self.assertEqual(crawler.rate_limited_count, 1)

    def test_rate_limited_page_is_counted_without_a_tracker(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.tracker = None
        crawler._track_result(URL, PageCrawlWorker.RESULT_RATE_LIMITED)
        self.assertEqual(crawler.rate_limited_count, 1)

    def test_summary_warns_with_counts_and_settings_to_change(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.rate_limited_count = 1538
        with self.assertLogs("crawlers.website_crawler", logging.WARNING) as logs:
            crawler._warn_if_rate_limited(2021)
        output = "\n".join(logs.output)
        self.assertIn("1538 of 2021", output)
        self.assertIn("num_per_second", output)
        self.assertIn("ray_workers", output)

    def test_no_summary_when_nothing_was_rate_limited(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        with self.assertNoLogs("crawlers.website_crawler", logging.WARNING):
            crawler._warn_if_rate_limited(2021)


if __name__ == "__main__":
    unittest.main()
