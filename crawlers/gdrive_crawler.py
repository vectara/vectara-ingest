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

import pandas as pd
from slugify import slugify
from typing import List, Tuple, Optional

import ray

from core.indexer import Indexer
from core.utils import setup_logging


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_FILE = '/home/vectara/env/credentials.json'

def get_credentials(delegated_user: str) -> service_account.Credentials:
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
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

def download_or_export_file_old(service: Resource, file_id: str, mime_type: Optional[str] = None) -> Optional[io.BytesIO]:
    try:
        if mime_type:
            request = service.files().export_media(fileId=file_id, mimeType=mime_type)
        else:
            request = service.files().get_media(fileId=file_id)

        byte_stream = io.BytesIO()  # an in-memory bytestream
        downloader = MediaIoBaseDownload(byte_stream, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        byte_stream.seek(0)  # Reset the file pointer to the beginning
        return byte_stream
    except HttpError as error:
        logging.info(f"An error occurred: {error}")
        return None

# List of permission display names that are allowed to be crawled
# In this example only files shared with 'Vectara' or 'all' are allowed
# this means that only files shared with anyone in Vectara or files shared with anyone (public) are included
ALLOWED_PERMISSION_DISPLAY_NAMES = ['Vectara', 'all']

class UserWorker(object):
    def __init__(self, indexer: Indexer, crawler: Crawler) -> None:
        self.crawler = crawler
        self.indexer = indexer
        self.creds = None
        self.service = None
        self.access_token = None

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def list_files(self, service: Resource, date_threshold: Optional[str] = None) -> List[dict]:
        results = []
        page_token = None
        query = f"('root' in parents or sharedWithMe) and trashed=false and modifiedTime > '{date_threshold}'"

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
                    if any(p.get('displayName') in ALLOWED_PERMISSION_DISPLAY_NAMES for p in permissions):
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
            if error.resp.status == 403 and "exportSizeLimitExceeded" in str(error):
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
        sanitized_name = slugify(name)
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

    def handle_file(self, file: dict) -> Tuple[Optional[str], Optional[str]]:
        file_id = file['id']
        mime_type = file['mimeType']
        name = file['name']
        permissions = file.get('permissions', [])

        if self.crawler.verbose:
            logging.info(f"Handling file: '{name}' with MIME type '{mime_type}'")

        if not any(p.get('displayName') == 'Vectara' or p.get('displayName') == 'all' for p in permissions):
            logging.info(f"Skipping restricted file: {name}")
            return None

        url = get_gdrive_url(file_id, mime_type)
        if mime_type == 'application/vnd.google-apps.document':
            local_file_path = self.save_local_file(file_id, name + '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            local_file_path = self.save_local_file(file_id, name + '.csv', 'text/csv')
        elif mime_type == 'application/vnd.google-apps.presentation':
            local_file_path = self.save_local_file(file_id, name + '.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
        elif mime_type.startswith('application/'):
            local_file_path = self.save_local_file(file_id, name)
            if local_file_path and name.endswith('.xlsx'):
                df = pd.read_excel(local_file_path)
                csv_file_path = local_file_path.replace('.xlsx', '.csv')
                df.to_csv(csv_file_path, index=False)
                local_file_path = csv_file_path
        else:
            logging.info(f"Unsupported file type: {mime_type}")
            return None, None

        if local_file_path:
            return local_file_path, url
        else:
            return None, None

    def crawl_file(self, file: dict) -> None:
        local_file_path, url = self.handle_file(file)
        if local_file_path:
            file_id = file['id']
            name = file['name']
            mime_type = file['mimeType']
            created_time = file.get('createdTime', 'N/A')
            modified_time = file.get('modifiedTime', 'N/A')
            owners = ', '.join([owner['displayName'] for owner in file.get('owners', [])])
            size = file.get('size', 'N/A')

            logging.info(f'Crawling file {name}')
            file_metadata = {
                'id': file_id,
                'name': name,
                'created_at': created_time,
                'modified_at': modified_time,
                'owners': owners,
                'size': size,
                'url': get_gdrive_url(file_id, mime_type),
                'source': 'gdrive'
            }

            try:
                self.indexer.index_file(filename=local_file_path, uri=url, metadata=file_metadata)
            except Exception as e:
                logging.info(f"Error {e} indexing document for file {name}, file_id {file_id}")

            os.remove(local_file_path)  # remove the local file after indexing

    def process(self, user: str, date_threshold: datetime) -> None:
        logging.info(f"Processing files for user: {user}")
        self.creds = get_credentials(user)
        self.service = build("drive", "v3", credentials=self.creds)
        files = self.list_files(self.service, date_threshold=date_threshold.isoformat() + 'Z')
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
            self.crawl_file(file)

class GdriveCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        logging.info("Google Drive Crawler initialized")

        self.delegated_users = cfg.gdrive_crawler.delegated_users

    def crawl(self) -> None:
        N = self.cfg.gdrive_crawler.get("days_back", 7)
        date_threshold = datetime.now() - timedelta(days=N)
        if self.verbose:
            logging.info(f"Crawling documents from {date_threshold.date()}")
        ray_workers = self.cfg.gdrive_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(UserWorker).remote(self.indexer, self) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u, user=user, date_threshold=date_threshold), self.delegated_users))
                
        else:
            crawl_worker = UserWorker(self.indexer, self)
            for user in self.delegated_users:
                logging.info(f"Crawling for user {user}")
                crawl_worker.process(user, date_threshold)
