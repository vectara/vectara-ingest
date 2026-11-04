"""Regression: pages that come back with an HTTP error must not be indexed.

The static pre-fetch swallowed HTTP errors at DEBUG and the browser path ignored the
status of page.goto(), so a site's 429 page was indexed as if it were the real
document, replacing the good copy in the corpus while the run logged success.
"""

import importlib.machinery
import logging
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import requests

# Heavy native deps that the import chain touches.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())
_pw_mock = MagicMock()
_pw_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf  # noqa: E402

from core.crawl_tracker import CrawlShutdownException  # noqa: E402
from core.indexer import Indexer  # noqa: E402
from core.spider import recursive_crawl  # noqa: E402
from core.utils import (  # noqa: E402
    AdaptiveRateController, create_session_with_retries, leave_429_to_caller,
)
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
        status=goto_status, ok=goto_status < 400,
        headers={"retry-after": "30"} if goto_status == 429 else {},
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
    response.raw = MagicMock()
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
        self.assertTrue(result["throttled"])
        self.assertEqual(result["retry_after"], "60")

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

    def test_browser_429_keeps_static_retry_after_when_it_sends_none(self):
        extractor = _make_extractor(goto_status=429)
        goto = extractor.browser.new_context.return_value.new_page.return_value.goto
        goto.return_value = SimpleNamespace(status=429, ok=False, headers={})
        result = _fetch(extractor, static_status=429, headers={"Retry-After": "120"})
        self.assertEqual(result["retry_after"], "120")

    def test_browser_429_returns_without_waiting_for_the_page(self):
        extractor = _make_extractor(goto_status=429)
        result = _fetch(extractor)
        extractor._scroll_to_bottom.assert_not_called()
        self.assertEqual(result["text"], "")

    def test_browser_429_counts_as_a_working_browser(self):
        extractor = _make_extractor(goto_status=429)
        extractor.consecutive_failures = 2
        _fetch(extractor)
        self.assertEqual(extractor.consecutive_failures, 0)
        self.assertEqual(extractor.browser_use_count, 1)

    def test_one_static_429_keeps_static_fetches(self):
        extractor = _make_extractor(goto_status=200)
        _fetch(extractor, static_status=429)
        self.assertFalse(extractor.skip_static_prefetch)

    def test_repeated_static_429s_switch_to_the_browser(self):
        extractor = _make_extractor(goto_status=200)
        for _ in range(extractor.STATIC_REFUSALS_BEFORE_BROWSER_ONLY):
            _fetch(extractor, static_status=429)
        self.assertTrue(extractor.skip_static_prefetch)

    def test_a_static_success_restarts_the_count(self):
        extractor = _make_extractor(goto_status=200)
        for _ in range(extractor.STATIC_REFUSALS_BEFORE_BROWSER_ONLY - 1):
            _fetch(extractor, static_status=429)
        _fetch(extractor, static_status=200)
        for _ in range(extractor.STATIC_REFUSALS_BEFORE_BROWSER_ONLY - 1):
            _fetch(extractor, static_status=429)
        self.assertFalse(extractor.skip_static_prefetch)

    def test_static_429_then_browser_429_keeps_static_fetches(self):
        extractor = _make_extractor(goto_status=429)
        _fetch(extractor, static_status=429)
        self.assertFalse(extractor.skip_static_prefetch)


class TestStaticPathMatchesBrowser(unittest.TestCase):
    """The same page must index the same way on the static and browser paths."""

    FILLER = "Body text long enough for the static path to keep the page. " * 15

    def _fetch(self, html, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response.headers["content-type"] = "text/html"
        response._content = html.encode()
        extractor = _make_extractor(goto_status=200)
        with patch("core.web_content_extractor.requests.get", return_value=response), \
                patch("core.web_content_extractor.PlaywrightTimeoutError", TimeoutError):
            result = extractor.fetch_page_contents(URL, **kwargs)
        page = extractor.browser.new_context.return_value.new_page.return_value
        return result, page

    def _html(self, extra=""):
        return f"<html><head><title>Real title</title></head><body>{extra}<p>{self.FILLER}</p></body></html>"

    def test_remove_code_applies(self):
        result, _ = self._fetch(self._html("<pre>codeblock</pre><code>inline</code>"), remove_code=True)
        self.assertNotIn("codeblock", result["text"])
        self.assertNotIn("inline", result["text"])

    def test_code_kept_by_default(self):
        result, _ = self._fetch(self._html("<pre>codeblock</pre>"))
        self.assertIn("codeblock", result["text"])

    def test_removing_code_does_not_send_the_page_to_the_browser(self):
        html = f"<html><body><pre>{self.FILLER}</pre><p>{'word ' * 10}</p></body></html>"
        result, page = self._fetch(html, remove_code=True)
        page.goto.assert_not_called()
        self.assertNotIn("Body text", result["text"])

    def test_nav_counts_towards_the_minimum_and_keeps_its_links(self):
        html = (f'<html><body><nav><a href="/next">{self.FILLER}</a></nav>'
                "<p>Short body.</p></body></html>")
        result, page = self._fetch(html)
        page.goto.assert_not_called()
        self.assertEqual(result["links"], ["/next"])

    def test_title_survives_removing_the_head(self):
        result, _ = self._fetch(self._html(), html_processing={"tags_to_remove": ["head"]})
        self.assertEqual(result["title"], "Real title")

    def test_static_page_serves_tables_in_the_browser_format(self):
        """Tables are each table's outerHTML, as `_extract_tables` returns from the browser."""
        table = "<table><tr><td>x</td></tr></table>"
        result, page = self._fetch(self._html(table), extract_tables=True)
        page.goto.assert_not_called()
        self.assertEqual(result["tables"], [table])

    def test_tables_are_not_extracted_unless_requested(self):
        result, _ = self._fetch(self._html("<table><tr><td>x</td></tr></table>"))
        self.assertEqual(result["tables"], [])

    def test_removed_elements_leave_their_tables_out(self):
        html = self._html('<div class="ad"><table><tr><td>ad</td></tr></table></div>')
        result, _ = self._fetch(html, extract_tables=True, html_processing={"classes_to_remove": ["ad"]})
        self.assertEqual(result["tables"], [])


class TestScrapyExtractorReportsStatus(unittest.TestCase):

    def _fetch(self, status, headers=None):
        from core.scrapy_content_extractor import ScrapyContentExtractor

        extractor = ScrapyContentExtractor.__new__(ScrapyContentExtractor)
        extractor.timeout = 5
        extractor.session = MagicMock()
        response = _http_error(status, headers)
        response._content = b"<html><head><title>t</title></head><body>x</body></html>"
        response.url = URL
        extractor.session.get.return_value = response
        return extractor.fetch_page_contents(URL)

    def test_429_is_reported(self):
        result = self._fetch(429, {"Retry-After": "60"})
        self.assertEqual(result["status_code"], 429)
        self.assertEqual(result["retry_after"], "60")

    def test_success_is_reported(self):
        self.assertEqual(self._fetch(200)["status_code"], 200)


class TestInlinePdf429(unittest.TestCase):

    def test_browser_fallback_pdf_reports_status(self):
        extractor = _make_extractor(goto_status=429)
        page = extractor.browser.new_context.return_value.new_page.return_value
        page.expect_download.return_value.__enter__.side_effect = TimeoutError("no download")
        page.goto.return_value = SimpleNamespace(
            status=429, url=URL, headers={"content-type": "application/pdf", "retry-after": "60"},
            body=lambda: b"refused",
        )
        errors = SimpleNamespace(TargetClosedError=type("TargetClosedError", (Exception,), {}),
                                 Error=type("PlaywrightError", (Exception,), {}))
        with patch.dict(sys.modules, {"playwright._impl": MagicMock(), "playwright._impl._errors": errors}), \
                patch("core.web_content_extractor.requests.head", side_effect=requests.ConnectionError):
            result = extractor.check_download_or_pdf(URL)
        self.assertEqual(result["status_code"], 429)
        self.assertEqual(result["retry_after"], "60")

    def test_get_status_is_returned_with_the_pdf(self):
        extractor = _make_extractor()
        head = _http_error(200, {"content-type": "application/pdf"})
        get = _http_error(429, {"Retry-After": "60"})
        errors = {"playwright._impl": MagicMock(), "playwright._impl._errors": MagicMock()}
        with patch.dict(sys.modules, errors), \
                patch("core.web_content_extractor.requests.head", return_value=head), \
                patch("core.web_content_extractor.requests.get", return_value=get):
            result = extractor.check_download_or_pdf(URL)
        self.assertEqual(result["status_code"], 429)
        self.assertEqual(result["retry_after"], "60")


class TestDiscovery429(unittest.TestCase):

    def test_429_is_flagged_and_its_links_are_not_followed(self):
        section = "https://docs.example.com/guide/"
        indexer = MagicMock()
        indexer.fetch_page_contents.return_value = {
            "url": section, "links": ["https://docs.example.com/error-page-link"],
            "status_code": 429,
        }
        visited = recursive_crawl(section, 2, [re.compile(".*")], [], indexer)
        self.assertEqual(visited, {section})
        self.assertIs(indexer.discovery_rate_limited, True)

    def _crawl_with_controller(self, controller, statuses, html="<p>page</p>"):
        section = "https://docs.example.com/guide/"
        indexer = MagicMock()
        indexer.discovery_rate_limited = False
        indexer.fetch_page_contents.side_effect = [
            {"url": section, "links": [f"{section}{status}/"], "status_code": status, "retry_after": "60",
             "html": html}
            for status in statuses
        ]
        sleep = MagicMock()
        recursive_crawl(section, 5, [re.compile(".*")], [], indexer,
                        rate_controller=controller, sleep=sleep)
        return indexer, sleep

    def test_429_reaches_the_controller(self):
        controller = MagicMock()
        controller.acquire.return_value = 0
        self._crawl_with_controller(controller, [200, 429])
        controller.report_429.assert_called_once_with("60")
        controller.report_ok.assert_called_once_with()

    def test_failed_fetches_do_not_count_as_success(self):
        for statuses, html in (([503], "<p>Service Unavailable</p>"), ([None], "")):
            controller = MagicMock()
            controller.acquire.return_value = 0
            self._crawl_with_controller(controller, statuses, html=html)
            controller.report_ok.assert_not_called()

    def test_fetches_wait_for_the_controller(self):
        controller = MagicMock()
        controller.acquire.return_value = 7
        _, sleep = self._crawl_with_controller(controller, [429])
        sleep.assert_called_once_with(7)

    def test_static_429_rescued_by_browser_slows_discovery(self):
        controller = MagicMock()
        controller.acquire.return_value = 0
        indexer = MagicMock()
        indexer.fetch_page_contents.return_value = {
            "url": URL, "links": [], "status_code": 200, "throttled": True, "retry_after": "60",
            "html": "<p>page</p>",
        }
        recursive_crawl(URL + "/page", 1, [re.compile(".*")], [], indexer,
                        rate_controller=controller, sleep=MagicMock())
        self.assertEqual([c[0] for c in controller.method_calls], ["acquire", "report_429", "report_ok"])
        controller.report_429.assert_called_once_with("60")

    def test_discovery_waits_out_cooldown_before_next_homepage_or_indexing(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.cfg = OmegaConf.create({"website_crawler": {"pages_source": "crawl"}})
        crawler.indexer = MagicMock(verbose=False)
        crawler.pos_patterns = [re.compile(".*")]
        crawler.neg_patterns = []
        crawler.check_shutdown = MagicMock()
        clock = FakeClock()
        fetched = []

        def fetch(url):
            fetched.append(clock.now)
            return {"url": url, "links": [], "status_code": 429, "retry_after": "60"}

        crawler.indexer.fetch_page_contents.side_effect = fetch
        with patch("core.utils.time.monotonic", clock), \
                patch("core.utils.time.sleep", lambda seconds: setattr(clock, "now", clock.now + seconds)):
            crawler._discover_urls_with_internal_crawler([URL + "/first", URL + "/other"], 1, False)
        self.assertEqual(fetched, [1000, 1060])
        self.assertEqual(clock.now, 1120)

    def test_nothing_is_fetched_once_the_controller_gives_up(self):
        controller = MagicMock()
        controller.acquire.return_value = None
        indexer, _ = self._crawl_with_controller(controller, [200])
        indexer.fetch_page_contents.assert_not_called()
        self.assertIs(indexer.discovery_rate_limited, True)

    def test_a_shutdown_is_not_swallowed(self):
        controller = MagicMock()
        controller.acquire.return_value = 1
        indexer = MagicMock()
        with self.assertRaises(CrawlShutdownException):
            recursive_crawl("https://docs.example.com/guide/", 2, [], [], indexer,
                            rate_controller=controller,
                            sleep=MagicMock(side_effect=CrawlShutdownException))

    def test_refused_sitemap_flags_discovery(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.indexer = MagicMock(discovery_rate_limited=False)
        session = requests.Session()
        crawler.indexer.session = session
        crawler.cfg = OmegaConf.create({"website_crawler": {"pages_source": "sitemap"}})
        with crawler._flag_refused_sitemaps():
            session.hooks["response"][0](_http_error(200))
            self.assertIs(crawler.indexer.discovery_rate_limited, False)
            session.hooks["response"][0](_http_error(429))
            self.assertIs(crawler.indexer.discovery_rate_limited, True)

    def test_sitemap_hook_is_removed_after_discovery(self):
        """Vectara API calls share the session, so a 429 after discovery isn't a sitemap's."""
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.indexer = MagicMock(discovery_rate_limited=False)
        crawler.indexer.session = requests.Session()
        crawler.cfg = OmegaConf.create({"website_crawler": {"urls": [URL], "pages_source": "sitemap"}})
        hooks_during = []
        crawler._discover_urls_with_internal_crawler = MagicMock(
            side_effect=lambda *_: hooks_during.append(len(crawler.indexer.session.hooks["response"])) or [])
        crawler._discover_urls()
        self.assertEqual(hooks_during, [1])
        self.assertEqual(crawler.indexer.session.hooks["response"], [])

    def test_sitemap_hook_is_removed_when_discovery_fails(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.indexer = MagicMock(discovery_rate_limited=False)
        crawler.indexer.session = requests.Session()
        crawler.cfg = OmegaConf.create({"website_crawler": {"urls": [URL], "pages_source": "sitemap"}})
        crawler._discover_urls_with_internal_crawler = MagicMock(side_effect=CrawlShutdownException)
        with self.assertRaises(CrawlShutdownException):
            crawler._discover_urls()
        self.assertEqual(crawler.indexer.session.hooks["response"], [])

    def test_crawl_is_marked_interrupted(self):
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler._crawl_interrupted = False
        crawler.indexer = MagicMock(discovery_rate_limited=True)
        crawler._configure_indexer_session = MagicMock()
        crawler._discover_urls = MagicMock(return_value=[URL])
        crawler._filter_and_prepare_urls = MagicMock(return_value=[URL])
        crawler._dispatch_crawl_jobs = MagicMock()
        crawler._remove_old_content_if_needed = MagicMock()
        crawler.crawl()
        self.assertTrue(crawler._crawl_interrupted)


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
        ix.index_file = MagicMock(return_value=True)
        ix.session = MagicMock()
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

    def test_static_429_rescued_by_the_browser_is_indexed_and_flagged(self):
        ix = self._make_indexer(200, retry_after="60")
        ix.fetch_page_contents.return_value["throttled"] = True
        self.assertTrue(ix.index_url(URL, metadata={"url": URL}))
        self.assertTrue(ix.last_throttled)
        self.assertEqual(ix.last_retry_after, "60")

    def test_429_on_a_download_url_is_reported(self):
        ix = self._make_indexer(200)
        ix.url_triggers_download.return_value = True
        ix.session.get.return_value = _http_error(429, {"Retry-After": "60"})
        self.assertFalse(ix.index_url(URL, metadata={"url": URL}))
        self.assertEqual(ix.last_fetch_status, 429)
        self.assertEqual(ix.last_retry_after, "60")

    def test_429_on_a_markdown_file_is_reported_not_raised(self):
        ix = self._make_indexer(200)
        ix.session.get.return_value = _http_error(429, {"Retry-After": "60"})
        self.assertFalse(ix.index_url("https://docs.example.com/a.md", metadata={"url": URL}))
        self.assertEqual(ix.last_fetch_status, 429)

    def test_429_on_an_inline_pdf_is_not_indexed(self):
        ix = self._make_indexer(200)
        ix.check_download_or_pdf.return_value = {
            "type": "pdf", "url": URL, "content": b"Too many requests",
            "status_code": 429, "retry_after": "60",
        }
        self.assertFalse(ix.index_url(URL, metadata={"url": URL}))
        ix.index_file.assert_not_called()
        self.assertEqual(ix.last_fetch_status, 429)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestSession429Retries(unittest.TestCase):
    """urllib3 must hand a crawled site's 429 straight back, and keep retrying the API's."""

    SITEMAP = (b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               b'<url><loc>https://docs.example.com/a</loc></url></urlset>')

    def setUp(self):
        hits = self.hits = []
        self.refusals = refusals = [10**6]  # 429s to send before serving the page

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                if refusals[0] > 0:
                    refusals[0] -= 1
                    self.send_response(429)
                    self.send_header("Retry-After", "0")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = (b"Sitemap: https://docs.example.com/sitemap.xml\n" if self.path == "/robots.txt"
                        else TestSession429Retries.SITEMAP)
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):  # pylint: disable=redefined-builtin
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)
        self.url = f"http://127.0.0.1:{self.server.server_port}/a.md"

    def test_crawled_url_gets_one_request(self):
        session = create_session_with_retries()
        leave_429_to_caller(session, self.url)
        self.assertEqual(session.get(self.url).status_code, 429)
        self.assertEqual(len(self.hits), 1)

    def test_other_hosts_keep_their_retries(self):
        session = create_session_with_retries()
        leave_429_to_caller(session, "https://docs.example.com/a.md")
        adapter = session.get_adapter(self.url)
        self.assertIn(429, adapter.max_retries.status_forcelist)
        self.assertTrue(adapter.max_retries.respect_retry_after_header)

    def test_other_retries_are_kept_for_the_crawled_host(self):
        session = create_session_with_retries()
        leave_429_to_caller(session, self.url)
        retry = session.get_adapter(self.url).max_retries
        self.assertFalse(retry.is_retry("GET", 429, has_retry_after=True))
        self.assertTrue(retry.respect_retry_after_header)
        self.assertTrue(retry.is_retry("GET", 413, has_retry_after=True))
        self.assertIn(503, retry.status_forcelist)
        self.assertEqual(retry.increment("GET", self.url).total, retry.total - 1)
        self.assertFalse(retry.increment("GET", self.url).is_retry("GET", 429, has_retry_after=True))

    def test_session_without_retries_gets_none(self):
        session = requests.Session()
        leave_429_to_caller(session, self.url)
        self.assertEqual(session.get_adapter(self.url).max_retries.total, 0)

    def test_sitemap_fetch_retries_429(self):
        from core.spider import _download

        self.refusals[0] = 1
        self.assertEqual(_download(self.url, session=create_session_with_retries()), self.SITEMAP)
        self.assertEqual(len(self.hits), 2)

    def test_robots_fetch_retries_429(self):
        from core.spider import _robots_directives

        self.refusals[0] = 1
        root = self.url.rsplit("/", 1)[0]
        self.assertEqual(_robots_directives(root, session=create_session_with_retries()),
                         ["https://docs.example.com/sitemap.xml"])

    def test_index_url_keeps_429_retries_for_other_crawlers(self):
        ix = TestIndexerSkipsErrorPages()._make_indexer(200)
        ix.session = create_session_with_retries()
        ix.session.get = MagicMock(return_value=_http_error(429))
        md_url = "https://docs.example.com/a.md"
        ix.index_url(md_url, metadata={"url": md_url})
        self.assertIn(429, ix.session.get_adapter(md_url).max_retries.status_forcelist)


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

    def test_429_sent_before_the_pause_began_does_not_halve_again(self):
        sent_at = self.clock.now
        self.clock.now += 30  # slow browser loads: still in flight when the 429s start
        self.controller.report_429("0", sent_at=sent_at)
        self.clock.now += AdaptiveRateController.MIN_PAUSE + 1
        for _ in range(7):
            self.controller.report_429("0", sent_at=sent_at)
        self.assertEqual(self.controller.rate, 4)
        self.assertEqual(self.controller.pause_remaining(), 0)
        self.controller.report_429("0", sent_at=self.clock.now)
        self.assertEqual(self.controller.rate, 2)

    def test_rate_has_a_floor(self):
        for _ in range(20):
            self.controller.report_429("1")
            self.clock.now += 6
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
        self.clock.now += 6
        for _ in range(1000):
            self.controller.report_ok()
        self.assertEqual(self.controller.rate, 8)

    def test_success_does_not_raise_rate_during_a_pause(self):
        self.controller.report_429("60")
        self.controller.report_ok()
        self.assertEqual(self.controller.rate, 4)

    def test_retry_after_zero_or_negative_still_pauses_and_halves_once(self):
        for value in ("0", "-5"):
            with self.subTest(value=value):
                controller = AdaptiveRateController(max_rate=8)
                for _ in range(8):
                    controller.report_429(value)
                self.assertEqual(controller.rate, 4)
                self.assertEqual(controller.acquire(), AdaptiveRateController.MIN_PAUSE)

    def _fail_pauses(self, count):
        for _ in range(count):
            self.controller.report_429("60")
            self.clock.now += 61

    def test_gives_up_after_consecutive_pauses_without_a_success(self):
        self._fail_pauses(AdaptiveRateController.MAX_FAILED_PAUSES - 1)
        self.assertIsNotNone(self.controller.acquire())
        self._fail_pauses(1)
        self.assertIsNone(self.controller.acquire())

    def test_one_burst_does_not_give_up(self):
        for _ in range(500):
            self.controller.report_429("60")
        self.assertIsNotNone(self.controller.acquire())

    def test_success_resets_the_give_up_count(self):
        self._fail_pauses(AdaptiveRateController.MAX_FAILED_PAUSES - 1)
        self.controller.report_ok()
        self._fail_pauses(AdaptiveRateController.MAX_FAILED_PAUSES - 1)
        self.assertIsNotNone(self.controller.acquire())

    def test_pause_remaining(self):
        self.assertEqual(self.controller.pause_remaining(), 0)
        self.controller.report_429("60")
        self.clock.now += 20
        self.assertEqual(self.controller.pause_remaining(), 40)

    def test_rescheduled_workers_keep_the_reduced_rate_spacing(self):
        self.controller.acquire()
        self.controller.acquire()
        self.controller.report_429("60")
        self.assertEqual(self.controller.recheck(), 60)
        self.assertEqual(self.controller.recheck(), 60.25)
        self.clock.now += 60.25
        self.assertEqual(self.controller.recheck(), 0)

    def test_slot_booked_before_a_pause_is_rescheduled_after_it(self):
        booked_at = self.clock.now
        self.controller.rate = 1
        waits = [self.controller.acquire() for _ in range(8)]  # slots 0..7s ahead
        self.clock.now += 0.5
        self.controller.report_429("5")  # pause until +5.5s, rate 0.5
        self.clock.now = booked_at + waits[-1]
        self.assertGreater(self.controller.recheck(booked_at), 0)

    def test_slot_booked_after_the_pause_began_is_kept(self):
        self.controller.report_429("5")
        self.clock.now += 6
        booked_at = self.clock.now
        self.controller.acquire()
        self.assertEqual(self.controller.recheck(booked_at), 0)

    def test_recheck_stops_even_when_the_final_pause_has_expired(self):
        self._fail_pauses(AdaptiveRateController.MAX_FAILED_PAUSES)
        self.assertEqual(self.controller.pause_remaining(), 0)
        self.assertIsNone(self.controller.recheck())


class TestPageCrawlWorkerRateControl(unittest.TestCase):

    def _worker(self, succeeded, status, retry_after=None):
        worker = PageCrawlWorker.__new__(PageCrawlWorker)
        worker.indexer = MagicMock()
        worker.indexer.session = requests.Session()
        worker.indexer.index_url.return_value = succeeded
        worker.indexer.was_skipped.return_value = False
        worker.indexer.last_skip_reason = None
        worker.indexer.last_fetch_status = status
        worker.indexer.last_retry_after = retry_after
        worker.indexer.last_throttled = False
        worker.sitemap_lastmods = {}
        worker.prior_fingerprints = {}
        worker.html_processing = {}
        worker.rate_limiter = MagicMock()
        worker.rate_controller = MagicMock()
        worker.rate_controller.acquire.return_value = 0
        worker.rate_controller.recheck.return_value = 0
        return worker

    def test_429_is_rate_limited_and_reported_with_retry_after(self):
        worker = self._worker(False, 429, "60")
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_RATE_LIMITED)
        worker.rate_controller.report_429.assert_called_once_with("60", ANY)
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
        with patch("core.utils.time.sleep") as sleep:
            worker.process(URL, source="web")
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list), 7)

    def test_worker_leaves_429s_from_its_pages_to_the_controller(self):
        worker = self._worker(True, 200)
        worker.indexer.session = create_session_with_retries()
        worker.process(URL, source="web")
        self.assertNotIn(429, worker.indexer.session.get_adapter(URL).max_retries.status_forcelist)

    def test_worker_without_a_controller_keeps_429_retries(self):
        worker = self._worker(True, 200)
        worker.rate_controller = None
        worker.indexer.session = create_session_with_retries()
        worker.process(URL, source="web")
        self.assertIn(429, worker.indexer.session.get_adapter(URL).max_retries.status_forcelist)

    def test_worker_without_a_controller_still_runs(self):
        worker = self._worker(True, 200)
        worker.rate_controller = None
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_INDEXED)

    def test_worker_rechecks_pauses_imposed_and_extended_while_waiting(self):
        for extend in (False, True):
            with self.subTest(extend=extend):
                clock = FakeClock()
                controller = AdaptiveRateController(max_rate=2)
                worker = self._worker(True, 200)
                worker.rate_controller = controller
                pauses = []

                def sleep(seconds):
                    clock.now += seconds
                    if not pauses or (extend and len(pauses) == 1 and clock.now >= 1030):
                        controller.report_429("60")
                        pauses.append(clock.now + 60)

                def index_url(*args, **kwargs):
                    self.assertGreaterEqual(clock.now, pauses[-1])
                    return True

                worker.indexer.index_url.side_effect = index_url
                with patch("core.utils.time.monotonic", clock), patch("core.utils.time.sleep", sleep):
                    controller.acquire()  # Another worker reserved the first slot.
                    result = worker.process(URL, source="web")
                self.assertEqual(result, PageCrawlWorker.RESULT_INDEXED)
                self.assertEqual(len(pauses), 2 if extend else 1)
                worker.indexer.index_url.assert_called_once()

    def test_worker_rechecks_pause_after_the_per_worker_limiter(self):
        clock = FakeClock()
        controller = AdaptiveRateController(max_rate=2)
        worker = self._worker(True, 200)
        worker.rate_controller = controller
        worker.rate_limiter.__enter__.side_effect = lambda: controller.report_429("60")

        def index_url(*args, **kwargs):
            self.assertEqual(controller.pause_remaining(), 0)
            return True

        worker.indexer.index_url.side_effect = index_url
        with patch("core.utils.time.monotonic", clock), \
                patch("core.utils.time.sleep", lambda seconds: setattr(clock, "now", clock.now + seconds)):
            self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_INDEXED)
        worker.indexer.index_url.assert_called_once()

    def test_waiting_worker_stops_when_the_controller_gives_up(self):
        worker = self._worker(True, 200)
        worker.rate_controller.recheck.return_value = None
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_RATE_LIMITED)
        worker.indexer.index_url.assert_not_called()

    def test_unchanged_page_recovers_the_rate(self):
        worker = self._worker(True, 200)
        worker.indexer.was_skipped.return_value = True
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_SKIPPED)
        worker.rate_controller.report_ok.assert_called_once_with()

    def test_page_is_not_fetched_once_the_controller_gives_up(self):
        worker = self._worker(True, 200)
        worker.rate_controller.acquire.return_value = None
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_RATE_LIMITED)
        worker.indexer.index_url.assert_not_called()

    def test_static_429_rescued_by_the_browser_slows_the_crawl(self):
        worker = self._worker(True, 200, "60")
        worker.indexer.last_throttled = True
        self.assertEqual(worker.process(URL, source="web"), PageCrawlWorker.RESULT_INDEXED)
        worker.rate_controller.report_429.assert_called_once_with("60", ANY)

    def test_rescued_pages_do_not_count_towards_giving_up(self):
        controller = AdaptiveRateController(max_rate=8)
        worker = self._worker(True, 200, "60")
        worker.indexer.last_throttled = True
        worker.rate_controller = controller
        for _ in range(AdaptiveRateController.MAX_FAILED_PAUSES):
            with patch("core.utils.time.monotonic", return_value=controller._paused_until), \
                    patch("core.utils.time.sleep"):
                worker.process(URL, source="web")
        self.assertIsNotNone(controller.acquire())

    def test_a_shutdown_during_a_wait_stops_the_worker(self):
        worker = self._worker(True, 200)
        worker.rate_controller.acquire.return_value = 3
        worker.shutdown_check = MagicMock(side_effect=CrawlShutdownException)
        with patch("core.utils.time.sleep"), self.assertRaises(CrawlShutdownException):
            worker.process(URL, source="web")
        worker.indexer.index_url.assert_not_called()

    def test_a_shutdown_during_a_rescheduled_wait_stops_the_worker(self):
        worker = self._worker(True, 200)
        worker.rate_controller.recheck.return_value = 3
        worker.shutdown_check = MagicMock(side_effect=CrawlShutdownException)
        with patch("core.utils.time.sleep"), self.assertRaises(CrawlShutdownException):
            worker.process(URL, source="web")
        worker.indexer.index_url.assert_not_called()


class TestRateLimitRetryPass(unittest.TestCase):

    def _crawler(self, urls, still_limited=()):
        """`still_limited` holds, per pass, the URLs that get a 429 again."""
        crawler = WebsiteCrawler.__new__(WebsiteCrawler)
        crawler.cfg = OmegaConf.create({"website_crawler": {"rate_limit_retry_wait": 10}})
        crawler.tracker = MagicMock()
        crawler.shutdown_requested = False
        crawler.rate_limited_urls = list(urls)
        passes = iter(still_limited)
        worker = MagicMock()
        self.controllers = []  # one per pass
        self.limited = ()

        def process(url, source):
            if not self.controllers or self.controllers[-1] is not worker.rate_controller:
                self.assertEqual(worker.rate_controller.max_rate, 1)
                self.controllers.append(worker.rate_controller)
                self.limited = next(passes, ())
            return (PageCrawlWorker.RESULT_RATE_LIMITED if url in self.limited
                    else PageCrawlWorker.RESULT_INDEXED)

        worker.process.side_effect = process
        crawler._new_single_process_worker = MagicMock(return_value=worker)
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
        with patch("core.utils.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list), 10)
        crawler.tracker.track_indexed.assert_called_once_with(URL, url=URL)
        crawler.tracker.track_failed.assert_not_called()
        self.assertEqual(crawler.rate_limited_urls, [])

    def test_wait_grows_and_page_can_recover_on_the_last_pass(self):
        crawler = self._crawler([URL], still_limited=[(URL,)])
        with patch("core.utils.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list), 30)
        crawler.tracker.track_failed.assert_not_called()

    def test_page_still_limited_after_all_passes_is_failed_once(self):
        crawler = self._crawler([URL], still_limited=[(URL,), (URL,)])
        with patch("core.utils.time.sleep"):
            crawler._retry_rate_limited("web", {}, {})
        crawler.tracker.track_failed.assert_called_once_with(URL, url=URL)
        self.assertEqual(crawler.rate_limited_urls, [URL])

    def test_nothing_to_retry_does_not_wait(self):
        crawler = self._crawler([])
        with patch("core.utils.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        sleep.assert_not_called()
        crawler._new_single_process_worker.assert_not_called()

    def test_retry_waits_out_the_pause_the_site_asked_for(self):
        crawler = self._crawler([URL])
        crawler._rate_pause_left = 250
        with patch("core.utils.time.sleep") as sleep:
            crawler._retry_rate_limited("web", {}, {})
        self.assertEqual(sum(c.args[0] for c in sleep.call_args_list), 250)

    def test_a_shutdown_ends_the_retry_wait(self):
        crawler = self._crawler([URL])
        crawler.shutdown_requested = True
        with patch("core.utils.time.sleep") as sleep, self.assertRaises(CrawlShutdownException):
            crawler._retry_rate_limited("web", {}, {})
        sleep.assert_called_once()
        crawler._new_single_process_worker.assert_not_called()

    def test_retry_passes_share_one_worker_with_a_fresh_controller_each(self):
        crawler = self._crawler([URL], still_limited=[(URL,)])
        with patch("core.utils.time.sleep"):
            crawler._retry_rate_limited("web", {}, {})
        crawler._new_single_process_worker.assert_called_once_with(1, {}, {})
        crawler._new_single_process_worker.return_value.cleanup.assert_called_once_with()
        self.assertEqual(len(self.controllers), 2)

    def test_retry_worker_is_cleaned_up_when_the_first_pass_recovers_everything(self):
        crawler = self._crawler([URL])
        with patch("core.utils.time.sleep"):
            crawler._retry_rate_limited("web", {}, {})
        crawler._new_single_process_worker.return_value.cleanup.assert_called_once_with()

    def test_pages_still_limited_block_old_content_removal(self):
        crawler = self._crawler([URL], still_limited=[(URL,), (URL,)])
        crawler._crawl_interrupted = False
        with patch("core.utils.time.sleep"):
            crawler._retry_rate_limited("web", {}, {})
        self.assertTrue(crawler._crawl_interrupted)

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
