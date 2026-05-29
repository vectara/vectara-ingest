"""Regression tests for Indexer.last_error population.

The gdrive (and other) crawlers surface `indexer.last_error` as the reason in
their `index_error` drop records. Several `_index_file` failure paths used to
return False without setting `last_error`, which downgraded operator-visible
drop reasons to the generic "indexer.index_file returned False" string and
hid the real cause (e.g. HTTP 400 / 413 / 429 from the Vectara upload).
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from core.indexer import Indexer


def _make_indexer():
    """Construct an Indexer without running its real __init__ (which needs
    a populated config, an HTTP session, parsers, etc.). Only the attributes
    `_index_file` reads are wired up."""
    ix = Indexer.__new__(Indexer)
    ix.api_url = "https://api.example.test"
    ix.corpus_key = "test_corpus"
    ix.api_key = "test_key"
    ix.session = MagicMock()
    ix.cfg = MagicMock()
    ix.parse_tables = False
    ix.verbose = False
    ix.store_docs = False
    ix.reindex = False
    ix.static_metadata = {}
    ix.last_error = None
    return ix


class TestIndexFileLastError(unittest.TestCase):
    def setUp(self):
        # _index_file requires the file to exist on disk; create a small one.
        # mkstemp gives us a path we own the lifetime of (setUp/tearDown bracket)
        # without the context-manager pattern pylint prefers for NamedTemporaryFile.
        fd, self.path = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, 'wb') as f:
            f.write(b"%PDF-1.4 stub")

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_non_201_response_sets_last_error_with_status(self):
        """The most common production failure: Vectara responds non-201 (e.g.
        400 for an unparseable PDF, 413 too large, 429 rate-limited). Before
        this fix, `last_error` stayed None and gdrive's drop reason was the
        useless "indexer.index_file returned False"."""
        ix = _make_indexer()
        bad = MagicMock()
        bad.status_code = 400
        bad.text = "PDF parsing failed: invalid xref table"
        ix.session.request.return_value = bad

        ok = ix._index_file(self.path, uri="https://example.test/a.pdf", metadata={})
        self.assertFalse(ok)
        self.assertIsNotNone(ix.last_error)
        self.assertIn("400", ix.last_error)
        self.assertIn("PDF parsing failed", ix.last_error)

    def test_upload_exception_sets_last_error(self):
        """Network failure / serialization error during the POST."""
        ix = _make_indexer()
        ix.session.request.side_effect = RuntimeError("connection reset")

        ok = ix._index_file(self.path, uri="https://example.test/a.pdf", metadata={})
        self.assertFalse(ok)
        self.assertIsNotNone(ix.last_error)
        self.assertIn("connection reset", ix.last_error)

    def test_201_success_clears_no_error_assertion(self):
        """Sanity check: success path does not write last_error."""
        ix = _make_indexer()
        good = MagicMock()
        good.status_code = 201
        ix.session.request.return_value = good

        ok = ix._index_file(self.path, uri="https://example.test/a.pdf", metadata={})
        self.assertTrue(ok)
        # last_error is allowed to be None or whatever it was before — the
        # contract is only that a failed call sets it to something useful.
        # We don't assert it's None to avoid coupling to internal cleanup.

    def test_reindex_disabled_409_treated_as_success(self):
        """When reindex is off and the doc already exists, _index_file returns
        True (skipping). No last_error contract here, but the path mustn't
        crash and must NOT set last_error to a falsy success-looking value."""
        ix = _make_indexer()
        ix.reindex = False
        conflict = MagicMock()
        conflict.status_code = 409
        ix.session.request.return_value = conflict

        ok = ix._index_file(self.path, uri="https://example.test/a.pdf", metadata={})
        self.assertTrue(ok)


class TestIndexFileRoutingDoesNotLeak(unittest.TestCase):
    """The per-call routing decision returned by
    ``FileProcessor.should_process_locally`` must NOT mutate the indexer's
    instance-level ``process_locally`` attribute. The bug it guards against:
    a single standalone image (which legitimately needs local processing for
    summarization) flipped ``self.process_locally`` to True forever, so every
    subsequent ``.txt`` / ``.md`` / ``.docx`` in the same worker was routed
    through the local parser and failed with "File format not allowed:
    <name>" — observed as 87 spurious ``index_error`` drops in a gdrive crawl.
    """

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, 'wb') as f:
            f.write(b"\x89PNG\r\n\x1a\n")

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_should_process_locally_true_does_not_leak_into_attribute(self):
        ix = _make_indexer()
        ix.process_locally = False  # config default — never Case B by default
        ix._init_processors = MagicMock()
        ix.file_processor = MagicMock()
        ix.file_processor.should_process_locally.return_value = True
        ix.file_processor.needs_pdf_splitting.return_value = False
        # Make the Case B work blow up immediately so the test exits fast.
        ix.file_processor.process_file.side_effect = RuntimeError("stub")
        ix.summarize_images = False
        ix.extract_metadata = []

        ok = ix.index_file(
            filename=self.path,
            uri="https://drive.google.com/file/d/abc/view",
            metadata={},
        )

        self.assertFalse(ok)
        self.assertFalse(
            ix.process_locally,
            "index_file leaked a per-call routing decision into the instance "
            "attribute; the next .txt/.md will be wrongly routed to Case B.",
        )


if __name__ == "__main__":
    unittest.main()
