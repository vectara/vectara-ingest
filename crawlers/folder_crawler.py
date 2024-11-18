import logging
from core.crawler import Crawler
import os
import pathlib
import time
import pandas as pd


class FolderCrawler(Crawler):

    def crawl(self) -> None:
        folder = "/home/vectara/data"
        extensions = self.cfg.folder_crawler.get("extensions", ["*"])
        metadata_file = self.cfg.folder_crawler.get("metadata_file", None)
        if metadata_file:
            df = pd.read_csv(f"{folder}/{metadata_file}")
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}
        self.model = None

        # Walk the directory and upload files with the specified extension to Vectara
        logging.info(f"indexing files in {self.cfg.folder_crawler.path} with extensions {extensions}")
        source = self.cfg.folder_crawler.source
        for root, _, files in os.walk(folder):
            for file in files:
                if metadata_file and file.endswith(metadata_file):
                    continue
                file_extension = pathlib.Path(file).suffix
                if file_extension in extensions or "*" in extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    file_metadata = {
                        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getctime(file_path))),
                        'modified_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getmtime(file_path))),
                        'file_size': os.path.getsize(file_path),
                        'source': source,
                        'title': file_name
                    }
                    if file_name in metadata:
                        file_metadata.update(metadata.get(file_name, {}))
                    logging.info(f"Processing file {file_path}")
                    if file_extension in ['.mp3', '.mp4']:
                        self.indexer.index_media_file(file_path, metadata=file_metadata)
                    else:
                        self.indexer.index_file(filename=file_path, uri=file_name, metadata=file_metadata)
