import unittest
import tempfile
import os
import sqlite3
import time
import signal

from core.crawl_tracker import CrawlTracker, CrawlShutdownException


class TestCrawlTrackerInit(unittest.TestCase):
    """Test database initialization and table creation."""

    def test_init_creates_db_and_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            tracker = CrawlTracker(db_path, "website")
            tracker.close()

            self.assertTrue(os.path.exists(db_path))

            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()

            self.assertIn("documents", tables)
            self.assertIn("crawl_state", tables)

    def test_init_sets_running_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            tracker = CrawlTracker(db_path, "website")
            tracker.close()

            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT status FROM crawl_state WHERE crawler_type='website'"
            ).fetchone()
            conn.close()

            self.assertEqual(row[0], "running")

    def test_init_wal_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            tracker = CrawlTracker(db_path, "website")
            tracker.close()

            conn = sqlite3.connect(db_path)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            conn.close()

            self.assertEqual(mode, "wal")


class TestCrawlTrackerTracking(unittest.TestCase):
    """Test document tracking operations."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir.name
        self.db_path = os.path.join(self.tmpdir, "crawl_tracking.db")
        self.tracker = CrawlTracker(self.db_path, "website")

    def tearDown(self):
        self.tracker.close()
        self._tmpdir.cleanup()

    def test_track_indexed_and_is_indexed(self):
        self.assertFalse(self.tracker.is_indexed("doc1"))
        self.tracker.track_indexed("doc1", url="http://example.com", title="Example")
        self.assertTrue(self.tracker.is_indexed("doc1"))

    def test_track_failed_then_retry_succeeds(self):
        self.tracker.track_failed("doc1", url="http://example.com", error="timeout")
        self.assertIn("doc1", self.tracker.get_failed_ids())
        self.assertFalse(self.tracker.is_indexed("doc1"))

        # Retry succeeds — INSERT OR REPLACE overwrites the failed status
        self.tracker.track_indexed("doc1", url="http://example.com", title="Example")
        self.assertTrue(self.tracker.is_indexed("doc1"))
        self.assertNotIn("doc1", self.tracker.get_failed_ids())

    def test_get_indexed_ids(self):
        self.tracker.track_indexed("doc1")
        self.tracker.track_indexed("doc2")
        self.tracker.track_failed("doc3")
        indexed = self.tracker.get_indexed_ids()
        self.assertEqual(indexed, {"doc1", "doc2"})

    def test_get_failed_ids(self):
        self.tracker.track_failed("doc1", error="err")
        self.tracker.track_failed("doc2", error="err")
        self.tracker.track_indexed("doc3")
        failed = self.tracker.get_failed_ids()
        self.assertEqual(failed, {"doc1", "doc2"})

    def test_track_skipped(self):
        self.tracker.track_skipped("doc1", reason="duplicate")
        self.assertFalse(self.tracker.is_indexed("doc1"))
        # Skipped docs should not appear in indexed or failed sets
        self.assertNotIn("doc1", self.tracker.get_indexed_ids())
        self.assertNotIn("doc1", self.tracker.get_failed_ids())

    def test_idempotent_track(self):
        self.tracker.track_indexed("doc1", url="http://a.com", title="A")
        self.tracker.track_indexed("doc1", url="http://a.com", title="A updated")

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE doc_id='doc1' AND crawler_type='website'"
        ).fetchone()
        conn.close()
        self.assertEqual(rows[0], 1)

    def test_stats_counters(self):
        self.tracker.track_indexed("d1")
        self.tracker.track_indexed("d2")
        self.tracker.track_failed("d3", error="err")
        self.tracker.track_skipped("d4", reason="dup")

        stats = self.tracker.get_stats()
        self.assertEqual(stats["indexed_docs"], 2)
        self.assertEqual(stats["failed_docs"], 1)
        self.assertEqual(stats["skipped_docs"], 1)
        self.assertEqual(stats["total_docs"], 4)


class TestCrawlTrackerShutdown(unittest.TestCase):
    """Test graceful shutdown mechanics."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir.name
        self.db_path = os.path.join(self.tmpdir, "crawl_tracking.db")
        self.tracker = CrawlTracker(self.db_path, "website")

    def tearDown(self):
        self.tracker.close()
        self._tmpdir.cleanup()

    def test_check_shutdown_raises_when_stopped(self):
        """check_shutdown should raise CrawlShutdownException when shutdown requested."""
        self.tracker.request_shutdown()
        with self.assertRaises(CrawlShutdownException):
            self.tracker.check_shutdown()

    def test_shutdown_exception_preserves_db_status(self):
        """After CrawlShutdownException, DB status should still be 'stopped'."""
        self.tracker.request_shutdown()
        with self.assertRaises(CrawlShutdownException):
            self.tracker.check_shutdown()
        stats = self.tracker.get_stats()
        self.assertEqual(stats["status"], "stopped")

    def test_check_shutdown_noop_when_running(self):
        """check_shutdown should return immediately when status is running."""
        start = time.monotonic()
        self.tracker.check_shutdown()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)


class TestCrawlTrackerState(unittest.TestCase):
    """Test crawl state transitions."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir.name
        self.db_path = os.path.join(self.tmpdir, "crawl_tracking.db")
        self.tracker = CrawlTracker(self.db_path, "website")

    def tearDown(self):
        self.tracker.close()
        self._tmpdir.cleanup()

    def test_mark_completed(self):
        self.tracker.mark_completed()
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM crawl_state WHERE crawler_type='website'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "completed")

    def test_mark_failed(self):
        self.tracker.mark_failed()
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM crawl_state WHERE crawler_type='website'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "failed")


class TestCrawlTrackerConcurrency(unittest.TestCase):
    """Test concurrent access scenarios."""

    def test_concurrent_access_two_instances(self):
        """Two CrawlTracker instances on same DB should not deadlock (WAL mode)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            t1 = CrawlTracker(db_path, "website")
            t2 = CrawlTracker(db_path, "website")

            # Interleaved writes should not raise "database is locked"
            t1.track_indexed("doc1")
            t2.track_indexed("doc2")
            t1.track_failed("doc3", error="err")
            t2.track_indexed("doc4")

            indexed = t1.get_indexed_ids()
            self.assertEqual(indexed, {"doc1", "doc2", "doc4"})

            t1.close()
            t2.close()

    def test_crash_recovery(self):
        """Data persists after close without mark_completed, simulating crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")

            tracker = CrawlTracker(db_path, "website")
            tracker.track_indexed("doc1", url="http://a.com")
            tracker.track_indexed("doc2", url="http://b.com")
            tracker.track_failed("doc3", error="timeout")
            # Close without mark_completed — simulates crash
            tracker.close()

            # Reopen — data should be intact
            tracker2 = CrawlTracker(db_path, "website")
            self.assertEqual(tracker2.get_indexed_ids(), {"doc1", "doc2"})
            self.assertEqual(tracker2.get_failed_ids(), {"doc3"})
            tracker2.close()

    def test_multiple_crawler_types(self):
        """Two tracker instances with different crawler_types see only their own docs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            web = CrawlTracker(db_path, "website")
            jira = CrawlTracker(db_path, "jira")

            web.track_indexed("url1")
            web.track_indexed("url2")
            jira.track_indexed("JIRA-1")
            jira.track_indexed("JIRA-2")
            jira.track_indexed("JIRA-3")

            self.assertEqual(web.get_indexed_ids(), {"url1", "url2"})
            self.assertEqual(jira.get_indexed_ids(), {"JIRA-1", "JIRA-2", "JIRA-3"})

            web.close()
            jira.close()


class TestSignalHandler(unittest.TestCase):
    """Test that SIGTERM triggers graceful shutdown."""

    def test_signal_handler_requests_shutdown(self):
        """Verify the signal handler pattern sets stopped state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            tracker = CrawlTracker(db_path, "website")

            # Simulate what the signal handler in ingest.py does
            shutdown_requested = [False]

            def handler(signum, frame):
                if not shutdown_requested[0]:
                    shutdown_requested[0] = True
                    tracker.request_shutdown()
                else:
                    raise KeyboardInterrupt

            old_handler = signal.signal(signal.SIGTERM, handler)
            try:
                os.kill(os.getpid(), signal.SIGTERM)
                self.assertTrue(shutdown_requested[0])
                stats = tracker.get_stats()
                self.assertEqual(stats["status"], "stopped")
            finally:
                signal.signal(signal.SIGTERM, old_handler)
                tracker.close()


class TestCrawlerShutdownWithoutTracker(unittest.TestCase):
    """Test that graceful shutdown works even when tracking is disabled."""

    def test_check_shutdown_raises_without_tracker(self):
        """check_shutdown should raise CrawlShutdownException via shutdown_requested flag even without tracker."""
        from core.crawl_tracker import CrawlShutdownException

        class MockCrawler:
            """Minimal mock that replicates the Crawler base class shutdown logic."""
            def __init__(self):
                self.tracker = None
                self.shutdown_requested = False

            def check_shutdown(self):
                if self.shutdown_requested:
                    raise CrawlShutdownException("Graceful shutdown requested")
                if self.tracker:
                    self.tracker.check_shutdown()

        crawler = MockCrawler()
        # Should be no-op when not requested
        crawler.check_shutdown()

        # Should raise when shutdown_requested is set (simulating SIGTERM without tracker)
        crawler.shutdown_requested = True
        with self.assertRaises(CrawlShutdownException):
            crawler.check_shutdown()

    def test_check_shutdown_with_tracker_still_works(self):
        """check_shutdown should also work via tracker when both are present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "crawl_tracking.db")
            tracker = CrawlTracker(db_path, "website")

            from core.crawl_tracker import CrawlShutdownException

            class MockCrawler:
                def __init__(self):
                    self.tracker = None
                    self.shutdown_requested = False

                def check_shutdown(self):
                    if self.shutdown_requested:
                        raise CrawlShutdownException("Graceful shutdown requested")
                    if self.tracker:
                        self.tracker.check_shutdown()

            crawler = MockCrawler()
            crawler.tracker = tracker

            # No-op when running
            crawler.check_shutdown()

            # Trigger via tracker's DB status
            tracker.request_shutdown()
            with self.assertRaises(CrawlShutdownException):
                crawler.check_shutdown()

            tracker.close()


if __name__ == "__main__":
    unittest.main()
