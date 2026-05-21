"""
SQLite-backed crawl tracking for pause/resume and crash recovery.

Provides document-level progress tracking, crawl state management,
and a Ray actor wrapper for parallel crawlers.
"""

import logging
import os
import sqlite3
import threading
import time
from typing import Set

logger = logging.getLogger(__name__)


class CrawlShutdownException(Exception):
    """Raised when a graceful shutdown is requested, signaling the process should exit cleanly."""


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT NOT NULL,
    crawler_type  TEXT NOT NULL,
    status        TEXT NOT NULL CHECK(status IN ('indexed', 'failed', 'skipped', 'auth_required')),
    url           TEXT,
    title         TEXT,
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (doc_id, crawler_type)
);
CREATE INDEX IF NOT EXISTS idx_documents_crawler_status ON documents(crawler_type, status);

CREATE TABLE IF NOT EXISTS crawl_state (
    crawler_type        TEXT PRIMARY KEY,
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK(status IN ('running', 'stopped', 'completed', 'failed')),
    started_at          TEXT,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    total_docs          INTEGER DEFAULT 0,
    indexed_docs        INTEGER DEFAULT 0,
    failed_docs         INTEGER DEFAULT 0,
    skipped_docs        INTEGER DEFAULT 0,
    auth_required_docs  INTEGER DEFAULT 0
);
"""


class CrawlTracker:
    """
    SQLite-backed tracker for document-level crawl progress.

    Thread-safe within a single process via threading.Lock.
    Use CrawlTrackerActor for Ray-parallel access.
    """

    def __init__(self, db_path: str, crawler_type: str):
        self.db_path = db_path
        self.crawler_type = crawler_type
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA_SQL)
        self._migrate_schema()

        # Upsert crawl_state row to 'running'
        self._conn.execute(
            """INSERT INTO crawl_state (crawler_type, status, started_at, updated_at)
               VALUES (?, 'running', datetime('now'), datetime('now'))
               ON CONFLICT(crawler_type) DO UPDATE SET
                   status='running', started_at=datetime('now'), updated_at=datetime('now')""",
            (crawler_type,),
        )
        self._conn.commit()
        logger.info("CrawlTracker initialized: db=%s crawler=%s", db_path, crawler_type)

    # ------------------------------------------------------------------
    # Schema migration (idempotent; safe to call on every open)
    # ------------------------------------------------------------------

    def _migrate_schema(self):
        """In-place upgrade for DBs created by older versions.

        Adds the auth_required_docs counter and widens the documents.status
        CHECK constraint to allow 'auth_required'. Existing rows are kept.
        """
        # 1) crawl_state.auth_required_docs column
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(crawl_state)").fetchall()}
        if "auth_required_docs" not in cols:
            self._conn.execute(
                "ALTER TABLE crawl_state ADD COLUMN auth_required_docs INTEGER DEFAULT 0"
            )

        # 2) documents.status CHECK constraint. SQLite has no ALTER for
        #    CHECK constraints — inspect the stored CREATE TABLE statement
        #    and recreate the table only if it predates 'auth_required'.
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
        ).fetchone()
        if row and row[0] and "auth_required" not in row[0]:
            self._conn.executescript("""
                CREATE TABLE documents_new (
                    doc_id        TEXT NOT NULL,
                    crawler_type  TEXT NOT NULL,
                    status        TEXT NOT NULL CHECK(status IN ('indexed', 'failed', 'skipped', 'auth_required')),
                    url           TEXT,
                    title         TEXT,
                    error         TEXT,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (doc_id, crawler_type)
                );
                INSERT INTO documents_new
                    (doc_id, crawler_type, status, url, title, error, created_at, updated_at)
                    SELECT doc_id, crawler_type, status, url, title, error, created_at, updated_at
                    FROM documents;
                DROP TABLE documents;
                ALTER TABLE documents_new RENAME TO documents;
                CREATE INDEX IF NOT EXISTS idx_documents_crawler_status ON documents(crawler_type, status);
            """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Document tracking
    # ------------------------------------------------------------------

    def is_indexed(self, doc_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM documents WHERE doc_id=? AND crawler_type=? AND status='indexed'",
                (doc_id, self.crawler_type),
            ).fetchone()
            return row is not None

    def get_indexed_ids(self) -> Set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id FROM documents WHERE crawler_type=? AND status='indexed'",
                (self.crawler_type,),
            ).fetchall()
            return {r[0] for r in rows}

    def get_failed_ids(self) -> Set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id FROM documents WHERE crawler_type=? AND status='failed'",
                (self.crawler_type,),
            ).fetchall()
            return {r[0] for r in rows}

    def _track_document(self, doc_id: str, status: str, url: str = "",
                        title: str = "", error: str = ""):
        """Insert or replace a document record and update counters."""
        with self._lock:
            # Check previous status to adjust counters correctly
            prev = self._conn.execute(
                "SELECT status FROM documents WHERE doc_id=? AND crawler_type=?",
                (doc_id, self.crawler_type),
            ).fetchone()

            self._conn.execute(
                """INSERT INTO documents
                   (doc_id, crawler_type, status, url, title, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                   ON CONFLICT(doc_id, crawler_type) DO UPDATE SET
                       status=excluded.status, url=excluded.url, title=excluded.title,
                       error=excluded.error, updated_at=datetime('now')""",
                (doc_id, self.crawler_type, status, url, title, error),
            )

            # Build counter updates: decrement old status, increment new
            counter_col = {"indexed": "indexed_docs", "failed": "failed_docs",
                           "skipped": "skipped_docs",
                           "auth_required": "auth_required_docs"}
            updates = []
            if prev:
                old_col = counter_col.get(prev[0])
                if old_col:
                    updates.append(f"{old_col} = MAX({old_col} - 1, 0)")
            else:
                updates.append("total_docs = total_docs + 1")

            new_col = counter_col[status]
            updates.append(f"{new_col} = {new_col} + 1")
            updates.append("updated_at = datetime('now')")

            self._conn.execute(
                f"UPDATE crawl_state SET {', '.join(updates)} WHERE crawler_type=?",
                (self.crawler_type,),
            )
            self._conn.commit()

    def track_indexed(self, doc_id: str, url: str = "", title: str = ""):
        self._track_document(doc_id, "indexed", url=url, title=title)

    def track_failed(self, doc_id: str, url: str = "", title: str = "",
                     error: str = ""):
        self._track_document(doc_id, "failed", url=url, title=title, error=error)

    def track_skipped(self, doc_id: str, url: str = "", title: str = "",
                      reason: str = ""):
        self._track_document(doc_id, "skipped", url=url, title=title, error=reason)

    def track_auth_required(self, doc_id: str, url: str = "", title: str = "",
                            reason: str = ""):
        """Record that a URL couldn't be indexed because it required auth.

        Distinct from track_failed: a sign-in redirect isn't a broken page,
        it's a missing credential. Surfacing this separately lets the user
        see at a glance how many URLs are gated and need auth configured.
        """
        self._track_document(doc_id, "auth_required", url=url, title=title, error=reason)

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    def check_shutdown(self):
        """Raise CrawlShutdownException if a graceful shutdown has been requested."""
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM crawl_state WHERE crawler_type=?",
                (self.crawler_type,),
            ).fetchone()
        if row and row[0] == "stopped":
            logger.info("Crawl stopped for %s — exiting cleanly.", self.crawler_type)
            raise CrawlShutdownException(f"Crawl stopped for {self.crawler_type}")

    def request_shutdown(self):
        """Set status to 'stopped' to signal a graceful shutdown."""
        with self._lock:
            self._conn.execute(
                "UPDATE crawl_state SET status='stopped', updated_at=datetime('now') WHERE crawler_type=?",
                (self.crawler_type,),
            )
            self._conn.commit()
        logger.info("Shutdown requested for %s", self.crawler_type)

    # ------------------------------------------------------------------
    # Final state
    # ------------------------------------------------------------------

    def mark_completed(self):
        with self._lock:
            self._conn.execute(
                "UPDATE crawl_state SET status='completed', updated_at=datetime('now') "
                "WHERE crawler_type=? AND status='running'",
                (self.crawler_type,),
            )
            self._conn.commit()

    def mark_failed(self):
        with self._lock:
            self._conn.execute(
                "UPDATE crawl_state SET status='failed', updated_at=datetime('now') WHERE crawler_type=?",
                (self.crawler_type,),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                """SELECT total_docs, indexed_docs, failed_docs, skipped_docs,
                          auth_required_docs, status
                   FROM crawl_state WHERE crawler_type=?""",
                (self.crawler_type,),
            ).fetchone()
        if not row:
            return {}
        return {
            "total_docs": row[0],
            "indexed_docs": row[1],
            "failed_docs": row[2],
            "skipped_docs": row[3],
            "auth_required_docs": row[4],
            "status": row[5],
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.commit()
                self._conn.close()
                self._conn = None


class CrawlTrackerActor:
    """
    Ray actor wrapper for CrawlTracker.

    One actor owns the SQLite connection; Ray workers call .remote() on it.
    Create with: ray.remote(num_cpus=0)(CrawlTrackerActor).remote(db_path, crawler_type)
    """

    def __init__(self, db_path: str, crawler_type: str):
        self._tracker = CrawlTracker(db_path, crawler_type)

    def is_indexed(self, doc_id: str) -> bool:
        return self._tracker.is_indexed(doc_id)

    def get_indexed_ids(self) -> Set[str]:
        return self._tracker.get_indexed_ids()

    def get_failed_ids(self) -> Set[str]:
        return self._tracker.get_failed_ids()

    def track_indexed(self, doc_id: str, url: str = "", title: str = ""):
        self._tracker.track_indexed(doc_id, url=url, title=title)

    def track_failed(self, doc_id: str, url: str = "", title: str = "",
                     error: str = ""):
        self._tracker.track_failed(doc_id, url=url, title=title, error=error)

    def track_skipped(self, doc_id: str, url: str = "", title: str = "",
                      reason: str = ""):
        self._tracker.track_skipped(doc_id, url=url, title=title, reason=reason)

    def track_auth_required(self, doc_id: str, url: str = "", title: str = "",
                            reason: str = ""):
        self._tracker.track_auth_required(doc_id, url=url, title=title, reason=reason)

    def get_stats(self) -> dict:
        return self._tracker.get_stats()

    def close(self):
        self._tracker.close()


