"""Regression: html_processing (ids_to_remove / classes_to_remove / tags_to_remove)
must apply on the static pre-fetch path of WebContentExtractor.fetch_page_contents.

The browser path removes these elements before capturing `html` and `text`, but the
static `requests.get` path (taken for any server-rendered page with >500 chars of
text) returned the raw response untouched. With `remove_boilerplate: true` the
indexer re-extracts text from `res['html']`, so the configured removals were
silently ignored for most documentation sites.
"""

import importlib.machinery
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Heavy native deps that the import chain touches.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())
_pw_mock = MagicMock()
_pw_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf  # noqa: E402

from core.indexer import Indexer  # noqa: E402

URL = "https://docs.example.com/guide/page.html"
FILLER = "Article body sentence about configuring the cluster. " * 20

PAGE = f"""<html><head><title>Guide</title></head><body>
<div id="tg-sb-sidebar">SIDEBAR_BY_ID</div>
<div class="header-container top">HEADER_BY_CLASS</div>
<div class="footer">FOOTER_BY_CLASS</div>
<aside>ASIDE_BY_TAG</aside>
<main><p>KEEP_ME {FILLER}</p></main>
</body></html>"""

HTML_PROCESSING = {
    "ids_to_remove": ["tg-sb-sidebar"],
    "classes_to_remove": ["header-container", "footer"],
    "tags_to_remove": ["aside"],
}
REMOVED_MARKERS = [
    "SIDEBAR_BY_ID",
    "HEADER_BY_CLASS",
    "FOOTER_BY_CLASS",
    "ASIDE_BY_TAG",
]


def _make_extractor():
    """WebContentExtractor with a stub browser so __init__ doesn't launch Chromium."""
    from core.web_content_extractor import WebContentExtractor

    cfg = SimpleNamespace(
        vectara=SimpleNamespace(get=lambda key, default=None: default)
    )
    extractor = WebContentExtractor(cfg=cfg, browser=MagicMock(name="browser"))
    extractor.p = MagicMock(name="playwright_runner")
    return extractor


def _static_response(html: str):
    resp = MagicMock()
    resp.headers = {"content-type": "text/html; charset=utf-8"}
    resp.url = URL
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


class TestStaticPrefetchAppliesHtmlProcessing(unittest.TestCase):

    def _fetch(self, html_processing):
        extractor = _make_extractor()
        with patch(
            "core.web_content_extractor.requests.get",
            return_value=_static_response(PAGE),
        ):
            result = extractor.fetch_page_contents(URL, html_processing=html_processing)
        # Static path must have been taken, otherwise this test proves nothing.
        extractor.browser.new_context.assert_not_called()
        return result

    def test_removed_elements_absent_from_html_and_text(self):
        result = self._fetch(HTML_PROCESSING)
        for marker in REMOVED_MARKERS:
            self.assertNotIn(marker, result["html"], f"{marker} still in html")
            self.assertNotIn(marker, result["text"], f"{marker} still in text")

    def test_unlisted_content_is_kept(self):
        result = self._fetch(HTML_PROCESSING)
        self.assertIn("KEEP_ME", result["html"])
        self.assertIn("KEEP_ME", result["text"])
        self.assertEqual(result["title"], "Guide")

    def test_no_html_processing_leaves_page_untouched(self):
        result = self._fetch({})
        for marker in REMOVED_MARKERS:
            self.assertIn(marker, result["html"])


class TestRemoveBoilerplateRespectsHtmlProcessing(unittest.TestCase):
    """End to end through Indexer.index_url: with remove_boilerplate on, the HTML
    handed to the boilerplate extractor must already have the configured removals."""

    def _make_indexer(self, extractor):
        ix = Indexer.__new__(Indexer)
        ix.cfg = OmegaConf.create({"vectara": {"verbose": False}, "doc_processing": {}})
        ix.incremental = False
        ix.add_image_bytes = False
        ix.summarize_images = False
        ix.process_locally = False
        ix.remove_boilerplate = True
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
        ix.fetch_page_contents = lambda **kw: extractor.fetch_page_contents(
            kw["url"], html_processing=kw["html_processing"]
        )
        ix.index_segments = MagicMock(return_value=True)
        return ix

    def test_boilerplate_input_excludes_removed_elements(self):
        extractor = _make_extractor()
        ix = self._make_indexer(extractor)
        with patch(
            "core.web_content_extractor.requests.get",
            return_value=_static_response(PAGE),
        ), patch(
            "core.indexer.get_article_content", return_value=("article text", "Guide")
        ) as gac:
            ix.index_url(URL, metadata={"url": URL}, html_processing=HTML_PROCESSING)

        gac.assert_called_once()
        boilerplate_input_html = gac.call_args.args[0]
        self.assertIn("KEEP_ME", boilerplate_input_html)
        for marker in REMOVED_MARKERS:
            self.assertNotIn(
                marker, boilerplate_input_html, f"{marker} reached remove_boilerplate"
            )
        ix.index_segments.assert_called_once()


if __name__ == "__main__":
    unittest.main()
