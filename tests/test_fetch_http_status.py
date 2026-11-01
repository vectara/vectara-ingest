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
from core.utils import AdaptiveRateController  # noqa: E402
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
    page.goto.return_value = None if goto_status is None else SimpleNamespace(
        status=goto_status, headers={"retry-after": "30"} if goto_status == 429 else {}
    )
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

    def test_browser_retry_after_is_reported(self):
        result = _fetch(_make_extractor(goto_status=429))
        self.assertEqual(result["retry_after"], "30")

    def test_browser_success_after_static_429_is_not_an_error(self):
        result = _fetch(
            _make_extractor(goto_status=200), static_status=429, headers={"Retry-After": "60"}
        )
        self.assertEqual(result["status_code"], 200)
        self.assertIsNone(result["retry_after"])

    def test_static_429_kept_when_browser_also_fails(self):
        extractor = _make_extractor(goto_error=RuntimeError("browser gone"))
        result = _fetch(extractor, static_status=429, headers={"Retry-After": "60"})
        self.assertEqual(result["status_code"], 429)
        self.assertEqual(result["retry_after"], "60")

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

    def _make_indexer(self, status, retry_after=None):
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
            "retry_after": retry_after,
        })
        ix.index_segments = MagicMock(return_value=True)
        return ix

    def test_429_is_not_indexed(self):
        ix = self._make_indexer(429, retry_after="60")
        self.assertFalse(ix.index_url(URL, metadata={"url": URL}))
        ix.index_segments.assert_not_called()
        self.assertEqual(ix.last_fetch_status, 429)
        self.assertEqual(ix.last_retry_after, "60")
        self.assertIn("429", ix.last_error)

    def test_other_statuses_are_indexed_as_before(self):
        for status in (200, None, 403, 404, 503):
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


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestAdaptiveRateController(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        patcher = patch("core.utils.time.monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.controller = AdaptiveRateController(max_rate=8)

    def test_slots_are_spaced_by_the_rate(self):
        self.assertEqual(self.controller.acquire(), 0)
        self.assertEqual(self.controller.acquire(), 0.125)
        self.assertEqual(self.controller.acquire(), 0.25)

    def test_429_halves_the_rate_and_pauses_for_retry_after(self):
        self.controller.report_429("60")
        self.assertEqual(self.controller.rate, 4)
        self.assertEqual(self.controller.acquire(), 60)

    def test_burst_of_429s_only_halves_once(self):
        for _ in range(40):
            self.controller.report_429("60")
        self.assertEqual(self.controller.rate, 4)

    def test_429_after_the_pause_halves_again(self):
        self.controller.report_429("60")
        self.clock.now += 61
        self.controller.report_429("60")
        self.assertEqual(self.controller.rate, 2)

    def test_rate_has_a_floor(self):
        for _ in range(20):
            self.controller.report_429("1")
            self.clock.now += 2
        self.assertEqual(self.controller.rate, AdaptiveRateController.MIN_RATE)

    def test_missing_or_http_date_retry_after_uses_default_pause(self):
        for value in (None, "Wed, 21 Oct 2026 07:28:00 GMT"):
            with self.subTest(value=value):
                controller = AdaptiveRateController(max_rate=8)
                controller.report_429(value)
                self.assertEqual(controller.acquire(), AdaptiveRateController.DEFAULT_PAUSE)

    def test_huge_retry_after_is_capped(self):
        self.controller.report_429("86400")
        self.assertEqual(self.controller.acquire(), AdaptiveRateController.MAX_PAUSE)

    def test_success_recovers_rate_up_to_the_maximum(self):
        self.controller.report_429("1")
        self.clock.now += 2
        for _ in range(1000):
            self.controller.report_ok()
        self.assertEqual(self.controller.rate, 8)

    def test_success_does_not_raise_rate_during_a_pause(self):
        self.controller.report_429("60")
        self.controller.report_ok()
        self.assertEqual(self.controller.rate, 4)


class TestPageCrawlWorkerRateControl(unittest.TestCase):

    def _worker(self, succeeded, status, retry_after=None):
        worker = PageCrawlWorker.__new__(PageCrawlWorker)
        worker.indexer = MagicMock()
        worker.indexer.index_url.return_value = succeeded
        worker.indexer.was_skipped.return_value = False
        worker.indexer.last_skip_reason = None
        worker.indexer.last_fetch_status = status
        worker.indexer.last_retry_after = retry_after
        worker.sitemap_lastmods = {}
        worker.prior_fingerprints = {}
        worker.html_processing = {}
        worker.rate_limiter = MagicMock()
        worker.rate_controller = MagicMock()
        worker.rate_controller.acquire.return_value = 0
        return worker

    def test_429_is_rate_limited_and_reported_with_retry_after(self):
        worker = self._worker(False, 429, "60")
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_RATE_LIMITED)
        worker.rate_controller.report_429.assert_called_once_with("60")
        worker.rate_controller.report_ok.assert_not_called()

    def test_other_errors_are_failed_and_not_reported(self):
        worker = self._worker(False, 503)
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_FAILED)
        worker.rate_controller.report_429.assert_not_called()

    def test_success_is_reported(self):
        worker = self._worker(True, 200)
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_INDEXED)
        worker.rate_controller.report_ok.assert_called_once_with()

    def test_worker_waits_for_its_slot_before_fetching(self):
        worker = self._worker(True, 200)
        worker.rate_controller.acquire.return_value = 7
        with patch("crawlers.website_crawler.time.sleep") as sleep:
            worker.process(URL, source="web")
        sleep.assert_called_once_with(7)

    def test_worker_without_a_controller_still_runs(self):
        worker = self._worker(True, 200)
        worker.rate_controller = None
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_INDEXED)


class TestRateLimitRetryPass(unittest.TestCase):

    def _crawler(self, urls, still_limited=()):
        """`still_limited` holds, per pass, the URLs that get a 429 again."""
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.cfg = OmegaConf.create({"website_crawler": {"rate_limit_retry_wait": 10}})
        crawler.tracker = MagicMock()
        crawler.rate_limited_urls = list(urls)
        passes = iter(still_limited)

        def dispatch(urls, num_per_second, source, prior_fingerprints, sitemap_lastmods):
            self.assertEqual(num_per_second, 1)
            limited = next(passes, ())
            for url in urls:
                result = (PageCrawlWorker.RESULT_RATE_LIMITED if url in limited
                          else PageCrawlWorker.RESULT_INDEXED)
                crawler._track_result(url, result)

        crawler._dispatch_to_single_process = MagicMock(side_effect=dispatch)
        return crawler

    def test_rate_limited_page_is_deferred_not_failed(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.tracker = MagicMock()
        crawler.rate_limited_urls = []
        crawler._track_result(URL, PageCrawlWorker.RESULT_RATE_LIMITED)
        crawler.tracker.track_failed.assert_not_called()
        self.assertEqual(crawler.rate_limited_urls, [URL])

    def test_page_that_recovers_is_indexed(self):
        crawler = self._crawler([URL])
        with patch("crawlers.website_crawler.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        sleep.assert_called_once_with(10)
        crawler.tracker.track_indexed.assert_called_once_with(URL, url=URL)
        crawler.tracker.track_failed.assert_not_called()
        self.assertEqual(crawler.rate_limited_urls, [])

    def test_wait_grows_and_page_can_recover_on_the_last_pass(self):
        crawler = self._crawler([URL], still_limited=[(URL,)])
        with patch("crawlers.website_crawler.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [10, 20])
        crawler.tracker.track_failed.assert_not_called()

    def test_page_still_limited_after_all_passes_is_failed_once(self):
        crawler = self._crawler([URL], still_limited=[(URL,), (URL,)])
        with patch("crawlers.website_crawler.time.sleep"):
            crawler._retry_rate_limited("web", {}, {})
        crawler.tracker.track_failed.assert_called_once_with(URL, url=URL)
        self.assertEqual(crawler.rate_limited_urls, [URL])

    def test_nothing_to_retry_does_not_wait(self):
        crawler = self._crawler([])
        with patch("crawlers.website_crawler.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        sleep.assert_not_called()
        crawler._dispatch_to_single_process.assert_not_called()

    def test_summary_warns_with_counts_and_settings_to_change(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.rate_limited_urls = ["u"] * 1538
        with self.assertLogs("crawlers.website_crawler", logging.WARNING) as logs:
            crawler._warn_if_rate_limited(2021)
        output = "\n".join(logs.output)
        self.assertIn("1538 of 2021", output)
        self.assertIn("num_per_second", output)
        self.assertIn("ray_workers", output)

    def test_no_summary_when_nothing_was_rate_limited(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.rate_limited_urls = []
        with self.assertNoLogs("crawlers.website_crawler", logging.WARNING):
            crawler._warn_if_rate_limited(2021)


if __name__ == "__main__":
    unittest.main()
