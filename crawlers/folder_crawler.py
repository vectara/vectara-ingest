import logging
import os
import pathlib
import time
import pandas as pd
import ray
import psutil

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import setup_logging, get_docker_or_local_path
from core.summary import TableSummarizer
from omegaconf import DictConfig
from core.dataframe_parser import (
    supported_by_dataframe_parser,
    DataframeParser,
    determine_dataframe_type,
    get_separator_by_file_name,
)

logger = logging.getLogger(__name__)

class FileCrawlWorker(object):
    def __init__(self, cfg: DictConfig, crawler_config: DictConfig, indexer: Indexer, num_per_second: int):
        self.indexer = indexer
        self.cfg = cfg
        self.crawler_config = crawler_config

    def setup(self):
        self.indexer.setup()
        setup_logging()
        # Initialize the parser once per worker
        table_summarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
        self.df_parser = DataframeParser(self.cfg, self.crawler_config, self.indexer, table_summarizer)

    def process(self, file_path: str, file_name: str, metadata: dict):
        extension = pathlib.Path(file_path).suffix
        try:
            if extension in [".mp3", ".mp4"]:
                self.indexer.index_media_file(file_path, metadata=metadata)
            
            elif supported_by_dataframe_parser(file_path):
                logger.info(f"Parsing dataframe {file_path}")
                file_type = determine_dataframe_type(file_path)
                doc_title = os.path.basename(file_path)
                
                if file_type == 'csv':
                    separator = get_separator_by_file_name(file_path)
                    df = pd.read_csv(file_path, sep=separator)
                    self.df_parser.process_dataframe(df, doc_id=file_path, doc_title=doc_title, metadata=metadata)

                elif file_type == 'xls':
                    xls = pd.ExcelFile(file_path)
                    sheet_names = self.crawler_config.get("sheet_names", xls.sheet_names)
                    for sheet_name in sheet_names:
                        if sheet_name not in xls.sheet_names:
                            logger.warning(f"Sheet '{sheet_name}' not found in '{file_path}'. Skipping.")
                            continue
                        
                        df = pd.read_excel(xls, sheet_name=sheet_name)
                        sheet_doc_id = f"{file_path}_{sheet_name}"
                        sheet_doc_title = f"{doc_title} - {sheet_name}"
                        self.df_parser.process_dataframe(df, doc_id=sheet_doc_id, doc_title=sheet_doc_title, metadata=metadata)

            else:
                uri_to_use = file_name if "url" not in metadata else metadata["url"]
                self.indexer.index_file(filename=file_path, uri=uri_to_use, metadata=metadata)

        except Exception as e:
            import traceback
            logger.error(f"Error while indexing {file_path}: {e}, traceback={traceback.format_exc()}")
            return -1
        return 0


class FolderCrawler(Crawler):

    def crawl(self) -> None:
        folder_config = self.cfg.folder_crawler
        docker_path = "/home/vectara/data"
        config_path = folder_config.path

        folder = get_docker_or_local_path(docker_path=docker_path, config_path=config_path)

        extensions = folder_config.get("extensions", ["*"])
        metadata_file = folder_config.get("metadata_file", None)
        ray_workers = folder_config.get("ray_workers", 0)
        num_per_second = max(folder_config.get("num_per_second", 10), 1)
        source = folder_config.get("source", "folder")

        if metadata_file:
            df = pd.read_csv(f"{folder}/{metadata_file}")
            metadata = {row["filename"].strip(): row.drop("filename").to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}

        logger.info(f"Indexing files in {folder_config.path} with extensions {extensions}")
        
        files_to_process = []
        for root, _, files in os.walk(folder):
            for file in files:
                if metadata_file and file.endswith(metadata_file):
                    continue

                file_extension = pathlib.Path(file).suffix
                if "*" in extensions or file_extension in extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    
                    rel_under_container = os.path.relpath(root, folder)
                    full_folder_path = os.path.normpath(os.path.join(folder_config.path, rel_under_container))
                    parent = os.path.basename(full_folder_path)

                    file_metadata = {
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(os.path.getctime(file_path))),
                        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(os.path.getmtime(file_path))),
                        "file_size": os.path.getsize(file_path),
                        "source": source,
                        "title": file_name,
                        "parent_folder": parent,
                        "folder_path": full_folder_path,
                    }
                    if file_name in metadata:
                        file_metadata.update(metadata.get(file_name, {}))
                    
                    files_to_process.append((file_path, file_name, file_metadata))

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        # Decide which config to use for the dataframe parser
        df_parser_config = self.cfg.get('dataframe_processing', self.cfg.get('folder_crawler'))

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [
                ray.remote(FileCrawlWorker).remote(self.cfg, df_parser_config, self.indexer, num_per_second)
                for _ in range(ray_workers)
            ]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u[0], u[1], u[2]), files_to_process))
        else:
            crawl_worker = FileCrawlWorker(self.cfg, df_parser_config, self.indexer, num_per_second)
            crawl_worker.setup()
            for inx, (file_path, file_name, file_metadata) in enumerate(files_to_process):
                if (inx + 1) % 100 == 0:
                    logger.info(f"Crawling file number {inx+1} out of {len(files_to_process)}")
                crawl_worker.process(file_path, file_name, file_metadata)
