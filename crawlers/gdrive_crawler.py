import json
import os
from core.crawler import Crawler
from omegaconf import OmegaConf
import logging
import io
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
from typing import List

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SERVICE_ACCOUNT_FILE = 'credentials.json'

def get_credentials(delegated_user):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    delegated_credentials = credentials.with_subject(delegated_user)
    return delegated_credentials

def sanitize_filename(name):
    # Remove or replace characters that are not allowed in filenames
    return "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in name)

def download_file(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}.")
        file.seek(0)  # Reset the file pointer to the beginning
        return file
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def export_file(service, file_id, mime_type):
    try:
        request = service.files().export_media(fileId=file_id, mimeType=mime_type)
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}.")
        file.seek(0)  # Reset the file pointer to the beginning
        return file
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def save_local_file(service, file_id, name, mime_type=None):
    sanitized_name = sanitize_filename(name)
    file_path = os.path.join("/tmp", sanitized_name)
    try:
        if mime_type:
            file = export_file(service, file_id, mime_type)
        else:
            file = download_file(service, file_id)
        if file:
            with open(file_path, 'wb') as f:
                f.write(file.read())
            return file_path
    except Exception as e:
        print(f"Error saving local file: {e}")
    return None

class GdriveCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str, delegated_users: List[str]) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        logging.info("Google Drive Crawler initialized")

        self.delegated_users = delegated_users
        self.creds = None
        self.service = None
        self.api_key = api_key
        self.customer_id = customer_id
        self.corpus_id = corpus_id  

    def list_files(self, service, parent_id=None, date_threshold=None):
        results = []
        page_token = None
        query = f"('{parent_id}' in parents or sharedWithMe) and trashed=false and modifiedTime > '{date_threshold}'" if parent_id else f"('root' in parents or sharedWithMe) and trashed=false and modifiedTime > '{date_threshold}'"

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
                    if any(p.get('displayName') == 'Vectara' or p.get('displayName') == 'all' for p in permissions):
                        results.append(file)
                page_token = response.get('nextPageToken', None)
                if not page_token:
                    break
            except HttpError as error:
                print(f"An error occurred: {error}")
                break
        return results

    def handle_file(self, file):
        file_id = file['id']
        mime_type = file['mimeType']
        name = file['name']
        permissions = file.get('permissions', [])
        
        print(f"\nHandling file: {name} with MIME type: {mime_type}")

        if not any(p.get('displayName') == 'Vectara' or p.get('displayName') == 'all' for p in permissions):
            print(f"Skipping restricted file: {name}")
            return None

        if mime_type == 'application/vnd.google-apps.document':
            local_file_path = save_local_file(self.service, file_id, name + '.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            url = f'https://docs.google.com/document/d/{file_id}/edit'
        elif mime_type == 'application/vnd.google-apps.spreadsheet':
            local_file_path = save_local_file(self.service, file_id, name + '.csv', 'text/csv')
            url = f'https://docs.google.com/spreadsheets/d/{file_id}/edit'
        elif mime_type == 'application/vnd.google-apps.presentation':
            local_file_path = save_local_file(self.service, file_id, name + '.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
            url = f'https://docs.google.com/presentation/d/{file_id}/edit'
        elif mime_type.startswith('application/'):
            local_file_path = save_local_file(self.service, file_id, name)
            if local_file_path and name.endswith('.xlsx'):
                df = pd.read_excel(local_file_path)
                csv_file_path = local_file_path.replace('.xlsx', '.csv')
                df.to_csv(csv_file_path, index=False)
                local_file_path = csv_file_path
            url = f'https://drive.google.com/file/d/{file_id}/view'
        else:
            print(f"Unsupported file type: {mime_type}")
            return None, None

        if local_file_path:
            print(f"local_file_path :: {local_file_path}")
            return local_file_path, url
        else:
            print(f"local_file_path :: None")
            return None, None

    def crawl_file(self, file):
        local_file_path, url = self.handle_file(file)
        if local_file_path:
            file_id = file['id']
            name = file['name']
            created_time = file.get('createdTime', 'N/A')
            modified_time = file.get('modifiedTime', 'N/A')
            owners = ', '.join([owner['displayName'] for owner in file.get('owners', [])])
            size = file.get('size', 'N/A')

            print(f'\nCrawling file {name}')

            file_metadata = {
                'id': file_id,
                'name': name,
                'created_at': created_time,
                'modified_at': modified_time,
                'owners': owners,
                'size': size,
                'source': 'gdrive'
            }

            print(f'file_metadata : {file_metadata}')

            try:
                self.indexer.index_file(filename=local_file_path, uri=url, metadata=file_metadata)
            except Exception as e:
                logging.info(f"Error {e} indexing document for file {name}, file_id {file_id}")

    def crawl(self) -> None:
        N = 7  # Number of days to look back
        date_threshold = (datetime.utcnow() - timedelta(days=N)).isoformat() + 'Z'
        
        for user in self.delegated_users:
            print(f"Processing files for user: {user}")
            self.creds = get_credentials(user)
            self.service = build("drive", "v3", credentials=self.creds)
            
            list_files = self.list_files(self.service, date_threshold=date_threshold)
            for file in list_files:
                modified_time = file.get('modifiedTime', 'N/A')
                if modified_time > date_threshold:
                    self.crawl_file(file)
