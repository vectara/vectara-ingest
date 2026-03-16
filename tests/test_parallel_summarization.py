"""
Tests for parallel image and table summarization in document parsers.

The key behavior being tested:
1. When summarization_workers > 1, image and table summarizations run concurrently
   via ThreadPoolExecutor, reducing wall-clock time for docs with many images/tables.
2. When summarization_workers <= 1, behavior is sequential (same as before).
3. Results are identical regardless of parallelism (order preserved, same content).
4. Failures in individual summarizations don't crash the batch.
"""
import unittest
import sys
import time
from unittest.mock import MagicMock, patch, call
from concurrent.futures import ThreadPoolExecutor

# Mock cairosvg before it's imported by other modules
sys.modules['cairosvg'] = MagicMock()


class TestParallelImageSummarization(unittest.TestCase):
    """Test _parallel_summarize_images on the DocumentParser base class."""

    def _make_parser(self, workers=4):
        """Create a DocumentParser with mocked dependencies."""
        from core.doc_parser import DocumentParser

        cfg = MagicMock()
        cfg.doc_processing = MagicMock()
        cfg.doc_processing.get.side_effect = lambda key, default=None: {
            'summarization_workers': workers,
        }.get(key, default)

        model_config = {
            'text': {'provider': 'openai', 'model_name': 'gpt-4.1-mini'},
            'vision': {'provider': 'openai', 'model_name': 'gpt-4.1-mini'},
        }

        with patch.object(DocumentParser, '__init__', lambda self_, *a, **kw: None):
            parser = DocumentParser.__new__(DocumentParser)
            parser.cfg = cfg
            parser.model_config = model_config
            parser.verbose = False
            parser.summarize_images = True
            parser.parse_tables = True
            parser.summarization_workers = workers

            # Mock summarizers
            parser.image_summarizer = MagicMock()
            parser.table_summarizer = MagicMock()

        return parser

    def test_parallel_images_returns_correct_summaries(self):
        """Summaries are returned in the same order as inputs, with correct content."""
        parser = self._make_parser(workers=4)

        # Each call returns a distinct summary
        parser.image_summarizer.summarize_image.side_effect = [
            "Summary for image 0",
            "Summary for image 1",
            "Summary for image 2",
        ]

        image_tasks = [
            {'image_path': '', 'source_url': 'http://example.com',
             'previous_text': 'before0', 'next_text': 'after0', 'image_bytes': b'img0'},
            {'image_path': '', 'source_url': 'http://example.com',
             'previous_text': 'before1', 'next_text': 'after1', 'image_bytes': b'img1'},
            {'image_path': '', 'source_url': 'http://example.com',
             'previous_text': 'before2', 'next_text': 'after2', 'image_bytes': b'img2'},
        ]

        results = parser._parallel_summarize_images(image_tasks)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], "Summary for image 0")
        self.assertEqual(results[1], "Summary for image 1")
        self.assertEqual(results[2], "Summary for image 2")

    def test_parallel_images_preserves_order(self):
        """Even with varying response times, result order matches input order."""
        parser = self._make_parser(workers=4)

        def slow_summarize(path, url, prev, nxt, image_bytes=None):
            # Simulate varying latencies
            idx = [b'img0', b'img1', b'img2'].index(image_bytes)
            delays = [0.05, 0.01, 0.03]  # img1 finishes first
            time.sleep(delays[idx])
            return f"Summary {idx}"

        parser.image_summarizer.summarize_image.side_effect = slow_summarize

        image_tasks = [
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img0'},
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img1'},
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img2'},
        ]

        results = parser._parallel_summarize_images(image_tasks)

        self.assertEqual(results, ["Summary 0", "Summary 1", "Summary 2"])

    def test_parallel_images_handles_failures(self):
        """A failing summarization returns None, others are unaffected."""
        parser = self._make_parser(workers=4)

        parser.image_summarizer.summarize_image.side_effect = [
            "Good summary 0",
            Exception("Vision API error"),
            "Good summary 2",
        ]

        image_tasks = [
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img0'},
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img1'},
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'img2'},
        ]

        results = parser._parallel_summarize_images(image_tasks)

        self.assertEqual(results[0], "Good summary 0")
        self.assertIsNone(results[1])
        self.assertEqual(results[2], "Good summary 2")

    def test_sequential_when_workers_is_1(self):
        """With workers=1, runs sequentially (no thread pool overhead)."""
        parser = self._make_parser(workers=1)

        call_order = []

        def track_call(path, url, prev, nxt, image_bytes=None):
            call_order.append(image_bytes)
            return f"summary for {image_bytes}"

        parser.image_summarizer.summarize_image.side_effect = track_call

        image_tasks = [
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'a'},
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': b'b'},
        ]

        results = parser._parallel_summarize_images(image_tasks)

        self.assertEqual(len(results), 2)
        self.assertEqual(call_order, [b'a', b'b'])

    def test_empty_task_list(self):
        """Empty input returns empty output."""
        parser = self._make_parser(workers=4)
        results = parser._parallel_summarize_images([])
        self.assertEqual(results, [])


class TestParallelTableSummarization(unittest.TestCase):
    """Test _parallel_summarize_tables on the DocumentParser base class."""

    def _make_parser(self, workers=4):
        from core.doc_parser import DocumentParser

        cfg = MagicMock()
        cfg.doc_processing = MagicMock()
        cfg.doc_processing.get.side_effect = lambda key, default=None: {
            'summarization_workers': workers,
        }.get(key, default)

        with patch.object(DocumentParser, '__init__', lambda self_, *a, **kw: None):
            parser = DocumentParser.__new__(DocumentParser)
            parser.cfg = cfg
            parser.verbose = False
            parser.parse_tables = True
            parser.summarization_workers = workers
            parser.table_summarizer = MagicMock()

        return parser

    def test_parallel_tables_returns_correct_summaries(self):
        """Table summaries are returned in input order."""
        parser = self._make_parser(workers=4)

        parser.table_summarizer.summarize_table_text.side_effect = [
            "Table summary 0",
            "Table summary 1",
        ]

        table_texts = ["| col1 | col2 |\n|---|---|\n| a | b |",
                       "| x | y |\n|---|---|\n| 1 | 2 |"]

        results = parser._parallel_summarize_tables(table_texts)

        self.assertEqual(results, ["Table summary 0", "Table summary 1"])

    def test_parallel_tables_handles_failures(self):
        """A failing table summarization returns empty string."""
        parser = self._make_parser(workers=4)

        parser.table_summarizer.summarize_table_text.side_effect = [
            "Good table summary",
            Exception("LLM timeout"),
        ]

        table_texts = ["table1_md", "table2_md"]
        results = parser._parallel_summarize_tables(table_texts)

        self.assertEqual(results[0], "Good table summary")
        self.assertEqual(results[1], "")

    def test_empty_table_list(self):
        parser = self._make_parser(workers=4)
        results = parser._parallel_summarize_tables([])
        self.assertEqual(results, [])


class TestParallelActualConcurrency(unittest.TestCase):
    """Verify that parallel mode actually runs concurrently (wall time check)."""

    def _make_parser(self, workers=4):
        from core.doc_parser import DocumentParser

        cfg = MagicMock()
        cfg.doc_processing = MagicMock()
        cfg.doc_processing.get.side_effect = lambda key, default=None: {
            'summarization_workers': workers,
        }.get(key, default)

        with patch.object(DocumentParser, '__init__', lambda self_, *a, **kw: None):
            parser = DocumentParser.__new__(DocumentParser)
            parser.cfg = cfg
            parser.verbose = False
            parser.summarize_images = True
            parser.summarization_workers = workers
            parser.image_summarizer = MagicMock()

        return parser

    def test_parallel_is_faster_than_sequential(self):
        """With 4 workers and 4 tasks each taking 0.1s, parallel should be ~0.1s not ~0.4s."""
        parser = self._make_parser(workers=4)

        def slow_summarize(path, url, prev, nxt, image_bytes=None):
            time.sleep(0.1)
            return "summary"

        parser.image_summarizer.summarize_image.side_effect = slow_summarize

        tasks = [
            {'image_path': '', 'source_url': 'url', 'previous_text': None,
             'next_text': None, 'image_bytes': bytes([i])}
            for i in range(4)
        ]

        start = time.time()
        results = parser._parallel_summarize_images(tasks)
        elapsed = time.time() - start

        self.assertEqual(len(results), 4)
        # Sequential would take ~0.4s. Parallel with 4 workers should be ~0.1s.
        # Use 0.25s as threshold to account for overhead.
        self.assertLess(elapsed, 0.25,
                        f"Parallel execution took {elapsed:.2f}s, expected < 0.25s")


if __name__ == '__main__':
    unittest.main()
