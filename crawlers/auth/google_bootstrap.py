"""One-time interactive bootstrap to capture a Google session for headless crawling.

Run OUTSIDE the Docker container (Playwright needs a display for headed mode):

    python -m crawlers.auth.google_bootstrap --output /path/to/google_storage_state.json

By default the script opens a real Google Chrome window (installed Chrome, not
Playwright's bundled Chromium — Chromium is reliably flagged by Cloudflare /
Google bot detection). Pass `--browser firefox` to use Playwright's bundled
Firefox instead. Note: there is no installed-Firefox equivalent of the
chromium `channel="chrome"` escape hatch (Playwright always uses its own
patched Firefox build), so Firefox is more bot-detectable than installed
Chrome — we set `dom.webdriver.enabled = false` to hide the main signal, but
Cloudflare may still challenge. Prefer Chrome unless you have a reason not
to. Either way you sign in to Google (including 2FA / SSO / account-chooser
steps), and the resulting cookies and localStorage are written to `--output`
as a JSON file. Mount that file into the container at the path you set in
`website_crawler.google_auth.storage_state_path`.

A persistent browser profile is kept under `--profile-dir` so subsequent runs
look like a returning user and usually skip CAPTCHAs / Cloudflare challenges
entirely. The default profile directory is suffixed with the browser name for
Firefox (Chromium and Firefox profile formats are not interchangeable).

Prerequisites (one-time):

    pip install playwright
    playwright install chrome      # for the default --browser chromium
    playwright install firefox     # for --browser firefox

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
    p.add_argument(
        "--profile-dir",
        default=None,
        help=(
            "Persistent browser profile directory. Reusing the same directory "
            "across runs avoids repeated CAPTCHAs / Cloudflare challenges. "
            "Defaults to ~/.cache/vectara-ingest/google_bootstrap_profile "
            "(suffixed with the browser name for non-chromium browsers, since "
            "their profile formats are not interchangeable)."
        ),
    )
    p.add_argument(
        "--browser",
        choices=("chromium", "firefox"),
        default="chromium",
        help=(
            "Playwright browser engine to launch (default: %(default)s). "
            "Use 'firefox' if Chrome is not installed locally or you prefer "
            "Firefox for the interactive sign-in flow."
        ),
    )
    p.add_argument(
        "--channel",
        default="chrome",
        help=(
            "Playwright browser channel (chromium only). Defaults to installed "
            "Google Chrome ('chrome'), which is far less likely to be flagged "
            "as a bot than bundled Chromium. Pass an empty string to use "
            "Playwright's bundled Chromium instead. Ignored when "
            "--browser firefox is set."
        ),
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
            "`pip install playwright` and then `playwright install chrome` "
            "(or `playwright install firefox` for --browser firefox)."
        )
        return 2

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if args.profile_dir is None:
        suffix = "" if args.browser == "chromium" else f"_{args.browser}"
        args.profile_dir = os.path.expanduser(
            f"~/.cache/vectara-ingest/google_bootstrap_profile{suffix}"
        )
    profile_dir = os.path.abspath(args.profile_dir)
    os.makedirs(profile_dir, exist_ok=True)

    channel = args.channel or None
    if args.browser == "firefox" and channel and channel != "chrome":
        # 'chrome' is the parser default — only warn when the user actually
        # passed something non-default that we're about to ignore.
        logging.warning(
            "Ignoring --channel %r: the channel parameter is chromium-only "
            "and has no effect with --browser firefox.",
            channel,
        )

    if args.browser == "firefox":
        browser_label = "bundled Firefox"
    else:
        browser_label = channel or "bundled Chromium"
    logging.info(
        f"Opening {browser_label} for Google sign-in. "
        f"Complete the login flow in the browser window."
    )
    logging.info(f"Target start URL: {args.start_url}")
    logging.info(f"Using persistent profile: {profile_dir}")
    logging.info(f"Will save storage state to: {output_path}")

    with sync_playwright() as pw:
        browser_type = getattr(pw, args.browser)
        launch_kwargs = {
            "user_data_dir": profile_dir,
            "headless": False,
        }
        if args.browser == "chromium":
            launch_kwargs["channel"] = channel
            launch_kwargs["args"] = [
                "--disable-blink-features=AutomationControlled"
            ]
        elif args.browser == "firefox":
            # Firefox sets navigator.webdriver=true by default under Playwright;
            # Cloudflare/Google use that as a primary bot signal. Turning the
            # pref off is the Firefox analogue of chromium's
            # --disable-blink-features=AutomationControlled flag. It is not a
            # full stealth solution — Playwright's Firefox is a patched build
            # with other detectable fingerprints — but it is the single biggest
            # cheap win and gets most interactive sign-in flows through.
            launch_kwargs["firefox_user_prefs"] = {
                "dom.webdriver.enabled": False,
            }
        context = browser_type.launch_persistent_context(**launch_kwargs)
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
            context.close()
            return 1

        context.storage_state(path=output_path)
        logging.info(f"Saved Google session to {output_path}")
        context.close()

    return 0


if __name__ == "__main__":
    sys.exit(run())
