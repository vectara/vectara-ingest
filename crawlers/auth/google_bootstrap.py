"""One-time interactive bootstrap to capture a Google session for headless crawling.

Run OUTSIDE the Docker container (Playwright needs a display for headed mode):

    python -m crawlers.auth.google_bootstrap --output /path/to/google_storage_state.json

The script opens a real Chromium window, waits for you to sign in to Google
(including 2FA / SSO / account-chooser steps), then writes the resulting cookies
and localStorage to `--output` as a JSON file. Mount that file into the
container at the path you set in `website_crawler.google_auth.storage_state_path`.

Re-run whenever the stored session expires (typical for Workspace SSO: a few
weeks). The crawler surfaces a clear error message when this happens.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m crawlers.auth.google_bootstrap",
        description="Capture a Google sign-in session for the website crawler.",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Path to write the Playwright storage_state JSON file.",
    )
    p.add_argument(
        "--start-url",
        default="https://sites.google.com",
        help="URL to open for sign-in (default: %(default)s).",
    )
    p.add_argument(
        "--success-url-contains",
        default="sites.google.com",
        help=(
            "When the browser URL contains this substring AND is NOT on "
            "accounts.google.com, sign-in is considered complete and the "
            "session is saved (default: %(default)s)."
        ),
    )
    p.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Max seconds to wait for sign-in to complete (default: %(default)s).",
    )
    return p.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logging.error(
            "Playwright is not installed. Install it locally with "
            "`pip install playwright && playwright install chromium`."
        )
        return 2

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    logging.info("Opening Chromium for Google sign-in. Complete the login flow in the browser window.")
    logging.info(f"Target start URL: {args.start_url}")
    logging.info(f"Will save storage state to: {output_path}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(args.start_url, wait_until="domcontentloaded")

        deadline_ms = args.timeout_seconds * 1000
        try:
            page.wait_for_function(
                "(needle) => location.href.includes(needle) && !location.href.includes('accounts.google.com')",
                arg=args.success_url_contains,
                timeout=deadline_ms,
            )
        except Exception as e:
            logging.error(f"Sign-in did not complete within {args.timeout_seconds}s: {e}")
            browser.close()
            return 1

        context.storage_state(path=output_path)
        logging.info(f"Saved Google session to {output_path}")
        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(run())
