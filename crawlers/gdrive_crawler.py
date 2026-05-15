import io
import json
import logging
import mimetypes
import os
import re
import warnings
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import ray
from omegaconf import OmegaConf, ListConfig
from slugify import slugify

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from core.crawler import Crawler
from core.dataframe_parser import (
    DataframeParser,
    supported_by_dataframe_parser,
    process_dataframe_file,
)
from core.indexer import Indexer
from core.summary import TableSummarizer
from core.utils import setup_logging, safe_remove_file, get_docker_or_local_path

logger = logging.getLogger(__name__)

logging.getLogger('googleapiclient.http').setLevel(logging.ERROR)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_LABELS_SCOPE = "https://www.googleapis.com/auth/drive.labels.readonly"
SERVICE_ACCOUNT_FILE = '/home/vectara/env/credentials.json'

# Roles that grant read-or-above access to a file's content (all non-owner roles confer read).
READ_ROLES = frozenset({'reader', 'commenter', 'writer', 'fileOrganizer', 'organizer'})

# Drive API permission subfields we need for ACL metadata extraction.
_PERM_FIELDS = (
    'permissions(id,type,role,emailAddress,domain,deleted,displayName,permissionDetails)'
)

# Legacy crawl-time displayName gate, opt-in. When configured, files are
# indexed only if one of their permissions has a matching displayName. The
# default is unset (None) so every file the delegated user can read flows
# through; tenants that want ACL-style gating should configure ABAC instead.

# Values for the acl_source metadata field. Persisted in the corpus, so stable.
ACL_SOURCE_SHARED_DRIVE = 'shared_drive'
ACL_SOURCE_SHARED_DRIVE_PARTIAL = 'shared_drive_partial'
ACL_SOURCE_MY_DRIVE_DIRECT = 'my_drive_direct'
ACL_SOURCE_MY_DRIVE_RESOLVED = 'my_drive_resolved'
ACL_SOURCE_MY_DRIVE_PARTIAL = 'my_drive_partial'

FOLDER_MIME = 'application/vnd.google-apps.folder'
SHORTCUT_MIME = 'application/vnd.google-apps.shortcut'

_FOLDER_ID_PATTERN = re.compile(r'/folders/([a-zA-Z0-9_-]+)')


def extract_folder_id(value: Optional[str]) -> Optional[str]:
    """Return the Drive folder id from a URL like
    `https://drive.google.com/drive/folders/<id>` (query/hash tolerated),
    or pass a bare id through unchanged. Returns the input for falsy values.
    """
    if not value:
        return value
    m = _FOLDER_ID_PATTERN.search(value)
    return m.group(1) if m else value.strip()


def resolve_root_folders(value: Any) -> List[str]:
    """Normalize `gdrive_crawler.root_folder` into a list of folder ids.

    Accepts either a single string (URL or bare id) or a list of strings,
    so a single config key can scope the crawl to one folder, a Shared Drive
    id, or any combination. Misconfigured scalars (int, dict, etc.) raise
    TypeError — the same loud-fail pattern as the displayName gate; an
    empty crawl is harder to debug than a startup exception.
    """
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, str):
        items: List[Any] = [value]
    elif isinstance(value, (list, tuple, ListConfig)):
        # OmegaConf wraps YAML lists as ListConfig, not list. Without it here
        # a multi-root YAML config crashes the crawler at __init__.
        items = list(value)
    else:
        raise TypeError(
            "gdrive_crawler.root_folder must be a string or list of strings, "
            f"got {type(value).__name__}"
        )

    seen: Set[str] = set()
    out: List[str] = []
    for item in items:
        if not isinstance(item, str):
            raise TypeError(
                "gdrive_crawler.root_folder list entries must be strings, "
                f"got {type(item).__name__}"
            )
        fid = extract_folder_id(item)
        if fid and fid not in seen:
            seen.add(fid)
            out.append(fid)
    return out


def build_scopes(abac_cfg: Optional[Any] = None) -> List[str]:
    """Return the OAuth scopes required given the ABAC configuration.

    Adds the Drive Labels scope only when ABAC is enabled AND label fetching is
    enabled, so a stale `fetch_labels: true` left in config doesn't force an
    extra OAuth consent that no code path actually uses. Group membership is
    intentionally not resolved here — the query layer is expected to enumerate
    the requesting user's groups (transitively) and filter against `acl_groups`
    directly.
    """
    scopes = [DRIVE_READONLY_SCOPE]
    if abac_cfg is not None and abac_cfg.get('enabled', False):
        if abac_cfg.get('fetch_labels', False):
            scopes.append(DRIVE_LABELS_SCOPE)
    return scopes


# Shared cache to keep track of files that have already been crawled
class SharedCache:
    def __init__(self):
        self.cache = set()

    def add(self, id: str):
        self.cache.add(id)

    def contains(self, id: str) -> bool:
        return id in self.cache

def get_credentials(delegated_user: str, config_path: str,
                    scopes: Optional[List[str]] = None) -> service_account.Credentials:
    """Get service account credentials with domain-wide delegation."""
    credentials_file = get_docker_or_local_path(
        docker_path=SERVICE_ACCOUNT_FILE,
        config_path=config_path
    )
    effective_scopes = scopes or [DRIVE_READONLY_SCOPE]
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=effective_scopes)
    delegated_credentials = credentials.with_subject(delegated_user)
    return delegated_credentials

def get_oauth_credentials(credentials_file: str,
                          scopes: Optional[List[str]] = None) -> Credentials:
    """
    Get OAuth 2.0 credentials from token JSON file.

    Args:
        credentials_file: Path to the OAuth token JSON file
        scopes: OAuth scopes to request. Defaults to drive.readonly only.

    Returns:
        OAuth credentials object
    """
    effective_scopes = scopes or [DRIVE_READONLY_SCOPE]
    try:
        # Read the token file
        with open(credentials_file, 'r') as f:
            token_data = json.load(f)

        # Create credentials from the token data
        creds = Credentials.from_authorized_user_info(token_data, effective_scopes)

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Refreshed OAuth token")

                # Save the refreshed token back to the file
                refreshed_token_data = {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes
                }
                with open(credentials_file, 'w') as f:
                    json.dump(refreshed_token_data, f, indent=2)
                logger.info(f"Saved refreshed token to {credentials_file}")
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                raise

        return creds
    except FileNotFoundError:
        logger.error(f"OAuth credentials file not found: {credentials_file}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid OAuth token JSON in {credentials_file}: {e}")
        raise ValueError(f"Invalid OAuth token format in credentials file: {e}")
    except Exception as e:
        logger.error(f"Error creating OAuth credentials: {e}")
        raise

def get_gdrive_url(file_id: str, mime_type: str = '') -> str:
    if mime_type == 'application/vnd.google-apps.document':
        url = f'https://docs.google.com/document/d/{file_id}/view'
    elif mime_type == 'application/vnd.google-apps.spreadsheet':
        url = f'https://docs.google.com/spreadsheets/d/{file_id}/view'
    elif mime_type == 'application/vnd.google-apps.presentation':
        url = f'https://docs.google.com/presentation/d/{file_id}/view'
    else:
        url = f'https://drive.google.com/file/d/{file_id}/view'
    return url


def extract_acl_metadata(
    file_obj: Dict[str, Any],
    parent_permissions: Optional[List[Dict[str, Any]]] = None,
    labels: Optional[List[str]] = None,
    include_anyone: bool = True,
    source: str = ACL_SOURCE_MY_DRIVE_DIRECT,
) -> Dict[str, Any]:
    """Extract ABAC metadata from a Drive file permission set.

    Merges direct permissions with optional inherited permissions from parent
    folders (deduped by permission id), filters out deleted grants, buckets the
    survivors by grantee type and role, and appends any label strings. Group
    grants are recorded in `acl_groups`; resolution to individual members is
    intentionally deferred to the query layer (which knows the requesting
    user's live group membership). `source` becomes `acl_source` verbatim;
    callers can derive completeness from it (`shared_drive` and
    `my_drive_resolved` reflect a full ACL; `my_drive_direct` and
    `my_drive_partial` may be missing inherited grants).
    """
    owners: Set[str] = set()
    readers: Set[str] = set()
    groups: Set[str] = set()
    domains: Set[str] = set()
    is_public = False

    direct = list(file_obj.get('permissions') or [])
    combined = list(direct)
    seen_ids: Set[str] = {p['id'] for p in direct if p.get('id')}
    for p in (parent_permissions or []):
        pid = p.get('id')
        if pid and pid in seen_ids:
            continue
        if pid:
            seen_ids.add(pid)
        combined.append(p)

    for p in combined:
        if p.get('deleted'):
            continue
        ptype = p.get('type')
        role = p.get('role')
        email = (p.get('emailAddress') or '').lower() or None
        domain = (p.get('domain') or '').lower() or None

        if ptype == 'user' and email:
            if role == 'owner':
                owners.add(email)
            elif role in READ_ROLES:
                readers.add(email)
        elif ptype == 'group' and email:
            groups.add(email)
        elif ptype == 'domain':
            if domain:
                domains.add(domain)
        elif ptype == 'anyone':
            if include_anyone:
                is_public = True

    return {
        'acl_owners': sorted(owners),
        'acl_readers': sorted(readers),
        'acl_groups': sorted(groups),
        'acl_domains': sorted(domains),
        'acl_is_public': bool(is_public),
        'acl_is_org_wide': bool(domains),
        'acl_labels': list(labels or []),
        'acl_source': source,
    }


# Buckets reported in the per-user filter summary. Order is the order files
# traverse the pipeline; keeping it stable makes log diffs across runs easy
# to compare. `listed` is files returned by Drive (post-server-query); each
# subsequent bucket is a drop reason; `indexed` is the terminal success.
FILTER_STAGES = (
    'listed',
    'display_name_dropped',
    'cache_skipped',
    'mime_dropped',
    'unsupported_ext_dropped',
    'download_failed',
    'index_error',
    'indexed',
)


class UserWorker(object):
    def __init__(
            self,
            cfg: dict,
            indexer: Indexer, crawler: Crawler,
            shared_cache: SharedCache,
            date_threshold: datetime,
            permission_display_filter: Optional[List[str]] = None,
            use_ray: bool = False) -> None:
        # Convert cfg back to OmegaConf if it's a dict (from Ray serialization)
        if isinstance(cfg, dict):
            self.cfg = OmegaConf.create(cfg)
        else:
            self.cfg = cfg
        self.crawler = crawler
        self.indexer = indexer
        self.creds = None
        self.service = None
        self.access_token = None
        self.shared_cache = shared_cache
        self.date_threshold = date_threshold
        self.permission_display_filter = permission_display_filter
        self.use_ray = use_ray

        self.abac = self.cfg.gdrive_crawler.get('abac', {}) if hasattr(self.cfg, 'gdrive_crawler') else {}

        # Hoist config flags out of the per-file hot path.
        self._abac_enabled = self.abac.get('enabled', False)
        self._abac_resolve_inherited = self.abac.get('resolve_inherited', False)
        self._abac_include_anyone = self.abac.get('include_anyone', True)
        self._abac_fetch_labels = self.abac.get('fetch_labels', False)

        # Optional: restrict the crawl to one or more subtrees. Accepts either
        # a single Drive folder URL/id (legacy form) or a list of them, so a
        # config can mix a My-Drive folder with a Shared Drive id without
        # needing a second config key. Empty/unset means "sweep everything
        # the delegated user can see," as before.
        root_folder_raw = (
            self.cfg.gdrive_crawler.get('root_folder', None)
            if hasattr(self.cfg, 'gdrive_crawler') else None
        )
        self._root_folder_ids = resolve_root_folders(root_folder_raw)

        # Caches populated during a worker's lifetime
        self._folder_acl_cache: Dict[str, Tuple[List[Dict[str, Any]], List[str]]] = {}
        # Per-Shared-Drive cache of (drive-level permissions, acl_source).
        # The source is cached too so a failed permissions.list (e.g. 403 when
        # the delegated user lacks fileOrganizer on the drive) doesn't get
        # retried once per file in that drive.
        self._drive_perms_cache: Dict[str, Tuple[List[Dict[str, Any]], str]] = {}
        self._label_defs: Optional[Dict[str, Dict[str, Any]]] = None

        # Per-user filter pipeline counters. Reset at the start of process();
        # incremented by _record_drop()/_record_indexed() as files traverse the
        # gates documented in CRAWLERS.md. A summary is logged when process()
        # returns so operators can see how many files were dropped at each
        # stage (most opaque drop today is the display-name gate).
        self._stats: Dict[str, int] = {k: 0 for k in FILTER_STAGES}

        # Standalone images are routed through the indexer's ImageFileParser,
        # but only when a vision-capable summarizer is enabled. Gating on this
        # flag avoids downloading images we'd have to drop at index time.
        doc_processing = self.cfg.get('doc_processing', {}) if hasattr(self.cfg, 'get') else {}
        self._summarize_images = bool(doc_processing.get('summarize_images', False))

        # Shared DataframeParser for routing .csv/.xls/.xlsx (and native Google
        # Sheets exported as .xlsx). Matches the pattern in box/sharepoint/folder.
        model_config = doc_processing.get('model_config', {})
        self.df_parser = DataframeParser(
            self.cfg,
            self.cfg.get('dataframe_processing', {}),
            self.indexer,
            TableSummarizer(self.cfg, model_config.get('text')),
        )

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def _passes_display_filter(self, permissions: List[Dict[str, Any]]) -> bool:
        """Legacy crawl-time gate: only index files whose permission displayName matches the filter."""
        if not self.permission_display_filter:
            return True
        allow = set(self.permission_display_filter)
        return any(p.get('displayName') in allow for p in permissions)

    def _record_drop(self, bucket: str, file_obj: Dict[str, Any], reason: str) -> None:
        """Increment a drop counter and emit an INFO line so the operator can
        see exactly which file was filtered and why. Cheap enough to do for
        every drop — Drive crawls are network-bound, not log-bound.
        """
        if bucket not in self._stats:
            raise KeyError(f"unknown filter bucket: {bucket}")
        self._stats[bucket] += 1
        logger.info(
            f"gdrive filter drop [{bucket}] file='{file_obj.get('name', '?')}' "
            f"id={file_obj.get('id', '?')} mime={file_obj.get('mimeType', '?')} :: {reason}"
        )

    def _record_indexed(
        self,
        file_obj: Dict[str, Any],
        file_metadata: Optional[Dict[str, Any]] = None,
        parent_permissions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._stats['indexed'] += 1
        # Per-file success line is gated behind verbose: on large corpora the
        # summary counter is the signal operators want, and one INFO per
        # indexed file dominates log volume on healthy runs.
        if not self.crawler.verbose:
            return

        line = (
            f"gdrive indexed file='{file_obj.get('name', '?')}' "
            f"id={file_obj.get('id', '?')}"
        )
        # Raw permissions are logged independent of ABAC so operators can debug
        # acl_* derivation (or just inspect what Drive returned) even with ABAC
        # off. parent_permissions is appended only when non-empty to keep the
        # line tight for Shared Drive files and non-resolve_inherited runs.
        line += f" permissions={file_obj.get('permissions', [])!r}"
        if parent_permissions:
            line += f" parent_permissions={parent_permissions!r}"
        # When ABAC is on, append the resolved acl_* values so operators can
        # confirm per-file what the indexer actually shipped to the corpus
        # (inheritance source, public/org-wide flags, group/domain grants,
        # labels). Order is stable for grep-ability.
        if self._abac_enabled and file_metadata is not None:
            acl_keys = (
                'acl_source',
                'acl_is_public',
                'acl_is_org_wide',
                'acl_owners',
                'acl_readers',
                'acl_groups',
                'acl_domains',
                'acl_labels',
            )
            line += ' ' + ' '.join(
                f"{k}={file_metadata[k]!r}" for k in acl_keys if k in file_metadata
            )
        logger.info(line)

    def _log_filter_summary(self, user: str) -> None:
        parts = ' '.join(f"{k}={self._stats[k]}" for k in FILTER_STAGES)
        logger.info(f"gdrive filter summary for user={user} :: {parts}")

    def list_files(self, service: Resource, date_threshold: Optional[str] = None) -> List[dict]:
        results = []
        page_token = None
        query = f"((('root' in parents) or sharedWithMe or ('me' in owners) or ('me' in writers) or ('me' in readers)) and trashed=false and modifiedTime > '{date_threshold}')"

        fields = (
            'nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, '
            'owners, size, parents, driveId, ' + _PERM_FIELDS + ')'
        )

        while True:
            try:
                params = {
                    'fields': fields,
                    'q': query,
                    'corpora': 'allDrives',
                    'includeItemsFromAllDrives': True,
                    'supportsAllDrives': True
                }
                if page_token:
                    params['pageToken'] = page_token
                response = service.files().list(**params).execute()
                files = response.get('files', [])

                for file in files:
                    self._stats['listed'] += 1
                    if self._passes_display_filter(file.get('permissions', [])):
                        results.append(file)
                    else:
                        self._record_drop(
                            'display_name_dropped',
                            file,
                            f"no permission displayName matched {self.permission_display_filter}",
                        )
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            except Exception as error:
                logger.warning(f"An HTTP error occurred: {error}")
                break
        return results

    def _list_subtree(self, service: Resource, root_folder_id: str,
                      date_threshold: str) -> List[dict]:
        """BFS the folder subtree rooted at `root_folder_id`.

        Descends into every subfolder regardless of its modifiedTime (old
        folders may still contain recently-modified files), but filters leaf
        files server-side by `modifiedTime`. Shortcuts are not followed, so
        the crawl stays strictly inside the chosen subtree. Folder ids are
        tracked to avoid cycles from pathological parent/child loops.
        """
        results: List[dict] = []
        fields = (
            'nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, '
            'owners, size, parents, driveId, ' + _PERM_FIELDS + ')'
        )

        seen: Set[str] = set()
        frontier: List[str] = [root_folder_id]

        while frontier:
            next_frontier: List[str] = []
            for current in frontier:
                if current in seen:
                    continue
                seen.add(current)

                query = (
                    f"'{current}' in parents and trashed=false and "
                    f"(mimeType='{FOLDER_MIME}' or modifiedTime > '{date_threshold}')"
                )
                page_token: Optional[str] = None
                while True:
                    try:
                        params = {
                            'fields': fields,
                            'q': query,
                            'corpora': 'allDrives',
                            'includeItemsFromAllDrives': True,
                            'supportsAllDrives': True,
                        }
                        if page_token:
                            params['pageToken'] = page_token
                        response = service.files().list(**params).execute()
                        children = response.get('files', []) or []

                        for f in children:
                            mime = f.get('mimeType')
                            if mime == FOLDER_MIME:
                                fid = f.get('id')
                                if fid and fid not in seen:
                                    next_frontier.append(fid)
                            elif mime == SHORTCUT_MIME:
                                continue
                            else:
                                self._stats['listed'] += 1
                                if self._passes_display_filter(f.get('permissions', [])):
                                    results.append(f)
                                else:
                                    self._record_drop(
                                        'display_name_dropped',
                                        f,
                                        f"no permission displayName matched {self.permission_display_filter}",
                                    )

                        page_token = response.get('nextPageToken')
                        if not page_token:
                            break
                    except Exception as error:
                        logger.warning(
                            f"Error listing children of folder {current}: {error}"
                        )
                        break

            frontier = next_frontier
        return results

    def _collect_listable_files(self, date_threshold_str: str) -> List[dict]:
        """Initial listing dispatch.

        With no `root_folder` configured, fall back to the user-wide
        list_files() sweep. With one or more configured, walk each subtree
        and union the results, deduping by file id so a document that lives
        under two configured roots (e.g. via shortcut) is indexed only once.
        """
        if not self._root_folder_ids:
            return self.list_files(self.service, date_threshold=date_threshold_str)

        seen: Set[str] = set()
        out: List[dict] = []
        for root_id in self._root_folder_ids:
            logger.info(f"Restricting crawl to folder subtree: {root_id}")
            for f in self._list_subtree(self.service, root_id, date_threshold_str):
                fid = f.get('id')
                if fid and fid not in seen:
                    seen.add(fid)
                    out.append(f)
        return out

    def _fetch_drive_permissions(self, drive_id: str) -> Tuple[List[Dict[str, Any]], str]:
        """Return (members, source) for a Shared Drive, with per-worker caching.

        Drive's `files.list` does not propagate drive-level member grants onto
        a file's `permissions` array — so a Shared Drive file whose access is
        purely inherited from the drive comes back from list() with
        `permissions=[]`, which downstream renders as an empty acl_*. To
        recover the true ACL we fetch `permissions.list(fileId=<driveId>)`
        once per drive and let the caller merge those grants in.

        Caveat: enumerating a Shared Drive's full member list requires the
        delegated user to have at least the `fileOrganizer` role on that
        drive. Lower roles get a 403; we mark the source as
        `shared_drive_partial` and cache that outcome so we don't hammer
        Drive once per file. Sub-folder-level overrides within the drive
        are out of scope here — they would need an ancestor walk like the
        My Drive path, which is the existing `_folder_acl_cache` flow.
        """
        cached = self._drive_perms_cache.get(drive_id)
        if cached is not None:
            return cached

        fields = (
            'nextPageToken,' + _PERM_FIELDS
        )
        collected: List[Dict[str, Any]] = []
        source = ACL_SOURCE_SHARED_DRIVE
        page_token: Optional[str] = None
        while True:
            params = {
                'fileId': drive_id,
                'supportsAllDrives': True,
                'fields': fields,
            }
            if page_token:
                params['pageToken'] = page_token
            try:
                resp = self.service.permissions().list(**params).execute()
            except HttpError as e:
                logger.info(f"permissions.list failed for shared drive {drive_id}: {e}")
                collected = []
                source = ACL_SOURCE_SHARED_DRIVE_PARTIAL
                break
            except Exception as e:
                logger.info(f"Error listing permissions for shared drive {drive_id}: {e}")
                collected = []
                source = ACL_SOURCE_SHARED_DRIVE_PARTIAL
                break

            for p in (resp.get('permissions') or []):
                collected.append(p)
            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        self._drive_perms_cache[drive_id] = (collected, source)
        return collected, source

    def _resolve_parent_acl(self, file_obj: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
        """Resolve inherited permissions for a file.

        For Shared Drive files: fetch the drive's member list (cached per
        worker per drive). For My Drive files with `resolve_inherited=True`:
        walk ancestor folders and union their ACLs.

        Returns (union of inherited permissions, source discriminator).
        """
        drive_id = file_obj.get('driveId')
        if drive_id:
            return self._fetch_drive_permissions(drive_id)

        if not self._abac_resolve_inherited:
            return [], ACL_SOURCE_MY_DRIVE_DIRECT

        parents = file_obj.get('parents') or []
        if not parents:
            return [], ACL_SOURCE_MY_DRIVE_RESOLVED

        collected: Dict[str, Dict[str, Any]] = {}
        seen: Set[str] = set()
        partial = False
        frontier = list(parents)

        while frontier:
            next_frontier: List[str] = []
            for folder_id in frontier:
                if folder_id in seen:
                    continue
                seen.add(folder_id)

                if folder_id in self._folder_acl_cache:
                    perms, fparents = self._folder_acl_cache[folder_id]
                else:
                    try:
                        resp = self.service.files().get(
                            fileId=folder_id,
                            fields='id,parents,' + _PERM_FIELDS,
                            supportsAllDrives=True,
                        ).execute()
                    except HttpError as e:
                        logger.info(f"Skipping ancestor folder {folder_id}: {e}")
                        partial = True
                        continue
                    except Exception as e:
                        logger.info(f"Error reading ancestor folder {folder_id}: {e}")
                        partial = True
                        continue
                    perms = resp.get('permissions', []) or []
                    fparents = resp.get('parents', []) or []
                    self._folder_acl_cache[folder_id] = (perms, fparents)

                for p in perms:
                    pid = p.get('id')
                    if pid and pid not in collected:
                        collected[pid] = p

                next_frontier.extend(fparents)

            frontier = next_frontier

        source = ACL_SOURCE_MY_DRIVE_PARTIAL if partial else ACL_SOURCE_MY_DRIVE_RESOLVED
        return list(collected.values()), source

    def _load_label_defs(self) -> Dict[str, Dict[str, Any]]:
        """Fetch and cache Drive Labels definitions keyed by labelId."""
        if self._label_defs is not None:
            return self._label_defs

        defs: Dict[str, Dict[str, Any]] = {}
        try:
            labels_service = build(
                'drivelabels', 'v2', credentials=self.creds, cache_discovery=False
            )
            page_token: Optional[str] = None
            while True:
                params = {'view': 'LABEL_VIEW_FULL'}
                if page_token:
                    params['pageToken'] = page_token
                resp = labels_service.labels().list(**params).execute()
                for lbl in resp.get('labels', []) or []:
                    label_id = lbl.get('id')
                    if not label_id:
                        continue
                    props = lbl.get('properties') or {}
                    title = props.get('title') or label_id
                    fields: Dict[str, Dict[str, Any]] = {}
                    for f in lbl.get('fields', []) or []:
                        fid = f.get('id')
                        if not fid:
                            continue
                        fprops = f.get('properties') or {}
                        f_title = fprops.get('displayName') or fid
                        choices: Dict[str, str] = {}
                        sel = f.get('selectionOptions') or {}
                        for c in sel.get('choices', []) or []:
                            cid = c.get('id')
                            cprops = c.get('properties') or {}
                            c_title = cprops.get('displayName') or cid
                            if cid:
                                choices[cid] = c_title
                        fields[fid] = {'title': f_title, 'choices': choices}
                    defs[label_id] = {'title': title, 'fields': fields}
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except Exception as e:
            logger.warning(f"Failed to load Drive Labels definitions: {e}")

        self._label_defs = defs
        return defs

    def _fetch_labels(self, file_id: str) -> List[str]:
        """Return human-readable label strings for a file as '<Label>=<Value>'."""
        out: List[str] = []
        defs = self._load_label_defs()
        try:
            resp = self.service.files().listLabels(fileId=file_id).execute()
        except HttpError as e:
            logger.info(f"listLabels failed for {file_id}: {e}")
            return out
        except Exception as e:
            logger.info(f"listLabels error for {file_id}: {e}")
            return out

        for lbl in resp.get('labels', []) or []:
            label_id = lbl.get('id')
            ldef = defs.get(label_id, {}) if label_id else {}
            label_title = ldef.get('title') or label_id or ''
            fields = lbl.get('fields') or {}
            if not fields:
                if label_title:
                    out.append(str(label_title))
                continue
            for fid, fdata in fields.items():
                fdef = (ldef.get('fields') or {}).get(fid, {})
                choices = fdef.get('choices') or {}
                values: List[str] = []
                if 'selection' in fdata:
                    for cid in fdata.get('selection') or []:
                        values.append(choices.get(cid, cid))
                elif 'text' in fdata:
                    values.append(str(fdata.get('text', '')))
                elif 'integer' in fdata:
                    values.append(str(fdata.get('integer', '')))
                elif 'dateString' in fdata:
                    values.append(str(fdata.get('dateString', '')))
                elif 'user' in fdata:
                    for u in fdata.get('user') or []:
                        ue = u.get('emailAddress') if isinstance(u, dict) else u
                        if ue:
                            values.append(str(ue))
                for v in values:
                    if v:
                        out.append(f"{label_title}={v}")
        return out

    def download_or_export_file(self, file_id: str, mime_type: Optional[str] = None) -> Tuple[Optional[io.BytesIO], Optional[str]]:
        try:
            if mime_type:
                request = self.service.files().export_media(fileId=file_id, mimeType=mime_type)
            else:
                request = self.service.files().get_media(fileId=file_id)

            byte_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(byte_stream, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            byte_stream.seek(0)
            return byte_stream, None

        except HttpError as error:
            if error.resp.status == 403 and \
               any(e.get('reason') == 'exportSizeLimitExceeded' or e.get('reason') == 'fileNotDownloadable' for e in error.error_details):
                get_url = f'https://www.googleapis.com/drive/v3/files/{file_id}?fields=exportLinks'
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Accept': 'application/json',
                }
                response = requests.get(get_url, headers=headers)
                if response.status_code == 200:
                    export_links = response.json().get('exportLinks', {})
                    pdf_link = export_links.get('application/pdf')
                    if pdf_link:
                        pdf_response = requests.get(pdf_link, headers=headers)
                        if pdf_response.status_code == 200:
                            logger.info(f"Downloaded file {file_id} via link (as pdf)")
                            return io.BytesIO(pdf_response.content), None
                        else:
                            reason = f"export link returned HTTP {pdf_response.status_code}"
                            logger.error(f"An error occurred loading via link: {pdf_response.status_code}")
                            return None, reason
                    return None, "no application/pdf export link available"
                return None, f"exportLinks lookup returned HTTP {response.status_code}"
            reason = f"HttpError {error.resp.status}: {error}"
            logger.error(f"An error occurred downloading file: {error}")
            return None, reason

    def save_local_file(
        self, file_id: str, name: str, mime_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Download a Drive file to /tmp. Returns (local_path, error_reason);
        on success error_reason is None, on failure local_path is None and
        error_reason names the failing stage so callers can surface it."""
        path, extension = os.path.splitext(name)
        sanitized_name = f"{slugify(path)}{extension}"
        file_path = os.path.join("/tmp", sanitized_name)
        try:
            byte_stream, download_reason = self.download_or_export_file(file_id, mime_type)
            if byte_stream is None:
                return None, download_reason or "download_or_export_file returned no bytes"
            with open(file_path, 'wb') as f:
                f.write(byte_stream.read())
            return file_path, None
        except Exception as e:
            logger.warning(f"Error saving local file: {e}")
            return None, f"local file write failed: {e}"

    def crawl_file(self, file: dict) -> None:
        file_id = file['id']
        mime_type = file['mimeType']
        name = file['name']

        url = get_gdrive_url(file_id, mime_type)
        if mime_type == 'application/vnd.google-apps.document':
            local_file_path, download_error = self.save_local_file(file_id, name + '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif mime_type == 'application/vnd.google-apps.presentation':
            local_file_path, download_error = self.save_local_file(file_id, name + '.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            local_file_path, download_error = self.save_local_file(file_id, name + '.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        else:
            # Drive often surfaces files without a filename extension (e.g. a PDF
            # uploaded with just a title). The mime type is authoritative — use it
            # to synthesize the extension so the downstream filter at line 765 can
            # route the file.
            name_for_save = name
            if mime_type and not os.path.splitext(name)[1]:
                guessed_ext = mimetypes.guess_extension(mime_type)
                if guessed_ext:
                    name_for_save = name + guessed_ext
            local_file_path, download_error = self.save_local_file(file_id, name_for_save)

        if not local_file_path:
            self._record_drop('download_failed', file, download_error or "unknown save_local_file failure")
            return

        # Route by type: dataframes go through DataframeParser; images use the
        # indexer's standalone-image auto-routing (ImageFileParser) — but only
        # when summarize_images is enabled.
        supported_extensions = ['.doc', '.docx', '.ppt', '.pptx', '.pdf', '.odt', '.txt', '.html', '.md', '.rtf', '.epub', '.lxml']
        if self._summarize_images:
            supported_extensions += ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.svg', '.ico', '.eps']

        is_dataframe = supported_by_dataframe_parser(local_file_path)
        if not is_dataframe and not any(local_file_path.lower().endswith(ext) for ext in supported_extensions):
            self._record_drop(
                'unsupported_ext_dropped',
                file,
                f"local path {local_file_path!r} not in supported extensions {supported_extensions}",
            )
            safe_remove_file(local_file_path)
            return

        if self.crawler.verbose:
            logger.info(f"Handling file: '{name}' with MIME type '{mime_type}'")

        created_time = file.get('createdTime', 'N/A')
        modified_time = file.get('modifiedTime', 'N/A')
        owners = ', '.join([owner['displayName'] for owner in file.get('owners', [])])
        size = file.get('size', 'N/A')

        logger.info(f'Crawling file {name}')
        file_metadata = {
            'id': file_id,
            'name': name,
            'title': name,
            'created_at': created_time,
            'last_updated': modified_time,
            'owners': owners,
            'size': size,
            'url': url,
            'source': 'gdrive'
        }

        parent_perms: Optional[List[Dict[str, Any]]] = None
        if self._abac_enabled:
            parent_perms, source = self._resolve_parent_acl(file)

            labels: List[str] = []
            if self._abac_fetch_labels:
                labels = self._fetch_labels(file_id)

            file_metadata.update(extract_acl_metadata(
                file_obj=file,
                parent_permissions=parent_perms,
                labels=labels,
                include_anyone=self._abac_include_anyone,
                source=source,
            ))

        try:
            if is_dataframe:
                ok = process_dataframe_file(
                    file_path=local_file_path,
                    metadata=file_metadata,
                    doc_id=file_id,
                    df_parser=self.df_parser,
                    df_config=self.cfg.get('dataframe_processing', {}),
                    source_name='gdrive',
                )
                if ok:
                    self._record_indexed(file, file_metadata, parent_permissions=parent_perms)
                else:
                    reason = self.df_parser.last_error or "process_dataframe_file returned False"
                    self._record_drop('index_error', file, reason)
            else:
                ok = self.indexer.index_file(filename=local_file_path, uri=url, metadata=file_metadata)
                if ok:
                    self._record_indexed(file, file_metadata, parent_permissions=parent_perms)
                else:
                    reason = self.indexer.last_error or "indexer.index_file returned False"
                    self._record_drop('index_error', file, reason)
        except Exception as e:
            logger.warning(f"Error {e} indexing document for file {name}, file_id {file_id}")
            self._record_drop('index_error', file, f"exception: {e}")

        safe_remove_file(local_file_path)

    def process(self, user: str) -> None:
        logger.info(f"Processing files for user: {user}")

        # Reset per-user filter counters so each call to process() yields a
        # clean summary line. With Ray, this matters because the same actor
        # services multiple users sequentially.
        self._stats = {k: 0 for k in FILTER_STAGES}

        # Determine authentication method based on configuration
        auth_type = self.cfg.gdrive_crawler.get("auth_type", "service_account")

        # Get credentials file path (same field name for both auth types)
        credentials_file = get_docker_or_local_path(
            docker_path=SERVICE_ACCOUNT_FILE,
            config_path=self.cfg.gdrive_crawler.credentials_file
        )

        scopes = build_scopes(self.abac)

        if auth_type == "oauth":
            # Use OAuth authentication with token from credentials.json
            logger.info("Using OAuth authentication")
            self.creds = get_oauth_credentials(credentials_file, scopes=scopes)
        else:
            # Use service account with domain-wide delegation (default)
            logger.info(f"Using service account authentication for user: {user}")
            self.creds = get_credentials(
                user,
                config_path=self.cfg.gdrive_crawler.credentials_file,
                scopes=scopes,
            )

        self.service = build("drive", "v3", credentials=self.creds, cache_discovery=False)

        date_threshold_str = self.date_threshold.isoformat() + 'Z'
        files = self._collect_listable_files(date_threshold_str)

        # Cache gate: drop files already crawled by another user/worker.
        def _already_seen(file_id: str) -> bool:
            return (ray.get(self.shared_cache.contains.remote(file_id))
                    if self.use_ray else self.shared_cache.contains(file_id))
        kept: List[dict] = []
        for f in files:
            if _already_seen(f['id']):
                self._record_drop('cache_skipped', f, "already crawled in this run")
            else:
                kept.append(f)
        files = kept

        # MIME prefix gate: drop file types the parsers won't handle.
        mime_prefix_to_remove = [
            'audio', 'video',
            'application/vnd.google-apps.folder', 'application/x-adobe-indesign',
            'application/x-rar-compressed', 'application/zip', 'application/x-7z-compressed',
            'application/x-executable',
            'text/php', 'text/javascript', 'text/css', 'text/xml', 'text/x-sql', 'text/x-python-script',
        ]
        if not self._summarize_images:
            mime_prefix_to_remove.append('image')
        kept = []
        for f in files:
            matched = next((p for p in mime_prefix_to_remove if f['mimeType'].startswith(p)), None)
            if matched is not None:
                self._record_drop('mime_dropped', f, f"mimeType starts with blocked prefix '{matched}'")
            else:
                kept.append(f)
        files = kept

        if self.crawler.verbose:
            logger.info(f"identified {len(files)} files for user {user} (post mime/cache gates)")

        # get access token
        try:
            self.creds.refresh(Request())
            self.access_token = self.creds.token
        except Exception as e:
            logger.warning(f"Error refreshing token: {e} for user {user}")
            self._log_filter_summary(user)
            return

        for file in files:
            if self.use_ray:
                if not ray.get(self.shared_cache.contains.remote(file['id'])):
                    self.shared_cache.add.remote(file['id'])
            else:
                if not self.shared_cache.contains(file['id']):
                    self.shared_cache.add(file['id'])
            self.crawl_file(file)

        self._log_filter_summary(user)

class GdriveCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        logger.info("Google Drive Crawler initialized")

        # Get auth type
        auth_type = cfg.gdrive_crawler.get("auth_type", "service_account")

        # For OAuth mode, use a dummy user; for service account, use delegated_users
        if auth_type == "oauth":
            self.delegated_users = ["oauth_user"]  # Dummy user for OAuth mode
        else:
            if "delegated_users" not in cfg.gdrive_crawler:
                raise ValueError(
                    "gdrive_crawler.delegated_users is required for auth_type='service_account'. "
                    "Provide a list of user emails to impersonate, or set auth_type: oauth."
                )
            self.delegated_users = cfg.gdrive_crawler.delegated_users

    def _resolve_permission_display_filter(self) -> Optional[List[str]]:
        """Read the crawl-time displayName gate, honoring the deprecated 'permissions' key.

        Returns None when the gate is disabled (config null, empty list, or
        unset — the default), else the list of allowed displayName strings.
        """
        gdrive = self.cfg.gdrive_crawler
        if 'permission_display_filter' in gdrive:
            value = gdrive.get('permission_display_filter')
        elif 'permissions' in gdrive:
            warnings.warn(
                "gdrive_crawler.permissions is deprecated; rename to gdrive_crawler.permission_display_filter",
                DeprecationWarning,
                stacklevel=2,
            )
            value = gdrive.get('permissions')
        else:
            return None

        if value is None:
            return None
        if isinstance(value, str):
            raise TypeError(
                "gdrive_crawler.permission_display_filter must be a list of displayName "
                f"strings, got a single string {value!r}. Wrap it as [{value!r}]."
            )
        resolved = list(value)
        return resolved or None

    def crawl(self) -> None:
        N = self.cfg.gdrive_crawler.get("days_back", 7)
        date_threshold = datetime.now() - timedelta(days=N)
        if self.verbose:
            logger.info(f"Crawling documents from {date_threshold.date()}")
        ray_workers = self.cfg.gdrive_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        permission_display_filter = self._resolve_permission_display_filter()

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            shared_cache = ray.remote(SharedCache).remote()
            # Convert OmegaConf to dict for proper Ray serialization
            cfg_dict = OmegaConf.to_container(self.cfg, resolve=True)
            actors = [ray.remote(UserWorker).remote(cfg_dict, self.indexer, self, shared_cache, date_threshold, permission_display_filter, use_ray=True) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, user: a.process.remote(user), self.delegated_users))
            ray.shutdown()

        else:
            shared_cache = SharedCache()
            crawl_worker = UserWorker(self.cfg, self.indexer, self, shared_cache, date_threshold, permission_display_filter, use_ray=False)
            for user in self.delegated_users:
                logger.info(f"Crawling for user {user}")
                crawl_worker.process(user)
