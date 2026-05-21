"""Spec tests for crawlers/auth/google_bootstrap.py.

Pin down behavior of the one-time interactive bootstrap CLI, in particular the
choice between Chromium (default, back-compat) and Firefox (new).

Playwright is mocked via sys.modules so these tests run without the real
playwright package installed and never open a real browser window.
"""

from __future__ import annotations

import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Some sibling modules in this repo transitively pull in heavy native deps at
# import time. Stub them defensively so importing google_bootstrap stays cheap.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_fake_playwright():
    """Build a fake `playwright.sync_api` module suitable for sys.modules patching.

    Returns (fake_module, chromium_lpc_mock, firefox_lpc_mock, context_mock)
    so individual tests can inspect call_args on either browser dispatch.
    """
    page = MagicMock(name="page")
    # wait_for_function is the gate that normally blocks until sign-in finishes.
    # As a MagicMock it returns immediately, so run() proceeds to storage_state.
    page.wait_for_function = MagicMock(return_value=None)
    page.goto = MagicMock(return_value=None)

    context = MagicMock(name="context")
    context.new_page.return_value = page
    context.storage_state = MagicMock(return_value=None)
    context.close = MagicMock(return_value=None)

    chromium_lpc = MagicMock(
        name="chromium.launch_persistent_context", return_value=context
    )
    firefox_lpc = MagicMock(
        name="firefox.launch_persistent_context", return_value=context
    )

    pw = MagicMock(name="pw")
    pw.chromium.launch_persistent_context = chromium_lpc
    pw.firefox.launch_persistent_context = firefox_lpc

    sync_playwright = MagicMock(name="sync_playwright")
    sync_playwright.return_value.__enter__.return_value = pw
    sync_playwright.return_value.__exit__.return_value = False

    fake_module = MagicMock()
    fake_module.sync_playwright = sync_playwright

    return fake_module, chromium_lpc, firefox_lpc, context


def _run(argv):
    """Import google_bootstrap and invoke run(argv) with a fake playwright.

    Returns (return_code, chromium_lpc, firefox_lpc, context) for assertions.
    """
    fake, chromium_lpc, firefox_lpc, context = _install_fake_playwright()
    with patch.dict(sys.modules, {"playwright.sync_api": fake}):
        from crawlers.auth import google_bootstrap
        rc = google_bootstrap.run(argv)
    return rc, chromium_lpc, firefox_lpc, context


# ---------------------------------------------------------------------------
# Argparse layer
# ---------------------------------------------------------------------------

def test_parse_args_defaults_browser_to_chromium():
    from crawlers.auth.google_bootstrap import _parse_args
    args = _parse_args(["--output", "/tmp/x.json"])
    assert args.browser == "chromium"


def test_parse_args_accepts_browser_firefox():
    from crawlers.auth.google_bootstrap import _parse_args
    args = _parse_args(["--output", "/tmp/x.json", "--browser", "firefox"])
    assert args.browser == "firefox"


def test_parse_args_rejects_invalid_browser():
    from crawlers.auth.google_bootstrap import _parse_args
    with pytest.raises(SystemExit):
        _parse_args(["--output", "/tmp/x.json", "--browser", "safari"])


def test_parse_args_channel_default_chrome_unchanged():
    """Back-compat lock-in: --channel default must remain 'chrome' so existing
    users who invoke the script with no extra flags get installed Chrome."""
    from crawlers.auth.google_bootstrap import _parse_args
    args = _parse_args(["--output", "/tmp/x.json"])
    assert args.channel == "chrome"


# ---------------------------------------------------------------------------
# Default profile-dir derivation
# ---------------------------------------------------------------------------

def test_default_profile_dir_chromium_has_no_suffix(tmp_path, monkeypatch):
    """Back-compat lock-in: the chromium default path is unchanged.

    Existing users who already have a persistent profile at
    ~/.cache/vectara-ingest/google_bootstrap_profile must keep using it.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    rc, chromium_lpc, _ff, _ctx = _run(["--output", str(tmp_path / "state.json")])
    assert rc == 0
    _, kwargs = chromium_lpc.call_args
    expected = os.path.abspath(
        str(tmp_path / ".cache/vectara-ingest/google_bootstrap_profile")
    )
    assert kwargs["user_data_dir"] == expected


def test_default_profile_dir_firefox_has_firefox_suffix(tmp_path, monkeypatch):
    """Firefox gets its own profile dir — Chromium and Firefox profile
    formats are mutually incompatible and would corrupt each other."""
    monkeypatch.setenv("HOME", str(tmp_path))
    rc, _ch, firefox_lpc, _ctx = _run(
        ["--output", str(tmp_path / "state.json"), "--browser", "firefox"]
    )
    assert rc == 0
    _, kwargs = firefox_lpc.call_args
    expected = os.path.abspath(
        str(tmp_path / ".cache/vectara-ingest/google_bootstrap_profile_firefox")
    )
    assert kwargs["user_data_dir"] == expected


def test_explicit_profile_dir_is_not_suffixed(tmp_path):
    explicit = str(tmp_path / "my_profile")
    rc, _ch, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--browser", "firefox",
        "--profile-dir", explicit,
    ])
    assert rc == 0
    _, kwargs = firefox_lpc.call_args
    assert kwargs["user_data_dir"] == os.path.abspath(explicit)


# ---------------------------------------------------------------------------
# run() dispatch — which Playwright browser type is used
# ---------------------------------------------------------------------------

def test_run_uses_chromium_launch_persistent_context_by_default(tmp_path):
    rc, chromium_lpc, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
    ])
    assert rc == 0
    chromium_lpc.assert_called_once()
    firefox_lpc.assert_not_called()


def test_run_uses_firefox_launch_persistent_context_when_requested(tmp_path):
    rc, chromium_lpc, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
        "--browser", "firefox",
    ])
    assert rc == 0
    firefox_lpc.assert_called_once()
    chromium_lpc.assert_not_called()


# ---------------------------------------------------------------------------
# run() launch kwargs — chromium-only opts must not leak into Firefox launch
# ---------------------------------------------------------------------------

def test_run_passes_channel_and_disable_blink_args_for_chromium(tmp_path):
    rc, chromium_lpc, _ff, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
        "--channel", "chrome",
    ])
    assert rc == 0
    _, kwargs = chromium_lpc.call_args
    assert kwargs.get("channel") == "chrome"
    assert kwargs.get("args") == ["--disable-blink-features=AutomationControlled"]
    assert kwargs.get("headless") is False


def test_run_omits_channel_and_args_for_firefox(tmp_path):
    """--disable-blink-features=AutomationControlled is a Chromium-only flag;
    passing it to Firefox would be at best ignored and at worst rejected.
    The `channel` parameter is also Chromium-only in practice."""
    rc, _ch, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
        "--browser", "firefox",
    ])
    assert rc == 0
    _, kwargs = firefox_lpc.call_args
    assert "channel" not in kwargs
    assert "args" not in kwargs
    assert kwargs.get("headless") is False


def test_run_passes_firefox_user_prefs_to_hide_webdriver(tmp_path):
    """Firefox sets navigator.webdriver=true by default under Playwright, which
    Cloudflare flags. Disabling `dom.webdriver.enabled` removes that signal.

    It is NOT a full stealth solution — Playwright's patched Firefox still
    leaves other fingerprints — but it is the single biggest cheap win and
    matches the role `--disable-blink-features=AutomationControlled` plays for
    chromium."""
    rc, _ch, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
        "--browser", "firefox",
    ])
    assert rc == 0
    _, kwargs = firefox_lpc.call_args
    assert kwargs.get("firefox_user_prefs") == {"dom.webdriver.enabled": False}


def test_run_does_not_pass_firefox_user_prefs_for_chromium(tmp_path):
    """firefox_user_prefs is a Firefox-only parameter — must not leak into the
    chromium launch call."""
    rc, chromium_lpc, _ff, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
    ])
    assert rc == 0
    _, kwargs = chromium_lpc.call_args
    assert "firefox_user_prefs" not in kwargs


# ---------------------------------------------------------------------------
# Edge case: --channel passed together with --browser firefox
# ---------------------------------------------------------------------------

def test_run_warns_and_ignores_channel_when_browser_is_firefox(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    rc, _ch, firefox_lpc, _ctx = _run([
        "--output", str(tmp_path / "state.json"),
        "--profile-dir", str(tmp_path / "profile"),
        "--browser", "firefox",
        "--channel", "chrome-beta",
    ])
    assert rc == 0
    # A warning that names --channel must have been logged.
    assert any(
        "channel" in record.message.lower() for record in caplog.records
    ), f"expected a warning mentioning 'channel'; got {[r.message for r in caplog.records]}"
    # And --channel must not have been forwarded to Playwright.
    _, kwargs = firefox_lpc.call_args
    assert "channel" not in kwargs
