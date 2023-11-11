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
                gr_str = name if type(name)==str else ' - '.join(str(x) for x in name)
                index_df(doc_id=gr_str, title=gr_str, df=group)
        else:
            rows_per_chunk = self.cfg.csv_crawler.get("rows_per_chunk", 500)
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

        csv_file = '/home/vectara/data/file.csv'
        sep = self.cfg.csv_crawler.get("separator", ",")
        df = pd.read_csv(csv_file, usecols=all_columns, sep=sep)

        csv_path = self.cfg.csv_crawler.csv_path
        logging.info(f"indexing {len(df)} rows from the CSV file {csv_path}")

        doc_id_columns = list(self.cfg.csv_crawler.get("doc_id_columns", None))
        self.index_dataframe(df, text_columns, title_column, metadata_columns, doc_id_columns)