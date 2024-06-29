import logging
from core.crawler import Crawler
import pandas as pd
import unicodedata

class CsvCrawler(Crawler):

    def index_dataframe(self, df: pd.DataFrame, text_columns, title_column, metadata_columns, doc_id_columns) -> None:
        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)
        
        def index_df(doc_id: str, title: str, df: pd.DataFrame) -> None:
            texts = []
            titles = []
            metadatas = []
            for _, row in df.iterrows():
                if title_column:
                    titles.append(str(row[title_column]))
                text = ' - '.join(str(x) for x in row[text_columns].tolist() if x) + '\n'
                texts.append(unicodedata.normalize('NFD', text))
                metadatas.append({column: row[column] for column in metadata_columns})
            logging.info(f"Indexing df for '{doc_id}' with ({len(df)}) rows")
            if len(titles)==0:
                titles = None
            self.indexer.index_segments(doc_id, texts=texts, titles=titles, metadatas=metadatas, 
                                        doc_title=title, doc_metadata = {'source': 'csv'})

        if doc_id_columns:
            grouped = df.groupby(doc_id_columns)
            for name, group in grouped:
                gr_str = name if isinstance(name, str) else ' - '.join(str(x) for x in name)
                index_df(doc_id=gr_str, title=gr_str, df=group)
        else:
            rows_per_chunk = self.cfg.csv_crawler.get("rows_per_chunk", 500) if 'csv_crawler' in self.cfg else 500
            if rows_per_chunk < len(df):
                rows_per_chunk = len(df)
            for inx in range(0, df.shape[0], rows_per_chunk):
                sub_df = df[inx: inx+rows_per_chunk]
                name = f'rows {inx}-{inx+rows_per_chunk-1}'
                index_df(doc_id=name, title=name, df=sub_df)
        
    def crawl(self) -> None:
        text_columns = list(self.cfg.csv_crawler.get("text_columns", []))
        title_column = self.cfg.csv_crawler.get("title_column", None)
        metadata_columns = list(self.cfg.csv_crawler.get("metadata_columns", []))
        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)

        orig_file_path = self.cfg.csv_crawler.file_path
        file_path = '/home/vectara/data/file'
        try:
            if orig_file_path.endswith('.csv'):
                sep = self.cfg.csv_crawler.get("separator", ",")
                df = pd.read_csv(file_path, usecols=all_columns, sep=sep)
            elif orig_file_path.endswith('.xlsx'):
                sheet_name = self.cfg.csv_crawler.get("sheet_name", 0)
                logging.info(f"Reading Sheet {sheet_name} from XLSX file")
                df = pd.read_excel(file_path, usecols=all_columns, sheet_name=sheet_name)
            else:
                logging.info(f"Unknown file extension for the file {orig_file_path}")
                return
        except Exception as e:
            logging.warning(f"Exception ({e}) occurred while loading file")
            return

        logging.info(f"indexing {len(df)} rows from the file {file_path}")
        doc_id_columns = list(self.cfg.csv_crawler.get("doc_id_columns", None))
        self.index_dataframe(df, text_columns, title_column, metadata_columns, doc_id_columns)