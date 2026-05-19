"""Spec tests for GoogleAuthManager.

Defines the contract for `crawlers/auth/google_manager.py` before the
implementation lands. All external boundaries (Playwright, google.auth,
google.oauth2) are mocked so tests are hermetic.
"""

import json
import sys
from unittest.mock import MagicMock, patch

# Stub heavy native deps that some sibling modules transitively import.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())

import pytest


# ---------------------------------------------------------------------------
# __init__ validation
# ---------------------------------------------------------------------------

def test_init_service_account_mode_requires_delegated_user():
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {"mode": "service_account"}
    secrets = {"credentials_file": "/tmp/sa.json"}

    with pytest.raises(ValueError, match="delegated_user"):
        GoogleAuthManager(config, secrets)


def test_init_oauth_user_mode_does_not_require_delegated_user():
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {"mode": "oauth_user"}
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = GoogleAuthManager(config, secrets)
    assert mgr.mode == "oauth_user"


def test_init_rejects_unknown_mode():
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {"mode": "magic"}
    secrets = {"credentials_file": "/tmp/x.json"}

    with pytest.raises(ValueError, match="mode"):
        GoogleAuthManager(config, secrets)


def test_init_does_not_require_credentials_file_when_only_cookies_needed():
    """Crawls that only consume sites.google.com cookies (via storage_state)
    must work without ever providing GOOGLE_CREDENTIALS_FILE — that secret
    only matters for API-style Bearer calls, which a content crawl doesn't
    make."""
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {"mode": "oauth_user", "storage_state_path": "/tmp/state.json"}
    secrets = {}

    mgr = GoogleAuthManager(config, secrets)
    assert mgr.credentials_file is None


def test_get_credentials_raises_when_credentials_file_missing():
    """The credential check is deferred — but the moment a caller actually
    asks for API credentials, the manager must complain loudly."""
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {"mode": "oauth_user"}
    secrets = {}

    mgr = GoogleAuthManager(config, secrets)
    with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS_FILE"):
        mgr.get_credentials()


def test_init_accepts_optional_storage_state_path():
    from crawlers.auth.google_manager import GoogleAuthManager

    config = {
        "mode": "oauth_user",
        "storage_state_path": "/tmp/state.json",
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = GoogleAuthManager(config, secrets)
    assert mgr.storage_state_path == "/tmp/state.json"


def test_storage_state_path_uses_docker_mount_when_present(monkeypatch):
    """Inside Docker, run.sh mounts the host file to a fixed container path.
    When that fixed path exists, it wins over the YAML-supplied host path —
    the YAML field is a host path, not a container path."""
    from crawlers.auth import google_manager

    real_exists = google_manager.os.path.exists

    def fake_exists(p):
        if p == google_manager.DOCKER_STORAGE_STATE_PATH:
            return True
        return real_exists(p)

    monkeypatch.setattr(google_manager.os.path, "exists", fake_exists)

    config = {
        "mode": "oauth_user",
        "storage_state_path": "/some/host/path/state.json",
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = google_manager.GoogleAuthManager(config, secrets)
    assert mgr.storage_state_path == google_manager.DOCKER_STORAGE_STATE_PATH


def test_storage_state_path_falls_back_to_config_path_when_no_docker_mount(monkeypatch):
    """Running natively (or in Docker without the auto-mount), the YAML path
    is used directly."""
    from crawlers.auth import google_manager

    real_exists = google_manager.os.path.exists

    def fake_exists(p):
        if p == google_manager.DOCKER_STORAGE_STATE_PATH:
            return False
        return real_exists(p)

    monkeypatch.setattr(google_manager.os.path, "exists", fake_exists)

    config = {
        "mode": "oauth_user",
        "storage_state_path": "/some/host/path/state.json",
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = google_manager.GoogleAuthManager(config, secrets)
    assert mgr.storage_state_path == "/some/host/path/state.json"


# ---------------------------------------------------------------------------
# get_credentials
# ---------------------------------------------------------------------------

def test_get_credentials_service_account_delegates_to_gdrive_helper():
    from crawlers.auth import google_manager

    config = {
        "mode": "service_account",
        "delegated_user": "user@example.com",
        "scopes": ["openid", "email"],
    }
    secrets = {"credentials_file": "/tmp/sa.json"}

    fake_creds = MagicMock(name="fake_sa_creds")
    with patch.object(google_manager, "get_credentials", return_value=fake_creds) as helper:
        mgr = google_manager.GoogleAuthManager(config, secrets)
        result = mgr.get_credentials()

    helper.assert_called_once()
    args, kwargs = helper.call_args
    # delegated_user, credentials path, scopes are passed through
    assert "user@example.com" in args or kwargs.get("delegated_user") == "user@example.com"
    assert result is fake_creds


def test_get_credentials_oauth_user_delegates_to_gdrive_helper():
    from crawlers.auth import google_manager

    config = {"mode": "oauth_user", "scopes": ["openid", "email"]}
    secrets = {"credentials_file": "/tmp/oauth.json"}

    fake_creds = MagicMock(name="fake_oauth_creds")
    with patch.object(google_manager, "get_oauth_credentials", return_value=fake_creds) as helper:
        mgr = google_manager.GoogleAuthManager(config, secrets)
        result = mgr.get_credentials()

    helper.assert_called_once()
    args, kwargs = helper.call_args
    assert "/tmp/oauth.json" in args or kwargs.get("credentials_file") == "/tmp/oauth.json"
    assert result is fake_creds


def test_default_scopes_include_openid_and_email():
    from crawlers.auth import google_manager

    config = {"mode": "oauth_user"}  # no scopes specified
    secrets = {"credentials_file": "/tmp/oauth.json"}

    captured_scopes = {}

    def fake_oauth(credentials_file, scopes=None):
        captured_scopes["scopes"] = scopes
        return MagicMock()

    with patch.object(google_manager, "get_oauth_credentials", side_effect=fake_oauth):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        mgr.get_credentials()

    assert "openid" in captured_scopes["scopes"]
    assert "email" in captured_scopes["scopes"]


# ---------------------------------------------------------------------------
# get_authenticated_session
# ---------------------------------------------------------------------------

def test_get_authenticated_session_sets_bearer_header():
    from crawlers.auth import google_manager

    config = {"mode": "oauth_user"}
    secrets = {"credentials_file": "/tmp/oauth.json"}

    fake_creds = MagicMock()
    fake_creds.token = "ya29.fake-access-token"
    fake_creds.expired = False

    with patch.object(google_manager, "get_oauth_credentials", return_value=fake_creds):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        session = mgr.get_authenticated_session()

    assert session.headers.get("Authorization") == "Bearer ya29.fake-access-token"


# ---------------------------------------------------------------------------
# get_authenticated_cookies — storage_state happy path
# ---------------------------------------------------------------------------

def _build_playwright_chain(cookies, final_url="https://sites.google.com/d/abc/p/xyz"):
    """Build a nested-MagicMock Playwright chain that returns the given cookies.

    Mirrors: sync_playwright().start() -> chromium.launch() -> new_context(...) -> new_page().
    """
    page = MagicMock(name="page")
    page.url = final_url
    page.goto = MagicMock()
    page.content = MagicMock(return_value="<html><body>real site content</body></html>")
    page.wait_for_load_state = MagicMock()

    context = MagicMock(name="context")
    context.new_page.return_value = page
    context.cookies.return_value = cookies  # list of {name, value, domain, ...}

    browser = MagicMock(name="browser")
    browser.new_context.return_value = context

    chromium = MagicMock(name="chromium")
    chromium.launch.return_value = browser

    pw_instance = MagicMock(name="pw_instance")
    pw_instance.chromium = chromium

    pw_factory = MagicMock(name="pw_factory")
    pw_factory.start.return_value = pw_instance

    return pw_factory, context, page


def test_get_authenticated_cookies_uses_storage_state_when_present(tmp_path):
    from crawlers.auth import google_manager

    storage_file = tmp_path / "state.json"
    storage_file.write_text(json.dumps({"cookies": [], "origins": []}))

    config = {
        "mode": "oauth_user",
        "storage_state_path": str(storage_file),
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    cookies = [
        {"name": "SID", "value": "sid-val", "domain": ".google.com"},
        {"name": "SSID", "value": "ssid-val", "domain": ".google.com"},
        {"name": "unrelated", "value": "x", "domain": "example.com"},
    ]
    pw_factory, context, page = _build_playwright_chain(cookies)

    with patch.object(google_manager, "sync_playwright", return_value=pw_factory):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        result = mgr.get_authenticated_cookies()

    # Playwright was asked to load the existing storage state
    new_context_kwargs = context.new_context.call_args if hasattr(context, "call_args") else None
    # The browser.new_context call (not context.new_context) should have received storage_state
    chromium = pw_factory.start.return_value.chromium
    browser = chromium.launch.return_value
    _, kwargs = browser.new_context.call_args
    assert kwargs.get("storage_state") == str(storage_file)

    # Only *.google.com cookies are returned, as a {name: value} dict
    assert result == {"SID": "sid-val", "SSID": "ssid-val"}


def test_get_authenticated_cookies_raises_when_landing_on_login_page(tmp_path):
    """If after navigation the browser is sitting on accounts.google.com, the
    stored state has expired and we cannot authenticate silently. The manager
    should surface a clear error pointing users at the bootstrap script."""
    from crawlers.auth import google_manager

    storage_file = tmp_path / "state.json"
    storage_file.write_text(json.dumps({"cookies": [], "origins": []}))

    config = {
        "mode": "oauth_user",
        "storage_state_path": str(storage_file),
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    pw_factory, _ctx, _page = _build_playwright_chain(
        cookies=[],
        final_url="https://accounts.google.com/ServiceLogin?continue=...",
    )

    with patch.object(google_manager, "sync_playwright", return_value=pw_factory):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        with pytest.raises(RuntimeError, match="google_bootstrap"):
            mgr.get_authenticated_cookies()


def test_get_authenticated_cookies_raises_when_no_storage_state_configured():
    from crawlers.auth import google_manager

    config = {"mode": "oauth_user"}  # no storage_state_path
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = google_manager.GoogleAuthManager(config, secrets)
    with pytest.raises(RuntimeError, match="storage_state"):
        mgr.get_authenticated_cookies()


def test_get_authenticated_cookies_raises_when_storage_state_file_missing(tmp_path):
    from crawlers.auth import google_manager

    config = {
        "mode": "oauth_user",
        "storage_state_path": str(tmp_path / "does_not_exist.json"),
    }
    secrets = {"credentials_file": "/tmp/oauth.json"}

    mgr = google_manager.GoogleAuthManager(config, secrets)
    with pytest.raises(RuntimeError, match="bootstrap"):
        mgr.get_authenticated_cookies()
