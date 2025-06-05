import logging
import os
import pathlib
import time
import pandas as pd

from slugify import slugify

import ray
import psutil

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import RateLimiter, setup_logging, get_docker_or_local_path

class FileCrawlWorker(object):
    def __init__(self, indexer: Indexer, crawler: Crawler, num_per_second: int):
        self.crawler = crawler
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, file_path: str, file_name: str, metadata: dict):
        extension = pathlib.Path(file_path).suffix
        try:
            if extension in ['.mp3', '.mp4']:
                self.indexer.index_media_file(file_path, metadata=metadata)
            else:
                self.indexer.index_file(filename=file_path, uri=file_name, metadata=metadata)
        except Exception as e:
            import traceback
            logging.error(
                f"Error while indexing {file_path}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0

class FolderCrawler(Crawler):

    def crawl(self) -> None:
        docker_path = '/home/vectara/data'
        config_path = self.cfg.folder_crawler.path
        
        folder = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=config_path
        )
        
        extensions = self.cfg.folder_crawler.get("extensions", ["*"])
        metadata_file = self.cfg.folder_crawler.get("metadata_file", None)
        ray_workers = self.cfg.folder_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        num_per_second = max(self.cfg.folder_crawler.get("num_per_second", 10), 1)
        source = self.cfg.folder_crawler.get("source", "folder")

        if metadata_file:
            df = pd.read_csv(f"{folder}/{metadata_file}")
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}
        self.model = None

        # Walk the directory and upload files with the specified extension to Vectara
        logging.info(f"indexing files in {self.cfg.folder_crawler.path} with extensions {extensions}")
        files_to_process = []
        for root, _, files in os.walk(folder):
            for file in files:
                if metadata_file and file.endswith(metadata_file):
                    continue
                file_extension = pathlib.Path(file).suffix
                if file_extension in extensions or "*" in extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    rel_under_container = os.path.relpath(root, folder)
                    full_folder_path = os.path.normpath(os.path.join(self.cfg.folder_crawler.path, rel_under_container))
                    parent = os.path.basename(full_folder_path)
                    file_metadata = {
                        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getctime(file_path))),
                        'last_updated': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getmtime(file_path))),
                        'file_size': os.path.getsize(file_path),
                        'source': source,
                        'title': file_name,
                        'parent_folder': parent,
                        'folder_path': full_folder_path,
                    }
                    if file_name in metadata:
                        file_metadata.update(metadata.get(file_name, {}))
                    files_to_process.append((file_path, file_name, file_metadata))

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(FileCrawlWorker).remote(self.indexer, self, num_per_second) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u[0], u[1], u[2]), files_to_process))
        else:
            crawl_worker = FileCrawlWorker(self.indexer, self, num_per_second)
            for inx, tup in enumerate(files_to_process):
                if inx % 100 == 0:
                    logging.info(f"Crawling URL number {inx+1} out of {len(files_to_process)}")
                file_path, file_name, file_metadata = tup
                crawl_worker.process(file_path, file_name, file_metadata)
