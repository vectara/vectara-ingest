import io
import json
import logging
import mimetypes
import os
import re
import warnings
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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

# Mime -> canonical extension for every type the indexer (or its dataframe /
# image side-routes) can parse. Drive filenames are user-controlled — trailing
# dots, made-up extensions, and unrelated suffixes like ``.bak`` are common —
# so when Drive reports a mime we recognise, we trust it over the filename.
_MIME_TO_EXT: Dict[str, str] = {
    'application/pdf': '.pdf',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.ms-powerpoint': '.ppt',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
    'application/vnd.oasis.opendocument.text': '.odt',
    'application/rtf': '.rtf',
    'text/rtf': '.rtf',
    'text/plain': '.txt',
    'text/html': '.html',
    'text/markdown': '.md',
    'application/epub+zip': '.epub',
    # dataframes
    'text/csv': '.csv',
    'application/vnd.ms-excel': '.xls',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    # images (only used when summarize_images is on; harmless otherwise)
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/tiff': '.tiff',
    'image/svg+xml': '.svg',
}


def canonical_save_name(name: str, mime_type: Optional[str]) -> str:
    """Return the filename to use on disk so the downstream extension whitelist
    can route the file.

    If ``mime_type`` is in ``_MIME_TO_EXT``, append the canonical extension
    (unless the name already ends with it, case-insensitive). For unknown mime
    types, fall back to ``mimetypes.guess_extension``; if that also fails, the
    name is returned with any trailing dots stripped so ``os.path.splitext``
    downstream doesn't swallow the real extension (``"file.bin."`` →
    ``("file.bin", ".")``).
    """
    base = name.rstrip('.')
    if not mime_type:
        return base
    canonical = _MIME_TO_EXT.get(mime_type)
    if canonical is None:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed and not base.lower().endswith(guessed.lower()):
            return base + guessed
        return base
    if base.lower().endswith(canonical.lower()):
        return base
    return base + canonical

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


def _union_perms_by_id(
    perms: Iterable[Dict[str, Any]], seen: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """Dedupe a permission stream by permission id, preserving first-seen order.

    Drive permission objects always carry an `id`; any entry missing one is kept
    as-is (defensive). Pass a shared `seen` set to union across several streams
    (e.g. drive-root members, then a file's own grants) without re-counting ids
    already taken from an earlier stream — the set is mutated in place.
    """
    seen = seen if seen is not None else set()
    out: List[Dict[str, Any]] = []
    for p in perms:
        pid = p.get('id')
        if pid and pid in seen:
            continue
        if pid:
            seen.add(pid)
        out.append(p)
    return out


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
    combined = _union_perms_by_id(direct + list(parent_permissions or []))

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
        # Issue the Shared Drive membership listing as a domain admin. Lets a
        # domain-admin delegated user read drive members without holding a
        # per-drive fileOrganizer/organizer role (the usual cause of the 403
        # that downgrades files to acl_source=shared_drive_partial).
        self._abac_shared_drive_admin_access = self.abac.get('shared_drive_admin_access', False)

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
        # Make ABAC config state visible up-front. When operators see empty
        # acl_groups / acl_domains / acl_labels in production, this line tells
        # them whether the feature is gated off, the Labels scope wasn't
        # requested, or the data just isn't there to begin with.
        logger.info(
            "gdrive ABAC config: "
            f"enabled={self._abac_enabled} "
            f"resolve_inherited={self._abac_resolve_inherited} "
            f"include_anyone={self._abac_include_anyone} "
            f"fetch_labels={self._abac_fetch_labels}"
        )

    def _passes_display_filter(self, permissions: List[Dict[str, Any]]) -> bool:
        """Legacy crawl-time gate: only index files whose permission displayName matches the filter."""
        if not self.permission_display_filter:
            return True
        allow = set(self.permission_display_filter)
        return any(p.get('displayName') in allow for p in permissions)

    def _apply_mime_gate(self, files: List[dict]) -> List[dict]:
        """Drop file types the indexer can't parse, or that Drive itself
        refuses to return content for. Survivors are returned; drops are
        recorded against the `mime_dropped` counter with a human-readable
        reason so the per-user summary stays interpretable.

        Two classes of block:
          * **prefix block** — broad categories the parsers don't handle
            (audio/video/archives/code) plus the few specific types that
            historically caused trouble.
          * **Google Workspace types without a downloadable form** — Forms,
            Sites, My Maps, Jamboard, Fusion Tables. The Drive API returns
            404/403 on get_media for these; they were previously surfacing as
            `download_failed`, which misled operators into expecting a retry.
            Drawings are intentionally *not* in this list because they
            *do* export to PNG/PDF.
        """
        mime_prefix_to_remove = [
            'audio', 'video',
            'application/vnd.google-apps.folder', 'application/x-adobe-indesign',
            'application/x-rar-compressed', 'application/zip', 'application/x-7z-compressed',
            'application/x-executable',
            'text/php', 'text/javascript', 'text/css', 'text/xml', 'text/x-sql', 'text/x-python-script',
        ]
        if not self._summarize_images:
            mime_prefix_to_remove.append('image')

        unexportable_google_types = {
            'application/vnd.google-apps.form',
            'application/vnd.google-apps.site',
            'application/vnd.google-apps.map',
            'application/vnd.google-apps.jam',
            'application/vnd.google-apps.fusiontable',
        }

        kept: List[dict] = []
        for f in files:
            mime = f.get('mimeType', '')
            if mime in unexportable_google_types:
                self._record_drop(
                    'mime_dropped', f,
                    f"Google Workspace type '{mime}' is not exportable via Drive API",
                )
                continue
            matched = next((p for p in mime_prefix_to_remove if mime.startswith(p)), None)
            if matched is not None:
                self._record_drop(
                    'mime_dropped', f,
                    f"mimeType starts with blocked prefix '{matched}'",
                )
                continue
            kept.append(f)
        return kept

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

    def _fetch_item_permissions(self, item_id: str) -> Tuple[List[Dict[str, Any]], bool]:
        """Page through `permissions.list` for any Drive item (file/folder/drive).

        Returns `(permissions, ok)`. `ok` is False when the listing failed
        (e.g. a 403 because the delegated user can't read the item's ACL);
        callers downgrade their `acl_source` to a `*_partial` variant.

        This is the only reliable way to read a Shared Drive item's ACL: the
        File resource's `permissions` field is documented as "not populated for
        items in shared drives", so `files.list`/`files.get` return
        `permissions=[]` there. `permissions.list` on a shared-drive item
        returns the complete effective ACL — direct grants plus those inherited
        from parent folders and drive membership (surfaced via
        `permissionDetails.inheritedFrom`), including `type:'group'` grants.

        Enumerating these grants requires the delegated user to have at least
        `fileOrganizer` on the drive; lower roles get a 403. Set
        `abac.shared_drive_admin_access` (domain-admin delegated user) to read
        via `useDomainAdminAccess`.
        """
        fields = 'nextPageToken,' + _PERM_FIELDS
        collected: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            params = {
                'fileId': item_id,
                'supportsAllDrives': True,
                'fields': fields,
            }
            if self._abac_shared_drive_admin_access:
                params['useDomainAdminAccess'] = True
            if page_token:
                params['pageToken'] = page_token
            try:
                resp = self.service.permissions().list(**params).execute()
            except HttpError as e:
                logger.warning(
                    f"permissions.list failed for item {item_id}: {e}; "
                    "delegated user likely lacks fileOrganizer/organizer access — "
                    "grant a manager role or set abac.shared_drive_admin_access "
                    "(requires a domain-admin delegated user)."
                )
                return [], False
            except Exception as e:
                logger.info(f"Error listing permissions for item {item_id}: {e}")
                return [], False

            for p in (resp.get('permissions') or []):
                collected.append(p)
            page_token = resp.get('nextPageToken')
            if not page_token:
                break

        return collected, True

    def _fetch_drive_permissions(self, drive_id: str) -> Tuple[List[Dict[str, Any]], str]:
        """Return (members, source) for a Shared Drive, with per-worker caching.

        Fetches the drive-root membership via `permissions.list(fileId=<driveId>)`
        (see `_fetch_item_permissions`). A 403 (delegated user lacks
        fileOrganizer/organizer on the drive) yields an empty list and the
        `shared_drive_partial` source; the outcome is cached either way so we
        don't hammer Drive once per file.
        """
        cached = self._drive_perms_cache.get(drive_id)
        if cached is not None:
            return cached

        members, ok = self._fetch_item_permissions(drive_id)
        source = ACL_SOURCE_SHARED_DRIVE if ok else ACL_SOURCE_SHARED_DRIVE_PARTIAL
        result = (members, source)
        self._drive_perms_cache[drive_id] = result
        return result

    def _resolve_parent_acl(self, file_obj: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
        """Resolve inherited permissions for a file.

        For Shared Drive files: fetch the drive's member list (cached per
        worker per drive) and union any grants made on the folders between the
        file and the drive root. For My Drive files with `resolve_inherited=True`:
        walk ancestor folders and union their ACLs.

        Returns (union of inherited permissions, source discriminator).
        """
        drive_id = file_obj.get('driveId')
        if drive_id:
            members, source = self._fetch_drive_permissions(drive_id)
            # Drive's File resource does not populate `permissions` for items in
            # shared drives, so grants made directly on the file or inherited
            # from intermediate folders never appear in files.list output (the
            # file comes back with permissions=[]). `permissions.list` on the
            # file recovers the complete effective ACL — direct grants plus
            # those inherited from parent folders and drive membership,
            # including group grants. Union it with the drive-root membership
            # (deduped by permission id) so nothing is double-counted.
            #
            # The per-file `permissions.list` normally already includes the
            # drive-root grants (they show up as inherited entries), so the
            # drive-root fetch above is usually redundant. We keep it as a
            # cheap backup/fallback: it is cached one-call-per-drive, and it
            # guarantees drive membership is captured even if a file's own
            # listing ever comes back incomplete.
            combined = list(members)
            file_id = file_obj.get('id')
            if file_id:
                file_perms, file_ok = self._fetch_item_permissions(file_id)
                if not file_ok and source == ACL_SOURCE_SHARED_DRIVE:
                    source = ACL_SOURCE_SHARED_DRIVE_PARTIAL
                seen_ids = {p.get('id') for p in members if p.get('id')}
                combined.extend(_union_perms_by_id(file_perms, seen=seen_ids))
            return combined, source

        if not self._abac_resolve_inherited:
            return [], ACL_SOURCE_MY_DRIVE_DIRECT

        parents = file_obj.get('parents') or []
        if not parents:
            return [], ACL_SOURCE_MY_DRIVE_RESOLVED

        perms, partial = self._walk_ancestor_acls(parents)
        source = ACL_SOURCE_MY_DRIVE_PARTIAL if partial else ACL_SOURCE_MY_DRIVE_RESOLVED
        return perms, source

    def _walk_ancestor_acls(
        self, parents: List[str]
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """BFS up the ancestor-folder chain, unioning each folder's direct ACL.

        Used for My Drive's `resolve_inherited`, where `files.get` does populate
        a folder's `permissions`. (Shared drives read the full effective ACL
        straight off the file via `permissions.list`, so they don't walk here.)
        Folder ACLs are cached per worker in `_folder_acl_cache`, deduped by
        permission id. Returns (permissions, partial), where `partial` is True
        if any ancestor folder couldn't be read.
        """
        collected: List[Dict[str, Any]] = []
        perm_seen: Set[str] = set()
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

                collected.extend(_union_perms_by_id(perms, seen=perm_seen))
                next_frontier.extend(fparents)

            frontier = next_frontier

        return collected, partial

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
                # text/integer/dateString are arrays in the Drive API (like
                # selection/user), not scalars — iterate so a value renders
                # `Title=value`, not `Title=['value']`.
                if 'selection' in fdata:
                    for cid in fdata.get('selection') or []:
                        values.append(choices.get(cid, cid))
                elif 'text' in fdata:
                    for t in fdata.get('text') or []:
                        values.append(str(t))
                elif 'integer' in fdata:
                    for n in fdata.get('integer') or []:
                        values.append(str(n))
                elif 'dateString' in fdata:
                    for d in fdata.get('dateString') or []:
                        values.append(str(d))
                elif 'user' in fdata:
                    for u in fdata.get('user') or []:
                        ue = u.get('emailAddress') if isinstance(u, dict) else u
                        if ue:
                            values.append(str(ue))
                for v in values:
                    if v:
                        out.append(f"{label_title}={v}")
        return out

    def _download_via_drive(
        self, file_id: str, mime_type: Optional[str]
    ) -> Tuple[Optional[io.BytesIO], Optional[HttpError]]:
        """One download attempt. Returns (BytesIO, None) on success, or
        (None, HttpError) on failure so the caller can decide whether to
        retry. Routes through export_media when a mime is given (the
        supported way to convert Workspace docs) and get_media otherwise."""
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
            return None, error

    def download_or_export_file(
        self, file_id: str, mime_type: Optional[str] = None
    ) -> Tuple[Optional[io.BytesIO], Optional[str]]:
        """Download a Drive file's bytes. For Google Workspace exports that
        Drive refuses in the requested mime (oversized .pptx export, etc.),
        falls back to a PDF export via the same export_media path — the
        supported method, which uses the auto-refreshing service credential.
        We deliberately do not fall back to raw requests.get against
        exportLinks: that path used a cached access_token which goes stale
        on long crawls and produced 401s.
        """
        stream, error = self._download_via_drive(file_id, mime_type)
        if stream is not None:
            return stream, None

        retryable_reasons = {'exportSizeLimitExceeded', 'fileNotDownloadable'}
        should_retry_as_pdf = (
            mime_type is not None
            and mime_type != 'application/pdf'
            and error.resp.status == 403
            and any((e.get('reason') in retryable_reasons) for e in error.error_details)
        )
        if not should_retry_as_pdf:
            logger.error(f"An error occurred downloading file {file_id}: {error}")
            return None, f"HttpError {error.resp.status}: {error}"

        logger.info(
            f"Primary export of {file_id} refused ({error.resp.status}); retrying as PDF via export_media"
        )
        pdf_stream, pdf_error = self._download_via_drive(file_id, 'application/pdf')
        if pdf_stream is not None:
            return pdf_stream, None
        logger.error(f"PDF fallback export also failed for {file_id}: {pdf_error}")
        return None, f"HttpError {pdf_error.resp.status}: {pdf_error}"

    def save_local_file(
        self, file_id: str, name: str, mime_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Download a Drive file to /tmp. Returns (local_path, error_reason);
        on success error_reason is None, on failure local_path is None and
        error_reason names the failing stage so callers can surface it."""
        path, extension = os.path.splitext(name)
        # Treat a bare trailing dot (e.g. "Policy.") as "no extension" so the
        # saved file doesn't end in '.' — a downstream extension whitelist
        # check would then fail even when the mime type is supported.
        if extension == '.':
            extension = ''
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
            # Drive filenames are user-controlled: trailing dots, made-up
            # extensions ("report.xyz"), and unrelated suffixes (".bak") are all
            # common. When we recognise the mime, ensure the saved filename ends
            # with the canonical extension so the downstream whitelist routes
            # the file to the right parser.
            local_file_path, download_error = self.save_local_file(
                file_id, canonical_save_name(name, mime_type)
            )

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
                ok = self.indexer.index_file(
                    filename=local_file_path,
                    uri=url,
                    metadata=file_metadata,
                    id=file_id,
                )
                if ok:
                    self._record_indexed(file, file_metadata, parent_permissions=parent_perms)
                else:
                    reason = self.indexer.last_error or "indexer.index_file returned False"
                    self._record_drop('index_error', file, reason)
        except Exception as e:
            logger.warning(f"Error {e} indexing document for file {name}, file_id {file_id}")
            self._record_drop('index_error', file, f"exception: {e}")

        safe_remove_file(local_file_path)

    def _reconcile_oauth_scopes(self, credentials_file: str, scopes: List[str]) -> List[str]:
        """Drop the optional Drive Labels scope when the saved OAuth token wasn't
        granted it, so the token refresh doesn't fail with invalid_scope. A
        refresh token only carries the scopes consented to when it was minted, and
        Google rejects a refresh that asks for anything beyond that. Also disables
        label fetching for this run so we don't trade the crash for a per-file 403.
        Returns the scopes that are actually safe to request."""
        if DRIVE_LABELS_SCOPE not in scopes:
            return scopes
        try:
            with open(credentials_file, 'r') as f:
                granted = json.load(f).get("scopes") or []
        except (OSError, json.JSONDecodeError):
            # Couldn't read the grants — leave scopes untouched so
            # get_oauth_credentials surfaces the real file/JSON error.
            return scopes
        if DRIVE_LABELS_SCOPE in granted:
            return scopes
        logger.warning(
            "OAuth token %s was not granted the Drive Labels scope (%s); "
            "continuing without labels. Re-run "
            "scripts/gdrive/generate_oauth_token.py --with-labels to enable "
            "label ingestion.",
            credentials_file, DRIVE_LABELS_SCOPE,
        )
        self._abac_fetch_labels = False
        return [s for s in scopes if s != DRIVE_LABELS_SCOPE]

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
            scopes = self._reconcile_oauth_scopes(credentials_file, scopes)
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

        files = self._apply_mime_gate(files)

        if self.crawler.verbose:
            logger.info(f"identified {len(files)} files for user {user} (post mime/cache gates)")

        # Refresh credentials so the googleapiclient picks up a fresh token
        # for subsequent service.* calls.
        try:
            self.creds.refresh(Request())
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
