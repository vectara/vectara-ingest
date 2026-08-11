"""Regression tests for Indexer.delete_doc connection-error handling.

The remove_old_content cleanup in website_crawler loops over stale docs and
calls delete_doc for each. delete_doc used to let requests.ConnectionError
(e.g. RemoteDisconnected from a stale pooled keep-alive connection) propagate,
which aborted the entire ingest run after the crawl had already completed.
It must instead log the failure and return False so the caller can skip the
doc and continue.
"""
import sys
import unittest
from collections import OrderedDict
from http.client import RemoteDisconnected
from unittest.mock import MagicMock

import requests

sys.modules.setdefault('cairosvg', MagicMock())

from core.indexer import Indexer


def _make_indexer():
    """Construct an Indexer without running its real __init__ (which needs
    a populated config, an HTTP session, parsers, etc.). Only the attributes
    `delete_doc` reads are wired up."""
    ix = Indexer.__new__(Indexer)
    ix.api_url = "https://api.example.test"
    ix.corpus_key = "test_corpus"
    ix.api_key = "test_key"
    ix.x_source = "vectara-ingest-test"
    ix.session = MagicMock()
    ix._doc_exists_cache = OrderedDict()
    return ix


class TestDeleteDoc(unittest.TestCase):
    def test_connection_error_returns_false_instead_of_raising(self):
        """A stale keep-alive connection surfaces as ConnectionError wrapping
        RemoteDisconnected. delete_doc must swallow it and return False so
        one bad connection cannot abort the whole remove_old_content loop."""
        ix = _make_indexer()
        ix.session.delete.side_effect = requests.exceptions.ConnectionError(
            "Connection aborted.",
            RemoteDisconnected("Remote end closed connection without response"))

        self.assertFalse(ix.delete_doc("doc-1"))

    def test_successful_delete_returns_true_and_clears_cache(self):
        ix = _make_indexer()
        ix._doc_exists_cache["doc-1"] = True
        response = MagicMock()
        response.status_code = 204
        ix.session.delete.return_value = response

        self.assertTrue(ix.delete_doc("doc-1"))
        self.assertNotIn("doc-1", ix._doc_exists_cache)

    def test_non_204_response_returns_false(self):
        ix = _make_indexer()
        response = MagicMock()
        response.status_code = 404
        response.reason = "Not Found"
        response.text = "document not found"
        ix.session.delete.return_value = response

        self.assertFalse(ix.delete_doc("doc-1"))


if __name__ == "__main__":
    unittest.main()
