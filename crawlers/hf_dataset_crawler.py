import logging
from crawlers.csv_crawler import CsvCrawler
import pandas as pd

class HfDatasetCrawler(CsvCrawler):

    def crawl(self) -> None:
        doc_id_columns = list(self.cfg.database_crawler.get("doc_id_columns", None))
        text_columns = list(self.cfg.database_crawler.get("text_columns", []))
        title_column = self.cfg.database_crawler.get("title_column", None)
        metadata_columns = list(self.cfg.database_crawler.get("metadata_columns", []))
        all_columns = text_columns + metadata_columns
        if title_column:
            all_columns.append(title_column)

        hf_dataset_name = self.cfg.database_crawler.hf_dataset_name
        df = pd.read_json(hf_dataset_name, lines=True)
        logging.info(f"indexing {len(df)} rows from the dataset {hf_dataset_name}'")
        self.index_dataframe(df, text_columns, title_column, metadata_columns, doc_id_columns)
