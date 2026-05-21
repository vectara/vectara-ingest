"""Spec tests for crawlers/auth/google_firefox_import.py.

Imports Google session cookies from a real (non-Playwright) Firefox profile
and writes them as Playwright storage_state.json — the bypass path for when
Cloudflare Turnstile (or similar fingerprinting) blocks the Playwright-driven
bootstrap.

Tests build a synthetic Firefox cookies.sqlite + profiles.ini in tmp_path so
no real Firefox install is needed.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from unittest.mock import MagicMock

import pytest

# Defensive stubs for heavy native deps that sibling modules may transitively
# pull in. Mirrors test_google_bootstrap.py / test_google_auth_manager.py.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Subset of Firefox's moz_cookies columns that the importer actually reads.
# The real table has ~15 columns; we only need these.
_MOZ_COOKIES_SCHEMA = """
CREATE TABLE moz_cookies (
    id INTEGER PRIMARY KEY,
    name TEXT,
    value TEXT,
    host TEXT,
    path TEXT,
    expiry INTEGER,
    isSecure INTEGER,
    isHttpOnly INTEGER,
    sameSite INTEGER
);
"""


# Mirrors Firefox 138+ Selectable Profiles schema for the Profile Groups DB.
# Source: Firefox source tree, profile-groups SQLite migration. Only `name`,
# `path`, and `avatar` are surfaced to the user; theme columns are written by
# Firefox but the importer doesn't need them.
_PROFILE_GROUPS_SCHEMA = """
CREATE TABLE Profiles (
    id INTEGER PRIMARY KEY NOT NULL,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    avatar TEXT NOT NULL,
    themeId TEXT NOT NULL,
    themeFg TEXT NOT NULL,
    themeBg TEXT NOT NULL
);
"""


def _make_profile_groups_db(firefox_root, store_id, profiles):
    """Lay down a Profile Groups SQLite DB at <root>/Profile Groups/<id>.sqlite.

    `profiles` is a list of dicts: path (relative to firefox_root, e.g.
    'Profiles/abc.default-release'), name (user-facing), avatar (optional).
    """
    pg_dir = os.path.join(str(firefox_root), "Profile Groups")
    os.makedirs(pg_dir, exist_ok=True)
    db_path = os.path.join(pg_dir, f"{store_id}.sqlite")
    conn = sqlite3.connect(db_path)
    conn.executescript(_PROFILE_GROUPS_SCHEMA)
    conn.executemany(
        "INSERT INTO Profiles (path, name, avatar, themeId, themeFg, themeBg) "
        "VALUES (?, ?, ?, '', '', '')",
        [(p["path"], p["name"], p.get("avatar", "")) for p in profiles],
    )
    conn.commit()
    conn.close()
    return db_path


def _make_firefox_profile(profile_dir, cookies):
    """Build a fake Firefox profile dir with a cookies.sqlite at `profile_dir`.

    `cookies` is a list of dicts: name, value, host, path, expiry,
    isSecure, isHttpOnly, sameSite (Firefox int convention: 0=None,1=Lax,2=Strict).
    """
    os.makedirs(profile_dir, exist_ok=True)
    db_path = os.path.join(profile_dir, "cookies.sqlite")
    conn = sqlite3.connect(db_path)
    conn.executescript(_MOZ_COOKIES_SCHEMA)
    conn.executemany(
        "INSERT INTO moz_cookies "
        "(name, value, host, path, expiry, isSecure, isHttpOnly, sameSite) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                c["name"], c["value"], c["host"], c["path"],
                c.get("expiry", 0), c.get("isSecure", 1),
                c.get("isHttpOnly", 1), c.get("sameSite", 1),
            )
            for c in cookies
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def _google_cookies():
    """A representative cross-section of cookies the importer should keep."""
    return [
        {"name": "SID", "value": "sid-val", "host": ".google.com", "path": "/",
         "expiry": 9999999999, "isSecure": 1, "isHttpOnly": 1, "sameSite": 1},
        {"name": "__Host-1PLSID", "value": "psid-val",
         "host": "accounts.google.com", "path": "/",
         "expiry": 9999999999, "isSecure": 1, "isHttpOnly": 1, "sameSite": 1},
        {"name": "OSID", "value": "osid-val",
         "host": "sites.google.com", "path": "/",
         "expiry": 0, "isSecure": 1, "isHttpOnly": 0, "sameSite": 2},
    ]


def _non_google_cookies():
    """Cookies the importer must drop — leaking these into storage_state.json
    would let the crawler send them to Google on cross-domain redirects."""
    return [
        {"name": "rippling_session", "value": "rip", "host": ".rippling.com",
         "path": "/", "isSecure": 1, "isHttpOnly": 1, "sameSite": 1},
        {"name": "tracking", "value": "ex", "host": "example.com",
         "path": "/", "isSecure": 0, "isHttpOnly": 0, "sameSite": 0},
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_imports_google_cookies_from_explicit_profile(tmp_path):
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), _google_cookies() + _non_google_cookies())
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    assert rc == 0

    state = json.loads(output.read_text())
    # Top-level Playwright storage_state shape
    assert set(state) == {"cookies", "origins"}
    assert state["origins"] == []   # we don't extract localStorage

    names = {c["name"]: c for c in state["cookies"]}
    assert set(names) == {"SID", "__Host-1PLSID", "OSID"}, \
        "Only Google-family cookies should survive the filter"


def test_imported_cookies_have_playwright_storage_state_shape(tmp_path):
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), _google_cookies())
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())

    sid = next(c for c in state["cookies"] if c["name"] == "SID")
    # Required Playwright storage_state cookie fields
    assert sid["value"] == "sid-val"
    assert sid["domain"] == ".google.com"
    assert sid["path"] == "/"
    assert sid["httpOnly"] is True
    assert sid["secure"] is True
    assert sid["sameSite"] == "Lax"          # Firefox int 1 -> "Lax"
    assert sid["expires"] == 9999999999

    # __Host-* cookie must keep its host-scoped domain (not get promoted to
    # .google.com); GoogleAuthManager relies on this to prevent cookie
    # leakage on cross-domain redirects.
    host_cookie = next(c for c in state["cookies"] if c["name"] == "__Host-1PLSID")
    assert host_cookie["domain"] == "accounts.google.com"


def test_samesite_none_cookies_are_force_marked_secure(tmp_path):
    """Chromium 80+ silently drops cookies with `SameSite=None` and
    `Secure=false`. Firefox stores some Google session cookies (SID, HSID,
    APISID, SIDCC — the primary auth cookies) with isSecure=0 in
    multi-account profile state, even though Google originally sent them
    with the Secure attribute and they only ever flow over HTTPS.

    Without normalization, those four cookies vanish on `new_context(
    storage_state=...)` and Google's session lookup sees an anonymous
    request → account chooser fires → crawl fails.

    Regression coverage for the broadcom-google-site crawl that showed
    'redirected to identity-provider accounts.google.com' even after the
    Firefox-import path produced what looked like a fully-populated state.

    Fix: when sameSite='None' and secure=false, force secure=true. The
    transformation is safe (cookies were always HTTPS-only in practice) and
    is the only way to keep Chromium honoring them.
    """
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        # Mirrors what Firefox stores for SID in a multi-account Vectara
        # Workspace profile: SameSite=None (Firefox int 0), Secure=0.
        {"name": "SID", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 9999999999, "isSecure": 0, "isHttpOnly": 0,
         "sameSite": 0},
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())
    sid = state["cookies"][0]
    assert sid["sameSite"] == "None"
    assert sid["secure"] is True, (
        "SameSite=None cookies must be emitted as Secure=true or Chromium "
        "drops them"
    )


def test_samesite_lax_cookies_are_not_promoted_to_secure(tmp_path):
    """Don't OVER-normalize: cookies with SameSite=Lax (or Strict) and
    secure=false are valid in Chromium, so leave them alone. Only the
    SameSite=None + !Secure combination needs the workaround."""
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        {"name": "PREF", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 9999999999, "isSecure": 0, "isHttpOnly": 0,
         "sameSite": 1},   # Lax
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    cookies = json.loads(output.read_text())["cookies"]
    pref = next(c for c in cookies if c["name"] == "PREF")
    assert pref["sameSite"] == "Lax"
    assert pref["secure"] is False, \
        "non-None SameSite cookies must keep their original Secure value"


def test_expiry_stored_as_milliseconds_is_converted_to_seconds(tmp_path):
    """Firefox 100+ (mid-2022 onward) stores cookies.sqlite `expiry` in
    MILLISECONDS, not seconds. Playwright's storage_state schema requires
    seconds and rejects values that exceed its valid range with:
        'Cookie should have a valid expires, only -1 or a positive number
         for the unix timestamp in seconds is allowed'

    The importer must detect the unit and convert. Heuristic threshold:
    any positive expiry > 10^11 is impossible as seconds (year 5138) so
    it MUST be milliseconds — divide by 1000.

    Regression coverage for the customer-blocking bug: with the raw 13-digit
    ms value passed through unchanged, the crawler container crashed at
    `_setup_google_auth` -> Browser.new_context(storage_state=...).
    """
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        # 1813944148629 ms = 2027-06-25 (typical Firefox 138-era expiry).
        # As seconds it would be year 59519 and Playwright rejects it.
        {"name": "SID", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 1813944148629, "isSecure": 1, "isHttpOnly": 1,
         "sameSite": 1},
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())
    sid = state["cookies"][0]
    # ms / 1000 = 1813944148 seconds → year 2027, well inside Playwright's range
    assert sid["expires"] == 1813944148, \
        f"ms value should be /1000 to seconds; got {sid['expires']!r}"


def test_legacy_expiry_in_seconds_is_passed_through_unchanged(tmp_path):
    """Pre-Firefox-100 cookies have expiry already in seconds (10-digit
    values). Those must NOT be divided by 1000 — that would push the
    expiry into 1970 territory and the cookie would look expired."""
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        # 1900000000 seconds = year 2030 (legacy Firefox stored this way).
        {"name": "SID", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 1900000000, "isSecure": 1, "isHttpOnly": 1,
         "sameSite": 1},
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())
    sid = state["cookies"][0]
    assert sid["expires"] == 1900000000, \
        f"legacy seconds value must be unchanged; got {sid['expires']!r}"


def test_session_cookie_expiry_zero_maps_to_minus_one(tmp_path):
    """Firefox stores session cookies with expiry=0; Playwright uses -1."""
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        {"name": "SESS", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 0, "isSecure": 1, "isHttpOnly": 1, "sameSite": 1},
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())
    assert state["cookies"][0]["expires"] == -1


# ---------------------------------------------------------------------------
# SameSite int -> str mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ff_int,playwright_str", [
    (0, "None"),
    (1, "Lax"),
    (2, "Strict"),
])
def test_samesite_mapping_firefox_int_to_playwright_string(
    tmp_path, ff_int, playwright_str
):
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), [
        {"name": "C", "value": "v", "host": ".google.com", "path": "/",
         "expiry": 9999999999, "isSecure": 1, "isHttpOnly": 1,
         "sameSite": ff_int},
    ])
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    state = json.loads(output.read_text())
    assert state["cookies"][0]["sameSite"] == playwright_str


# ---------------------------------------------------------------------------
# Profile auto-detection via profiles.ini
# ---------------------------------------------------------------------------

def _write_profiles_ini(firefox_root, profile_relpath):
    """Write a minimal Firefox profiles.ini pointing at `profile_relpath`."""
    os.makedirs(firefox_root, exist_ok=True)
    (firefox_root / "profiles.ini").write_text(
        "[Install4F96D1932A9F858E]\n"
        f"Default={profile_relpath}\n"
        "Locked=1\n"
        "\n"
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "Default=1\n"
    )


def test_autodetects_default_profile_via_profiles_ini_macos(tmp_path, monkeypatch):
    """On macOS, Firefox lives at ~/Library/Application Support/Firefox."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    profile_relpath = "Profiles/abc123.default-release"
    profile_dir = ff_root / profile_relpath
    _write_profiles_ini(ff_root, profile_relpath)
    _make_firefox_profile(str(profile_dir), _google_cookies())

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--output", str(output)])
    assert rc == 0
    state = json.loads(output.read_text())
    assert len(state["cookies"]) == 3


def test_autodetects_default_profile_via_profiles_ini_linux(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    ff_root = tmp_path / ".mozilla" / "firefox"
    profile_relpath = "abc123.default-release"
    profile_dir = ff_root / profile_relpath
    _write_profiles_ini(ff_root, profile_relpath)
    _make_firefox_profile(str(profile_dir), _google_cookies())

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--output", str(output)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_profile_name_resolves_to_path_via_profiles_ini(tmp_path, monkeypatch):
    """--profile-name <name> must look up the matching profile in
    profiles.ini and use its path. This is the customer-facing happy path —
    end users don't know the hash-prefixed directory names."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        "Path=Profiles/xxx.default-release\n"
        "Default=1\n"
        "\n"
        "[Profile1]\n"
        "Name=vectara\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "vectara",
        "--output", str(output),
    ])
    assert rc == 0, "profile-name lookup must succeed when the name exists"
    state = json.loads(output.read_text())
    assert len(state["cookies"]) == 3


def test_profile_name_lookup_is_case_insensitive(tmp_path, monkeypatch):
    """End users may type the name with arbitrary casing. Firefox itself is
    case-sensitive about Name= but that's a footgun we should absorb."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.vectara"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=Vectara\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "VECTARA",       # different case
        "--output", str(output),
    ])
    assert rc == 0


def test_profile_name_unknown_lists_available_names_in_error(
    tmp_path, monkeypatch, caplog
):
    """If the user types a name that doesn't exist, the error must list the
    names that DO exist so they can fix the typo without leaving the shell."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        "Path=Profiles/xxx.default-release\n"
        "Default=1\n"
        "\n"
        "[Profile1]\n"
        "Name=work\n"
        "IsRelative=1\n"
        "Path=Profiles/yyy.work\n"
    )

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "nonexistent",
        "--output", str(output),
    ])
    assert rc != 0
    combined = "\n".join(r.message for r in caplog.records).lower()
    assert "default-release" in combined, \
        f"error must list available profile names; got: {combined}"
    assert "work" in combined


def test_profile_name_and_firefox_profile_are_mutually_exclusive(
    tmp_path, caplog
):
    """Two ways to point at a profile, but a single invocation must pick
    exactly one. Combining them is almost always a user mistake we should
    catch loudly instead of silently preferring one."""
    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "vectara",
        "--firefox-profile", str(tmp_path / "some_path"),
        "--output", str(output),
    ])
    assert rc != 0


def test_list_profiles_includes_orphaned_profile_dirs(
    tmp_path, monkeypatch, capsys
):
    """Firefox sometimes creates conflict-resolved profile dirs (e.g.
    'default-release-<timestamp>') and leaves them out of profiles.ini.
    These dirs still have valid cookies and users need to be able to target
    them, so --list-profiles must surface them too with an indicator.

    Regression coverage for the real-world case where a customer's actual
    Google sign-in landed in an orphaned dir invisible to about:profiles.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    profiles_subdir = ff_root / "Profiles"
    os.makedirs(profiles_subdir, exist_ok=True)
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        "Path=Profiles/registered.default-release\n"
        "Default=1\n"
    )
    # Registered profile (has cookies.sqlite to be realistic)
    _make_firefox_profile(
        str(profiles_subdir / "registered.default-release"), _google_cookies()
    )
    # Orphan profile dir, NOT in profiles.ini, also has cookies
    _make_firefox_profile(
        str(profiles_subdir / "lejyncb1.default-release-1702388672115"),
        _google_cookies(),
    )
    # Empty orphan dir — must NOT be surfaced (no cookies.sqlite)
    os.makedirs(str(profiles_subdir / "j0ukr4ra.empty"), exist_ok=True)

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--list-profiles"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "default-release" in out
    # The orphan must be listed — and clearly marked so the user knows
    # it isn't registered with Firefox itself.
    assert "lejyncb1.default-release-1702388672115" in out, \
        f"orphaned profile must appear in listing; got:\n{out}"
    assert "unregistered" in out.lower() or "orphan" in out.lower(), \
        f"orphaned profiles must be marked; got:\n{out}"
    # Empty orphan must not be listed (avoid noise)
    assert "j0ukr4ra" not in out


def test_list_profiles_prints_every_profile_from_profiles_ini(
    tmp_path, monkeypatch, capsys
):
    """--list-profiles should enumerate ALL profiles in profiles.ini, not
    only the default one, so the user can pick the right --firefox-profile
    path. Multi-profile users (work + personal, default + dev-edition) need
    this to disambiguate."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    (ff_root / "profiles.ini").write_text(
        "[Install4F96D1932A9F858E]\n"
        "Default=Profiles/aaa.default-release\n"
        "Locked=1\n"
        "\n"
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        "Path=Profiles/aaa.default-release\n"
        "Default=1\n"
        "\n"
        "[Profile1]\n"
        "Name=work\n"
        "IsRelative=1\n"
        "Path=Profiles/bbb.work\n"
    )
    # The dirs themselves don't need to exist for listing (the user might be
    # listing precisely because they're unsure which dir is real).

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--list-profiles"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "default-release" in out, f"missing default-release in output:\n{out}"
    assert "work" in out, f"missing work profile in output:\n{out}"
    # Default flag must be surfaced so the user knows which one auto-detect
    # would have picked.
    assert "yes" in out.lower() or "*" in out, \
        f"output should mark the default profile somehow:\n{out}"
    # Absolute paths in the output, not just relative — so the user can
    # copy-paste straight into --firefox-profile.
    assert str(ff_root) in out, \
        f"output should include the absolute Firefox root path:\n{out}"


def test_list_profiles_does_not_require_output_flag(tmp_path, monkeypatch):
    """--list-profiles is a pure read; --output is required by the importer
    in normal mode but should NOT be required when only listing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    # No Firefox install at all — listing still must not crash.
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--list-profiles"])
    assert rc == 0   # graceful no-op, not an error


def test_errors_when_explicit_profile_dir_does_not_exist(tmp_path, caplog):
    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--firefox-profile", str(tmp_path / "nope"),
        "--output", str(output),
    ])
    assert rc != 0
    assert not output.exists()


def test_errors_when_cookies_sqlite_missing(tmp_path):
    profile = tmp_path / "ff_profile"
    profile.mkdir()
    # No cookies.sqlite inside
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    assert rc != 0


def test_errors_when_no_google_cookies_found(tmp_path):
    """Customer ran the importer without first signing in — clear error,
    not a silent empty storage_state."""
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), _non_google_cookies())
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    assert rc != 0


def test_errors_when_autodetect_finds_no_firefox(tmp_path, monkeypatch):
    """No Firefox install in HOME — must error with a pointer to
    --firefox-profile, not silently produce an empty file."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--output", str(output)])
    assert rc != 0


# ---------------------------------------------------------------------------
# Robustness: locked DB (Firefox running) — importer copies before reading
# ---------------------------------------------------------------------------

def test_reads_cookies_written_to_wal_when_firefox_still_running(tmp_path):
    """Firefox keeps cookies.sqlite in WAL journal mode. While Firefox is
    open, fresh writes (the very cookies the customer just signed in to
    obtain) live in `cookies.sqlite-wal` until SQLite checkpoints them into
    the main DB on quit. The importer must copy the WAL (and -shm) alongside
    the main file or it'll see a stale, pre-sign-in view of the DB.

    This test sets up a WAL-mode DB, writes a cookie WITHOUT checkpointing,
    then asserts the importer still finds it. Regression coverage for the
    bug where customer ran the importer with Firefox open and got
    'No Google cookies found' even though they had just signed in.
    """
    profile = tmp_path / "ff_profile"
    profile.mkdir()
    db_path = str(profile / "cookies.sqlite")

    # Set up a Firefox-shaped DB in WAL mode.
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_MOZ_COOKIES_SCHEMA)
    conn.commit()
    conn.close()

    # Re-open and write a cookie. Hold the connection open without closing
    # so the write stays in the WAL (Firefox-still-running simulation).
    live_conn = sqlite3.connect(db_path)
    live_conn.execute("PRAGMA journal_mode=WAL")
    live_conn.execute(
        "INSERT INTO moz_cookies "
        "(name, value, host, path, expiry, isSecure, isHttpOnly, sameSite) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("SID", "wal-val", ".google.com", "/", 9999999999, 1, 1, 1),
    )
    live_conn.commit()

    try:
        # Sanity-check the test setup: the WAL file should exist and the
        # main DB on its own should NOT yet contain the new cookie.
        assert os.path.exists(db_path + "-wal"), \
            "test setup: expected a -wal file alongside cookies.sqlite"

        output = tmp_path / "state.json"
        from crawlers.auth import google_firefox_import
        rc = google_firefox_import.run([
            "--firefox-profile", str(profile),
            "--output", str(output),
        ])
        assert rc == 0, "importer should succeed and see the WAL write"

        state = json.loads(output.read_text())
        assert any(
            c["name"] == "SID" and c["value"] == "wal-val"
            for c in state["cookies"]
        ), (
            "importer missed a cookie that was in the WAL — it must copy "
            "cookies.sqlite-wal (and -shm) alongside the main DB"
        )
    finally:
        live_conn.close()


def test_no_google_cookies_diagnostic_reports_what_was_seen(tmp_path, caplog):
    """When zero Google cookies match, the error must surface enough detail
    to distinguish the three real-world causes apart:
      - wrong profile / wrong Firefox flavor (lots of non-Google hosts)
      - sign-in not completed (Google-like hosts seen but the right
        cookies aren't there yet)
      - empty DB / never signed in to anything (zero rows)
    Without this, we cannot debug a customer's 'no cookies found' failure
    without remote SSH access.
    """
    profile = tmp_path / "ff_profile"
    _make_firefox_profile(str(profile), _non_google_cookies())
    output = tmp_path / "state.json"

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])
    assert rc != 0

    combined = "\n".join(r.message for r in caplog.records).lower()
    # Diagnostic must mention the total cookie count we did see in the DB...
    assert "2" in combined, f"expected total cookie count in error; got: {combined}"
    # ...and the profile path we read, so the customer can sanity-check it.
    assert str(profile).lower() in combined


def test_profile_name_resolves_via_profile_groups_db_user_facing_name(
    tmp_path, monkeypatch
):
    """Firefox 138+ stores user-facing profile names ('vectara') in a separate
    SQLite at Profile Groups/<StoreID>.sqlite, NOT in profiles.ini (where
    Name= is the legacy internal label like 'default-release').

    Regression coverage: when a profile is named in Firefox's Profile
    Manager UI (e.g. 'vectara'), --profile-name was failing because the
    importer only knew about profiles.ini.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"      # legacy internal name
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=deadbeef\n"          # points at Profile Groups DB
        "Default=1\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())
    _make_profile_groups_db(ff_root, "deadbeef", [
        {"path": profile_relpath, "name": "vectara", "avatar": "heart"},
    ])

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "vectara",     # user-facing name from new DB
        "--output", str(output),
    ])
    assert rc == 0, "--profile-name should match user-facing name from Profile Groups DB"
    state = json.loads(output.read_text())
    assert len(state["cookies"]) == 3


def test_profile_name_resolves_via_legacy_name_when_db_also_present(
    tmp_path, monkeypatch
):
    """Back-compat: --profile-name <legacy Name= field> still works even when
    the new Profile Groups DB is present. Customers who learned the legacy
    name (e.g. 'default-release') from earlier docs or from poking around
    profiles.ini directly should not break."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=deadbeef\n"
        "Default=1\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())
    _make_profile_groups_db(ff_root, "deadbeef", [
        {"path": profile_relpath, "name": "vectara"},
    ])

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "default-release",   # legacy name from profiles.ini
        "--output", str(output),
    ])
    assert rc == 0
    state = json.loads(output.read_text())
    assert len(state["cookies"]) == 3


def test_profile_groups_db_missing_falls_back_to_legacy_name(
    tmp_path, monkeypatch
):
    """If profiles.ini lists a StoreID but the Profile Groups DB doesn't
    exist (e.g. freshly upgraded Firefox that hasn't migrated yet), the
    importer must NOT crash and must still resolve via legacy Name=."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=nonexistent\n"     # DB file doesn't exist
        "Default=1\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())
    # Deliberately do NOT create the Profile Groups DB.

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "default-release",
        "--output", str(output),
    ])
    assert rc == 0, "missing Profile Groups DB must not block legacy-name lookup"


def test_list_profiles_shows_user_facing_name_with_legacy_in_parens(
    tmp_path, monkeypatch, capsys
):
    """When user-facing name (from Profile Groups DB) differs from legacy
    Name= (from profiles.ini), the listing should show the user-facing name
    prominently and indicate the legacy name in parens so users following
    older docs can connect the two."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=deadbeef\n"
        "Default=1\n"
    )
    _make_firefox_profile(str(profile_dir), _google_cookies())
    _make_profile_groups_db(ff_root, "deadbeef", [
        {"path": profile_relpath, "name": "vectara"},
    ])

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--list-profiles"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "vectara" in out
    # Legacy name shown in parens so users can correlate with older docs / profiles.ini
    assert "default-release" in out
    assert "legacy" in out.lower(), \
        f"output should label the secondary name as 'legacy'; got:\n{out}"


def test_list_profiles_includes_db_only_entries_not_in_profiles_ini(
    tmp_path, monkeypatch, capsys
):
    """The Profile Groups DB sometimes tracks profiles that aren't in
    profiles.ini (Firefox's 'Original profile' on upgraded installs is the
    canonical example). These must appear in the listing — labeling them
    as 'orphan' would be misleading since Firefox itself tracks them."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    registered_relpath = "Profiles/abc123.work"
    db_only_relpath = "Profiles/xyz999.legacy-release"
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={registered_relpath}\n"
        "StoreID=deadbeef\n"
        "Default=1\n"
    )
    _make_firefox_profile(str(ff_root / registered_relpath), _google_cookies())
    _make_firefox_profile(str(ff_root / db_only_relpath), _google_cookies())
    _make_profile_groups_db(ff_root, "deadbeef", [
        {"path": registered_relpath, "name": "vectara"},
        {"path": db_only_relpath, "name": "Original profile"},
    ])

    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run(["--list-profiles"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "vectara" in out
    assert "Original profile" in out
    # Crucially: 'Original profile' is in the DB, so it must NOT be marked orphan.
    # The previous orphan-only listing was misleading.
    orig_line = next(l for l in out.splitlines() if "Original profile" in l)
    assert "orphan" not in orig_line.lower(), \
        f"DB-tracked profile must not be labeled orphan; got: {orig_line!r}"


def test_profile_name_unknown_error_lists_both_user_facing_and_legacy_names(
    tmp_path, monkeypatch, caplog
):
    """When --profile-name <wrong> fails, the error must list both kinds of
    names that ARE available, so users following either set of docs can fix
    the typo without leaving the shell."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    profile_relpath = "Profiles/abc123.work"
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=deadbeef\n"
        "Default=1\n"
    )
    _make_profile_groups_db(ff_root, "deadbeef", [
        {"path": profile_relpath, "name": "vectara"},
    ])

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    rc = google_firefox_import.run([
        "--profile-name", "nonexistent",
        "--output", str(output),
    ])
    assert rc != 0
    combined = "\n".join(r.message for r in caplog.records).lower()
    assert "vectara" in combined, \
        f"error must list user-facing names too; got: {combined}"
    assert "default-release" in combined, \
        f"error must list legacy names too; got: {combined}"


def test_profile_groups_db_wal_writes_are_read(tmp_path, monkeypatch):
    """The Profile Groups DB is in WAL mode just like cookies.sqlite. If
    Firefox is running, fresh profile renames live in the WAL until
    checkpoint. Importer must copy the WAL or it'll see a stale name."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    ff_root = tmp_path / "Library" / "Application Support" / "Firefox"
    os.makedirs(ff_root, exist_ok=True)
    pg_dir = ff_root / "Profile Groups"
    pg_dir.mkdir()
    db_path = str(pg_dir / "deadbeef.sqlite")

    # Set up WAL-mode DB with schema, but DON'T checkpoint.
    setup_conn = sqlite3.connect(db_path)
    setup_conn.execute("PRAGMA journal_mode=WAL")
    setup_conn.executescript(_PROFILE_GROUPS_SCHEMA)
    setup_conn.commit()
    setup_conn.close()

    profile_relpath = "Profiles/abc123.work"
    profile_dir = ff_root / profile_relpath
    _make_firefox_profile(str(profile_dir), _google_cookies())
    (ff_root / "profiles.ini").write_text(
        "[Profile0]\n"
        "Name=default-release\n"
        "IsRelative=1\n"
        f"Path={profile_relpath}\n"
        "StoreID=deadbeef\n"
        "Default=1\n"
    )

    # Write the row from a live connection without closing — simulates
    # Firefox still running, just-renamed-the-profile, WAL not flushed.
    live = sqlite3.connect(db_path)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute(
        "INSERT INTO Profiles (path, name, avatar, themeId, themeFg, themeBg) "
        "VALUES (?, ?, '', '', '', '')",
        (profile_relpath, "vectara"),
    )
    live.commit()

    try:
        assert os.path.exists(db_path + "-wal"), \
            "test setup: expected -wal file"

        output = tmp_path / "state.json"
        from crawlers.auth import google_firefox_import
        rc = google_firefox_import.run([
            "--profile-name", "vectara",
            "--output", str(output),
        ])
        assert rc == 0, "importer must see profile name written to WAL"
    finally:
        live.close()


def test_does_not_modify_original_cookies_sqlite(tmp_path):
    """If Firefox is open when we run, we mustn't write to the live DB.

    Use mtime + content-hash as a coarse witness: file unchanged after run.
    """
    import hashlib

    profile = tmp_path / "ff_profile"
    db_path = _make_firefox_profile(str(profile), _google_cookies())
    original_bytes = open(db_path, "rb").read()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    original_mtime = os.path.getmtime(db_path)

    output = tmp_path / "state.json"
    from crawlers.auth import google_firefox_import
    google_firefox_import.run([
        "--firefox-profile", str(profile),
        "--output", str(output),
    ])

    after_bytes = open(db_path, "rb").read()
    after_hash = hashlib.sha256(after_bytes).hexdigest()
    after_mtime = os.path.getmtime(db_path)

    assert after_hash == original_hash, "importer must not mutate cookies.sqlite"
    assert after_mtime == original_mtime
