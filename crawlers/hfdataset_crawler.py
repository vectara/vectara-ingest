import logging
from core.crawler import Crawler
from datasets import load_dataset
import psutil
import ray

from core.indexer import Indexer
from core.utils import setup_logging
from itertools import islice

class RowIndexer(object):
    def __init__(self, indexer: Indexer, crawler: Crawler):
        self.crawler = crawler
        self.indexer = indexer

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def process(self, inx: int, row: dict,
                id_column: str,
                text_columns: list, metadata_columns: list,
                title_column: str = None):
        if inx % 100 == 0:
            logging.info(f"Indexing document # {inx+1}")
        doc_id = str(row[id_column]) if id_column else f'doc-{inx}'
        texts = [' - '.join([str(row[col]) for col in text_columns if row[col]]) + '\n']
        doc_title = str(row[title_column]) if title_column else None
        doc_metadata = {column: row[column] for column in metadata_columns}
        doc_metadata["_source"] = doc_metadata.get("source", "Unknown source")
        doc_metadata["source"] = "hf_dataset"
        self.indexer.index_segments(doc_id, texts=texts, 
                                    doc_title=doc_title, doc_metadata=doc_metadata)
        del texts, doc_metadata, doc_title, doc_id

class HfdatasetCrawler(Crawler):

    def crawl(self) -> None:
        text_columns = list(self.cfg.hfdataset_crawler.get("text_columns", []))
        title_column = self.cfg.hfdataset_crawler.get("title_column", None)
        id_column = self.cfg.hfdataset_crawler.get("id_column", None)
        metadata_columns = list(self.cfg.hfdataset_crawler.get("metadata_columns", []))

        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)

        dataset_name = self.cfg.hfdataset_crawler.dataset_name
        split = self.cfg.hfdataset_crawler.get("split", "corpus")
        logging.info(f"Loading data from {dataset_name}")
        ds = load_dataset(dataset_name, streaming=True)[split]

        if "select_condition" in self.cfg.hfdataset_crawler:
            select_condition = self.cfg.hfdataset_crawler.select_condition
            logging.info(f"Filtering by condition: {select_condition}")
            key, value = select_condition.split('=')
            key = key.strip()
            value = value.strip().strip("'")
            ds = ds.filter(lambda s: s[key] == value)

        num_rows = self.cfg.hfdataset_crawler.get("num_rows", None)
        if num_rows is not None:
            logging.info(f"Limiting to first {num_rows} rows")

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
            _ = list(pool.map(lambda a,args: a.process.remote(args[0], args[1], id_column, text_columns, metadata_columns, title_column), 
                              enumerate(islice(ds, num_rows))))
        else:
            crawl_worker = RowIndexer(self.indexer, self)
            for inx, row in enumerate(ds):
                if num_rows and inx >= num_rows:
                    break
                crawl_worker.process(inx, row, id_column, text_columns, metadata_columns, title_column)
