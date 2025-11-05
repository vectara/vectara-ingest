"""
Box Crawler for Vectara Ingest

This crawler connects to Box, lists files and folders, and downloads them.
Supports both JWT and OAuth 2.0 authentication.
"""

import logging
import os
import tempfile
from typing import Optional, List
import io

from omegaconf import OmegaConf
from boxsdk import Client, JWTAuth, OAuth2

from core.crawler import Crawler


class BoxCrawler(Crawler):
    """
    Crawler for Box cloud storage

    Configuration (in YAML):
      box_crawler:
        auth_type: jwt  # or oauth
        # For JWT authentication:
        jwt_config_file: /path/to/box_config.json  # Box JWT config file
        # For OAuth authentication:
        client_id: YOUR_CLIENT_ID
        client_secret: YOUR_CLIENT_SECRET
        access_token: YOUR_ACCESS_TOKEN
        refresh_token: YOUR_REFRESH_TOKEN  # optional
        # Common options:
        folder_ids: [0]  # List of folder IDs to crawl (0 = root)
        download_path: /tmp/box_downloads  # Where to download files
        file_extensions: [".pdf", ".docx", ".txt"]  # Filter by extension (empty = all)
        max_files: 100  # Maximum number of files to download (0 = all)
        recursive: true  # Recursively traverse subfolders
        skip_indexing: true  # Set to true to only download without indexing
    """

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.box_cfg = cfg.box_crawler
        self.client: Optional[Client] = None
        self.download_path = self.box_cfg.get("download_path", "/tmp/box_downloads")
        self.file_extensions = self.box_cfg.get("file_extensions", [])
        self.max_files = self.box_cfg.get("max_files", 0)
        self.recursive = self.box_cfg.get("recursive", True)
        self.skip_indexing = self.box_cfg.get("skip_indexing", True)
        self.files_downloaded = 0

        # Create download directory if it doesn't exist
        os.makedirs(self.download_path, exist_ok=True)

        logging.info(f"Box Crawler initialized")
        logging.info(f"Download path: {self.download_path}")
        logging.info(f"Skip indexing: {self.skip_indexing}")

    def _resolve_credentials_path(self, file_path: str) -> str:
        """
        Resolve credentials file path, checking multiple locations.

        For relative paths, checks:
        1. Relative to current working directory
        2. In /home/vectara/env/ (Docker mounted location)
        3. In /home/vectara/ (Docker working directory)

        Args:
            file_path: Path from config (can be relative or absolute)

        Returns:
            Resolved absolute path

        Raises:
            FileNotFoundError: If file cannot be found in any location
        """
        # If absolute path, use as-is
        if os.path.isabs(file_path):
            if os.path.exists(file_path):
                return file_path
            raise FileNotFoundError(f"Credentials file not found: {file_path}")

        # For relative paths, try multiple locations
        search_paths = [
            file_path,  # Current directory
            os.path.join("/home/vectara/env", file_path),  # Docker mounted location
            os.path.join("/home/vectara", file_path),  # Docker working directory
        ]

        for path in search_paths:
            if os.path.exists(path):
                logging.info(f"Found credentials file at: {path}")
                return path

        # Not found in any location
        raise FileNotFoundError(
            f"Credentials file '{file_path}' not found. Searched in:\n" +
            "\n".join(f"  - {p}" for p in search_paths)
        )

    def _authenticate(self) -> Client:
        """
        Authenticate with Box using JWT or OAuth2
        """
        auth_type = self.box_cfg.get("auth_type", "jwt").lower()

        if auth_type == "jwt":
            return self._authenticate_jwt()
        elif auth_type == "oauth":
            return self._authenticate_oauth()
        else:
            raise ValueError(f"Unsupported auth_type: {auth_type}. Use 'jwt' or 'oauth'")

    def _authenticate_jwt(self) -> Client:
        """
        Authenticate using JWT (JSON Web Token)
        Requires a Box JWT config file from Box Developer Console

        Supports as-user authentication for enterprise-wide access:
        - If 'as_user_id' is specified, authenticates as that user
        - Otherwise, uses service account (limited access)
        """
        jwt_config_file = self.box_cfg.get("jwt_config_file")
        if not jwt_config_file:
            raise ValueError("jwt_config_file is required for JWT authentication")

        # Resolve the file path (handles both relative and absolute paths)
        jwt_config_file = self._resolve_credentials_path(jwt_config_file)

        logging.info(f"Authenticating with Box using JWT from {jwt_config_file}")
        auth = JWTAuth.from_settings_file(jwt_config_file)
        client = Client(auth)

        # Check if we should use as-user authentication
        as_user_id = self.box_cfg.get("as_user_id")
        if as_user_id:
            logging.info(f"Using as-user authentication with user ID: {as_user_id}")
            client = client.as_user(client.user(as_user_id))

        # Test authentication
        user = client.user().get()
        logging.info(f"Successfully authenticated as: {user.name} ({user.login})")

        return client

    def _authenticate_oauth(self) -> Client:
        """
        Authenticate using OAuth 2.0
        Requires client_id, client_secret, and access_token
        Can load from oauth_credentials_file or directly from config
        """
        import json

        # Try to load from credentials file first
        oauth_credentials_file = self.box_cfg.get("oauth_credentials_file")
        if oauth_credentials_file:
            # Resolve the file path (handles both relative and absolute paths)
            oauth_credentials_file = self._resolve_credentials_path(oauth_credentials_file)

            logging.info(f"Loading OAuth credentials from {oauth_credentials_file}")
            with open(oauth_credentials_file, 'r') as f:
                creds = json.load(f)

            client_id = creds.get("client_id")
            client_secret = creds.get("client_secret")
            access_token = creds.get("access_token")
        else:
            # Fall back to direct config values
            client_id = self.box_cfg.get("client_id")
            client_secret = self.box_cfg.get("client_secret")
            access_token = self.box_cfg.get("access_token")

        if not all([client_id, client_secret, access_token]):
            raise ValueError("client_id, client_secret, and access_token are required for OAuth. "
                           "Provide them via oauth_credentials_file or directly in config.")

        logging.info("Authenticating with Box using OAuth 2.0")

        oauth = OAuth2(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
        )

        client = Client(oauth)

        # Test authentication
        user = client.user().get()
        logging.info(f"Successfully authenticated as: {user.name} ({user.login})")

        return client

    def _should_download_file(self, file_name: str) -> bool:
        """
        Check if file should be downloaded based on extension filter
        """
        if not self.file_extensions:
            return True

        _, ext = os.path.splitext(file_name)
        return ext.lower() in [e.lower() for e in self.file_extensions]

    def _download_file(self, file_item) -> Optional[str]:
        """
        Download a file from Box to local storage

        Args:
            file_item: Box file object

        Returns:
            Local file path if successful, None otherwise
        """
        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            logging.info(f"Reached max_files limit ({self.max_files})")
            return None

        file_name = file_item.name
        file_id = file_item.id

        if not self._should_download_file(file_name):
            logging.debug(f"Skipping file (extension filter): {file_name}")
            return None

        try:
            # Create a sanitized filename
            safe_filename = "".join(c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            local_path = os.path.join(self.download_path, f"{file_id}_{safe_filename}")

            logging.info(f"Downloading: {file_name} (ID: {file_id})")

            # Download file content
            with open(local_path, 'wb') as output_file:
                file_item.download_to(output_file)

            file_size = os.path.getsize(local_path)
            logging.info(f"✓ Downloaded: {file_name} ({file_size:,} bytes) -> {local_path}")

            self.files_downloaded += 1

            # Get file metadata
            metadata = {
                "source": "Box",
                "title": file_name,
                "file_id": file_id,
                "url": f"https://app.box.com/file/{file_id}",
                "size": file_size,
                "created_at": str(file_item.created_at) if hasattr(file_item, 'created_at') else None,
                "modified_at": str(file_item.modified_at) if hasattr(file_item, 'modified_at') else None,
                "created_by": file_item.created_by.name if hasattr(file_item, 'created_by') and file_item.created_by else None,
                "modified_by": file_item.modified_by.name if hasattr(file_item, 'modified_by') and file_item.modified_by else None,
            }

            # Index the file if skip_indexing is False
            if not self.skip_indexing:
                logging.info(f"Indexing file: {file_name}")
                self.indexer.index_file(
                    filename=local_path,
                    uri=metadata["url"],
                    metadata=metadata,
                    id=file_id
                )

            return local_path

        except Exception as e:
            logging.error(f"Error downloading file {file_name}: {str(e)}")
            return None

    def _crawl_folder(self, folder_id: str, path: str = "") -> None:
        """
        Recursively crawl a Box folder and download files

        Args:
            folder_id: Box folder ID (use "0" for root folder)
            path: Current folder path for logging
        """
        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            return

        try:
            # Get the folder object and its items
            folder = self.client.folder(folder_id).get(fields=['name', 'id'])
            current_path = f"{path}/{folder.name}" if path else folder.name
            logging.info(f"Crawling folder: {current_path} (ID: {folder_id})")

            # Get items in the folder
            items = folder.get_items(limit=1000, offset=0)

            for item in items:
                if self.max_files > 0 and self.files_downloaded >= self.max_files:
                    break

                if item.type == 'file':
                    self._download_file(item)
                elif item.type == 'folder' and self.recursive:
                    self._crawl_folder(item.id, current_path)

        except Exception as e:
            logging.error(f"Error crawling folder {folder_id}: {str(e)}")

    def crawl(self) -> None:
        """
        Main crawl method - authenticates and downloads files from Box
        """
        try:
            # Authenticate
            self.client = self._authenticate()

            # Get folder IDs to crawl (default to root folder with ID '0')
            folder_ids = self.box_cfg.get("folder_ids", ["0"])
            # Convert OmegaConf ListConfig to regular Python list
            # Use OmegaConf.to_container to properly convert
            from omegaconf import OmegaConf
            folder_ids = OmegaConf.to_container(folder_ids, resolve=True)
            if not isinstance(folder_ids, list):
                folder_ids = [folder_ids]

            # If folder_id is "0", get all root-level folders the user has access to
            actual_folders = []
            for folder_id in folder_ids:
                folder_id_str = str(folder_id)
                logging.info(f"Processing folder_id: {folder_id_str} (type: {type(folder_id)})")

                if folder_id_str == "0":
                    logging.info("Fetching all root-level folders accessible to user")
                    try:
                        root_folder = self.client.folder("0")
                        root_items = root_folder.get_items(limit=1000, offset=0)

                        item_count = 0
                        # Collect all folders at root level
                        for item in root_items:
                            item_count += 1
                            if item.type == 'folder':
                                actual_folders.append(item.id)
                                logging.info(f"Found root folder: {item.name} (ID: {item.id})")
                            elif item.type == 'file':
                                # Also download files at root level
                                logging.info(f"Found root file: {item.name}")
                                self._download_file(item)

                        logging.info(f"Found {item_count} items at root level ({len(actual_folders)} folders)")
                    except Exception as e:
                        logging.error(f"Error fetching root-level items: {str(e)}")
                        logging.exception(e)
                else:
                    actual_folders.append(folder_id_str)

            logging.info(f"Starting Box crawl for {len(actual_folders)} folder(s)")

            # Crawl each folder
            for folder_id in actual_folders:
                self._crawl_folder(str(folder_id))

            logging.info(f"Box crawl complete. Downloaded {self.files_downloaded} files to {self.download_path}")

            if self.skip_indexing:
                logging.info("Files were NOT indexed (skip_indexing=true)")
            else:
                logging.info("Files were indexed to Vectara")

        except Exception as e:
            logging.error(f"Error during Box crawl: {str(e)}")
            raise
