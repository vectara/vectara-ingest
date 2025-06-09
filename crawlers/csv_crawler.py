import logging
from core.crawler import Crawler
import pandas as pd
import unicodedata
import gc
import psutil
import ray

from core.indexer import Indexer
from core.utils import setup_logging, html_table_to_header_and_rows
from core.summary import TableSummarizer


class DFIndexer(object):
    def __init__(self, 
                 indexer: Indexer,
                 crawler: Crawler, 
                 title_column: str, 
                 text_columns: list[str], 
                 metadata_columns: list[str],
                 source: str,
                 verbose: bool = False
        ):
        self.crawler = crawler
        self.indexer = indexer
        self.title_column = title_column
        self.text_columns = text_columns
        self.metadata_columns = metadata_columns
        self.source = source
        self.count = 0
        self.verbose = verbose

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
        if len(df)>1 and self.verbose:
            logging.info(f"Indexing df for '{doc_id}' with {len(df)} rows")
        if len(titles)==0:
            titles = None
        doc_metadata = {'source': self.source}
        for column in self.metadata_columns:
            if len(df[column].unique())==1 and not pd.isnull(df[column].iloc[0]):
                doc_metadata[column] = df[column].iloc[0]
        title = titles[0] if titles else doc_id
        if self.verbose:
            logging.info(f"Indexing {len(df)} rows for doc_id '{doc_id}'")
        self.indexer.index_segments(doc_id, texts=texts, titles=titles, metadatas=metadatas, 
                                    doc_title=title, doc_metadata=doc_metadata)
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

    def index_dataframe(
            self, df: pd.DataFrame,
            name: str,
            mode: str,
            text_columns, title_column, metadata_columns, doc_id_columns,
            rows_per_chunk: int = 500,
            source: str = 'csv',
            ray_workers: int = 0
        ) -> None:
        if mode not in ['table', 'element']:
            raise ValueError(f"Unsupported mode '{mode}' for crawler. Supported modes are 'table' and 'element'.")
        
        if mode == 'table':
            # index full table ('table' mode)
            max_rows = 500 ### TEMP 10000
            max_cols = 20  ### TEMP 500
            if df.shape[0] > max_rows or df.shape[1] > max_cols:
                logging.warning(
                    f"Table size is too large for {name} in 'table' mode. "
                    f"Table will be truncated to no more than {max_rows} rows and {max_cols} columns."
                )
                df = df.iloc[:max_rows, :max_cols]

            table_summarizer = TableSummarizer(
                cfg=self.cfg,
                table_model_config=self.cfg.doc_processing.model_config.text,
            )
            table_summary = table_summarizer.summarize_table_text(df)
            if table_summary:
                cols, rows = html_table_to_header_and_rows(df.to_html(index=False))
                cols_not_empty = any(col for col in cols)
                rows_not_empty = any(any(cell for cell in row) for row in rows)
                print(f"Table '{name}' has {len(cols)} columns and {len(rows)} rows. Summary: {table_summary}")
                if rows_not_empty and cols_not_empty:
                    table_dict = {'headers': cols, 'rows': rows, 'summary': table_summary}
                    self.indexer.index_segments(
                        doc_id=f'table_{name}',
                        texts=[table_summary],
                        tables=[table_dict] if cols_not_empty or rows_not_empty else None,
                        doc_title=name,
                        doc_metadata={'source': source}
                    )
            else:
                logging.warning(f"Table summarization failed for the table {name} with {df.shape[0]} rows and {df.shape[1]} columns.")
            
            return

        # Index each row as a separate document ('element' mode)
        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)
        
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logging.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [
                ray.remote(DFIndexer).remote(
                    self.indexer, self, title_column, text_columns, metadata_columns, source, self.verbose
                )
                for _ in range(ray_workers)
            ]
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
        doc_id_columns = list(self.cfg.csv_crawler.get("doc_id_columns", []))
        column_types = self.cfg.csv_crawler.get("column_types", {})
        mode = self.cfg.csv_crawler.get("mode", "table")
        all_columns = text_columns + metadata_columns + doc_id_columns
        if not all_columns:
            all_columns = None
        if title_column:
            all_columns.append(title_column)

        orig_file_path = self.cfg.csv_crawler.file_path
        file_path = '/home/vectara/data/file'
        try:
            if orig_file_path.endswith('.csv'):
                dtypes = {column: 'Int64' if column_types.get(column)=='int' else column_types.get(column, 'str') 
                          for column in all_columns}
                sep = self.cfg.csv_crawler.get("separator", ",")
                df = pd.read_csv(file_path, usecols=all_columns, sep=sep, dtype=dtypes)
                df = df.astype(object)   # convert to native types
                dfs = [(orig_file_path, df)]
            elif orig_file_path.endswith('.xlsx'):
                sheet_names = self.cfg.csv_crawler.get("sheet_names", [])
                valid_sheet_names = pd.ExcelFile(file_path).sheet_names
                if not sheet_names:
                    sheet_names = valid_sheet_names
                if not sheet_names:
                    logging.warning(f"No sheets found in the XLSX file '{orig_file_path}'.")
                    return
                dfs = []
                for sheet_name in sheet_names:
                    if sheet_name not in valid_sheet_names:
                        logging.warning(f"Sheet '{sheet_name}' not found in the XLSX file '{orig_file_path}'.")
                        continue
                    logging.info(f"Reading XLSX sheet '{sheet_name}'")
                    df = pd.read_excel(file_path, usecols=all_columns, sheet_name=sheet_name)
                    dfs.append((sheet_name, df))
            else:
                logging.info(f"Unknown file extension for the file {orig_file_path}")
                return
        except Exception as e:
            logging.warning(f"Exception ({e}) occurred while loading file")
            return

        # Index each DF into Vectara
        for df_tuple in dfs:
            name = df_tuple[0]
            df = df_tuple[1]
            df[doc_id_columns] = df[doc_id_columns].astype(str)
            orig_size = len(df)

            select_condition = self.cfg.csv_crawler.get("select_condition", None)
            if select_condition:
                df = df.query(select_condition)
                logging.info(f"Selected {len(df)} rows out of {orig_size} rows using the select condition")

            # index the dataframe
            rows_per_chunk = int(self.cfg.csv_crawler.get("rows_per_chunk", 500) if 'csv_crawler' in self.cfg else 500)
            ray_workers = self.cfg.csv_crawler.get("ray_workers", 0)

            logging.info(f"indexing {len(df)} rows from the file '{orig_file_path}'")
            self.index_dataframe(
                df = df, mode = mode,
                name = name,
                text_columns = text_columns, title_column = title_column, 
                metadata_columns = metadata_columns, 
                doc_id_columns = doc_id_columns, 
                rows_per_chunk = rows_per_chunk, 
                source='csv', 
                ray_workers=ray_workers
            )