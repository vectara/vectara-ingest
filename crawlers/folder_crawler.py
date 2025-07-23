import logging

from core.dataframe_parser import supported_by_dataframe_parser, DataframeParser, load_dataframe_metadata, DataFrameMetadata

logger = logging.getLogger(__name__)
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
from core.summary import TableSummarizer
from omegaconf import DictConfig
from dataclasses import dataclass, field


@dataclass
class FolderCrawlerConfig:
    path: str
    extensions: list[str] = field(default_factory=lambda: ['*'])
    metadata_file: str|None = None
    ray_workers: int = 0
    num_per_second: int = 10
    source: str = "folder"

class FileCrawlWorker(object):
    def __init__(self, cfg:DictConfig, indexer: Indexer, crawler: Crawler, num_per_second: int):
        self.crawler = crawler
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)
        self.cfg = cfg

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, file_path: str, file_name: str, metadata: dict):
        extension = pathlib.Path(file_path).suffix
        try:
            if extension in ['.mp3', '.mp4']:
                self.indexer.index_media_file(file_path, metadata=metadata)
            elif supported_by_dataframe_parser(file_path):
                logger.info(f"Indexing {file_path}")
                table_summarizer:TableSummarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
                df_parser:DataframeParser = DataframeParser(self.cfg, None, self.indexer, table_summarizer)
                df_metadata:DataFrameMetadata = load_dataframe_metadata(file_path)
                df_parser.parse(df_metadata, file_path, metadata)
            else:
                uri_to_use = file_name if 'url' not in metadata else metadata['url']
                self.indexer.index_file(filename=file_path, uri=uri_to_use, metadata=metadata)
        except Exception as e:
            import traceback
            logger.error(
                f"Error while indexing {file_path}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0

class FolderCrawler(Crawler):

    @property
    def folder_path(self) -> str:
        return self.cfg.folder_crawler.path

    @property
    def extensions(self) -> list:
        return self.cfg.folder_crawler.get("extensions", ["*"])

    @property
    def metadata_file(self) -> str:
        return self.cfg.folder_crawler.get("metadata_file", None)

    @property
    def ray_workers(self) -> int:
        return self.cfg.folder_crawler.get("ray_workers", 0)

    @property
    def num_per_second(self) -> int:
        return max(self.cfg.folder_crawler.get("num_per_second", 10), 1)

    @property
    def source(self) -> str:
        return self.cfg.folder_crawler.get("source", "folder")

    def crawl(self) -> None:
        docker_path = '/home/vectara/data'
        config_path = self.folder_path

        folder = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=config_path
        )

        if self.metadata_file:
            df = pd.read_csv(f"{folder}/{self.metadata_file}")
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}
        self.model = None

        # Walk the directory and upload files with the specified extension to Vectara
        logger.info(f"indexing files in {self.cfg.folder_crawler.path} with extensions {extensions}")
        files_to_process = []
        for root, _, files in os.walk(folder):
            for file in files:
                # don't index the self.metadata_file if it exists
                if self.metadata_file and file.endswith(self.metadata_file):
                    continue

                file_extension = pathlib.Path(file).suffix
                if file_extension in self.extensions or "*" in self.extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    rel_under_container = os.path.relpath(root, folder)
                    full_folder_path = os.path.normpath(os.path.join(self.folder_path, rel_under_container))
                    parent = os.path.basename(full_folder_path)
                    file_metadata = {
                        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getctime(file_path))),
                        'last_updated': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(os.path.getmtime(file_path))),
                        'file_size': os.path.getsize(file_path),
                        'source': self.source,
                        'title': file_name,
                        'parent_folder': parent,
                        'folder_path': full_folder_path,
                    }
                    if file_name in metadata:
                        file_metadata.update(metadata.get(file_name, {}))
                    files_to_process.append((file_path, file_name, file_metadata))

        if self.ray_workers == -1:
            self.ray_workers = psutil.cpu_count(logical=True)

        if self.ray_workers > 0:
            logger.info(f"Using {self.ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=self.ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(FileCrawlWorker).remote(self.cfg, self.indexer, self, self.num_per_second) for _ in range(self.ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u[0], u[1], u[2]), files_to_process))
        else:
            crawl_worker = FileCrawlWorker(self.cfg, self.indexer, self, self.num_per_second)
            for inx, tup in enumerate(files_to_process):
                if inx % 100 == 0:
                    logger.info(f"Crawling URL number {inx+1} out of {len(files_to_process)}")
                file_path, file_name, file_metadata = tup
                crawl_worker.process(file_path, file_name, file_metadata)
