import io
import json
import logging
import os
import warnings
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import ray
from omegaconf import OmegaConf
from slugify import slugify

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import setup_logging, safe_remove_file, get_docker_or_local_path

logger = logging.getLogger(__name__)

logging.getLogger('googleapiclient.http').setLevel(logging.ERROR)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
ADMIN_GROUP_MEMBER_SCOPE = "https://www.googleapis.com/auth/admin.directory.group.member.readonly"
DRIVE_LABELS_SCOPE = "https://www.googleapis.com/auth/drive.labels.readonly"
SERVICE_ACCOUNT_FILE = '/home/vectara/env/credentials.json'

# Roles that grant read-or-above access to a file's content (all non-owner roles confer read).
READ_ROLES = frozenset({'reader', 'commenter', 'writer', 'fileOrganizer', 'organizer'})

# Drive API permission subfields we need for ACL metadata extraction.
_PERM_FIELDS = (
    'permissions(id,type,role,emailAddress,domain,deleted,displayName,permissionDetails)'
)

# Legacy crawl-time displayName gate, preserved for backward compatibility.
# Files are indexed only if one of their permissions has a matching displayName.
# Set the config key to null/[] to disable and rely solely on ABAC metadata.
DEFAULT_PERMISSION_DISPLAY_FILTER = ['Vectara', 'all']

# Values for the acl_source metadata field. Persisted in the corpus, so stable.
ACL_SOURCE_SHARED_DRIVE = 'shared_drive'
ACL_SOURCE_MY_DRIVE_DIRECT = 'my_drive_direct'
ACL_SOURCE_MY_DRIVE_RESOLVED = 'my_drive_resolved'
ACL_SOURCE_MY_DRIVE_PARTIAL = 'my_drive_partial'
_AUTHORITATIVE_SOURCES = frozenset({ACL_SOURCE_SHARED_DRIVE, ACL_SOURCE_MY_DRIVE_RESOLVED})


def build_scopes(abac_cfg: Optional[Any] = None) -> List[str]:
    """Return the OAuth scopes required given the ABAC configuration.

    Adds Admin Directory and Drive Labels scopes only when the corresponding
    features are enabled, so unused features don't force extra consent.
    """
    scopes = [DRIVE_READONLY_SCOPE]
    if abac_cfg is not None:
        if abac_cfg.get('expand_groups', False):
            scopes.append(ADMIN_GROUP_MEMBER_SCOPE)
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
    group_members: Optional[Dict[str, Set[str]]] = None,
    labels: Optional[List[str]] = None,
    include_anyone: bool = True,
    source: str = ACL_SOURCE_MY_DRIVE_DIRECT,
) -> Dict[str, Any]:
    """Extract ABAC metadata from a Drive file permission set.

    Merges direct permissions with optional inherited permissions from parent
    folders (deduped by permission id), filters out deleted grants, buckets the
    survivors by grantee type and role, and appends any pre-resolved group
    members and label strings. `source` becomes `acl_source` verbatim and
    determines whether `acl_inherited_resolved` is true.
    """
    owners: Set[str] = set()
    readers: Set[str] = set()
    groups: Set[str] = set()
    domains: Set[str] = set()
    expanded: Set[str] = set()
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
            if group_members and email in group_members:
                expanded.update(m for m in group_members[email] if m)
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
        'acl_expanded_users': sorted(expanded),
        'acl_domains': sorted(domains),
        'acl_is_public': bool(is_public),
        'acl_is_org_wide': bool(domains),
        'acl_labels': list(labels or []),
        'acl_source': source,
        'acl_inherited_resolved': source in _AUTHORITATIVE_SOURCES,
    }


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
        self._abac_enabled = self.abac.get('enabled', True)
        self._abac_resolve_inherited = self.abac.get('resolve_inherited', False)
        self._abac_include_anyone = self.abac.get('include_anyone', True)
        self._abac_expand_groups = self.abac.get('expand_groups', False)
        self._abac_fetch_labels = self.abac.get('fetch_labels', False)

        # Caches populated during a worker's lifetime
        self._folder_acl_cache: Dict[str, Tuple[List[Dict[str, Any]], List[str]]] = {}
        self._group_member_cache: Dict[str, Set[str]] = {}
        self._admin_service: Optional[Resource] = None
        self._label_defs: Optional[Dict[str, Dict[str, Any]]] = None
        self._group_expansion_warned: bool = False

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def _passes_display_filter(self, permissions: List[Dict[str, Any]]) -> bool:
        """Legacy crawl-time gate: only index files whose permission displayName matches the filter."""
        if not self.permission_display_filter:
            return True
        allow = set(self.permission_display_filter)
        return any(p.get('displayName') in allow for p in permissions)

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
                    if self._passes_display_filter(file.get('permissions', [])):
                        results.append(file)
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            except Exception as error:
                logger.warning(f"An HTTP error occurred: {error}")
                break
        return results

    def _resolve_parent_acl(self, file_obj: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
        """Resolve inherited permissions for My Drive files by walking parent folders.

        Returns (union of ancestor permissions, source discriminator).
        """
        # Shared Drive files already receive inherited permissions on the file itself.
        if file_obj.get('driveId'):
            return [], ACL_SOURCE_SHARED_DRIVE

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

    def _get_admin_service(self) -> Optional[Resource]:
        """Build (and cache) an Admin Directory SDK service for group expansion."""
        if self._admin_service is not None:
            return self._admin_service
        admin_user = self.abac.get('admin_delegated_user', '') or ''
        if not admin_user:
            if not self._group_expansion_warned:
                logger.warning(
                    "abac.expand_groups=true but abac.admin_delegated_user is empty; "
                    "skipping group expansion"
                )
                self._group_expansion_warned = True
            return None
        auth_type = self.cfg.gdrive_crawler.get("auth_type", "service_account")
        if auth_type != "service_account":
            if not self._group_expansion_warned:
                logger.warning(
                    "abac.expand_groups requires service_account auth; skipping group expansion"
                )
                self._group_expansion_warned = True
            return None
        try:
            admin_creds = get_credentials(
                admin_user,
                config_path=self.cfg.gdrive_crawler.credentials_file,
                scopes=[ADMIN_GROUP_MEMBER_SCOPE],
            )
            self._admin_service = build(
                'admin', 'directory_v1', credentials=admin_creds, cache_discovery=False
            )
            return self._admin_service
        except Exception as e:
            logger.warning(f"Failed to build Admin SDK service: {e}; skipping group expansion")
            self._group_expansion_warned = True
            return None

    def _expand_group(self, group_email: str) -> Set[str]:
        """Return the set of member email addresses for a Google Group.

        Uses Admin Directory API with `includeDerivedMembership=true` so nested
        groups are expanded server-side. Results are cached per-worker.
        """
        key = (group_email or '').lower()
        if not key:
            return set()
        if key in self._group_member_cache:
            return self._group_member_cache[key]

        admin_service = self._get_admin_service()
        if admin_service is None:
            self._group_member_cache[key] = set()
            return set()

        members: Set[str] = set()
        page_token: Optional[str] = None
        try:
            while True:
                params = {
                    'groupKey': key,
                    'includeDerivedMembership': True,
                    'maxResults': 200,
                }
                if page_token:
                    params['pageToken'] = page_token
                resp = admin_service.members().list(**params).execute()
                for m in resp.get('members', []) or []:
                    email = m.get('email')
                    if email and m.get('type') != 'GROUP':
                        members.add(email.lower())
                page_token = resp.get('nextPageToken')
                if not page_token:
                    break
        except HttpError as e:
            logger.info(f"Group expansion failed for {group_email}: {e}")
        except Exception as e:
            logger.info(f"Group expansion error for {group_email}: {e}")

        self._group_member_cache[key] = members
        return members

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

    def download_or_export_file(self, file_id: str, mime_type: Optional[str] = None) -> Optional[io.BytesIO]:
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
            return byte_stream

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
                            return io.BytesIO(pdf_response.content)
                        else:
                            logger.error(f"An error occurred loading via link: {pdf_response.status_code}")
            else:
                logger.error(f"An error occurred downloading file: {error}")

            return None

    def save_local_file(self, file_id: str, name: str, mime_type: Optional[str] = None) -> Optional[str]:
        path, extension = os.path.splitext(name)
        sanitized_name = f"{slugify(path)}{extension}"
        file_path = os.path.join("/tmp", sanitized_name)
        try:
            byte_stream = self.download_or_export_file(file_id, mime_type)
            if byte_stream:
                with open(file_path, 'wb') as f:
                    f.write(byte_stream.read())
                return file_path
        except Exception as e:
            logger.warning(f"Error saving local file: {e}")
        return None

    def crawl_file(self, file: dict) -> None:
        file_id = file['id']
        mime_type = file['mimeType']
        name = file['name']

        url = get_gdrive_url(file_id, mime_type)
        if mime_type == 'application/vnd.google-apps.document':
            local_file_path = self.save_local_file(file_id, name + '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif mime_type == 'application/vnd.google-apps.presentation':
            local_file_path = self.save_local_file(file_id, name + '.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
        else:
            local_file_path = self.save_local_file(file_id, name)

        supported_extensions = ['.doc', '.docx', '.ppt', '.pptx', '.pdf', '.odt', '.txt', '.html', '.md', '.rtf', '.epub', '.lxml']
        if (not local_file_path) or (not any(local_file_path.endswith(extension) for extension in supported_extensions)):
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

        if self._abac_enabled:
            parent_perms, source = self._resolve_parent_acl(file)

            group_members: Dict[str, Set[str]] = {}
            if self._abac_expand_groups:
                for perm in list(file.get('permissions') or []) + parent_perms:
                    if perm.get('deleted') or perm.get('type') != 'group':
                        continue
                    email = (perm.get('emailAddress') or '').lower()
                    if email and email not in group_members:
                        group_members[email] = self._expand_group(email)

            labels: List[str] = []
            if self._abac_fetch_labels:
                labels = self._fetch_labels(file_id)

            file_metadata.update(extract_acl_metadata(
                file_obj=file,
                parent_permissions=parent_perms,
                group_members=group_members,
                labels=labels,
                include_anyone=self._abac_include_anyone,
                source=source,
            ))

        try:
            self.indexer.index_file(filename=local_file_path, uri=url, metadata=file_metadata)
        except Exception as e:
            logger.warning(f"Error {e} indexing document for file {name}, file_id {file_id}")

        safe_remove_file(local_file_path)

    def process(self, user: str) -> None:
        logger.info(f"Processing files for user: {user}")

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

        files = self.list_files(self.service, date_threshold=self.date_threshold.isoformat() + 'Z')
        if self.use_ray:
            files = [file for file in files if not ray.get(self.shared_cache.contains.remote(file['id']))]
        else:
            files = [file for file in files if not self.shared_cache.contains(file['id'])]

        # remove mime types we don't want to crawl
        mime_prefix_to_remove = [
            'image', 'audio', 'video',
            'application/vnd.google-apps.folder', 'application/x-adobe-indesign',
            'application/x-rar-compressed', 'application/zip', 'application/x-7z-compressed',
            'application/x-executable',
            'text/php', 'text/javascript', 'text/css', 'text/xml', 'text/x-sql', 'text/x-python-script',
        ]
        files = [file for file in files if not any(file['mimeType'].startswith(mime_type) for mime_type in mime_prefix_to_remove)]

        if self.crawler.verbose:
            logging.info(f"identified {len(files)} files for user {user}")

        # get access token
        try:
            self.creds.refresh(Request())
            self.access_token = self.creds.token
        except Exception as e:
            logger.warning(f"Error refreshing token: {e} for user {user}")
            return

        for file in files:
            if self.use_ray:
                if not ray.get(self.shared_cache.contains.remote(file['id'])):
                    self.shared_cache.add.remote(file['id'])
            else:
                if not self.shared_cache.contains(file['id']):
                    self.shared_cache.add(file['id'])
            self.crawl_file(file)

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
            self.delegated_users = cfg.gdrive_crawler.delegated_users

    def _resolve_permission_display_filter(self) -> Optional[List[str]]:
        """Read the crawl-time displayName gate, honoring the deprecated 'permissions' key.

        Returns None when the gate is disabled (config null or empty list), else
        the list of allowed displayName strings.
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
            value = list(DEFAULT_PERMISSION_DISPLAY_FILTER)

        if value is None:
            return None
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
