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
    with patch.object(
        google_manager, "get_service_account_credentials", return_value=fake_creds
    ) as helper:
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
        {"name": "SID", "value": "sid-val", "domain": ".google.com",
         "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
        {"name": "__Host-1PLSID", "value": "psid-val",
         "domain": "accounts.google.com", "path": "/", "secure": True,
         "httpOnly": True, "sameSite": "Lax"},
        {"name": "OSID", "value": "osid-val",
         "domain": "sites.google.com", "path": "/", "secure": True},
        {"name": "unrelated", "value": "x", "domain": "example.com",
         "path": "/", "secure": False},
        {"name": "rip", "value": "y", "domain": ".rippling.com",
         "path": "/", "secure": True},
    ]
    pw_factory, context, page = _build_playwright_chain(cookies)

    with patch.object(google_manager, "sync_playwright", return_value=pw_factory):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        result = mgr.get_authenticated_cookies()

    # The browser.new_context call should have received storage_state
    chromium = pw_factory.start.return_value.chromium
    browser = chromium.launch.return_value
    _, kwargs = browser.new_context.call_args
    assert kwargs.get("storage_state") == str(storage_file)

    # New contract: list of dicts with attributes preserved. Only Google-family
    # cookies (.google.com, accounts.google.com, sites.google.com) survive —
    # the example.com and .rippling.com entries are filtered out so they
    # don't leak cross-domain when Scrapy follows redirects.
    assert isinstance(result, list)
    names = {c["name"]: c for c in result}
    assert set(names) == {"SID", "__Host-1PLSID", "OSID"}

    sid = names["SID"]
    assert sid["value"] == "sid-val"
    assert sid["domain"] == ".google.com"
    assert sid["path"] == "/"
    assert sid["secure"] is True

    host_cookie = names["__Host-1PLSID"]
    # __Host-* cookies must keep their host-scoped domain so Scrapy doesn't
    # leak them to sites.google.com on a redirect.
    assert host_cookie["domain"] == "accounts.google.com"
    assert host_cookie["secure"] is True


def test_account_chooser_is_not_treated_as_expired_session(tmp_path):
    """When the stored Google session is valid but the user has MULTIPLE
    Google accounts signed in (very common — personal Gmail + work Workspace),
    bare https://sites.google.com redirects to the account chooser at
    https://accounts.google.com/v3/signin/accountchooser?continue=... .

    The session is fine — Google just wants the user to pick which account.
    The previous check `'accounts.google.com' in current_url` flagged this
    as 'session expired', breaking customers who imported cookies from a
    multi-account Firefox profile.

    Fix: only ServiceLogin (true sign-in page) means expired. accountchooser
    means signed in. Capture cookies and continue."""
    from crawlers.auth import google_manager

    storage_file = tmp_path / "state.json"
    storage_file.write_text(json.dumps({"cookies": [], "origins": []}))

    config = {"mode": "oauth_user", "storage_state_path": str(storage_file)}
    secrets = {"credentials_file": "/tmp/oauth.json"}

    cookies = [
        {"name": "SID", "value": "v", "domain": ".google.com",
         "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax"},
    ]
    pw_factory, _ctx, _page = _build_playwright_chain(
        cookies=cookies,
        final_url=(
            "https://accounts.google.com/v3/signin/accountchooser"
            "?continue=https%3A%2F%2Fsites.google.com%2F"
        ),
    )

    with patch.object(google_manager, "sync_playwright", return_value=pw_factory):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        # Must NOT raise — session is valid, just multi-account.
        result = mgr.get_authenticated_cookies()

    assert len(result) == 1
    assert result[0]["name"] == "SID"


def test_get_authenticated_cookies_uses_target_url_when_provided(tmp_path):
    """The auth manager should navigate to the caller's actual target URL
    when one is provided, instead of bare sites.google.com. Workspace-domain
    URLs (e.g. sites.google.com/vectara.com/help) typically route directly to
    the correct Google account without triggering the account chooser, so
    feeding the real target URL into the auth-establishing navigation is the
    cleanest way to avoid the multi-account ambiguity in the first place.
    """
    from crawlers.auth import google_manager

    storage_file = tmp_path / "state.json"
    storage_file.write_text(json.dumps({"cookies": [], "origins": []}))

    config = {"mode": "oauth_user", "storage_state_path": str(storage_file)}
    secrets = {"credentials_file": "/tmp/oauth.json"}

    pw_factory, _ctx, page = _build_playwright_chain(
        cookies=[
            {"name": "SID", "value": "v", "domain": ".google.com",
             "path": "/", "secure": True}
        ],
        final_url="https://sites.google.com/vectara.com/help/home",
    )

    target = "https://sites.google.com/vectara.com/help"
    with patch.object(google_manager, "sync_playwright", return_value=pw_factory):
        mgr = google_manager.GoogleAuthManager(config, secrets)
        mgr.get_authenticated_cookies(target_url=target)

    # The manager must navigate to the caller's URL, not to a hardcoded one.
    page.goto.assert_called()
    called_url = page.goto.call_args.args[0]
    assert called_url == target, (
        f"manager should navigate to caller's target URL; got {called_url!r}"
    )


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
