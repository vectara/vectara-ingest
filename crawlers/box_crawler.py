"""
Box Crawler for Vectara Ingest

This crawler connects to Box cloud storage and ingests files into Vectara.
Supports JWT and OAuth 2.0 authentication, file filtering, and flexible folder access.

Features:
- JWT and OAuth 2.0 authentication
- As-user authentication for enterprise-wide access
- File extension filtering (include/exclude lists)
- Recursive folder traversal
- Structure report generation
- CSV tracking for indexed/failed/skipped files (minimal disk usage)
- Ray parallel processing for indexing (streaming producer-consumer pattern)
- Automatic file cleanup after indexing to save disk space
"""

import csv
import json
import logging
import os
import psutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from boxsdk import Client, JWTAuth, OAuth2
from omegaconf import DictConfig, OmegaConf

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import setup_logging

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    logging.warning("Ray is not available. Install with: pip install ray")


class CSVTrackerActor:
    """
    Ray actor for thread-safe CSV tracking.

    All workers send tracking requests to this single actor, eliminating
    race conditions and ensuring data integrity.
    """

    def __init__(self, tracking_dir: str):
        """
        Initialize the CSV tracker actor.

        Args:
            tracking_dir: Directory to store CSV tracking files
        """
        self.tracking_dir = tracking_dir
        os.makedirs(tracking_dir, exist_ok=True)

        self.indexed_csv = os.path.join(tracking_dir, "indexed.csv")
        self.failed_csv = os.path.join(tracking_dir, "failed.csv")
        self.skipped_csv = os.path.join(tracking_dir, "skipped.csv")

        # Initialize CSV files with headers if they don't exist
        self._init_csv_file(self.indexed_csv, ["timestamp", "file_id", "name", "url", "size", "extension"])
        self._init_csv_file(self.failed_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "error"])
        self._init_csv_file(self.skipped_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "reason"])

        logging.info(f"CSVTrackerActor initialized - tracking dir: {tracking_dir}")

    def _init_csv_file(self, csv_path: str, headers: List[str]):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def track_indexed(self, file_id: str, name: str, url: str, size: int, extension: str):
        """Record a successfully indexed file (called remotely by workers)."""
        with open(self.indexed_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension])

    def track_failed(self, file_id: str, name: str, url: str, size: int, extension: str, error: str):
        """Record a failed file (called remotely by workers)."""
        with open(self.failed_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension, error])

    def track_skipped(self, file_id: str, name: str, url: str, size: int, extension: str, reason: str):
        """Record a skipped file (called remotely by workers)."""
        with open(self.skipped_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension, reason])


class BoxCrawlerTracker:
    """
    Local tracker for non-Ray mode (sequential processing).

    For Ray mode, use CSVTrackerActor instead.
    """

    def __init__(self, tracking_dir: str):
        """
        Initialize the tracker.

        Args:
            tracking_dir: Directory to store CSV tracking files
        """
        self.tracking_dir = tracking_dir
        os.makedirs(tracking_dir, exist_ok=True)

        self.indexed_csv = os.path.join(tracking_dir, "indexed.csv")
        self.failed_csv = os.path.join(tracking_dir, "failed.csv")
        self.skipped_csv = os.path.join(tracking_dir, "skipped.csv")

        # Initialize CSV files with headers if they don't exist
        self._init_csv_file(self.indexed_csv, ["timestamp", "file_id", "name", "url", "size", "extension"])
        self._init_csv_file(self.failed_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "error"])
        self._init_csv_file(self.skipped_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "reason"])

    def _init_csv_file(self, csv_path: str, headers: List[str]):
        """Initialize CSV file with headers if it doesn't exist."""
        if not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def track_indexed(self, file_id: str, name: str, url: str, size: int, extension: str):
        """Record a successfully indexed file."""
        with open(self.indexed_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension])

    def track_failed(self, file_id: str, name: str, url: str, size: int, extension: str, error: str):
        """Record a failed file."""
        with open(self.failed_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension, error])

    def track_skipped(self, file_id: str, name: str, url: str, size: int, extension: str, reason: str):
        """Record a skipped file."""
        with open(self.skipped_csv, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([datetime.now().isoformat(), file_id, name, url, size, extension, reason])


class BoxFileIndexWorker:
    """
    Ray worker for indexing downloaded Box files in parallel.

    This worker handles the CPU/GPU-intensive indexing phase while
    the main crawler handles sequential downloads from Box API.
    Files are automatically deleted after indexing to save disk space.
    """

    def __init__(self, cfg: DictConfig, indexer: Indexer, tracker_actor):
        """
        Initialize the Box file index worker.

        Args:
            cfg: Configuration object
            indexer: Vectara indexer instance
            tracker_actor: Ray actor reference for CSV tracking
        """
        self.cfg = cfg
        self.indexer = indexer
        self.tracker_actor = tracker_actor

    def setup(self):
        """Setup the worker - initialize indexer, logging, and file processor."""
        setup_logging()

        # Initialize the indexer session and basic setup
        self.indexer.setup(use_playwright=False)

        # Explicitly initialize file_processor with image/table summarizers
        # This is critical - without this, summarizers will be None
        self.indexer._init_processors()

        # Verify file processor was initialized correctly
        if hasattr(self.indexer, 'file_processor') and self.indexer.file_processor:
            logging.info("BoxFileIndexWorker initialized with file processor")
        else:
            logging.warning("BoxFileIndexWorker: file_processor not initialized")

        logging.info("BoxFileIndexWorker setup complete")

    def index_file(self, file_path: str, metadata: Dict[str, Any]) -> int:
        """
        Index a downloaded file to Vectara, track result, and delete file.

        Args:
            file_path: Local path to the downloaded file
            metadata: File metadata including file_id, url, etc.

        Returns:
            0 on success, -1 on failure
        """
        file_name = metadata.get("title", os.path.basename(file_path))
        file_id = metadata.get("file_id")
        url = metadata.get("url")
        size = metadata.get("size", 0)
        extension = os.path.splitext(file_name)[1]

        try:
            logging.info(f"Worker indexing: {file_name}")
            success = self.indexer.index_file(
                filename=file_path,
                uri=url,
                metadata=metadata,
                id=file_id,
            )

            if not success:
                logging.warning(f"Failed to index {file_name}")
                # Send tracking request to tracker actor (non-blocking)
                self.tracker_actor.track_failed.remote(file_id, file_name, url, size, extension, "Indexing returned False")
                # Delete file even on failure to save space
                self._cleanup_file(file_path)
                return -1

            logging.info(f"Successfully indexed: {file_name}")
            # Send tracking request to tracker actor (non-blocking)
            self.tracker_actor.track_indexed.remote(file_id, file_name, url, size, extension)

            # Delete file after successful indexing
            self._cleanup_file(file_path)
            return 0

        except Exception as e:
            import traceback
            error_msg = str(e)
            logging.error(
                f"Error indexing {file_name}: {e}, traceback={traceback.format_exc()}"
            )
            # Send tracking request to tracker actor (non-blocking)
            self.tracker_actor.track_failed.remote(file_id, file_name, url, size, extension, error_msg)

            # Delete file even on error to save space
            self._cleanup_file(file_path)
            return -1

    def _cleanup_file(self, file_path: str):
        """Delete the local file after processing."""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.debug(f"Deleted file: {file_path}")
        except Exception as e:
            logging.warning(f"Failed to delete file {file_path}: {e}")


class BoxCrawler(Crawler):
    """
    Crawler for Box cloud storage.

    Configuration (in YAML):
        box_crawler:
            # Authentication (choose one)
            auth_type: jwt  # or 'oauth'

            # JWT Authentication (recommended for production)
            jwt_config_file: box_config.json  # Path to Box JWT config file

            # OAuth Authentication (alternative)
            oauth_credentials_file: oauth_creds.json  # Path to OAuth credentials
            # OR provide directly:
            client_id: YOUR_CLIENT_ID
            client_secret: YOUR_CLIENT_SECRET
            access_token: YOUR_ACCESS_TOKEN

            # As-User Authentication (optional, for enterprise-wide access)
            as_user_id: "USER_ID"  # User ID to impersonate

            # Folder Configuration
            folder_ids:
                - "0"  # Root folder ID (0 = all accessible folders)
                - "123456"  # Specific folder ID

            # File Filtering
            file_extensions: [".pdf", ".docx"]  # Include only these extensions (empty = all)
            exclude_extensions: [".csv", ".xlsx"]  # Exclude these extensions

            # Download Settings
            download_path: /tmp/box_downloads  # Local download directory
            max_files: 100  # Maximum files to download (0 = unlimited)
            recursive: true  # Traverse subfolders recursively

            # Ray Parallel Processing
            ray_workers: 0  # Number of Ray workers for parallel indexing
                           # 0 = sequential (no Ray), -1 = auto-detect CPUs
                           # >0 = specific number of workers (e.g., 4)

            # Processing Options
            skip_indexing: false  # true = download only, false = download and index
            generate_report: false  # true = generate structure report, false = download files
            report_path: /tmp/box_structure_report.json  # Report output path
    """

    def __init__(
        self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str
    ) -> None:
        """
        Initialize the Box Crawler.

        Args:
            cfg: Configuration object
            endpoint: Vectara API endpoint
            corpus_key: Vectara corpus key
            api_key: Vectara API key
        """
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.box_cfg = cfg.box_crawler
        self.client: Optional[Client] = None

        # Configuration
        self.download_path = self.box_cfg.get("download_path", "/tmp/box_downloads")
        self.file_extensions = self.box_cfg.get("file_extensions", [])
        self.exclude_extensions = self.box_cfg.get("exclude_extensions", [])
        self.max_files = self.box_cfg.get("max_files", 0)
        self.recursive = self.box_cfg.get("recursive", True)
        self.skip_indexing = self.box_cfg.get("skip_indexing", False)
        self.generate_report = self.box_cfg.get("generate_report", False)
        self.report_path = self.box_cfg.get(
            "report_path", "/tmp/box_structure_report.json"
        )

        # Tracking directory for CSV files
        self.tracking_dir = self.box_cfg.get("tracking_dir", "/tmp/box_tracking")
        os.makedirs(self.tracking_dir, exist_ok=True)

        # Initialize CSV tracker
        self.tracker = BoxCrawlerTracker(self.tracking_dir)

        # State
        self.files_downloaded = 0

        # Report data structure
        self.report_data = {
            "scan_date": datetime.now().isoformat(),
            "authenticated_user": None,
            "total_folders": 0,
            "total_files": 0,
            "total_size_bytes": 0,
            "folders": [],
        }

        # Create download directory
        os.makedirs(self.download_path, exist_ok=True)

        logging.info("Box Crawler initialized")
        logging.info(f"Download path: {self.download_path}")
        logging.info(f"Tracking dir: {self.tracking_dir}")
        logging.info(f"Skip indexing: {self.skip_indexing}")
        logging.info(f"Generate report: {self.generate_report}")

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
        # If absolute path, verify it exists
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
            f"Credentials file '{file_path}' not found. Searched in:\n"
            + "\n".join(f"  - {p}" for p in search_paths)
        )

    def _authenticate(self) -> Client:
        """
        Authenticate with Box using JWT or OAuth2.

        Returns:
            Authenticated Box client

        Raises:
            ValueError: If auth_type is invalid or required credentials are missing
        """
        auth_type = self.box_cfg.get("auth_type", "jwt").lower()

        if auth_type == "jwt":
            return self._authenticate_jwt()
        elif auth_type == "oauth":
            return self._authenticate_oauth()
        else:
            raise ValueError(
                f"Unsupported auth_type: {auth_type}. Use 'jwt' or 'oauth'"
            )

    def _authenticate_jwt(self) -> Client:
        """
        Authenticate using JWT (JSON Web Token).

        Requires a Box JWT config file from Box Developer Console.
        Supports as-user authentication for enterprise-wide access.

        Returns:
            Authenticated Box client

        Raises:
            ValueError: If jwt_config_file is not provided
            FileNotFoundError: If jwt_config_file cannot be found
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

        # Test authentication and get user info
        user = client.user().get()
        logging.info(f"Successfully authenticated as: {user.name} ({user.login})")

        # Store user info in report
        if self.generate_report:
            self.report_data["authenticated_user"] = {
                "name": user.name,
                "login": user.login,
                "id": user.id,
            }

        return client

    def _authenticate_oauth(self) -> Client:
        """
        Authenticate using OAuth 2.0.

        Requires client_id, client_secret, and access_token.
        Can load from oauth_credentials_file or directly from config.

        Returns:
            Authenticated Box client

        Raises:
            ValueError: If required OAuth credentials are missing
            FileNotFoundError: If oauth_credentials_file cannot be found
        """
        # Try to load from credentials file first
        oauth_credentials_file = self.box_cfg.get("oauth_credentials_file")
        if oauth_credentials_file:
            oauth_credentials_file = self._resolve_credentials_path(
                oauth_credentials_file
            )

            logging.info(f"Loading OAuth credentials from {oauth_credentials_file}")
            with open(oauth_credentials_file, "r") as f:
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
            raise ValueError(
                "client_id, client_secret, and access_token are required for OAuth. "
                "Provide them via oauth_credentials_file or directly in config."
            )

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

    def _is_excluded_file(self, file_name: str) -> bool:
        """
        Check if file extension is in the exclude list.

        Args:
            file_name: Name of the file

        Returns:
            True if file should be excluded, False otherwise
        """
        _, ext = os.path.splitext(file_name)
        ext_lower = ext.lower()
        return ext_lower in [e.lower() for e in self.exclude_extensions]

    def _should_index_file(self, file_name: str) -> bool:
        """
        Check if file should be indexed based on extension filters.

        Logic:
        - If exclude_extensions is set, don't index files with those extensions
        - If file_extensions is set (whitelist), only index those extensions
        - If neither is set, index all files

        Args:
            file_name: Name of the file

        Returns:
            True if file should be indexed, False otherwise
        """
        _, ext = os.path.splitext(file_name)
        ext_lower = ext.lower()

        # Check exclude list first (blacklist)
        if self.exclude_extensions:
            if ext_lower in [e.lower() for e in self.exclude_extensions]:
                return False

        # Check include list (whitelist)
        if self.file_extensions:
            if ext_lower not in [e.lower() for e in self.file_extensions]:
                return False

        return True

    def _download_file(
        self, file_item, ray_mode: bool = False
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Download a file from Box to local storage.

        Excluded files are saved to the inspection folder but not indexed.

        Args:
            file_item: Box file object
            ray_mode: If True, return (file_path, metadata) for Ray processing.
                     If False, index immediately (legacy behavior).

        Returns:
            - If ray_mode=True: Tuple of (file_path, metadata) or None
            - If ray_mode=False: file_path string or None (legacy)
        """
        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            logging.info(f"Reached max_files limit ({self.max_files})")
            return None

        file_name = file_item.name
        file_id = file_item.id
        is_excluded = self._is_excluded_file(file_name)

        try:
            # Create a sanitized filename
            safe_filename = "".join(
                c for c in file_name if c.isalnum() or c in (" ", ".", "_", "-")
            ).rstrip()

            # Determine download path based on whether file is excluded
            if is_excluded:
                # Save excluded files directly to inspection folder
                inspection_dir = self.cfg.vectara.get("output_dir", "/tmp/box_inspection")
                os.makedirs(inspection_dir, exist_ok=True)
                local_path = os.path.join(inspection_dir, f"{file_id}_{safe_filename}")
                logging.info(
                    f"Downloading excluded file to inspection folder: {file_name} (ID: {file_id})"
                )
            else:
                local_path = os.path.join(
                    self.download_path, f"{file_id}_{safe_filename}"
                )
                logging.info(f"Downloading: {file_name} (ID: {file_id})")

            # Download file content
            with open(local_path, "wb") as output_file:
                file_item.download_to(output_file)

            file_size = os.path.getsize(local_path)

            if is_excluded:
                logging.info(
                    f"Downloaded excluded file: {file_name} ({file_size:,} bytes) -> {local_path}"
                )
            else:
                logging.info(
                    f"Downloaded: {file_name} ({file_size:,} bytes) -> {local_path}"
                )

            self.files_downloaded += 1

            # Get file metadata
            metadata = {
                "source": "Box",
                "title": file_name,
                "file_id": file_id,
                "url": f"https://app.box.com/file/{file_id}",
                "size": file_size,
                "created_at": (
                    str(file_item.created_at)
                    if hasattr(file_item, "created_at")
                    else None
                ),
                "modified_at": (
                    str(file_item.modified_at)
                    if hasattr(file_item, "modified_at")
                    else None
                ),
                "created_by": (
                    file_item.created_by.name
                    if hasattr(file_item, "created_by") and file_item.created_by
                    else None
                ),
                "modified_by": (
                    file_item.modified_by.name
                    if hasattr(file_item, "modified_by") and file_item.modified_by
                    else None
                ),
            }

            # Return different results based on mode
            if ray_mode:
                # Ray mode: return tuple for parallel processing
                if is_excluded:
                    # Track skipped file and delete it
                    extension = os.path.splitext(file_name)[1]
                    self.tracker.track_skipped(
                        file_id, file_name, metadata["url"], file_size, extension,
                        "Excluded by extension filter"
                    )
                    # Delete skipped file to save space
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    return None
                return (local_path, metadata)
            else:
                # Legacy mode: index immediately
                if not is_excluded and not self.skip_indexing:
                    logging.info(f"Indexing file: {file_name}")
                    try:
                        success = self.indexer.index_file(
                            filename=local_path,
                            uri=metadata["url"],
                            metadata=metadata,
                            id=file_id,
                        )
                        if not success:
                            logging.warning(
                                f"Failed to index {file_name} - file saved to inspection folder"
                            )
                    except Exception as index_error:
                        logging.warning(
                            f"Failed to index {file_name}: {str(index_error)} - file saved to inspection folder"
                        )
                elif is_excluded:
                    logging.info(f"Skipping indexing for excluded file type: {file_name}")
                    # Track skipped file
                    extension = os.path.splitext(file_name)[1]
                    self.tracker.track_skipped(
                        file_id, file_name, metadata["url"], file_size, extension,
                        "Excluded by extension filter"
                    )

                return local_path

        except Exception as e:
            logging.error(f"Error downloading file {file_name}: {str(e)}")
            return None

    def _collect_folder_info(self, folder_id: str, path: str = "") -> Dict[str, Any]:
        """
        Recursively collect folder and file information for report.

        Args:
            folder_id: Box folder ID
            path: Current folder path

        Returns:
            Dictionary containing folder structure and file information
        """
        try:
            # Get folder with full metadata
            folder = self.client.folder(folder_id).get(
                fields=[
                    "name",
                    "id",
                    "created_at",
                    "modified_at",
                    "size",
                    "owned_by",
                    "created_by",
                    "modified_by",
                ]
            )

            current_path = f"{path}/{folder.name}" if path else folder.name

            folder_info = {
                "name": folder.name,
                "id": folder.id,
                "path": current_path,
                "created_at": (
                    str(folder.created_at)
                    if hasattr(folder, "created_at") and folder.created_at
                    else None
                ),
                "modified_at": (
                    str(folder.modified_at)
                    if hasattr(folder, "modified_at") and folder.modified_at
                    else None
                ),
                "owner": (
                    folder.owned_by.name
                    if hasattr(folder, "owned_by") and folder.owned_by
                    else None
                ),
                "files": [],
                "subfolders": [],
            }

            # Get items in the folder with proper paging
            # Box SDK handles paging internally when iterating
            items = folder.get_items(
                fields=[
                    "name",
                    "id",
                    "type",
                    "size",
                    "created_at",
                    "modified_at",
                    "created_by",
                    "modified_by",
                    "extension",
                ],
            )

            folder_file_count = 0
            folder_size = 0

            for item in items:
                if item.type == "file":
                    file_info = {
                        "name": item.name,
                        "id": item.id,
                        "size": (
                            item.size
                            if hasattr(item, "size") and item.size
                            else 0
                        ),
                        "extension": (
                            item.extension
                            if hasattr(item, "extension")
                            else os.path.splitext(item.name)[1]
                        ),
                        "created_at": (
                            str(item.created_at)
                            if hasattr(item, "created_at") and item.created_at
                            else None
                        ),
                        "modified_at": (
                            str(item.modified_at)
                            if hasattr(item, "modified_at") and item.modified_at
                            else None
                        ),
                        "created_by": (
                            item.created_by.name
                            if hasattr(item, "created_by") and item.created_by
                            else None
                        ),
                        "url": f"https://app.box.com/file/{item.id}",
                    }
                    folder_info["files"].append(file_info)
                    folder_file_count += 1
                    folder_size += file_info["size"]

                elif item.type == "folder" and self.recursive:
                    # Recursively collect subfolder info
                    subfolder_info = self._collect_folder_info(item.id, current_path)
                    folder_info["subfolders"].append(subfolder_info)
                    folder_file_count += subfolder_info.get("file_count", 0)
                    folder_size += subfolder_info.get("total_size", 0)

            folder_info["file_count"] = folder_file_count
            folder_info["total_size"] = folder_size

            # Update global counters
            self.report_data["total_folders"] += 1
            self.report_data["total_files"] += len(folder_info["files"])
            self.report_data["total_size_bytes"] += folder_size

            return folder_info

        except Exception as e:
            logging.error(f"Error collecting info for folder {folder_id}: {str(e)}")
            return {
                "name": f"Error accessing folder {folder_id}",
                "id": folder_id,
                "error": str(e),
                "files": [],
                "subfolders": [],
            }

    def _crawl_folder(
        self, folder_id: str, path: str = "", ray_mode: bool = False
    ) -> Optional[List[Tuple[str, Dict[str, Any]]]]:
        """
        Recursively crawl a Box folder and download files.

        Args:
            folder_id: Box folder ID (use "0" for root folder)
            path: Current folder path for logging
            ray_mode: If True, collect files for Ray processing instead of indexing

        Returns:
            - If ray_mode=True: List of (file_path, metadata) tuples
            - If ray_mode=False: None (legacy behavior)
        """
        files_to_process = [] if ray_mode else None

        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            return files_to_process

        try:
            # Get the folder object and its items
            folder = self.client.folder(folder_id).get(fields=["name", "id"])
            current_path = f"{path}/{folder.name}" if path else folder.name
            logging.info(f"Crawling folder: {current_path} (ID: {folder_id})")

            # Get items in the folder with proper paging
            # Box SDK handles paging internally when iterating
            items = folder.get_items()

            for item in items:
                if self.max_files > 0 and self.files_downloaded >= self.max_files:
                    break

                if item.type == "file":
                    result = self._download_file(item, ray_mode=ray_mode)
                    if ray_mode and result:
                        files_to_process.append(result)
                elif item.type == "folder" and self.recursive:
                    if ray_mode:
                        subfolder_files = self._crawl_folder(
                            item.id, current_path, ray_mode=True
                        )
                        if subfolder_files:
                            files_to_process.extend(subfolder_files)
                    else:
                        self._crawl_folder(item.id, current_path, ray_mode=False)

        except Exception as e:
            logging.error(f"Error crawling folder {folder_id}: {str(e)}")

        return files_to_process

    def _crawl_folder_streaming(
        self, folder_id: str, path: str = ""
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Generator-style crawl that yields files as they're downloaded.

        Args:
            folder_id: Box folder ID (use "0" for root folder)
            path: Current folder path for logging

        Yields:
            Tuple of (file_path, metadata) for each downloaded file
        """
        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            return []

        files_yielded = []

        try:
            # Get the folder object and its items
            folder = self.client.folder(folder_id).get(fields=["name", "id"])
            current_path = f"{path}/{folder.name}" if path else folder.name
            logging.info(f"Crawling folder: {current_path} (ID: {folder_id})")

            # Get items in the folder with proper paging
            # Box SDK handles paging internally when iterating
            items = folder.get_items()

            for item in items:
                if self.max_files > 0 and self.files_downloaded >= self.max_files:
                    break

                if item.type == "file":
                    result = self._download_file(item, ray_mode=True)
                    if result:
                        files_yielded.append(result)
                elif item.type == "folder" and self.recursive:
                    # Recursively get files from subfolders
                    subfolder_files = self._crawl_folder_streaming(item.id, current_path)
                    files_yielded.extend(subfolder_files)

        except Exception as e:
            logging.error(f"Error crawling folder {folder_id}: {str(e)}")

        return files_yielded

    def _crawl_with_ray(
        self, folder_ids: List[str], ray_workers: int
    ) -> None:
        """
        Crawl Box folders with Ray parallel processing using streaming pattern.

        Uses a streaming producer-consumer pattern:
        - Main thread downloads files sequentially (respects Box API rate limits)
        - As each file is downloaded, it's immediately sent to an available Ray worker
        - Ray workers process files in parallel (CPU/GPU intensive indexing)
        - Download and indexing happen concurrently for maximum throughput
        - Dedicated CSV tracker actor handles all tracking (no race conditions)

        Args:
            folder_ids: List of Box folder IDs to crawl
            ray_workers: Number of Ray workers for parallel indexing
        """
        logging.info("=" * 80)
        logging.info(f"RAY STREAMING PARALLEL PROCESSING - {ray_workers} workers")
        logging.info("=" * 80)
        logging.info("Download and indexing happen concurrently:")
        logging.info("  - Main thread downloads files sequentially")
        logging.info("  - Ray workers index files in parallel as they're downloaded")
        logging.info("  - Dedicated CSV tracker actor handles all tracking")
        logging.info("=" * 80)

        try:
            # Clear browser/playwright and file_processor from indexer (not serializable for Ray)
            # Each worker will recreate its own file_processor with summarizers
            self.indexer.p = self.indexer.browser = None
            self.indexer.file_processor = None

            # Initialize Ray with memory monitoring
            ray.init(
                num_cpus=ray_workers,
                log_to_driver=True,
                include_dashboard=False,
                _metrics_export_port=None,  # Disable metrics export (suppresses warnings)
                _system_config={
                    "automatic_object_spilling_enabled": True,
                    "object_spilling_config": json.dumps({
                        "type": "filesystem",
                        "params": {"directory_path": "/tmp/ray_spill"}
                    }),
                    "enable_metrics_collection": False,  # Disable metrics collection
                }
            )

            # Create dedicated CSV tracker actor (single writer, no race conditions)
            # Use 0 CPUs for tracker (lightweight CSV writes only)
            tracker_actor = ray.remote(num_cpus=0)(CSVTrackerActor).remote(self.tracking_dir)
            logging.info("Created dedicated CSV tracker actor")

            # Create Ray indexing workers with tracker actor reference
            # Note: Not reserving memory explicitly - let Ray use available memory naturally
            # Each worker will use ~4-6GB for docling models + processing
            # With 24GB Docker: 2 workers is safe, more may cause OOM
            actors = [
                ray.remote(num_cpus=1)(BoxFileIndexWorker).remote(
                    self.cfg, self.indexer, tracker_actor
                )
                for _ in range(ray_workers)
            ]

            # Setup all workers
            ray.get([actor.setup.remote() for actor in actors])

            # Track pending tasks and results
            pending_tasks = []
            completed_count = 0
            failed_count = 0
            actor_index = 0

            # Process each folder
            for folder_id in folder_ids:
                # Download files and immediately submit to workers
                # We download in chunks to avoid holding all files in memory
                folder_items = self._crawl_folder_streaming(str(folder_id))

                for file_path, metadata in folder_items:
                    # Round-robin assignment to actors
                    actor = actors[actor_index % len(actors)]
                    actor_index += 1

                    # Submit task to actor (non-blocking)
                    task = actor.index_file.remote(file_path, metadata)
                    pending_tasks.append(task)

                    # Log progress
                    file_name = metadata.get("title", "unknown")
                    logging.info(
                        f"Submitted to worker {(actor_index-1) % len(actors)}: {file_name} "
                        f"(pending: {len(pending_tasks)})"
                    )

                    # Periodically collect completed tasks to avoid memory buildup
                    if len(pending_tasks) >= ray_workers * 2:
                        # Wait for at least one task to complete
                        ready_tasks, pending_tasks = ray.wait(
                            pending_tasks, num_returns=1, timeout=None
                        )

                        # Process completed tasks
                        results = ray.get(ready_tasks)
                        for result in results:
                            if result == 0:
                                completed_count += 1
                            else:
                                failed_count += 1

                        logging.info(
                            f"Progress: {completed_count} indexed, {failed_count} failed, "
                            f"{len(pending_tasks)} pending"
                        )

            # Wait for all remaining tasks to complete
            if pending_tasks:
                logging.info(f"Waiting for {len(pending_tasks)} remaining tasks...")
                remaining_results = ray.get(pending_tasks)
                for result in remaining_results:
                    if result == 0:
                        completed_count += 1
                    else:
                        failed_count += 1

            logging.info("=" * 80)
            logging.info(f"Ray streaming processing complete:")
            logging.info(f"  Successfully indexed: {completed_count}")
            logging.info(f"  Failed to index: {failed_count}")
            logging.info(f"  Total processed: {completed_count + failed_count}")
            logging.info("=" * 80)
            logging.info(f"CSV tracking files saved to: {self.tracking_dir}")
            logging.info(f"  - indexed.csv: Successfully indexed files")
            logging.info(f"  - failed.csv: Files that failed indexing")
            logging.info(f"  - skipped.csv: Files skipped by filters")

        finally:
            # Shutdown Ray
            ray.shutdown()

    def _save_report(self) -> None:
        """Save the collected folder/file information to a report file."""
        try:
            # Create report directory if needed
            report_dir = os.path.dirname(self.report_path)
            if report_dir:
                os.makedirs(report_dir, exist_ok=True)

            # Format total size for readability
            total_gb = self.report_data["total_size_bytes"] / (1024**3)
            self.report_data["total_size_gb"] = round(total_gb, 2)

            # Save as JSON
            with open(self.report_path, "w") as f:
                json.dump(self.report_data, f, indent=2)

            logging.info("=" * 80)
            logging.info(f"REPORT SAVED: {self.report_path}")
            logging.info("=" * 80)
            logging.info(f"Total Folders: {self.report_data['total_folders']}")
            logging.info(f"Total Files: {self.report_data['total_files']}")
            logging.info(
                f"Total Size: {self.report_data['total_size_gb']:.2f} GB "
                f"({self.report_data['total_size_bytes']:,} bytes)"
            )
            logging.info("=" * 80)

        except Exception as e:
            logging.error(f"Error saving report: {str(e)}")

    def crawl(self) -> None:
        """
        Main crawl method - authenticates and generates report or downloads files from Box.

        Raises:
            Exception: If authentication or crawl fails
        """
        try:
            # Authenticate
            self.client = self._authenticate()

            # Get folder IDs to crawl (default to root folder with ID '0')
            folder_ids = self.box_cfg.get("folder_ids", ["0"])
            # Convert OmegaConf ListConfig to regular Python list
            folder_ids = OmegaConf.to_container(folder_ids, resolve=True)
            if not isinstance(folder_ids, list):
                folder_ids = [folder_ids]

            # If folder_id is "0", get all root-level folders the user has access to
            actual_folders = []
            for folder_id in folder_ids:
                folder_id_str = str(folder_id)
                logging.info(
                    f"Processing folder_id: {folder_id_str} (type: {type(folder_id)})"
                )

                if folder_id_str == "0":
                    logging.info("Fetching all root-level folders accessible to user")
                    try:
                        root_folder = self.client.folder("0")
                        # Box SDK handles paging internally when iterating
                        root_items = root_folder.get_items()

                        item_count = 0
                        # Collect all folders at root level
                        for item in root_items:
                            item_count += 1
                            if item.type == "folder":
                                actual_folders.append(item.id)
                                logging.info(
                                    f"Found root folder: {item.name} (ID: {item.id})"
                                )
                            elif item.type == "file":
                                logging.info(f"Found root file: {item.name}")
                                if not self.generate_report:
                                    # Only download if not generating report
                                    self._download_file(item)

                        logging.info(
                            f"Found {item_count} items at root level ({len(actual_folders)} folders)"
                        )
                    except Exception as e:
                        logging.error(f"Error fetching root-level items: {str(e)}")
                        logging.exception(e)
                else:
                    actual_folders.append(folder_id_str)

            logging.info(f"Starting Box crawl for {len(actual_folders)} folder(s)")

            # Generate report or download files
            if self.generate_report:
                logging.info("=" * 80)
                logging.info("GENERATING STRUCTURE REPORT (no downloads)")
                logging.info("=" * 80)

                # Collect folder structure information
                for folder_id in actual_folders:
                    folder_info = self._collect_folder_info(str(folder_id))
                    self.report_data["folders"].append(folder_info)

                # Save the report
                self._save_report()

                logging.info("Report generation complete!")
            else:
                # Check if Ray parallel processing is enabled
                ray_workers = self.box_cfg.get("ray_workers", 0)
                if ray_workers == -1:
                    ray_workers = psutil.cpu_count(logical=True)

                # Crawl and download files
                if ray_workers > 0 and RAY_AVAILABLE and not self.skip_indexing:
                    # Ray mode: download first, then index in parallel
                    self._crawl_with_ray(actual_folders, ray_workers)
                else:
                    # Sequential mode: download and index together
                    if ray_workers > 0 and not RAY_AVAILABLE:
                        logging.warning(
                            "Ray workers configured but Ray is not available. "
                            "Falling back to sequential processing."
                        )
                    for folder_id in actual_folders:
                        self._crawl_folder(str(folder_id), ray_mode=False)

                logging.info(
                    f"Box crawl complete. Downloaded {self.files_downloaded} files to {self.download_path}"
                )

                if self.skip_indexing:
                    logging.info("Files were NOT indexed (skip_indexing=true)")
                else:
                    logging.info("Files were indexed to Vectara")

        except Exception as e:
            logging.error(f"Error during Box crawl: {str(e)}")
            raise
