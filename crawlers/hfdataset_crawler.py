import logging
from core.crawler import Crawler
from datasets import load_dataset
import unicodedata
import psutil
import ray
from itertools import islice

from core.indexer import Indexer
from core.utils import setup_logging

class RowIndexer(object):
    def __init__(self, indexer: Indexer, crawler: Crawler):
        self.crawler = crawler
        self.indexer = indexer

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, inx: int, row: dict,
                text_columns: list, metadata_columns: list,
                title_column: str = None):
        doc_id = f'doc-{inx}'
        text = ' - '.join([str(row[col]) for col in text_columns if row[col]]) + '\n'
        texts = [unicodedata.normalize('NFD', text)]
        if title_column:
            titles = str(row[title_column])
        doc_metadata = [{column: row[column] for column in metadata_columns}]
        doc_metadata["source"] = "hf_dataset"
        self.indexer.index_segments(doc_id, texts=texts, titles=titles, metadatas=[], 
                                    doc_metadata=doc_metadata)

class HfdatasetCrawler(Crawler):

    def crawl(self) -> None:
        text_columns = list(self.cfg.hfdataset_crawler.get("text_columns", []))
        title_column = self.cfg.hfdataset_crawler.get("title_column", None)
        metadata_columns = list(self.cfg.hfdataset_crawler.get("metadata_columns", []))
        metadata_columns = ["_source" if col == "source" else col for col in metadata_columns]

        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)

        dataset_name = self.cfg.hfdataset_crawler.dataset_name
        split = self.cfg.hfdataset_crawler.get("split", "corpus")
        logging.info(f"Loading data from {dataset_name}")
        ds = load_dataset(dataset_name, streaming=True)
        
        num_rows = self.cfg.hfdataset_crawler.get("num_rows", None)
        ray_workers = self.cfg.hfdataset_crawler.get("ray_workers", 0)   # -1: use ray with ALL cores, 0: dont use ray
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(RowIndexer).remote(self.indexer, self) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a,args: a.process.remote(args[0], args[1], text_columns, metadata_columns, title_column), 
                              enumerate(islice(ds[split], num_rows))))
        else:
            crawl_worker = RowIndexer(self.indexer, self)
            for inx, row in enumerate(ds[split]):
                if inx >= num_rows:
                    break
                if inx % 100 == 0:
                    logging.info(f"Indexing {inx}th document")
                crawl_worker.process(inx, row, text_columns, metadata_columns, title_column)
