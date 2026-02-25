#!/usr/bin/env python3
"""
CLI for controlling a running crawl job (pause / resume / status).

Usage:
    python crawl_control.py pause  --db-path /path/to/crawl_tracking.db --crawler-type website
    python crawl_control.py resume --db-path /path/to/crawl_tracking.db --crawler-type website
    python crawl_control.py status --db-path /path/to/crawl_tracking.db --crawler-type website

In Docker:
    docker exec <container> python3 crawl_control.py pause \
        --db-path /home/vectara/vectara_ingest_output/crawl_tracking.db --crawler-type website
"""

import argparse
import sqlite3
import sys

from core.crawl_tracker import signal_crawl


def get_status(db_path: str, crawler_type: str) -> None:
    """Print current crawl state and document counters."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    row = conn.execute(
        """SELECT status, total_docs, indexed_docs, failed_docs, skipped_docs,
                  started_at, updated_at
           FROM crawl_state WHERE crawler_type=?""",
        (crawler_type,),
    ).fetchone()
    conn.close()

    if not row:
        print(f"No crawl state found for crawler_type='{crawler_type}'")
        sys.exit(1)

    print(f"Crawler:  {crawler_type}")
    print(f"Status:   {row[0]}")
    print(f"Total:    {row[1]}")
    print(f"Indexed:  {row[2]}")
    print(f"Failed:   {row[3]}")
    print(f"Skipped:  {row[4]}")
    print(f"Started:  {row[5]}")
    print(f"Updated:  {row[6]}")


def main():
    parser = argparse.ArgumentParser(description="Control a running crawl job")
    parser.add_argument("action", choices=["pause", "resume", "status"],
                        help="Action to perform")
    parser.add_argument("--db-path", required=True,
                        help="Path to crawl_tracking.db")
    parser.add_argument("--crawler-type", required=True,
                        help="Crawler type (e.g. website, jira, github)")
    args = parser.parse_args()

    if args.action == "status":
        get_status(args.db_path, args.crawler_type)
    else:
        signal_crawl(args.db_path, args.crawler_type, args.action)
        print(f"Sent '{args.action}' to {args.crawler_type}")


if __name__ == "__main__":
    main()
