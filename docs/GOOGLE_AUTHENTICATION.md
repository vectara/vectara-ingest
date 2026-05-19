# Google Authentication for Website Crawler

This document explains how to crawl private Google Sites (and other Google-protected
URLs) with `vectara-ingest`'s website crawler. It is the Google counterpart to
[`SAML_AUTHENTICATION.md`](./SAML_AUTHENTICATION.md) and is independent of it —
you can enable Google auth, SAML auth, both, or neither.

## When to use this

Reach for `google_auth` when an anonymous fetch of your start URL gets 302-redirected
to `https://accounts.google.com/ServiceLogin?...`. Typical cases:

- Private Google Sites at `https://sites.google.com/d/<id>/p/<page>/edit`
- Workspace-internal sites at `https://sites.google.com/<your-domain>/...`
- Drive-hosted content that needs a signed-in browser session

If your start URL is public but Google is rate-limiting / bot-checking, this is
not the right tool — set a User-Agent or back off instead.

## How it works (read this first)

A Google service-account OAuth bearer token is **not** accepted by
`sites.google.com` content URLs. Those URLs require browser session cookies — the
same ones a real browser gets after `accounts.google.com/ServiceLogin`. There is
no Google API that converts an SA token directly into those cookies.

The crawler bridges the gap with Playwright `storage_state`:

1. You run `crawlers/auth/google_bootstrap.py` once on a desktop machine. A real
   Chromium window opens; you sign in to Google (including 2FA / SSO / account
   chooser). When the browser lands on `sites.google.com`, the script writes the
   resulting cookies + localStorage to a JSON file.
2. You mount that JSON file into the crawler container at the path you set in
   `google_auth.storage_state_path`.
3. On each crawl, the crawler opens a headless Chromium with that state, captures
   the live `.google.com` cookies, and hands them to Scrapy / the indexer.

When the stored session expires (Workspace SSO usually expires sessions every few
weeks), the crawler fails fast with a message telling you to re-run the bootstrap.
There is no silent renewal.

## Auth modes

The `google_auth.mode` setting controls *which credential* the crawler binds to
for any API-style calls (Drive / Sites APIs). Both modes use the same Playwright
`storage_state` flow for `sites.google.com` content.

### `oauth_user` (recommended, no Workspace admin needed)

A regular Google account does a one-time OAuth consent. The resulting token JSON
file is the credential. Same shape used by `gdrive_crawler`'s
[`gdrive-oauth-setup.md`](./gdrive-oauth-setup.md).

Pick this when:
- You do not have Google Workspace admin access.
- The crawler runs as a specific person (e.g. you).

### `service_account` (Workspace orgs only)

A Workspace service account with domain-wide delegation impersonates
`delegated_user`. Workspace admin must grant DWD to the SA on the required
scopes.

Pick this when:
- You have Workspace admin and want crawls to run as a dedicated service identity.
- Multiple sites need to be crawled and you want predictable, shared credentials.

Even with `service_account`, you still need the one-time `storage_state` capture
(the SA itself cannot mint browser cookies — see "How it works" above).

## Configuration

### 1. YAML

```yaml
website_crawler:
  urls:
    - "https://sites.google.com/your-domain.com/internal-portal"
  crawl_method: "scrapy"           # "scrapy" or "internal" — both honor google_auth

  google_auth:
    mode: "oauth_user"             # or "service_account"
    delegated_user: "you@your-domain.com"   # required only for service_account
    scopes:                        # optional, sensible defaults applied
      - "openid"
      - "email"
      - "https://www.googleapis.com/auth/userinfo.profile"
    storage_state_path: "~/.config/vectara/google_storage_state.json"
```

Fields:

- `mode` (required): `"oauth_user"` or `"service_account"`.
- `delegated_user` (required for `service_account`): the Workspace user the SA
  impersonates.
- `scopes` (optional): OAuth scopes. Defaults to
  `["openid", "email", "https://www.googleapis.com/auth/userinfo.profile"]`.
- `storage_state_path` (required for any `sites.google.com` crawling): **host**
  path to the JSON file produced by `google_bootstrap.py`. When you launch via
  `run.sh`, this file is auto-mounted into the container at
  `/home/vectara/env/google_storage_state.json`; the crawler resolves to the
  container path automatically. When you run `python ingest.py` directly (no
  Docker), the file is read from this path on the local filesystem. The crawler
  will refuse to start `sites.google.com` crawls without this file present.

`crawl_method` choice: both `scrapy` and `internal` honor `google_auth`. The
captured session cookies are injected into the indexer's HTTP session and into
the Playwright `web_extractor` regardless of discovery method. Pick `scrapy`
for faster discovery on large sites; pick `internal` (the default) when you
want full Playwright-rendered fidelity end-to-end.

### 2. Secrets (optional)

`GOOGLE_CREDENTIALS_FILE` is only consumed when the crawler calls
`GoogleAuthManager.get_authenticated_session()` for Google API access (Drive,
Sites APIs). Plain `sites.google.com` page crawling does not call any Google
API and does not need this secret — `storage_state_path` is enough.

If you do want API access, add it to `secrets.toml`:

```toml
[default]
GOOGLE_CREDENTIALS_FILE = "/home/vectara/env/google_credentials.json"
```

`ingest.py` reads this value and stamps it onto `cfg.website_crawler.google_credentials_file`
at runtime — that is why the field is **not** placed inside the `google_auth:`
block in YAML.

`GOOGLE_CREDENTIALS_FILE` is:
- For `oauth_user`: the OAuth token JSON (with `token`, `refresh_token`, `token_uri`,
  `client_id`, `client_secret`, `scopes`). Same format as
  [`gdrive-oauth-setup.md`](./gdrive-oauth-setup.md) produces.
- For `service_account`: the SA key JSON downloaded from Google Cloud Console.

Note: this file is intentionally separate from `gdrive_crawler`'s hardcoded
`/home/vectara/env/credentials.json` — both can coexist with different SAs.

## One-time bootstrap

Run on a machine with a display (NOT in the Docker container):

```bash
pip install playwright
playwright install chromium

python -m crawlers.auth.google_bootstrap \
  --output ./google_storage_state.json
```

What you'll see:

1. A Chromium window opens to `https://sites.google.com`.
2. Sign in. Complete 2FA / SSO / account chooser as needed.
3. When the URL stabilizes on `sites.google.com` (and is no longer on
   `accounts.google.com`), the script writes `google_storage_state.json` and exits.

Then mount that file into your container at the path you set in
`google_auth.storage_state_path`.

Options:

- `--start-url <url>`: open a different starting URL (default `https://sites.google.com`).
- `--success-url-contains <substring>`: customise the success-detection check
  (default `sites.google.com`).
- `--timeout-seconds <n>`: how long to wait for sign-in (default 300).

## Setting up `oauth_user` credentials

Follow [`gdrive-oauth-setup.md`](./gdrive-oauth-setup.md) — the same OAuth client
and token JSON work for Google auth in the website crawler.

You need at minimum the `openid` and `email` scopes; the userinfo profile scope
is recommended. The `drive.readonly` scope is not required for `sites.google.com`
crawling.

## Setting up `service_account` credentials

In Google Cloud Console:

1. Create or select a Workspace-linked GCP project.
2. Create a service account; download its JSON key.
3. In Google Workspace Admin Console (admin.google.com), under
   **Security → Access and data control → API controls → Domain-wide delegation**,
   add the SA's client ID with the required scopes (`openid`, `email`, plus any
   API scopes you need).

The SA cannot crawl `sites.google.com` content on its own — you still need the
one-time `storage_state` capture as a Workspace user (typically the
`delegated_user`).

## Running a crawl

```bash
python ingest.py config/google-site-example.yaml default
```

Expected log lines:

```
Google authentication configured, capturing storage_state cookies...
Captured N Google session cookies.
Merged N Google session cookies into indexer session
Configured web extractor to inject authenticated cookies
```

If you instead see:

```
Stored Google session has expired (landed on https://accounts.google.com/...).
Re-run `python -m crawlers.auth.google_bootstrap --output ...`.
```

— re-run the bootstrap and re-mount the new file.

## Combining with SAML

The `google_auth` and `saml_auth` blocks are independent. If a single crawl
needs both (for example, a Workspace SSO domain that fronts internal apps with a
separate SAML flow), set both blocks. The crawler obtains cookies from each and
merges them before passing to Scrapy.

## Troubleshooting

- **`LinkSpider finished. Found 0 unique URLs.`** — anonymous fetches are
  bouncing off `accounts.google.com`. Check that `google_auth.storage_state_path`
  exists and is mounted into the container.
- **`Stored Google session has expired ...`** — re-run `google_bootstrap.py`.
  Workspace SSO typically forces re-auth every 2–4 weeks.
- **`google_auth requires 'credentials_file' in secrets ...`** — fires only
  when something asks for Google API credentials (e.g. a custom call to
  `GoogleAuthManager.get_authenticated_session()`). For plain `sites.google.com`
  crawling this error should never fire; if it does, you have third-party code
  calling the API path — set `GOOGLE_CREDENTIALS_FILE` in `secrets.toml`.
- **`google_auth mode 'service_account' requires 'delegated_user'`** — set the
  email of the Workspace user the SA should impersonate in YAML.
- **`Playwright is not available`** — install Playwright and download Chromium:
  `pip install playwright && playwright install chromium`.

## Limitations

- 2FA / SSO / BeyondCorp: handled by the one-time interactive bootstrap. The
  crawler itself runs headless.
- Session lifetime: tied to Google / Workspace policy. Plan to re-run the
  bootstrap when it expires; the crawler will tell you when.
- Cookie scope: only `.google.com` cookies are captured. The crawler will not
  inject Google session cookies into requests for unrelated domains.
