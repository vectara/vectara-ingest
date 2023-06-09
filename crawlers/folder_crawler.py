import logging
from core.crawler import Crawler
import os
import pathlib
import time

class FolderCrawler(Crawler):

    def crawl(self):
        folder = "/home/vectara/data"
        extensions = self.cfg.folder_crawler.extensions

        # Walk the directory and upload files with the specified extension to Vectara
        logging.info(f"indexing files in {folder} with extensions {extensions}")
        for root, _, files in os.walk(folder):
            for file in files:
                file_extension = pathlib.Path(file).suffix
                if file_extension in extensions or "*" in extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    file_metadata = {
                        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getctime(file_path))),
                        'modified_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getmtime(file_path))),
                        'file_size': os.path.getsize(file_path),
                        'source': 'folder',
                        'title': file_name,
                        'url': file_name
                    }
                    self.indexer.index_file(filename=file_path, uri=file_name, metadata=file_metadata)
