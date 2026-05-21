"""Import Google session cookies from a real (non-Playwright) Firefox profile.

Bypass path for the case where:
  - The customer cannot install Chrome (so the default `google_bootstrap`
    `--browser chromium --channel chrome` flow is unavailable), AND
  - Cloudflare Turnstile (or similar fingerprinting in the SSO chain — e.g.
    Rippling) blocks Playwright's Firefox even with `dom.webdriver.enabled`
    disabled.

The customer signs in to https://sites.google.com in their normal Firefox
browser — no automation, no Playwright, nothing for Cloudflare to flag. This
script then reads the resulting cookies out of Firefox's `cookies.sqlite` and
writes them as a Playwright `storage_state.json` that the website crawler
consumes identically to one produced by `google_bootstrap`.

Usage:

    # Friendliest form — look up your Firefox profile by its name
    # (the Name= field in profiles.ini, visible in about:profiles):
    python -m crawlers.auth.google_firefox_import \\
        --profile-name "default-release" \\
        --output ./google_storage_state.json

    # Don't know the name? See every available profile (macOS / Linux / Windows):
    python -m crawlers.auth.google_firefox_import --list-profiles

    # Auto-detect the default profile (omit both --profile-name and --firefox-profile):
    python -m crawlers.auth.google_firefox_import --output ./google_storage_state.json

    # Or point at an explicit profile directory (e.g. for orphaned profiles
    # not registered in profiles.ini):
    python -m crawlers.auth.google_firefox_import \\
        --firefox-profile ~/Library/Application\\ Support/Firefox/Profiles/abc.default-release \\
        --output ./google_storage_state.json

Run AFTER signing in to sites.google.com in Firefox. Firefox can be left open
— we read a copy of cookies.sqlite so the live DB is not touched.
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile

# Firefox stores sameSite as an int; Playwright wants a string.
# Source: Mozilla's nsICookie.idl (SAMESITE_NONE/LAX/STRICT).
_SAMESITE_INT_TO_STR = {0: "None", 1: "Lax", 2: "Strict"}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m crawlers.auth.google_firefox_import",
        description=(
            "Import Google session cookies from a real Firefox profile and "
            "write them as a Playwright storage_state.json file."
        ),
    )
    p.add_argument(
        "--output",
        required=False,    # not required when --list-profiles is used
        help="Path to write the Playwright storage_state JSON file.",
    )
    p.add_argument(
        "--firefox-profile",
        default=None,
        help=(
            "Path to the Firefox profile directory (the one containing "
            "cookies.sqlite). If omitted, we try to auto-detect the default "
            "profile via Firefox's profiles.ini. Use --list-profiles to see "
            "every available profile and its absolute path. Mutually "
            "exclusive with --profile-name."
        ),
    )
    p.add_argument(
        "--profile-name",
        default=None,
        help=(
            "Firefox profile name (the Name= field in profiles.ini, e.g. "
            "'default-release' or whatever you named your profile in "
            "Firefox's Profile Manager). Case-insensitive. The script looks "
            "up the path automatically — friendlier than --firefox-profile "
            "for end users who don't know the hash-prefixed directory name. "
            "Use --list-profiles to see all available names. Mutually "
            "exclusive with --firefox-profile."
        ),
    )
    p.add_argument(
        "--list-profiles",
        action="store_true",
        help=(
            "List every Firefox profile defined in profiles.ini (with its "
            "name, default flag, and absolute path) and exit. Useful when "
            "multiple profiles exist and you need to pick the right one to "
            "pass to --firefox-profile."
        ),
    )
    return p.parse_args(argv)


def _firefox_root() -> str | None:
    """Return the OS-specific Firefox install root, or None if not applicable."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Firefox")
    if sys.platform.startswith("linux"):
        return os.path.join(home, ".mozilla", "firefox")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "Mozilla", "Firefox")
    return None


def _find_default_firefox_profile() -> str | None:
    """Auto-detect the default Firefox profile directory.

    Returns the absolute profile path, or None if no Firefox install /
    profiles.ini can be located.
    """
    root = _firefox_root()
    if root is None:
        return None
    ini_path = os.path.join(root, "profiles.ini")
    if not os.path.isfile(ini_path):
        return None

    parser = configparser.ConfigParser()
    parser.read(ini_path)

    # Firefox writes [InstallXXXXXX] sections with a Default= line pointing to
    # the per-install default profile. Prefer that if present.
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            relpath = parser.get(section, "Default")
            candidate = os.path.join(root, relpath)
            if os.path.isdir(candidate):
                return candidate

    # Fallback: scan [ProfileN] sections for Default=1.
    for section in parser.sections():
        if section.startswith("Profile") and parser.getboolean(
            section, "Default", fallback=False
        ):
            relpath = parser.get(section, "Path", fallback=None)
            if not relpath:
                continue
            is_relative = parser.getboolean(section, "IsRelative", fallback=True)
            candidate = os.path.join(root, relpath) if is_relative else relpath
            if os.path.isdir(candidate):
                return candidate

    return None


def _read_profile_groups_db(root: str, store_id: str) -> list[dict]:
    """Read Firefox 138+'s Profile Groups SQLite for user-facing names.

    Returns a list of {"relpath", "name", "avatar"} dicts pulled from the
    `Profiles` table. Empty list if the DB doesn't exist (older Firefox, or
    StoreID provisioned in profiles.ini but the DB not yet created).

    Same WAL-copy idiom as `_read_all_firefox_cookies`: Firefox is typically
    running and just-renamed profiles live in the WAL until checkpoint.
    """
    db_path = os.path.join(root, "Profile Groups", f"{store_id}.sqlite")
    if not os.path.isfile(db_path):
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = os.path.join(tmpdir, f"{store_id}.sqlite")
        shutil.copyfile(db_path, tmp_db)
        for suffix in ("-wal", "-shm"):
            sibling = db_path + suffix
            if os.path.isfile(sibling):
                shutil.copyfile(sibling, tmp_db + suffix)

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT path, name, avatar FROM Profiles"
            ).fetchall()
        except sqlite3.OperationalError:
            # Schema differs (older alpha of Selectable Profiles, or future
            # rename) — be conservative and treat as if DB wasn't there.
            rows = []
        conn.close()

    return [
        {"relpath": r["path"], "name": r["name"], "avatar": r["avatar"]}
        for r in rows
    ]


def _list_all_firefox_profiles() -> list[dict]:
    """Enumerate every Firefox profile, merging two sources of truth:

    1. **profiles.ini** — legacy, contains internal `Name=` (e.g.
       'default-release') + `Path=` + `StoreID=` + Default flags.
    2. **Profile Groups DB** (Firefox 138+, when StoreID is set) — contains
       the *user-facing* name shown in about:profiles / hamburger menu
       (e.g. 'vectara'), plus avatar and theme.

    Returns dicts with:
      - "name": user-facing name from the DB if present, else legacy Name=
      - "legacy_name": legacy Name= when it differs from "name", else None
      - "path": absolute profile dir
      - "default": True for the profile auto-detect would pick
      - "source": "profile_groups" | "profiles_ini"

    Returns [] if no Firefox install / profiles.ini can be located.
    """
    root = _firefox_root()
    if root is None:
        return []
    ini_path = os.path.join(root, "profiles.ini")
    if not os.path.isfile(ini_path):
        return []

    parser = configparser.ConfigParser()
    parser.read(ini_path)

    # The Install* section's Default= points at the per-install default
    # profile (this is what _find_default_firefox_profile prefers).
    install_default_path = None
    for section in parser.sections():
        if section.startswith("Install") and parser.has_option(section, "Default"):
            install_default_path = parser.get(section, "Default")
            break

    # First pass: collect distinct StoreIDs and read each Profile Groups DB
    # exactly once. Build relpath -> {name, avatar} lookup keyed by the
    # `Path=` value that both ini and DB use.
    store_ids: set[str] = set()
    for section in parser.sections():
        if section.startswith("Profile"):
            sid = parser.get(section, "StoreID", fallback=None)
            if sid:
                store_ids.add(sid)
    db_by_relpath: dict[str, dict] = {}
    for sid in store_ids:
        for row in _read_profile_groups_db(root, sid):
            db_by_relpath[row["relpath"]] = {**row, "store_id": sid}

    profiles: list[dict] = []
    seen_relpaths: set[str] = set()

    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        legacy_name = parser.get(section, "Name", fallback=section)
        relpath = parser.get(section, "Path", fallback=None)
        if not relpath:
            continue
        is_relative = parser.getboolean(section, "IsRelative", fallback=True)
        abs_path = os.path.join(root, relpath) if is_relative else relpath
        is_default = (
            relpath == install_default_path
            or parser.getboolean(section, "Default", fallback=False)
        )

        db_entry = db_by_relpath.get(relpath)
        if db_entry and db_entry["name"]:
            user_facing = db_entry["name"]
            # Only surface legacy_name when it adds information; if the DB
            # name and the ini name happen to coincide, no need to confuse
            # users with a redundant "(legacy: vectara)" tag.
            legacy = legacy_name if legacy_name != user_facing else None
            source = "profile_groups"
        else:
            user_facing = legacy_name
            legacy = None
            source = "profiles_ini"

        profiles.append({
            "name": user_facing,
            "legacy_name": legacy,
            "path": abs_path,
            "default": is_default,
            "source": source,
        })
        seen_relpaths.add(relpath)

    # Second pass: DB-tracked profiles that don't appear in profiles.ini
    # (Firefox's 'Original profile' on upgraded installs). Surface them too —
    # the DB is authoritative, so these aren't orphans.
    for relpath, db_entry in db_by_relpath.items():
        if relpath in seen_relpaths:
            continue
        abs_path = os.path.join(root, relpath)
        profiles.append({
            "name": db_entry["name"],
            "legacy_name": None,
            "path": abs_path,
            "default": False,        # DB-only profiles aren't ini-default
            "source": "profile_groups",
        })

    return profiles


def _find_orphaned_firefox_profiles() -> list[dict]:
    """Find profile dirs on disk that aren't registered in profiles.ini.

    Firefox auto-creates conflict-resolved profile dirs (e.g.
    `xxxx.default-release-<timestamp>`) and sometimes leaves them out of
    profiles.ini, where about:profiles can no longer see them. They still
    have valid cookies, so they need to be reachable via --firefox-profile.
    We only surface orphans that actually contain a cookies.sqlite to avoid
    listing empty/abandoned dirs.
    """
    root = _firefox_root()
    if root is None:
        return []
    profiles_subdir = os.path.join(root, "Profiles")
    if not os.path.isdir(profiles_subdir):
        return []

    registered_paths = {p["path"] for p in _list_all_firefox_profiles()}

    orphans: list[dict] = []
    for entry in sorted(os.listdir(profiles_subdir)):
        path = os.path.join(profiles_subdir, entry)
        if not os.path.isdir(path) or path in registered_paths:
            continue
        if not os.path.isfile(os.path.join(path, "cookies.sqlite")):
            continue
        orphans.append({
            "name": entry,           # no Name= field — show the dir basename
            "path": path,
            "default": False,
            "unregistered": True,
        })
    return orphans


def _find_firefox_profile_by_name(name: str) -> tuple[str | None, list[str]]:
    """Look up a Firefox profile by name (case-insensitive).

    Matches against BOTH the user-facing name (Profile Groups DB on Firefox
    138+) AND the legacy profiles.ini `Name=` field, so callers following
    either set of docs / either Firefox UI surface land on the same profile.

    Returns (path, available_names). `available_names` includes every name
    by which a profile could be addressed — user-facing AND legacy, with
    the legacy form annotated `name (legacy)` so a typo'd user can tell at
    a glance which kind they were aiming at.
    """
    profiles = _list_all_firefox_profiles()
    available: list[str] = []
    for p in profiles:
        available.append(p["name"])
        if p["legacy_name"]:
            available.append(f"{p['legacy_name']} (legacy)")

    needle = name.lower()
    matches = [
        p for p in profiles
        if p["name"].lower() == needle
        or (p["legacy_name"] and p["legacy_name"].lower() == needle)
    ]
    if len(matches) == 1:
        return matches[0]["path"], available
    return None, available


def _is_google_cookie(host: str) -> bool:
    """Match the same domain set GoogleAuthManager keeps at runtime.

    `host.endswith(".google.com")` covers `accounts.google.com`,
    `sites.google.com`, and the leading-dot form `.google.com`; the second
    clause catches the bare apex.
    """
    host = (host or "").lower()
    return host.endswith(".google.com") or host == "google.com"


def _read_all_firefox_cookies(profile_dir: str) -> list[dict]:
    """Return every cookie row in Firefox's cookies.sqlite, as a list of
    Playwright-format dicts. No domain filtering — caller does that.

    Firefox stores cookies.sqlite in SQLite WAL journal mode. While Firefox
    is running, fresh writes live in `cookies.sqlite-wal` until checkpointed
    into the main DB. SQLite finds the WAL by looking for a sibling file with
    the same base name, so we copy `cookies.sqlite`, `cookies.sqlite-wal`,
    and `cookies.sqlite-shm` together into a tempdir keeping identical base
    names; the WAL is then applied transparently when we open the copy.
    Copying (instead of opening the live DB) keeps us safe from locks and
    guarantees we never write to the customer's profile.
    """
    db_path = os.path.join(profile_dir, "cookies.sqlite")
    if not os.path.isfile(db_path):
        raise FileNotFoundError(
            f"No cookies.sqlite at {db_path}. Sign in to sites.google.com in "
            f"this Firefox profile first, then re-run."
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = os.path.join(tmpdir, "cookies.sqlite")
        shutil.copyfile(db_path, tmp_db)
        for suffix in ("-wal", "-shm"):
            sibling = db_path + suffix
            if os.path.isfile(sibling):
                shutil.copyfile(sibling, tmp_db + suffix)

        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, "
            "sameSite FROM moz_cookies"
        ).fetchall()
        conn.close()

    cookies = []
    for r in rows:
        same_site = _SAMESITE_INT_TO_STR.get(r["sameSite"] or 0, "None")
        secure = bool(r["isSecure"])
        # Chromium 80+ silently drops cookies with SameSite=None + Secure=false.
        # Firefox sometimes stores Google session cookies (notably SID/HSID/
        # APISID/SIDCC on multi-account profiles) with isSecure=0 even though
        # the original Set-Cookie from Google had the Secure attribute and the
        # cookies only ever flow over HTTPS. Promote so Chromium accepts them
        # — otherwise the primary auth cookies vanish on storage_state load
        # and Google falls back to the account chooser.
        if same_site == "None" and not secure:
            secure = True
        cookies.append({
            "name": r["name"],
            "value": r["value"],
            "domain": r["host"] or "",
            "path": r["path"] or "/",
            "expires": _expiry_to_playwright_seconds(r["expiry"]),
            "httpOnly": bool(r["isHttpOnly"]),
            "secure": secure,
            "sameSite": same_site,
        })
    return cookies


def _expiry_to_playwright_seconds(expiry) -> int:
    """Convert Firefox's moz_cookies.expiry value to Playwright's expected
    `expires` field (unix seconds, or -1 for a session cookie).

    Firefox 100+ (mid-2022 onward) stores cookie expiry in MILLISECONDS;
    older releases used seconds. They're trivially distinguishable by
    magnitude: any value > 10^11 cannot be seconds (that would be year
    5138). The two-format world will persist for years across mixed-version
    user installs, so detect and convert defensively rather than picking
    one and breaking the other.

    Special values:
      - 0 / None / negative -> -1 (Playwright's session-cookie marker;
        Firefox uses 0 for session cookies)
    """
    if not expiry or expiry <= 0:
        return -1
    if expiry > 10**11:        # too large to be seconds — must be milliseconds
        return int(expiry // 1000)
    return int(expiry)


def run(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)

    if args.list_profiles:
        registered = _list_all_firefox_profiles()
        orphans = _find_orphaned_firefox_profiles()
        all_profiles = registered + orphans
        if not all_profiles:
            root = _firefox_root() or "(no Firefox root for this OS)"
            print(f"No Firefox profiles found under {root}")
            return 0
        # Build display labels. Format: "<name> (legacy: <legacy_name>)"
        # when the user-facing name differs from the legacy ini name, and
        # "(orphan, unregistered)" for true filesystem orphans not tracked
        # in either source of truth.
        def _label(p: dict) -> str:
            suffix = ""
            if p.get("unregistered"):
                suffix = " (orphan, unregistered)"
            elif p.get("legacy_name"):
                suffix = f" (legacy: {p['legacy_name']})"
            return p["name"] + suffix

        labeled = [{**p, "_label": _label(p)} for p in all_profiles]
        name_w = max(len("NAME"), max(len(p["_label"]) for p in labeled))
        print(f"{'NAME':<{name_w}}  {'DEFAULT':<7}  PATH")
        for p in labeled:
            flag = "yes" if p["default"] else "no"
            print(f"{p['_label']:<{name_w}}  {flag:<7}  {p['path']}")
        return 0

    if args.firefox_profile and args.profile_name:
        logging.error(
            "--firefox-profile and --profile-name are mutually exclusive — "
            "pick one. (--profile-name looks up the path for you via "
            "profiles.ini; --firefox-profile takes an explicit path.)"
        )
        return 2

    if not args.output:
        logging.error("--output is required (or use --list-profiles to enumerate profiles).")
        return 2

    if args.firefox_profile:
        profile_dir = os.path.abspath(args.firefox_profile)
    elif args.profile_name:
        path, available = _find_firefox_profile_by_name(args.profile_name)
        if path is None:
            available_str = ", ".join(repr(n) for n in available) or "(none)"
            logging.error(
                f"No Firefox profile named {args.profile_name!r}.\n"
                f"  Available profile names: {available_str}\n"
                f"\n"
                f"The user-facing name is what shows in Firefox at "
                f"about:profiles (Firefox 138+ stores this separately from "
                f"profiles.ini, in the Profile Groups SQLite). The 'legacy' "
                f"suffix above marks the older profiles.ini Name= form; "
                f"either form works with --profile-name.\n"
                f"\n"
                f"Run with --list-profiles to see paths too, or pass "
                f"--firefox-profile <path> directly."
            )
            return 1
        profile_dir = path
        logging.info(
            f"Selected profile {args.profile_name!r} -> {profile_dir}"
        )
    else:
        detected = _find_default_firefox_profile()
        if detected is None:
            logging.error(
                "Could not auto-detect a Firefox profile. Pass "
                "--profile-name <name> (friendlier — looks up the path for "
                "you), or --firefox-profile <path> pointing at the directory "
                "that contains cookies.sqlite. Run --list-profiles to see "
                "what's available."
            )
            return 1
        profile_dir = detected
        logging.info(f"Auto-detected Firefox profile: {profile_dir}")

    if not os.path.isdir(profile_dir):
        logging.error(f"Firefox profile directory does not exist: {profile_dir}")
        return 1

    try:
        all_cookies = _read_all_firefox_cookies(profile_dir)
    except FileNotFoundError as e:
        logging.error(str(e))
        return 1

    cookies = [c for c in all_cookies if _is_google_cookie(c["domain"])]

    if not cookies:
        # Surface enough detail to distinguish the three real-world causes:
        #   (1) wrong profile / wrong Firefox flavor (many non-Google hosts)
        #   (2) sign-in not completed (Google-like hosts present but filter
        #       didn't match)
        #   (3) empty DB / never signed in (zero rows)
        all_hosts = sorted({(c["domain"] or "").lower() for c in all_cookies})
        google_like = [h for h in all_hosts if "google" in h]
        logging.error(
            "No Google cookies found.\n"
            f"  Profile read:           {profile_dir}\n"
            f"  Total cookies in DB:    {len(all_cookies)}\n"
            f"  Distinct hosts in DB:   {len(all_hosts)}\n"
            f"  Google-like hosts seen: {google_like if google_like else '(none)'}\n"
            "\n"
            "Possible causes:\n"
            "  - You signed in via a different Firefox profile or flavor\n"
            "    (Firefox Developer Edition / Nightly use separate profile\n"
            "    dirs). Pass --firefox-profile <path> explicitly.\n"
            "  - Firefox is open and the cookies were just-written but the\n"
            "    SQLite WAL hasn't been read (the importer normally handles\n"
            "    this — if you still see this, quit Firefox with Cmd+Q to\n"
            "    force a checkpoint and re-run).\n"
            "  - The SSO sign-in didn't complete. The redirect chain must end\n"
            "    on sites.google.com, not on accounts.google.com or the IdP."
        )
        return 1

    state = {"cookies": cookies, "origins": []}

    output_path = os.path.abspath(args.output)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(state, f, indent=2)

    logging.info(f"Wrote {len(cookies)} Google cookies to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
