import logging
from core.crawler import Crawler
import pandas as pd
import unicodedata
import gc
import psutil
import ray
import os

from core.indexer import Indexer
from core.utils import setup_logging, get_docker_or_local_path

class DFIndexer(object):
    def __init__(self, 
                 indexer: Indexer,
                 crawler: Crawler, 
                 title_column: str, 
                 text_columns: list[str], 
                 metadata_columns: list[str],
                 source: str,
        ):
        self.crawler = crawler
        self.indexer = indexer
        self.title_column = title_column
        self.text_columns = text_columns
        self.metadata_columns = metadata_columns
        self.source = source
        self.count = 0

    def setup(self):
        self.indexer.setup(use_playwright=False)
        setup_logging()

    def process(self, doc_id: str, df: pd.DataFrame) -> None:
        texts = []
        titles = []
        metadatas = []
        for _, row in df.iterrows():
            if self.title_column:
                titles.append(str(row[self.title_column]))
            text = ' - '.join(str(row[col]) for col in self.text_columns if pd.notnull(row[col])) + '\n'
            texts.append(unicodedata.normalize('NFD', text))
            md = {column: row[column] for column in self.metadata_columns if pd.notnull(row[column])}
            metadatas.append(md)
        if len(df)>1:
            logging.info(f"Indexing df for '{doc_id}' with {len(df)} rows")
        if len(titles)==0:
            titles = None
        doc_metadata = {'source': self.source}
        for column in self.metadata_columns:
            if len(df[column].unique())==1 and not pd.isnull(df[column].iloc[0]):
                doc_metadata[column] = df[column].iloc[0]
        title = titles[0] if titles else doc_id
        self.indexer.index_segments(doc_id, texts=texts, titles=titles, metadatas=metadatas, 
                                    doc_title=title, doc_metadata = doc_metadata)
        self.count += 1
        if self.count % 100==0:
            logging.info(f"Indexed {self.count} documents in actor {ray.get_runtime_context().get_actor_id()}")
        gc.collect()

class CsvCrawler(Crawler):

    def generate_dfs_to_index(self, df: pd.DataFrame, doc_id_columns, rows_per_chunk: int):
        if doc_id_columns:
            grouped = df.groupby(doc_id_columns)
            for name, group in grouped:
                if isinstance(name, str):
                    doc_id = name
                else:
                    doc_id = ' - '.join([str(x) for x in name if x])
                yield (doc_id, group)
        else:
            if rows_per_chunk < len(df):
                rows_per_chunk = len(df)
            for inx in range(0, df.shape[0], rows_per_chunk):
                sub_df = df[inx: inx+rows_per_chunk]
                name = f'rows {inx}-{inx+rows_per_chunk-1}'
                yield (name, sub_df)

    def index_dataframe(self, df: pd.DataFrame, 
                        text_columns, title_column, metadata_columns, doc_id_columns,
                        rows_per_chunk: int = 500,
                        source: str = 'csv',
                        ray_workers: int = 0
        ) -> None:
        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)
        
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(DFIndexer).remote(self.indexer, self, title_column, text_columns, metadata_columns, source) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, args_inx: a.process.remote(args_inx[0], args_inx[1]), 
                              self.generate_dfs_to_index(df, doc_id_columns, rows_per_chunk)))
        else:
            crawl_worker = DFIndexer(self.indexer, self, title_column, text_columns, metadata_columns, source)
            for df_tuple in self.generate_dfs_to_index(df, doc_id_columns, rows_per_chunk):
                crawl_worker.process(df_tuple[0], df_tuple[1])

    def crawl(self) -> None:
        text_columns = list(self.cfg.csv_crawler.get("text_columns", []))
        title_column = self.cfg.csv_crawler.get("title_column", None)
        metadata_columns = list(self.cfg.csv_crawler.get("metadata_columns", []))
        doc_id_columns = list(self.cfg.csv_crawler.get("doc_id_columns", None))
        column_types = self.cfg.csv_crawler.get("column_types", {})
        all_columns = text_columns + metadata_columns + doc_id_columns
        if title_column:
            all_columns.append(title_column)

        orig_file_path = self.cfg.csv_crawler.file_path
        docker_path = '/home/vectara/data/file'
        
        file_path = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=orig_file_path
        )
        
        try:
            if orig_file_path.endswith('.csv'):
                dtypes = {column: 'Int64' if column_types.get(column)=='int' else column_types.get(column, 'str') 
                          for column in all_columns}
                sep = self.cfg.csv_crawler.get("separator", ",")
                df = pd.read_csv(file_path, usecols=all_columns, sep=sep, dtype=dtypes)
                df = df.astype(object)   # convert to native types
            elif orig_file_path.endswith('.xlsx'):
                sheet_name = self.cfg.csv_crawler.get("sheet_name", 0)
                logging.info(f"Reading Sheet {sheet_name} from XLSX file")
                df = pd.read_excel(file_path, usecols=all_columns, sheet_name=sheet_name)
            else:
                logging.info(f"Unknown file extension for the file {file_path}")
                return
        except Exception as e:
            logging.warning(f"Exception ({e}) occurred while loading file")
            return

        # make sure all ID columns are a string type
        df[doc_id_columns] = df[doc_id_columns].astype(str)
        orig_size = len(df)

        select_condition = self.cfg.csv_crawler.get("select_condition", None)
        if select_condition:
            df = df.query(select_condition)
            logging.info(f"Selected {len(df)} rows out of {orig_size} rows using the select condition")

        # index the dataframe
        rows_per_chunk = int(self.cfg.csv_crawler.get("rows_per_chunk", 500) if 'csv_crawler' in self.cfg else 500)
        ray_workers = self.cfg.csv_crawler.get("ray_workers", 0)

        logging.info(f"indexing {len(df)} rows from the file {file_path}")
        self.index_dataframe(df, text_columns, title_column, metadata_columns, doc_id_columns, rows_per_chunk, source='csv', ray_workers=ray_workers)