import os
from core.crawler import Crawler
from omegaconf import OmegaConf
import logging
import io
from datetime import datetime, timedelta
import requests

from google.oauth2 import service_account
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.auth.transport.requests import Request

from slugify import slugify
from typing import List, Optional

import ray

from core.indexer import Indexer
from core.utils import setup_logging, safe_remove_file, get_docker_or_local_path

logging.getLogger('googleapiclient.http').setLevel(logging.ERROR)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_FILE = '/home/vectara/env/credentials.json'

# Shared cache to keep track of files that have already been crawled
class SharedCache:
    def __init__(self):
        self.cache = set()

    def add(self, id: str):
        self.cache.add(id)

    def contains(self, id: str) -> bool:
        return id in self.cache

def get_credentials(delegated_user: str, config_path: str) -> service_account.Credentials:
    credentials_file = get_docker_or_local_path(
        docker_path=SERVICE_ACCOUNT_FILE,
        config_path=config_path
    )
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES)
    delegated_credentials = credentials.with_subject(delegated_user)
    return delegated_credentials

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

# List of permission display names that are allowed to be crawled
# In this example only files shared with 'Vectara' or 'all' are allowed
# this means that only files shared with anyone in Vectara or files shared with anyone (public) are included
DEFAULT_PERMISSIONS = ['Vectara', 'all']

class UserWorker(object):
    def __init__(
            self, indexer: Indexer, crawler: Crawler, 
            shared_cache: SharedCache,
            date_threshold: datetime,
            permissions: List = DEFAULT_PERMISSIONS, 
            use_ray: bool = False) -> None:
        self.crawler = crawler
        self.indexer = indexer
        self.creds = None
        self.service = None
        self.access_token = None
        self.shared_cache = shared_cache
        self.date_threshold = date_threshold
        self.permissions = permissions
        self.use_ray = use_ray

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def list_files(self, service: Resource, date_threshold: Optional[str] = None) -> List[dict]:
        results = []
        page_token = None
        query = f"((('root' in parents) or sharedWithMe or ('me' in owners) or ('me' in writers) or ('me' in readers)) and trashed=false and modifiedTime > '{date_threshold}')"

        while True:
            try:
                params = {
                    'fields': 'nextPageToken, files(id, name, mimeType, permissions, modifiedTime, createdTime, owners, size)',
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
                    permissions = file.get('permissions', [])
                    if any(p.get('displayName') in self.permissions for p in permissions):
                        results.append(file)
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            except Exception as error:
                logging.info(f"An HTTP error occurred: {error}")
                break
        return results

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
                            logging.info(f"Downloaded file {file_id} via link (as pdf)")
                            return io.BytesIO(pdf_response.content)
                        else:
                            logging.error(f"An error occurred loading via link: {pdf_response.status_code}")
            else:
                logging.error(f"An error occurred downloading file: {error}")
            
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
            logging.info(f"Error saving local file: {e}")
        return None

    def crawl_file(self, file: dict) -> None:
        file_id = file['id']
        mime_type = file['mimeType']
        name = file['name']
        permissions = file.get('permissions', [])

        if not any(p.get('displayName') == 'Vectara' or p.get('displayName') == 'all' for p in permissions):
            logging.info(f"Skipping restricted file: {name}")
            return None

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
            logging.info(f"Handling file: '{name}' with MIME type '{mime_type}'")

        if local_file_path:
            created_time = file.get('createdTime', 'N/A')
            modified_time = file.get('modifiedTime', 'N/A')
            owners = ', '.join([owner['displayName'] for owner in file.get('owners', [])])
            size = file.get('size', 'N/A')

            logging.info(f'Crawling file {name}')
            file_metadata = {
                'id': file_id,
                'name': name,
                'title': name,
                'created_at': created_time,
                'last_updated': modified_time,
                'owners': owners,
                'size': size,
                'url': get_gdrive_url(file_id, mime_type),
                'source': 'gdrive'
            }

            try:
                self.indexer.index_file(filename=local_file_path, uri=url, metadata=file_metadata)
            except Exception as e:
                logging.info(f"Error {e} indexing document for file {name}, file_id {file_id}")

            # remove file from local storage
            safe_remove_file(local_file_path)

    def process(self, user: str) -> None:
        logging.info(f"Processing files for user: {user}")
        self.creds = get_credentials(user, config_path=self.cfg.gdrive_crawler.credentials_file)
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
            logging.info(f"Error refreshing token: {e} for user {user}")
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
        logging.info("Google Drive Crawler initialized")

        self.delegated_users = cfg.gdrive_crawler.delegated_users

    def crawl(self) -> None:
        N = self.cfg.gdrive_crawler.get("days_back", 7)
        date_threshold = datetime.now() - timedelta(days=N)
        if self.verbose:
            logging.info(f"Crawling documents from {date_threshold.date()}")
        ray_workers = self.cfg.gdrive_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        permissions = self.cfg.gdrive_crawler.get("permissions", ['Vectara', 'all'])
        
        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            shared_cache = ray.remote(SharedCache).remote()
            actors = [ray.remote(UserWorker).remote(self.indexer, self, shared_cache, date_threshold, permissions, use_ray=True) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, user: a.process.remote(user), self.delegated_users))
                
        else:
            shared_cache = SharedCache()
            crawl_worker = UserWorker(self.indexer, self, shared_cache, date_threshold, permissions, use_ray=False)
            for user in self.delegated_users:
                logging.info(f"Crawling for user {user}")
                crawl_worker.process(user)
