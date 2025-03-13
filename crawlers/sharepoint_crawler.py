import logging
from importlib.resources import contents

from office365.sharepoint.client_context import ClientContext
from office365.sharepoint.files.file import File
from furl import furl
import os
import tempfile

from core.crawler import Crawler

def print_download_progress(offset):
    # type: (int) -> None
    print("Downloaded '{0}' bytes...".format(offset))

class SharepointCrawler(Crawler):

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
        download_url = self.new_url("_layouts/15/download.aspx")
        download_url.args['SourceUrl'] = file.serverRelativeUrl
        return download_url.url

    def configure_sharepoint_context(self)-> None:
        self.base_url = furl(self.cfg.sharepoint_crawler.team_site_url)

        self.team_site_url = self.cfg.sharepoint_crawler.team_site_url
        logging.info(f"team_site_url = '{self.team_site_url}")
        auth_type = self.cfg.sharepoint_crawler.get('auth_type', 'user_credentials')

        context = ClientContext(self.team_site_url)

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
                    cert_settings['passphrase'] = self.cfg.sharepoint_crawler.get('cert_passphrase')

                self.sharepoint_context = context.with_client_certificate(self.cfg.sharepoint_crawler.tenant_id, **cert_settings)
            case _:
                raise Exception(f"Unknown auth_type of f{auth_type}")

    def crawl_folder(self) -> None:
        recursive = self.cfg.sharepoint_crawler.get('recursive', False)
        target_folder = self.cfg.sharepoint_crawler.target_folder
        logging.info(f"target_folder = '{target_folder}' recursive = {recursive}")
        root_folder = self.sharepoint_context.web.get_folder_by_server_relative_path(target_folder)
        files = root_folder.get_files(recursive=recursive).execute_query()
        for file in files:
            supported_extensions = {
                ".pdf", ".md", ".odt", ".doc", ".docx", ".ppt",
                ".pptx", ".txt", ".html", ".htm", ".lxml",
                ".rtf", ".epub"
            }
            filename, file_extension = os.path.splitext(file.name)
            if not file_extension in supported_extensions:
                logging.warning(f"Skipping {file.serverRelativeUrl} because it's an unsupported file type.")
                continue

            metadata = {
                'url': self.download_url(file),
            }

            with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
                logging.debug(f"Writing content for {file.unique_id} to {f.name}")
                file.download_session(f).execute_query()
                f.flush()
                f.close()

                try:
                    succeeded = self.indexer.index_file(f.name, metadata['url'], metadata, file.unique_id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

                if not succeeded:
                    logging.error(f"Error indexing {file.unique_id} - {file.serverRelativeUrl}")



    def crawl(self) -> None:
        """
        Execute the Confluence crawl process.

        1. Configures the session and authentication.
        2. Executes a Confluence CQL query to find pages/blogposts.
        3. Fetches their content and processes attachments (if enabled).
        4. Passes all content to the indexer for indexing.

        This method loops over paginated search results until exhausted.
        """
        self.configure_sharepoint_context()

        mode = self.cfg.sharepoint_crawler.mode
        logging.info(f"mode = {mode}")
        match mode:
            case 'folder':
                self.crawl_folder()
            case _:
                raise Exception(f"Unknown mode of f{mode}")
