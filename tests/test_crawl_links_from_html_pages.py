"""The website and docs crawlers must read links from .html/.htm pages.

DOC_EXTENSIONS lists .html/.htm as attachment types for the Confluence Datacenter and Jira
crawlers. The web crawlers used the same list for "URLs that are files, not pages", so from
#304 on they indexed .html pages but never followed their links.
"""
import sys
from unittest.mock import MagicMock

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())

import pytest  # noqa: E402
from scrapy.exceptions import IgnoreRequest  # noqa: E402
from scrapy.http import HtmlResponse, Request  # noqa: E402

from core.spider import LinkSpider, recursive_crawl  # noqa: E402
from core.utils import DOC_EXTENSIONS, binary_extensions  # noqa: E402
from tests.test_spider_middleware import _make_mw  # noqa: E402

SITE = "https://docs.example.com"


def _indexer(seed, links):
    """Indexer whose fetch returns `links` for the seed page and none for the others."""
    indexer = MagicMock()
    indexer.fetch_page_contents.side_effect = lambda url: {
        "url": url, "links": links if url == seed else [], "text": "x", "html": "<p>x</p>", "title": "t",
    }
    return indexer


@pytest.mark.parametrize("page", ["index.html", "index.htm"])
def test_recursive_crawl_reads_links_from_html_pages(page):
    url = f"{SITE}/{page}"
    indexer = _indexer(url, ["/guide.html", "/manual.pdf"])
    visited = recursive_crawl(url, 2, [], [], indexer)
    assert visited == {url, f"{SITE}/guide.html", f"{SITE}/manual.pdf"}
    fetched = [c.args[0] for c in indexer.fetch_page_contents.call_args_list]
    assert fetched == [url, f"{SITE}/guide.html"]


def test_recursive_crawl_still_reads_no_links_from_documents():
    indexer = _indexer(f"{SITE}/manual.pdf", ["/other.html"])
    visited = recursive_crawl(f"{SITE}/manual.pdf", 2, [], [], indexer)
    assert visited == {f"{SITE}/manual.pdf"}
    indexer.fetch_page_contents.assert_not_called()


def _spider():
    return LinkSpider(start_urls=[f"{SITE}/"], positive_regexes=[".*"], negative_regexes=[], max_depth=2)


def test_scrapy_spider_follows_html_links_but_not_documents():
    spider = _spider()
    assert spider.should_follow(f"{SITE}/guide.html")
    assert spider.should_follow(f"{SITE}/guide.htm")
    assert not spider.should_follow(f"{SITE}/manual.pdf")


def test_scrapy_spider_reads_links_from_html_pages():
    url = f"{SITE}/index.html"
    response = HtmlResponse(url=url, request=Request(url, meta={"depth": 0}),
                            body=b'<html><body><a href="/guide.html">Guide</a></body></html>')
    requests = [i.url for i in _spider().parse(response) if isinstance(i, Request)]
    assert f"{SITE}/guide.html" in requests


def test_scrapy_redirect_to_html_page_is_followed():
    result = _make_mw()._redirect(Request(f"{SITE}/guide.html"), Request(f"{SITE}/guide"), 301)
    assert result.url == f"{SITE}/guide.html"


def test_scrapy_redirect_to_document_is_still_ignored():
    with pytest.raises(IgnoreRequest):
        _make_mw()._redirect(Request(f"{SITE}/manual.pdf"), Request(f"{SITE}/manual"), 302)


def test_docs_crawler_does_not_ignore_html_links():
    """docs_crawler adds binary_extensions to the link extensions it ignores."""
    assert ".html" not in binary_extensions and ".htm" not in binary_extensions
    assert ".pdf" in binary_extensions


def test_attachment_crawlers_still_parse_html_attachments():
    """Confluence Datacenter and Jira process attachments whose extension is in DOC_EXTENSIONS."""
    assert ".html" in DOC_EXTENSIONS and ".htm" in DOC_EXTENSIONS
