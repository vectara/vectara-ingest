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
from core.dataframe_parser import supported_by_dataframe_parser, process_dataframe_file, DataframeParser
from core.summary import TableSummarizer

try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    RAY_AVAILABLE = False
    logging.warning("Ray is not available. Install with: pip install ray")


def create_dataframe_parser(cfg: DictConfig, indexer: Indexer) -> DataframeParser:
    """
    Create a DataframeParser instance for Excel/CSV file processing.

    Args:
        cfg: Configuration object
        indexer: Vectara indexer instance

    Returns:
        Configured DataframeParser instance
    """
    model_config = cfg.doc_processing.get("model_config", {})
    if "text" in model_config:
        table_summarizer = TableSummarizer(cfg, model_config["text"])
    else:
        table_summarizer = TableSummarizer(cfg, None)

    df_config = cfg.get("dataframe_processing", {})
    return DataframeParser(cfg, df_config, indexer, table_summarizer)


class BoxCrawlerTracker:
    """
    CSV tracker for Box crawler file status (indexed/failed/skipped).

    Used directly in sequential mode, or wrapped by CSVTrackerActor for Ray parallel mode.
    """

    def __init__(self, tracking_dir: str, preserve_existing: bool = False):
        """
        Initialize the tracker.

        Args:
            tracking_dir: Directory to store CSV tracking files
            preserve_existing: If True, preserve existing CSV files (append mode).
                             If False, overwrite existing files (fresh start).
        """
        self.tracking_dir = tracking_dir
        os.makedirs(tracking_dir, exist_ok=True)

        self.indexed_csv = os.path.join(tracking_dir, "indexed.csv")
        self.failed_csv = os.path.join(tracking_dir, "failed.csv")
        self.skipped_csv = os.path.join(tracking_dir, "skipped.csv")

        # Initialize CSV files with headers
        self._init_csv_file(self.indexed_csv, ["timestamp", "file_id", "name", "url", "size", "extension"], preserve_existing)
        self._init_csv_file(self.failed_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "error"], preserve_existing)
        self._init_csv_file(self.skipped_csv, ["timestamp", "file_id", "name", "url", "size", "extension", "reason"], preserve_existing)

    def _init_csv_file(self, csv_path: str, headers: List[str], preserve_existing: bool = False):
        """Initialize CSV file with headers."""
        if not preserve_existing or not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def get_indexed_file_ids(self) -> set:
        """Get set of already indexed file IDs from CSV."""
        indexed_ids = set()
        if os.path.exists(self.indexed_csv):
            try:
                with open(self.indexed_csv, "r", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if "file_id" in row:
                            indexed_ids.add(row["file_id"])
                logging.info(f"Loaded {len(indexed_ids)} already-indexed file IDs from {self.indexed_csv}")
            except Exception as e:
                logging.warning(f"Failed to load indexed file IDs: {e}")
        return indexed_ids

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


class CSVTrackerActor:
    """
    Ray actor wrapper for thread-safe CSV tracking in parallel mode.

    Wraps BoxCrawlerTracker to provide thread-safe access from multiple Ray workers.
    All workers send tracking requests to this single actor, eliminating race conditions.
    """

    def __init__(self, tracking_dir: str, preserve_existing: bool = False):
        """Initialize the actor with a BoxCrawlerTracker instance."""
        self._tracker = BoxCrawlerTracker(tracking_dir, preserve_existing)
        logging.info(f"CSVTrackerActor initialized - tracking dir: {tracking_dir}, preserve_existing: {preserve_existing}")

    def get_indexed_file_ids(self) -> set:
        """Get set of already indexed file IDs from CSV."""
        return self._tracker.get_indexed_file_ids()

    def track_indexed(self, file_id: str, name: str, url: str, size: int, extension: str):
        """Record a successfully indexed file (called remotely by workers)."""
        self._tracker.track_indexed(file_id, name, url, size, extension)

    def track_failed(self, file_id: str, name: str, url: str, size: int, extension: str, error: str):
        """Record a failed file (called remotely by workers)."""
        self._tracker.track_failed(file_id, name, url, size, extension, error)

    def track_skipped(self, file_id: str, name: str, url: str, size: int, extension: str, reason: str):
        """Record a skipped file (called remotely by workers)."""
        self._tracker.track_skipped(file_id, name, url, size, extension, reason)


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

        # Check if file deletion should be disabled
        box_config = cfg.get("box_crawler", {})
        self.delete_after_index = box_config.get("delete_after_index", True)

    def setup(self):
        """Setup the worker - initialize indexer, logging, and file processor."""
        setup_logging()

        # Initialize the indexer session and basic setup
        self.indexer.setup(use_playwright=False)

        # Explicitly initialize file_processor with image/table summarizers
        # This is critical - without this, summarizers will be None
        self.indexer._init_processors()

        # Initialize DataframeParser for Excel/CSV files
        self.df_parser = create_dataframe_parser(self.cfg, self.indexer)

        # Verify file processor was initialized correctly
        if hasattr(self.indexer, 'file_processor') and self.indexer.file_processor:
            logging.info("BoxFileIndexWorker initialized with file processor")
        else:
            logging.warning("BoxFileIndexWorker: file_processor not initialized")

        logging.info("BoxFileIndexWorker setup complete (with DataframeParser)")

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

            # Route Excel/CSV files to DataframeParser instead of docling
            if supported_by_dataframe_parser(file_path):
                logging.info(f"Processing as dataframe file: {file_name}")
                df_config = self.cfg.get("dataframe_processing", {})
                success = process_dataframe_file(
                    file_path=file_path,
                    metadata=metadata,
                    doc_id=file_id,
                    df_parser=self.df_parser,
                    df_config=df_config,
                    source_name="box"
                )
            else:
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
        """Delete the local file after processing (if enabled)."""
        if not self.delete_after_index:
            logging.debug(f"Keeping file: {file_path} (delete_after_index=False)")
            return

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
            skip_indexed: false  # true = skip files already in indexed.csv (resume capability)
            delete_after_index: true  # true = delete files after indexing, false = keep files
            generate_report: false  # true = generate structure report, false = download files
            report_path: /tmp/box_structure_report.json  # Report output path
            tracking_dir: /data/box_tracking  # Directory for CSV tracking files

            # Permission Collection (optional)
            collect_permissions: false  # true = collect folder collaborations
            # When enabled, file metadata includes "permissions" list (group names and user emails)
            # Permissions are inherited from parent folders - useful for Okta/SSO integration
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

        # Skip already indexed files option
        self.skip_indexed = self.box_cfg.get("skip_indexed", False)
        self.indexed_file_ids = set()

        # Permission collection option
        self.collect_permissions = self.box_cfg.get("collect_permissions", False)
        self._permissions_cache: Dict[str, List[Dict[str, Any]]] = {}  # folder_id -> collaborations

        # Initialize CSV tracker
        # If skip_indexed is True, preserve existing CSV files (append mode)
        # If skip_indexed is False, start fresh (overwrite mode)
        self.tracker = BoxCrawlerTracker(self.tracking_dir, preserve_existing=self.skip_indexed)

        if self.skip_indexed:
            self.indexed_file_ids = self.tracker.get_indexed_file_ids()
            logging.info(f"Skip indexed enabled: will skip {len(self.indexed_file_ids)} already-indexed files")
        else:
            logging.info("Starting fresh crawl - CSV tracking files will be overwritten")

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
        logging.info(f"Collect permissions: {self.collect_permissions}")

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

    def _get_folder_collaborations(self, folder_id: str, folder_path: str = "") -> List[Dict[str, Any]]:
        """
        Get group collaborations for a folder from Box API.

        Only collects group permissions, skips individual user permissions.
        Uses caching to avoid redundant API calls for the same folder.

        Args:
            folder_id: Box folder ID
            folder_path: Folder path for logging context

        Returns:
            List of group collaboration dicts with type, name, id, role, status, source info
        """
        # Check cache first
        if folder_id in self._permissions_cache:
            return self._permissions_cache[folder_id]

        collaborations = []
        try:
            folder = self.client.folder(folder_id)
            collabs = folder.get_collaborations()

            for collab in collabs:
                accessible_by = collab.accessible_by
                if accessible_by is None:
                    continue

                # Only collect group permissions, skip users
                collab_type = accessible_by.type if hasattr(accessible_by, 'type') else "unknown"
                if collab_type != "group":
                    continue

                collab_info = {
                    "type": collab_type,
                    "name": accessible_by.name if hasattr(accessible_by, 'name') else None,
                    "id": accessible_by.id if hasattr(accessible_by, 'id') else None,
                    "role": collab.role if hasattr(collab, 'role') else None,
                    "status": collab.status if hasattr(collab, 'status') else None,
                    "source_folder_id": folder_id,
                    "source_folder_path": folder_path,
                }
                collaborations.append(collab_info)

            logging.debug(f"Retrieved {len(collaborations)} collaborations for folder {folder_id}")

        except Exception as e:
            logging.warning(f"Failed to get collaborations for folder {folder_id}: {e}")

        # Cache the result
        self._permissions_cache[folder_id] = collaborations
        return collaborations

    def _merge_permissions(
        self,
        parent_perms: List[Dict[str, Any]],
        folder_perms: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge parent folder permissions with current folder permissions.

        Permissions are accumulated (child folders add to parent permissions).
        Deduplication is done by type+id to avoid duplicates.

        Args:
            parent_perms: Permissions inherited from parent folders
            folder_perms: Permissions from the current folder

        Returns:
            Merged list of permissions
        """
        # Build dict keyed by type:id for deduplication
        merged = {}

        # Add parent permissions first
        for perm in parent_perms:
            key = f"{perm.get('type', 'unknown')}:{perm.get('id', 'unknown')}"
            merged[key] = perm

        # Add folder permissions (new ones only; if type:id already exists from parent, skip duplicate)
        for perm in folder_perms:
            key = f"{perm.get('type', 'unknown')}:{perm.get('id', 'unknown')}"
            if key not in merged:
                merged[key] = perm

        return list(merged.values())

    def _build_permissions_list(self, collaborations: List[Dict[str, Any]]) -> List[str]:
        """
        Build a simple permissions list from group collaborations for Vectara filtering.

        Args:
            collaborations: List of collaboration dicts (groups only)

        Returns:
            List of group names, e.g., ["Engineering", "Marketing"]
        """
        permissions = set()
        for collab in collaborations:
            name = collab.get("name")
            if name:
                permissions.add(name)
        return sorted(list(permissions))

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

    def _should_download_file(self, file_name: str) -> bool:
        """
        Check if file should be downloaded based on whitelist filter.

        Logic:
        - If file_extensions is set (whitelist), only download those extensions
        - If file_extensions is empty, download all files

        Note: exclude_extensions is handled separately in the download flow.
        Files in exclude_extensions are not downloaded; they are only tracked
        in skipped.csv using Box API metadata.

        Args:
            file_name: Name of the file

        Returns:
            True if file should be downloaded, False otherwise
        """
        # If no whitelist, download all files
        if not self.file_extensions:
            return True

        _, ext = os.path.splitext(file_name)
        ext_lower = ext.lower()

        # Check if in whitelist
        return ext_lower in [e.lower() for e in self.file_extensions]

    def _download_file(
        self,
        file_item,
        ray_mode: bool = False,
        inherited_permissions: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Download a file from Box to local storage.

        Excluded files are saved to the inspection folder but not indexed.

        Args:
            file_item: Box file object
            ray_mode: If True, return (file_path, metadata) for Ray processing.
                     If False, index immediately (legacy behavior).
            inherited_permissions: List of permission dicts inherited from parent folders.
                                  Used when collect_permissions is enabled.

        Returns:
            - If ray_mode=True: Tuple of (file_path, metadata) or None
            - If ray_mode=False: file_path string or None (legacy)
        """
        if self.max_files > 0 and self.files_downloaded >= self.max_files:
            logging.info(f"Reached max_files limit ({self.max_files})")
            return None

        file_name = file_item.name
        file_id = file_item.id

        # Skip already indexed files if option is enabled
        if self.skip_indexed and file_id in self.indexed_file_ids:
            logging.info(f"Skipping already indexed file: {file_name} (ID: {file_id})")
            return None

        # Check if file should be downloaded based on whitelist
        if not self._should_download_file(file_name):
            logging.info(f"Skipping file (not in file_extensions whitelist): {file_name}")
            return None

        # Check if file is in exclude list - skip download, just track in skipped.csv
        if self._is_excluded_file(file_name):
            extension = os.path.splitext(file_name)[1]
            file_size = file_item.size if hasattr(file_item, 'size') else 0
            url = f"https://app.box.com/file/{file_id}"
            logging.info(f"Skipping excluded file (not downloading): {file_name} (ID: {file_id})")
            self.tracker.track_skipped(
                file_id, file_name, url, file_size, extension,
                "Excluded by extension filter"
            )
            return None

        try:
            # Create a sanitized filename
            safe_filename = "".join(
                c for c in file_name if c.isalnum() or c in (" ", ".", "_", "-")
            ).rstrip()

            local_path = os.path.join(
                self.download_path, f"{file_id}_{safe_filename}"
            )
            logging.info(f"Downloading: {file_name} (ID: {file_id})")

            # Download file content
            with open(local_path, "wb") as output_file:
                file_item.download_to(output_file)

            file_size = os.path.getsize(local_path)
            logging.info(f"Downloaded: {file_name} ({file_size:,} bytes) -> {local_path}")
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

            # Add permissions if collect_permissions is enabled
            if self.collect_permissions and inherited_permissions:
                metadata["permissions"] = self._build_permissions_list(inherited_permissions)

            # Return different results based on mode
            if ray_mode:
                # Ray mode: return tuple for parallel processing
                return (local_path, metadata)
            else:
                # Legacy mode: index immediately
                if not self.skip_indexing:
                    logging.info(f"Indexing file: {file_name}")
                    try:
                        # Route Excel/CSV files to DataframeParser instead of docling
                        if supported_by_dataframe_parser(local_path):
                            logging.info(f"Processing as dataframe file: {file_name}")
                            df_config = self.cfg.get("dataframe_processing", {})
                            success = process_dataframe_file(
                                file_path=local_path,
                                metadata=metadata,
                                doc_id=file_id,
                                df_parser=self.df_parser,
                                df_config=df_config,
                                source_name="box"
                            )
                        else:
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
        self,
        folder_id: str,
        path: str = "",
        ray_mode: bool = False,
        inherited_permissions: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[List[Tuple[str, Dict[str, Any]]]]:
        """
        Recursively crawl a Box folder and download files.

        Args:
            folder_id: Box folder ID (use "0" for root folder)
            path: Current folder path for logging
            ray_mode: If True, collect files for Ray processing instead of indexing
            inherited_permissions: Permissions inherited from parent folders

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

            # Collect and merge permissions if enabled
            current_permissions = inherited_permissions or []
            if self.collect_permissions:
                folder_perms = self._get_folder_collaborations(folder_id, current_path)
                current_permissions = self._merge_permissions(
                    inherited_permissions or [], folder_perms
                )
                if folder_perms:
                    logging.info(f"Folder {current_path}: {len(folder_perms)} direct collaborations, {len(current_permissions)} total")

            # Get items in the folder with proper paging
            # Box SDK handles paging internally when iterating
            items = folder.get_items()

            for item in items:
                if self.max_files > 0 and self.files_downloaded >= self.max_files:
                    break

                if item.type == "file":
                    result = self._download_file(
                        item,
                        ray_mode=ray_mode,
                        inherited_permissions=current_permissions if self.collect_permissions else None
                    )
                    if ray_mode and result:
                        files_to_process.append(result)
                elif item.type == "folder" and self.recursive:
                    if ray_mode:
                        subfolder_files = self._crawl_folder(
                            item.id,
                            current_path,
                            ray_mode=True,
                            inherited_permissions=current_permissions if self.collect_permissions else None
                        )
                        if subfolder_files:
                            files_to_process.extend(subfolder_files)
                    else:
                        self._crawl_folder(
                            item.id,
                            current_path,
                            ray_mode=False,
                            inherited_permissions=current_permissions if self.collect_permissions else None
                        )

        except Exception as e:
            logging.error(f"Error crawling folder {folder_id}: {str(e)}")

        return files_to_process

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
            # Pass skip_indexed flag to control whether to preserve existing CSV files
            tracker_actor = ray.remote(num_cpus=0)(CSVTrackerActor).remote(
                self.tracking_dir, preserve_existing=self.skip_indexed
            )
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
                folder_items = self._crawl_folder(str(folder_id), ray_mode=True)

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
                # Initialize DataframeParser for Excel/CSV files (sequential mode)
                self.df_parser = create_dataframe_parser(self.cfg, self.indexer)

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
