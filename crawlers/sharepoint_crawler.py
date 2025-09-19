import zipfile
import logging
logger = logging.getLogger(__name__)
import time
import pandas as pd
from typing import Optional

from office365.runtime.client_request_exception import ClientRequestException
from office365.sharepoint.client_context import ClientContext
from furl import furl
import os
import tempfile
from core.crawler import Crawler
from core.dataframe_parser import DataframeParser
from core.summary import TableSummarizer
from core.dataframe_parser import (
    supported_by_dataframe_parser, 
    determine_dataframe_type,
    get_separator_by_file_name
)

# Supported extensions for regular document processing
supported_document_extensions = {
    ".pdf", ".md", ".odt", ".doc", ".docx", ".ppt",
    ".pptx", ".txt", ".html", ".htm", ".lxml",
    ".rtf", ".epub"
}

# Supported extensions for dataframe processing
supported_dataframe_extensions = {
    ".csv", ".xlsx", ".xls"
}

# All supported extensions
supported_extensions = supported_document_extensions | supported_dataframe_extensions

class SharepointCrawler(Crawler):
    """
    A crawler implementation for ingesting and indexing documents from SharePoint sites.

    The SharepointCrawler class connects to SharePoint, authenticates using specified credentials,
    recursively crawls specified folders, downloads supported document types, and indexes them
    using the configured indexing service. Supports advanced CSV/Excel processing using DataframeParser
    with 'table' and 'element' modes.
    """
    
    # SharePoint system components to skip
    SYSTEM_LIBRARIES = {
        'Form Templates', 'Style Library', 'Site Assets', 'Site Pages',
        'Master Page Gallery', 'Theme Gallery', 'Solution Gallery',
        'List Template Gallery', 'Web Part Gallery', 'Workflow History',
        'Translation Management Library', 'Converted Forms',
        'Site Collection Documents', 'Site Collection Images',
        'Customized Reports', 'Pages', 'Reusable Content', 'Images',
        'SiteAssets', '_catalogs', '_layouts', '_vti_bin'
    }
    
    # SharePoint system files to skip (individual files within libraries)
    SYSTEM_FILES = {
        'Forms', 'AllItems.aspx', 'DispForm.aspx', 'EditForm.aspx', 
        'NewForm.aspx', 'Upload.aspx', 'WebPartPages', 'repair.aspx',
        'Combine.aspx', 'Thumbnails.aspx', 'template.dotx'
    }

    def __init__(self, cfg, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        # Initialize dataframe processing components with safe defaults
        try:
            # Check if doc_processing configuration exists
            if hasattr(self.cfg, 'doc_processing') and hasattr(self.cfg.doc_processing, 'model_config'):
                model_config = self.cfg.doc_processing.model_config.text
            else:
                logger.info("doc_processing.model_config not found, using default model configuration")
                model_config = None
            
            self.table_summarizer = TableSummarizer(
                self.cfg,
                model_config
            )
            
            # Check if dataframe_processing configuration exists, provide defaults if missing
            if hasattr(self.cfg.sharepoint_crawler, 'dataframe_processing'):
                df_config = self.cfg.sharepoint_crawler.dataframe_processing
            else:
                logger.info("dataframe_processing configuration not found, using defaults")
                # Create default dataframe processing config
                from omegaconf import OmegaConf
                df_config = OmegaConf.create({
                    'mode': 'element',
                    'doc_id_columns': [],
                    'text_columns': [],
                    'metadata_columns': []
                })
            
            self.df_parser = DataframeParser(
                self.cfg,
                df_config,
                self.indexer,
                self.table_summarizer
            )
            logger.info("DataframeParser initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize DataframeParser: {e}. Dataframe processing will be disabled.")
            self.df_parser = None
            self.table_summarizer = None

    def _get_sharepoint_property(self, obj, property_names, default=None):
        """
        Get property from SharePoint object with multiple name fallbacks.
        
        Args:
            obj: SharePoint object to get property from
            property_names: String or list of property names to try
            default: Default value if no property is found
            
        Returns:
            Property value or default if not found
        """
        if isinstance(property_names, str):
            property_names = [property_names]
        
        for prop_name in property_names:
            value = getattr(obj, prop_name, None)
            if value is not None:
                return value
        return default

    def new_url(self, *paths) -> furl:
        """
        Constructs a new URL by copying the base URL and appending additional path segments.

        Args:
            *paths (str): One or more path segments to append.

        Returns:
            furl.furl: A new furl object representing the resulting URL.
        """
        result = self.base_url.copy()
        for p in paths:
            result.path = os.path.join(str(result.path), str(p))
        return result

    def download_url(self, file):
        """
        Generates a direct download URL for the given SharePoint file.

        Args:
            file: A SharePoint file object with a server-relative URL attribute.

        Returns:
            str: Direct URL to download the specified file.
        """
        download_url = self.new_url("_layouts/15/download.aspx")
        download_url.args['SourceUrl'] = file.serverRelativeUrl
        return download_url.url

    def _create_authenticated_context(self, test_session: bool = True) -> None:
        """
        Creates and authenticates a SharePoint client context.
        
        Args:
            test_session: Whether to test the session after authentication
        """
        auth_type = self.cfg.sharepoint_crawler.get('auth_type', 'user_credentials')
        allow_ntlm = bool(self.cfg.sharepoint_crawler.get('allow_ntlm', 'True'))
        context = ClientContext(self.team_site_url, allow_ntlm=allow_ntlm)

        match auth_type:
            case 'user_credentials':
                self.sharepoint_context = context.with_user_credentials(
                    self.cfg.sharepoint_crawler.username,
                    self.cfg.sharepoint_crawler.password
                )
            case 'client_credentials':
                self.sharepoint_context = context.with_client_credentials(
                    self.cfg.sharepoint_crawler.client_id,
                    self.cfg.sharepoint_crawler.client_secret
                )
            case 'client_certificate':
                cert_settings = {
                    'client_id': self.cfg.sharepoint_crawler.client_id,
                    'thumbprint': self.cfg.sharepoint_crawler.cert_thumbprint,
                    'cert_path': self.cfg.sharepoint_crawler.cert_path
                }
                if self.cfg.sharepoint_crawler.get('cert_passphrase'):
                    cert_settings['passphrase'] = self.cfg.sharepoint_crawler.cert_passphrase
                self.sharepoint_context = context.with_client_certificate(
                    self.cfg.sharepoint_crawler.tenant_id, **cert_settings
                )
            case _:
                raise Exception(f"Unknown auth_type '{auth_type}'")
        
        # Test the session if requested
        if test_session:
            self.sharepoint_context.load(self.sharepoint_context.web, ['Title', 'Url'])
            self.sharepoint_context.execute_query()
            logger.info(f"Authentication successful. Connected to site: {self.sharepoint_context.web.title}")

    def configure_sharepoint_context(self) -> None:
        """
        Configures and authenticates the SharePoint client context based on provided crawler configuration.

        Supported authentication methods:
            - User credentials (username/password)
            - Client credentials (client_id/client_secret)
            - Client certificates (client_id, thumbprint, certificate file, and optional passphrase)

        Raises:
            Exception: If an unsupported authentication type is specified in configuration.
        """
        self.base_url = furl(self.cfg.sharepoint_crawler.team_site_url)
        self.team_site_url = self.cfg.sharepoint_crawler.team_site_url
        logger.info(f"team_site_url = '{self.team_site_url}'")
        
        # Create authenticated context with session testing
        self._create_authenticated_context(test_session=True)

    def execute_with_retry(self, func):
        """
        Execute a SharePoint query with retry logic and session refresh.
        
        Args:
            func: The function to execute with retry
            
        Returns:
            The result of the function execution
        """
        retries = self.cfg.sharepoint_crawler.get("retry_attempts", 3)
        delay = self.cfg.sharepoint_crawler.get("retry_delay", 5)
        auto_refresh_session = self.cfg.sharepoint_crawler.get("auto_refresh_session", True)
        for attempt in range(retries):
            try:
                return func.execute_query()
            except Exception as e:
                error_str = str(e).lower()
                if "401" in error_str or "unauthorized" in error_str:
                    logger.warning(f"Authentication error detected (attempt {attempt + 1}): {e}")
                    if attempt < retries - 1 and auto_refresh_session:  # Don't refresh on last attempt
                        logger.info("Attempting to refresh SharePoint authentication session...")
                        try:
                            self.refresh_sharepoint_session()
                            logger.info("Session refresh successful, retrying operation...")
                        except Exception as refresh_error:
                            logger.warning(f"Session refresh failed: {refresh_error}")
                    elif not auto_refresh_session:
                        logger.info("Session auto-refresh is disabled in configuration")
                elif attempt == retries - 1:
                    raise
                else:
                    logger.warning(f"Attempt {attempt + 1} failed with error: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
    
    def refresh_sharepoint_session(self):
        """
        Refresh the SharePoint authentication session.
        This recreates the authentication context to handle session expiration.
        """
        logger.debug("Refreshing SharePoint authentication session...")
        
        # Create new authenticated context (without session testing to avoid recursion)
        self._create_authenticated_context(test_session=False)
        
        # Test the new session separately
        try:
            self.sharepoint_context.load(self.sharepoint_context.web, ['Title'])
            self.sharepoint_context.execute_query()
            logger.debug("SharePoint session refresh completed successfully")
        except Exception as e:
            logger.error(f"Session refresh test failed: {e}")
            raise

    def process_dataframe_file(self, file_path: str, metadata: dict, doc_id: str) -> bool:
        """
        Process CSV or Excel files using the DataframeParser.
        Similar to csv_crawler approach - no fallback to regular indexing.
        
        Args:
            file_path: Path to the CSV/Excel file
            metadata: Existing metadata dictionary
            doc_id: Document ID for indexing
            
        Returns:
            bool: Success status
        """
        if not self.df_parser:
            logger.error("DataframeParser not initialized. Cannot process dataframe file.")
            return False
        
        try:
            if not supported_by_dataframe_parser(file_path):
                logger.error(f"'{file_path}' is not supported by DataframeParser.")
                return False
            
            logger.info(f"Processing dataframe file: {file_path}")
            
            file_type = determine_dataframe_type(file_path)
            doc_title = os.path.basename(file_path)
            
            # Add SharePoint-specific metadata
            df_metadata = metadata.copy()
            df_metadata['source'] = 'sharepoint'
            df_metadata['file_type'] = file_type
            
            # Get dataframe processing config
            df_config = self.cfg.sharepoint_crawler.get('dataframe_processing', {})
            
            if file_type == 'csv':
                separator = get_separator_by_file_name(file_path)
                encoding = df_config.get('csv_encoding', 'utf-8')
                try:
                    df = pd.read_csv(file_path, sep=separator, encoding=encoding)
                except Exception as e:
                    logger.warning(f"Failed to read CSV with encoding {encoding}: {e}. Trying with 'latin-1'")
                    df = pd.read_csv(file_path, sep=separator, encoding='latin-1')
                
                self.df_parser.process_dataframe(
                    df=df,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    metadata=df_metadata
                )
                
            elif file_type in ['xls', 'xlsx']:
                xls = pd.ExcelFile(file_path)
                sheet_names = df_config.get("sheet_names")
                
                # If sheet_names is not specified or is None, process all sheets
                if sheet_names is None:
                    sheet_names = xls.sheet_names
                
                for sheet_name in sheet_names:
                    if sheet_name not in xls.sheet_names:
                        logger.warning(f"Sheet '{sheet_name}' not found in '{file_path}'. Skipping.")
                        continue
                    
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    sheet_doc_id = f"{doc_id}_{sheet_name}"
                    sheet_doc_title = f"{doc_title} - {sheet_name}"
                    sheet_metadata = df_metadata.copy()
                    sheet_metadata['sheet_name'] = sheet_name
                    
                    self.df_parser.process_dataframe(
                        df=df,
                        doc_id=sheet_doc_id,
                        doc_title=sheet_doc_title,
                        metadata=sheet_metadata
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing dataframe file {file_path}: {e}")
            return False

    def _should_skip_file(self, file) -> bool:
        """
        Determine if a file should be skipped during crawling.
        
        Args:
            file: SharePoint file object
            
        Returns:
            bool: True if file should be skipped, False otherwise
        """
        file_name = file.name
        
        server_relative_url = self._get_sharepoint_property(file, 'ServerRelativeUrl', '')
        
        # Skip system files and hidden files
        if file_name.startswith('.') or file_name.startswith('~'):
            logger.debug(f"Skipping hidden/temp file: {file_name}")
            return True
        
        # Skip common SharePoint system files
        if file_name in self.SYSTEM_FILES:
            logger.debug(f"Skipping system file: {file_name}")
            return True
        
        # Skip files with system file extensions
        system_extensions = {'.aspx', '.master', '.dwp', '.dotx'}
        _, file_extension = os.path.splitext(file_name)
        if file_extension.lower() in system_extensions:
            logger.debug(f"Skipping system file type: {file_name}")
            return True
        
        # Skip files in system directories (Forms, _vti_, etc.)
        if server_relative_url:
            system_paths = ['/Forms/', '/_vti_', '/_catalogs/', '/_layouts/']
            for system_path in system_paths:
                if system_path in server_relative_url:
                    logger.debug(f"Skipping file in system directory: {file_name} ({server_relative_url})")
                    return True
        
        logger.debug(f"File: {file_name}, URL: {server_relative_url}")
        
        return False

    def _process_files(self, files, library_name=None):
        """
        Process a collection of files for indexing.
        Enhanced to use DataframeParser for CSV and Excel files.
        
        Args:
            files: Collection of SharePoint file objects
            library_name: Optional name of the document library for logging
        """
        cleanup_temp_files = self.cfg.sharepoint_crawler.get("cleanup_temp_files", True)
        count = len(files)
        
        library_info = f" in {library_name}" if library_name else ""
        logger.info(f"Found {count} files{library_info}.")
        
        for file in files:
            try:
                # Check if this file should be skipped
                if self._should_skip_file(file):
                    continue
                    
                logger.info(f"Processing {file}")
                filename, file_extension = os.path.splitext(file.name)
                
                if file_extension.lower() == ".zip":
                    metadata = {'url': self.download_url(file)}
                    if library_name:
                        metadata['library'] = library_name
                        
                    server_relative_url = self._get_sharepoint_property(file, 'ServerRelativeUrl')
                    unique_id = self._get_sharepoint_property(file, ['UniqueId', 'unique_id'], str(file.name))
                    self.extract_and_upload_zip(server_relative_url, metadata, unique_id)
                    
                elif file_extension.lower() not in supported_extensions:
                    logger.warning(f"Skipping {file} due to unsupported file type '{file_extension}'.")
                    
                else:
                    metadata = {'url': self.download_url(file)}
                    if library_name:
                        metadata['library'] = library_name
                    metadata['file_name'] = file.name
                    
                    server_relative_url = self._get_sharepoint_property(file, 'ServerRelativeUrl')
                    if server_relative_url:
                        metadata['server_relative_url'] = server_relative_url
                    
                    logger.info(f"Downloading {file}")
                    with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
                        unique_id = self._get_sharepoint_property(file, ['UniqueId', 'unique_id'], str(file.name))
                        logger.debug(f"Downloading and writing content for {unique_id} to {f.name}")
                        file.download_session(f).execute_query()
                        f.flush()
                        f.close()
                        logger.debug(f"Wrote {os.path.getsize(f.name)} bytes to {f.name}")

                        try:
                            # Check if this is a dataframe file (CSV/Excel)
                            if file_extension.lower() in supported_dataframe_extensions:
                                succeeded = self.process_dataframe_file(f.name, metadata, unique_id)
                            else:
                                # Regular document processing
                                succeeded = self.indexer.index_file(f.name, metadata['url'], metadata, unique_id)
                            
                            if not succeeded:
                                logger.error(f"Error indexing {unique_id} - {server_relative_url}")
                        finally:
                            if cleanup_temp_files:
                                logger.debug(f"Cleaning up temp file: {f.name}")
                                if os.path.exists(f.name):
                                    os.remove(f.name)
                            else:
                                logger.debug(f"Keeping temp file: {f.name}")
                                
            except Exception as e:
                logger.error(f"Error processing file {file.name}: {e}")
                # Continue with next file

    def crawl_site(self) -> None:
        """
        Crawls all document libraries in a SharePoint site.
        
        This method discovers all document libraries in the site and crawls each one,
        respecting the recursive setting and excluded libraries configuration.
        """
        logger.info(f"Crawling entire site: {self.team_site_url}")
        
        recursive = self.cfg.sharepoint_crawler.get('recursive', False)
        excluded_libraries = self.cfg.sharepoint_crawler.get('exclude_libraries', [])
        
        all_lists = self.sharepoint_context.web.lists
        self.sharepoint_context.load(all_lists, ['Title', 'BaseTemplate', 'Hidden', 'ItemCount', 'RootFolder'])
        self.sharepoint_context.execute_query()
        
        logger.info(f"Found {len(all_lists)} lists in total")
        
        libraries_to_crawl = []
        
        for lst in all_lists:
            base_template = self._get_sharepoint_property(lst, ['base_template', 'BaseTemplate'])
            if base_template != 101:
                continue
                
            is_hidden = self._get_sharepoint_property(lst, ['hidden', 'Hidden'], False)
            if is_hidden:
                logger.debug(f"Skipping hidden library: {lst.title}")
                continue
            
            if lst.title in self.SYSTEM_LIBRARIES:
                logger.info(f"Skipping system library: {lst.title}")
                continue
                
            if lst.title in excluded_libraries:
                logger.info(f"Skipping excluded library: {lst.title}")
                continue
            
            logger.info(f"Found document library: {lst.title}")
            libraries_to_crawl.append(lst)
        
        logger.info(f"Will crawl {len(libraries_to_crawl)} document libraries")
        
        if not libraries_to_crawl:
            logger.error("No document libraries found. This could be due to:")
            logger.error("- No document libraries exist in this SharePoint site")
            logger.error("- All document libraries are hidden or excluded")
            logger.error("- Insufficient permissions to access document libraries")
            return
        
        for doc_lib in libraries_to_crawl:
            try:
                item_count = self._get_sharepoint_property(doc_lib, 'item_count', 'unknown')
                logger.info(f"Crawling document library: {doc_lib.title} (Items: {item_count})")
                
                root_folder = doc_lib.root_folder
                self.sharepoint_context.load(root_folder, ['ServerRelativeUrl', 'Exists'])
                
                # Use retry logic with session refresh for folder access
                try:
                    self.execute_with_retry(root_folder)
                except Exception as e:
                    logger.error(f"Failed to access root folder for library {doc_lib.title} after retries: {e}")
                    continue
                
                if not root_folder.exists:
                    logger.warning(f"Root folder for library {doc_lib.title} does not exist, skipping")
                    continue
                
                logger.info(f"Listing files in {doc_lib.title}. Large libraries can take a while...")
                files = root_folder.get_files(recursive=recursive)
                
                for file in files:
                    self.sharepoint_context.load(file, ['Name', 'ServerRelativeUrl', 'UniqueId', 'Length', 'TimeCreated', 'TimeLastModified'])
                
                # Use retry logic with session refresh for file listing
                try:
                    self.execute_with_retry(files)
                except Exception as e:
                    logger.error(f"Failed to list files in library {doc_lib.title} after retries: {e}")
                    continue
                
                self._process_files(files, doc_lib.title)
                
            except Exception as e:
                logger.error(f"Error crawling library {doc_lib.title}: {e}")

    def crawl_folder(self) -> None:
        """
        Crawls a specified SharePoint folder to locate, download, and index files.
        
        Requires target_folder to be configured. Fails if folder doesn't exist.
        """
        target_folder = self.cfg.sharepoint_crawler.get('target_folder')
        
        # Require target_folder for folder mode
        if not target_folder:
            logger.error("Folder mode requires 'target_folder' to be specified in configuration.")
            raise ValueError("Missing required configuration: sharepoint_crawler.target_folder must be specified for folder mode")
            return
        
        # Get the site's server relative URL to check if target is site root
        self.sharepoint_context.load(self.sharepoint_context.web, ['ServerRelativeUrl'])
        self.sharepoint_context.execute_query()
        site_relative_url = getattr(self.sharepoint_context.web, 'ServerRelativeUrl', None)
        
        # Fallback: extract site path from team_site_url if property access fails
        if site_relative_url is None:
            from urllib.parse import urlparse
            parsed_url = urlparse(self.team_site_url)
            site_relative_url = parsed_url.path
        
        # Normalize paths for comparison
        normalized_target = target_folder.rstrip('/')
        normalized_site_url = site_relative_url.rstrip('/')
        
        # Check if the target_folder is the site root  
        if normalized_target == normalized_site_url:
            logger.error(f"Target folder '{target_folder}' appears to be the site root. Use mode='site' instead of mode='folder' for site crawling.")
            raise ValueError("Invalid configuration: target_folder points to site root. Use mode='site' for site-wide crawling.")
            return
        
        # Try to access as a folder first
        recursive = self.cfg.sharepoint_crawler.get('recursive', False)
        logger.info(f"target_folder = '{target_folder}' recursive = {recursive}")

        try:
            root_folder = self.sharepoint_context.web.get_folder_by_server_relative_url(target_folder)
            self.sharepoint_context.load(root_folder, ['Exists', 'Name'])
            root_folder.execute_query()
            
            if not root_folder.exists:
                logger.error(f"Target folder '{target_folder}' does not exist.")
                raise ValueError(f"Folder not found: {target_folder}")
                return

            logger.info(f"Folder exists: {root_folder.exists}")
            logger.info(f"Listing files in {root_folder.name}. Large Directory Structures can take a while...")
            files = root_folder.get_files(recursive=recursive)
            self.execute_with_retry(files)
            
            # Use the common file processing method
            self._process_files(files, root_folder.name)
            
        except ClientRequestException as e:
            if "404" in str(e) or "Not Found" in str(e):
                logger.error(f"Folder not found: {target_folder}")
                raise ValueError(f"Folder not found: {target_folder}")
            else:
                logger.error(f"Error accessing folder {target_folder}: {e}")
                raise

    def crawl_list(self) -> None:
        """
        Crawls a SharePoint list and indexes its attachments.
        """
        list_name = self.cfg.sharepoint_crawler.target_list
        logger.info(f"Crawling list: {list_name}")
        
        target_list = self.sharepoint_context.web.lists.get_by_title(list_name)
        self.sharepoint_context.load(target_list, ['Id'])
        items = target_list.items.get().execute_query()

        load_properties = ["Attachments", "ID"]
        allowed_properties = self.cfg.sharepoint_crawler.get("list_item_metadata_properties", [])
        for p in allowed_properties:
            load_properties.append(p)

        logger.debug(f"Loading properties: {', '.join(load_properties)}")
        self.sharepoint_context.load(items, load_properties)
        self.sharepoint_context.execute_query()

        all_properties = None
        for item in items:
            if len(allowed_properties) == 0 and all_properties is None:
                for k, v in item.properties.items():
                    if all_properties is None:
                        all_properties = set()
                    all_properties.add(k)
                logger.info(f"Available properties in list items: {', '.join(all_properties)}")

            metadata = {k: v for k, v in item.properties.items() if k in allowed_properties}
            item_id = item.properties["ID"]
            metadata["list_id"] = str(target_list.id)
            metadata["list_item_id"] = str(item_id)
            
            if 'Attachments' in item.properties and item.properties['Attachments']:
                attachment_files = item.attachment_files
                self.sharepoint_context.load(attachment_files)
                self.sharepoint_context.execute_query()
                
                for attachment in attachment_files:
                    try:
                        server_relative_url = self._get_sharepoint_property(attachment, 'ServerRelativeUrl')
                        filename = os.path.basename(server_relative_url)
                        filename_base, file_extension = os.path.splitext(filename)
                        
                        if file_extension.lower() == ".zip":
                            doc_id = f"{target_list.id}-{item_id}-{filename}"
                            self.extract_and_upload_zip(server_relative_url, metadata, doc_id)
                            
                        elif file_extension.lower() not in supported_extensions:
                            logger.warning(f"Skipping {server_relative_url} due to unsupported file type '{file_extension}'.")
                            
                        else:
                            doc_id = f"{target_list.id}-{item_id}-{filename_base}"
                            attachment_url = attachment.resource_url
                            metadata["url"] = attachment_url
                            metadata["file_name"] = filename

                            with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
                                logger.info(f"Item Id {item_id}: Downloading {attachment_url}")
                                attachment_file = self.sharepoint_context.web.get_file_by_server_relative_url(
                                    attachment.server_relative_url
                                )
                                
                                try:
                                    attachment_file.download(f).execute_query()
                                    f.close()
                                    
                                    # Check if this is a dataframe file
                                    if file_extension.lower() in supported_dataframe_extensions:
                                        succeeded = self.process_dataframe_file(f.name, metadata, doc_id)
                                    else:
                                        succeeded = self.indexer.index_file(f.name, attachment_url, metadata, doc_id)
                                    
                                    if not succeeded:
                                        logger.error(f"Error indexing attachment {filename} for list item {item_id}")
                                        
                                except ClientRequestException as e:
                                    logger.error(f"ClientRequestException when downloading {attachment.server_relative_url}: {e}")
                                    
                                finally:
                                    if os.path.exists(f.name):
                                        os.remove(f.name)
                                        
                    except Exception as e:
                        logger.error(f"Error processing attachment for item {item_id}: {e}")
                        # Continue with next attachment

    def extract_and_upload_zip(self, zip_url: str, metadata: dict, doc_id_prefix: str) -> None:
        """
        Extracts and processes files from a ZIP archive.
        
        Args:
            zip_url: SharePoint relative URL to the ZIP file
            metadata: Metadata to apply to extracted files
            doc_id_prefix: Prefix for document IDs of extracted files
        """
        if not zip_url:
            logger.warning("No ZIP URL provided for extraction.")
            return

        tmp_zip_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb", delete=False) as tmp_zip:
                logger.info(f"Downloading ZIP file from {zip_url}")
                file_obj = self.sharepoint_context.web.get_file_by_server_relative_url(zip_url).download(tmp_zip)
                self.execute_with_retry(file_obj)
                tmp_zip_path = tmp_zip.name

            with tempfile.TemporaryDirectory() as extract_dir:
                with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                    logger.info(f"Extracted {len(zip_ref.namelist())} files from ZIP")

                for root, _, files in os.walk(extract_dir):
                    for name in files:
                        file_path = os.path.join(root, name)
                        _, ext = os.path.splitext(name)
                        
                        if ext.lower() not in supported_extensions:
                            logger.debug(f"Skipping {name} inside ZIP due to unsupported extension '{ext}'.")
                            continue

                        relative_path = os.path.relpath(file_path, extract_dir)
                        file_doc_id = f"{doc_id_prefix}/{relative_path}"
                        
                        try:
                            # Check if this is a dataframe file
                            if ext.lower() in supported_dataframe_extensions:
                                succeeded = self.process_dataframe_file(file_path, metadata, file_doc_id)
                            else:
                                succeeded = self.indexer.index_file(file_path, zip_url, metadata, file_doc_id)
                            
                            if not succeeded:
                                logger.error(f"Failed to index extracted file: {relative_path}")
                                
                        except Exception as e:
                            logger.error(f"Error indexing file {relative_path} from ZIP: {e}")
                            
        except Exception as e:
            logger.error(f"Error processing ZIP file {zip_url}: {e}")
            
        finally:
            if tmp_zip_path and os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)

    def crawl(self) -> None:
        """
        Initiates the crawling process based on the crawler configuration.
        
        Requires explicit mode configuration - no auto-detection or fallbacks.

        Steps performed:
            1. Configures SharePoint client context.
            2. Executes crawling operation based on the configured mode:
                - 'site': Crawls all document libraries in the site
                - 'folder': Crawls a specific SharePoint folder (requires target_folder)
                - 'list': Crawls a SharePoint list and its attachments (requires target_list)

        Raises:
            ValueError: If mode is not specified or if required configuration is missing.
            Exception: If the specified crawl mode is unknown or unsupported.
        """
        self.configure_sharepoint_context()
        
        # Require explicit mode configuration
        mode = self.cfg.sharepoint_crawler.get('mode')
        
        if not mode:
            logger.error("Crawl mode must be explicitly specified in configuration. Set 'mode' to 'site', 'folder', or 'list'.")
            raise ValueError("Missing required configuration: sharepoint_crawler.mode must be specified")
        
        logger.info(f"Crawl mode: '{mode}'")

        match mode:
            case 'site':
                self.crawl_site()
            case 'folder':
                self.crawl_folder()
            case 'list':
                self.crawl_list()
            case _:
                raise Exception(f"Unknown mode '{mode}'")