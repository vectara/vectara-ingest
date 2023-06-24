import logging
from core.crawler import Crawler
import pandas as pd
import unicodedata

class CsvCrawler(Crawler):

    def crawl(self):        
        text_columns = self.cfg.csv_crawler.text_columns
        metadata_columns = self.cfg.csv_crawler.metadata_columns
        csv_path = self.cfg.csv_crawler.csv_path
        rows_per_chunk = self.cfg.csv_crawler.get("rows_per_chunk", 500)

        all_columns = text_columns + metadata_columns
        df = pd.read_csv(csv_path, usecols=all_columns)
        
        logging.info(f"indexing {len(df)} rows from the CSV file {csv_path}")

        doc_id = 0
        parts = []
        metadatas = []
        for index, row in df.iterrows():
            text = ' - '.join(row[text_columns].tolist())
            parts.append(unicodedata.normalize('NFD', text))
            metadatas.append({column: row[column] for column in metadata_columns})  
            if index % rows_per_chunk == 0:
                logging.info(f"Indexing rows {doc_id*rows_per_chunk} to {(doc_id+1)*rows_per_chunk-1}")
                self.indexer.index_segments(str(doc_id), parts, metadatas, doc_metadata = {'source': 'csv', 'rows': f'{doc_id*rows_per_chunk} - {(doc_id+1)*rows_per_chunk-1}'})
                doc_id += 1
                parts = []
                metadatas = []
        