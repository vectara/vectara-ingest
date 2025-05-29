import zipfile
import logging
import time

from office365.runtime.client_request_exception import ClientRequestException

from office365.sharepoint.client_context import ClientContext
from furl import furl
import os
import tempfile
from core.crawler import Crawler

supported_extensions = {
    ".pdf", ".md", ".odt", ".doc", ".docx", ".ppt",
    ".pptx", ".txt", ".html", ".htm", ".lxml",
    ".rtf", ".epub"
}

class SharepointCrawler(Crawler):
    """
    A crawler implementation for ingesting and indexing documents from SharePoint sites.

    The SharepointCrawler class connects to SharePoint, authenticates using specified credentials,
    recursively crawls specified folders, downloads supported document types, and indexes them
    using the configured indexing service.
    """

    def new_url(self, /, *paths) -> furl:
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
        logging.info(f"team_site_url = '{self.team_site_url}'")
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

    def execute_with_retry(self, func):
        retries = self.cfg.sharepoint_crawler.get("retry_attempts", 3)
        delay = self.cfg.sharepoint_crawler.get("retry_delay", 5)
        for attempt in range(retries):
            try:
                return func.execute_query()
            except Exception as e:
                if attempt == retries - 1:
                    raise
                logging.warning(f"Attempt {attempt + 1} failed with error: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)

    def crawl_folder(self) -> None:
        """
        Crawls a specified SharePoint folder to locate, download, and index files.

        The method retrieves files from SharePoint and filters them based on supported extensions.
        Supported file types include: .pdf, .md, .odt, .doc, .docx, .ppt, .pptx, .txt, .html, .htm, .lxml, .rtf, and .epub.

        Files matching the supported types are downloaded temporarily, indexed, and then deleted.

        Logging:
            - Warns about skipped unsupported file types.
            - Logs indexing errors.
        """
        recursive = self.cfg.sharepoint_crawler.get('recursive', False)
        target_folder = self.cfg.sharepoint_crawler.target_folder
        cleanup_temp_files = self.cfg.sharepoint_crawler.get("cleanup_temp_files", True)
        logging.info(f"target_folder = '{target_folder}' recursive = {recursive}")

        root_folder = self.sharepoint_context.web.get_folder_by_server_relative_url(target_folder)
        self.sharepoint_context.load(root_folder, ['Exists', 'Name'])
        root_folder.execute_query()
        if not root_folder.exists:
            raise Exception(f"Folder {target_folder} was not found")

        logging.info(f"{root_folder.exists}")
        logging.info(f"Listing files in {root_folder.name}. Large Directory Structures can take a while...")
        files = root_folder.get_files(recursive=recursive).execute_query()
        count = len(files)
        logging.info(f"Found {count} files in {root_folder.name}.")
        for file in files:
            logging.info(f"Processing {file}")
            filename, file_extension = os.path.splitext(file.name)
            if file_extension.lower() == ".zip":
                metadata = {'url': self.download_url(file)}
                self.extract_and_upload_zip(file.server_relative_url, metadata, file.unique_id)
            elif file_extension.lower() not in supported_extensions:
                logging.warning(f"Skipping {file} due to unsupported file type '{file_extension}'.")
            else:
                metadata = {'url': self.download_url(file)}
                logging.info(f"Downloading {file}")
                with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
                    logging.debug(f"Downloading and writing content for {file.unique_id} to {f.name}")
                    file.download_session(f).execute_query()
                    f.flush()
                    f.close()
                    logging.debug(f"Wrote {os.path.getsize(f.name)} to {f.name}")

                    try:
                        succeeded = self.indexer.index_file(f.name, metadata['url'], metadata, file.unique_id)
                    finally:
                        if cleanup_temp_files:
                            logging.debug(f"Cleaning up temp file: {f.name}")
                            if os.path.exists(f.name):
                                os.remove(f.name)
                        else:
                            logging.warn(f"Skipping clean up of temp file: {f.name}")

                    if not succeeded:
                        logging.error(f"Error indexing {file.unique_id} - {file.serverRelativeUrl}")

    def crawl(self) -> None:
        """
        Initiates the crawling process based on the crawler configuration.

        Steps performed:
            1. Configures SharePoint client context.
            2. Executes crawling operation based on the configured mode:
                - 'folder': Initiates crawling of a SharePoint folder.
                - 'list': Initiates crawling of a SharePoint list and its attachments.

        Raises:
            Exception: If the specified crawl mode is unknown or unsupported.
        """
        self.configure_sharepoint_context()
        mode = self.cfg.sharepoint_crawler.mode
        logging.info(f"mode = '{mode}'")

        match mode:
            case 'folder':
                self.crawl_folder()
            case 'list':
                self.crawl_list()
            case _:
                raise Exception(f"Unknown mode '{mode}'")


    def crawl_list(self) -> None:
        list_name = self.cfg.sharepoint_crawler.target_list
        target_list = self.sharepoint_context.web.lists.get_by_title(list_name)
        self.sharepoint_context.load(target_list, ['Id'])
        items = target_list.items.get().execute_query()

        load_properties = ["Attachments", "ID"]
        allowed_properties = self.cfg.sharepoint_crawler.get("list_item_metadata_properties", [])
        for p in allowed_properties:
            load_properties.append(p)

        logging.debug(f"Loading properties: {', '.join(load_properties)}")
        self.sharepoint_context.load(items, load_properties)
        self.sharepoint_context.execute_query()

        allowed_properties = self.cfg.sharepoint_crawler.get("list_item_metadata_properties", [])
        all_properties = None
        for item in items:
            if len(allowed_properties) == 0:
                for k,v in item.properties.items():
                    if all_properties is None:
                        all_properties = set()
                    all_properties.add(k)
                logging.info(f"list_item_metadata_properties set to default([]) Available properties: {', '.join(all_properties)}")


            metadata = {k: v for k, v in item.properties.items() if k in allowed_properties}
            item_id = item.properties["ID"]
            metadata["list_id"] = str(target_list.id)
            metadata["list_item_id"] = str(item_id)
            if 'Attachments' in item.properties:
                attachment_files = item.attachment_files
                self.sharepoint_context.load(attachment_files)
                self.sharepoint_context.execute_query()
                for attachment in attachment_files:
                    filename = os.path.basename(attachment.server_relative_url)
                    filename, file_extension = os.path.splitext(filename)
                    if file_extension.lower() == ".zip":
                        doc_id = f"{target_list.id}-{item_id}-{filename}{file_extension}"
                        self.extract_and_upload_zip(attachment.server_relative_url, metadata, doc_id)
                    elif file_extension.lower() not in supported_extensions:
                        logging.warning(f"Skipping {attachment.server_relative_url} due to unsupported file type '{file_extension}'.")
                    else:
                        doc_id = f"{target_list.id}-{item_id}-{filename}"
                        attachment_url = attachment.resource_url
                        metadata["url"] = attachment_url

                        with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
                            logging.info(f"Item Id {item_id}: Downloading {attachment_url}")
                            logging.debug(f"Item Id {item_id}: Calling sharepoint_context.web.get_file_by_server_relative_url('{attachment.server_relative_url}')")
                            attachment_file = self.sharepoint_context.web.get_file_by_server_relative_url(attachment.server_relative_url)
                            logging.debug(f"attachment_file = {attachment_file}. Calling download...")

                            try:
                                attachment_file.download(f).execute_query()
                                succeeded = self.indexer.index_file(f.name, attachment_url, metadata, doc_id)
                            except ClientRequestException as e:
                                logging.error(f"ClientRequestException when downloading {attachment.server_relative_url}: {e}")
                                continue
                            finally:
                                if os.path.exists(f.name):
                                    os.remove(f.name)

                            if not succeeded:
                                logging.error(f"Error indexing attachment {filename} for list item {item_id}")

    def extract_and_upload_zip(self, zip_url: str, metadata: dict, doc_id_prefix: str) -> None:
        if not zip_url:
            logging.warning("No ZIP URL provided for extraction.")
            return

        tmp_zip_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb", delete=False) as tmp_zip:
                logging.info(f"Downloading ZIP file from {zip_url}")
                file_obj = self.sharepoint_context.web.get_file_by_server_relative_url(zip_url).download(tmp_zip)
                self.execute_with_retry(file_obj)
                tmp_zip_path = tmp_zip.name

            with tempfile.TemporaryDirectory() as extract_dir:
                with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                for root, _, files in os.walk(extract_dir):
                    for name in files:
                        file_path = os.path.join(root, name)
                        _, ext = os.path.splitext(name)
                        if ext.lower() not in supported_extensions:
                            logging.debug(f"Skipping {name} inside ZIP due to unsupported extension '{ext}'.")
                            continue

                        relative_path = os.path.relpath(file_path, extract_dir)
                        file_doc_id = f"{doc_id_prefix}/{relative_path}"
                        try:
                            succeeded = self.indexer.index_file(file_path, zip_url, metadata, file_doc_id)
                            if not succeeded:
                                logging.error(f"Failed to index extracted file: {relative_path}")
                        except Exception as e:
                            logging.error(f"Error indexing file {relative_path} from ZIP: {e}")
        finally:
            if tmp_zip_path and os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)