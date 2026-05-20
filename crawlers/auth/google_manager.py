"""Google authentication for `website_crawler` — mirrors `SAMLAuthManager`.

Two auth modes are supported, configured via `website_crawler.google_auth.mode`:

- `service_account`: SA key file + Workspace domain-wide delegation, impersonating
  `delegated_user`. Workspace admin must grant DWD to the SA.
- `oauth_user`: OAuth user refresh token (same shape as `gdrive_crawler`'s
  `get_oauth_credentials`). One-time consent, refresh token persisted.

A Google service-account bearer token is NOT accepted by `sites.google.com`
content URLs — those require browser session cookies. The bridge between
credentials and cookies is Playwright `storage_state`: a one-time interactive
login (see `google_bootstrap.py`) writes a JSON file; subsequent runs reuse it.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from typing import List, Optional

import requests

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None  # type: ignore[assignment]
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not available. Google authentication will be disabled.")

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials


logger = logging.getLogger(__name__)


DEFAULT_SCOPES = ["openid", "email", "https://www.googleapis.com/auth/userinfo.profile"]
VALID_MODES = ("service_account", "oauth_user")

# Fixed in-container path where `run.sh` mounts the host's storage_state JSON.
# Matches the gdrive `credentials.json` pattern. When this path exists at init
# time, it wins over any `storage_state_path` set in YAML — the YAML field is
# treated as a host path (for `run.sh` to mount), not a container path.
DOCKER_STORAGE_STATE_PATH = "/home/vectara/env/google_storage_state.json"


def get_credentials(
    delegated_user: str,
    credentials_file: str,
    scopes: Optional[List[str]] = None,
) -> service_account.Credentials:
    """Service account with domain-wide delegation, impersonating `delegated_user`.

    Deliberately does NOT use `core.utils.get_docker_or_local_path` — that helper
    silently swaps in `/home/vectara/env/credentials.json` when present, which
    would conflict with `gdrive_crawler` if both run in the same image with
    different SAs.
    """
    effective_scopes = scopes or DEFAULT_SCOPES
    creds = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=effective_scopes
    )
    return creds.with_subject(delegated_user)


def get_oauth_credentials(
    credentials_file: str,
    scopes: Optional[List[str]] = None,
) -> Credentials:
    """OAuth user credentials from a token JSON file.

    Refreshes the access token if expired and writes the refreshed token back
    to the same file (matches `gdrive_crawler.get_oauth_credentials` behavior).
    """
    effective_scopes = scopes or DEFAULT_SCOPES
    with open(credentials_file, "r") as f:
        token_data = json.load(f)

    creds = Credentials.from_authorized_user_info(token_data, effective_scopes)

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request as GoogleRequest

        creds.refresh(GoogleRequest())
        with open(credentials_file, "w") as f:
            json.dump(
                {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes,
                },
                f,
                indent=2,
            )
        logger.info("Refreshed and persisted OAuth token")

    return creds


class GoogleAuthManager:
    """Google authentication for website_crawler. See module docstring for modes."""

    def __init__(self, config: dict, secrets: dict):
        self.config = config or {}
        self.secrets = secrets or {}

        self.mode = self.config.get("mode")
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"google_auth.mode must be one of {VALID_MODES}, got: {self.mode!r}"
            )

        self.delegated_user = self.config.get("delegated_user")
        if self.mode == "service_account" and not self.delegated_user:
            raise ValueError(
                "google_auth mode 'service_account' requires 'delegated_user' in config"
            )

        # `credentials_file` is only needed for Bearer-token API calls
        # (Drive / Sites APIs). The common case — crawling sites.google.com
        # via persisted storage_state cookies — does not call any Google API,
        # so we defer the check until something actually asks for credentials.
        self.credentials_file = self.secrets.get("credentials_file")

        self.scopes = list(self.config.get("scopes") or DEFAULT_SCOPES)

        # In Docker, `run.sh` mounts the host file to DOCKER_STORAGE_STATE_PATH.
        # When that mount is present, prefer it over the YAML value (which is the
        # host-side path, not the container path). Falls back to the YAML value
        # for native runs and back-compat with explicit container paths.
        config_storage_state_path = self.config.get("storage_state_path")
        if config_storage_state_path and os.path.exists(DOCKER_STORAGE_STATE_PATH):
            self.storage_state_path = DOCKER_STORAGE_STATE_PATH
        else:
            self.storage_state_path = config_storage_state_path

        self._credentials: Optional[object] = None

    # --- credentials & API session -------------------------------------------------

    def get_credentials(self):
        if self._credentials is not None:
            return self._credentials

        if not self.credentials_file:
            raise ValueError(
                "google_auth requires 'credentials_file' in secrets to mint API "
                "credentials (set GOOGLE_CREDENTIALS_FILE in secrets.toml). "
                "Cookie-only crawls of sites.google.com do not need this — "
                "only callers of get_credentials()/get_authenticated_session() do."
            )

        if self.mode == "service_account":
            self._credentials = get_credentials(
                self.delegated_user,
                self.credentials_file,
                scopes=self.scopes,
            )
        else:
            self._credentials = get_oauth_credentials(
                self.credentials_file,
                scopes=self.scopes,
            )
        return self._credentials

    def get_authenticated_session(self) -> requests.Session:
        """Returns a `requests.Session` with `Authorization: Bearer <token>`.

        For Google API calls (Drive, Sites APIs) — NOT for `sites.google.com`
        content URLs, which require browser cookies. Use
        `get_authenticated_cookies()` for those.
        """
        creds = self.get_credentials()
        if getattr(creds, "expired", False) and hasattr(creds, "refresh"):
            from google.auth.transport.requests import Request as GoogleRequest

            creds.refresh(GoogleRequest())

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {creds.token}"
        return session

    # --- browser cookies -----------------------------------------------------------

    def get_authenticated_cookies(self) -> List[dict]:
        """Open Playwright with the persisted `storage_state`, navigate to
        `sites.google.com`, and capture Google-family cookies for Scrapy.

        Returns a list of `{name, value, domain, path, secure}` dicts. The
        full attribute set is required because Scrapy's CookieMiddleware
        needs `domain` to scope `__Host-*` / `__Secure-*` cookies to their
        original host — flattening to `{name: value}` causes
        `accounts.google.com` cookies to leak to `sites.google.com` on
        redirects, which Google rejects with `CookieMismatch`.

        Raises RuntimeError with a clear pointer to `google_bootstrap` if the
        storage state is missing, never captured, or has expired.
        """
        if not self.storage_state_path:
            raise RuntimeError(
                "google_auth.storage_state_path is required. Run "
                "`python -m crawlers.auth.google_bootstrap --output <path>` "
                "to capture an initial Google session, then set "
                "google_auth.storage_state_path in your config."
            )

        if not os.path.exists(self.storage_state_path):
            raise RuntimeError(
                f"Google storage_state file not found at {self.storage_state_path}. "
                f"Run `python -m crawlers.auth.google_bootstrap "
                f"--output {self.storage_state_path}` to capture it."
            )

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not available — install playwright to use google_auth."
            )

        with self._playwright_browser() as (_browser, context, page):
            try:
                page.goto(
                    "https://sites.google.com",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                logger.warning(
                    f"Google navigation did not fully settle (continuing anyway): {e}"
                )

            current = page.url or ""
            if "accounts.google.com" in current or "ServiceLogin" in current:
                raise RuntimeError(
                    f"Stored Google session has expired (landed on {current}). "
                    f"Re-run `python -m crawlers.auth.google_bootstrap "
                    f"--output {self.storage_state_path}`."
                )

            raw_cookies = context.cookies()

        cookies: List[dict] = []
        for c in raw_cookies:
            domain = (c.get("domain") or "").lower()
            # Match `.google.com` (covers `accounts.google.com`,
            # `sites.google.com`, etc.) and the bare `google.com` host. Drop
            # everything else so unrelated cookies from the storage_state
            # (Rippling, YouTube subdomains, etc.) can't leak to Google on
            # cross-domain redirects.
            if domain.endswith(".google.com") or domain == "google.com":
                cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                    "secure": bool(c.get("secure", False)),
                })

        logger.info(f"Captured {len(cookies)} Google session cookies for crawler use")
        return cookies

    @contextmanager
    def _playwright_browser(self):
        pw = None
        browser = None
        context = None
        page = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(storage_state=self.storage_state_path)
            page = context.new_page()
            yield browser, context, page
        finally:
            try:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
                if pw is not None:
                    pw.stop()
            except Exception as cleanup_error:
                logger.debug(f"Playwright cleanup error: {cleanup_error}")
