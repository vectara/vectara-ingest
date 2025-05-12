import os
import tempfile
import logging
from urllib.parse import urljoin

from shareplum import Office365
from shareplum.site import Site
from core.crawler import Crawler  # Assumes you have this base class

class SharepointCrawler(Crawler):
    """
    A SharePoint crawler implementation using SharePlum for on-premises SharePoint.

    This class authenticates with username/password, crawls folders, downloads supported documents,
    and indexes them.
    """

    def new_url(self, *paths) -> str:
        base = self.cfg.sharepoint_crawler.team_site_url.rstrip('/')
        for p in paths:
            base = urljoin(base + '/', p.lstrip('/'))
        return base

    def download_url(self, file) -> str:
        return self.new_url(file['ServerRelativeUrl'].lstrip('/'))

    def configure_sharepoint_context(self) -> None:
        self.base_url = self.cfg.sharepoint_crawler.team_site_url.rstrip('/')
        logging.info(f"Connecting to SharePoint at {self.base_url}")
        username = self.cfg.sharepoint_crawler.username
        password = self.cfg.sharepoint_crawler.password

        authcookie = Office365(self.base_url, username=username, password=password).GetCookies()
        self.sharepoint_site = Site(self.base_url, authcookie=authcookie)

    def crawl_folder(self) -> None:
        recursive = self.cfg.sharepoint_crawler.get('recursive', False)
        folder_path = self.cfg.sharepoint_crawler.target_folder.strip('/')
        logging.info(f"Crawling folder: {folder_path} (recursive={recursive})")

        supported_extensions = {
            ".pdf", ".md", ".odt", ".doc", ".docx", ".ppt",
            ".pptx", ".txt", ".html", ".htm", ".lxml", ".rtf", ".epub"
        }

        def process_folder(path):
            try:
                folder = self.sharepoint_site.Folder(path)
                files = folder.files
            except Exception as e:
                logging.error(f"Unable to access folder '{path}': {e}")
                return

            for file in files:
                name = file["Name"]
                ext = os.path.splitext(name)[1].lower()
                if ext not in supported_extensions:
                    logging.warning(f"Skipping unsupported file type: {file['ServerRelativeUrl']}")
                    continue

                metadata = {"url": self.download_url(file)}
                with tempfile.NamedTemporaryFile(suffix=ext, mode="wb", delete=False) as f:
                    try:
                        f.write(folder.get_file(name))
                        f.flush()
                        succeeded = self.indexer.index_file(f.name, metadata['url'], metadata, file['UniqueId'])
                    except Exception as e:
                        logging.error(f"Failed to process {name}: {e}")
                        succeeded = False
                    finally:
                        if os.path.exists(f.name):
                            os.remove(f.name)

                if not succeeded:
                    logging.error(f"Indexing failed for: {file['ServerRelativeUrl']}")

            if recursive:
                try:
                    subfolders = folder.folders
                    for sub in subfolders:
                        sub_path = os.path.join(path, sub["Name"])
                        if sub["Name"] not in {"Forms"}:  # skip system folders if needed
                            process_folder(sub_path)
                except Exception as e:
                    logging.error(f"Error accessing subfolders of {path}: {e}")

        process_folder(folder_path)

    def crawl(self) -> None:
        self.configure_sharepoint_context()
        if self.cfg.sharepoint_crawler.mode == 'folder':
            self.crawl_folder()
        else:
            raise Exception(f"Unsupported crawl mode: {self.cfg.sharepoint_crawler.mode}")
