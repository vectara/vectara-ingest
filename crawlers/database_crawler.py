import logging
from crawlers.csv_crawler import CsvCrawler
import sqlalchemy
import pandas as pd

class DatabaseCrawler(CsvCrawler):

    def crawl(self) -> None:
        text_columns = list(self.cfg.database_crawler.get("text_columns", []))
        title_column = self.cfg.database_crawler.get("title_column", None)
        metadata_columns = list(self.cfg.database_crawler.get("metadata_columns", []))
        doc_id_columns = list(self.cfg.database_crawler.get("doc_id_columns", None))
        all_columns = text_columns + metadata_columns + doc_id_columns
        if title_column:
            all_columns.append(title_column)

        select_condition = self.cfg.database_crawler.get("select_condition", None)
        db_url = self.cfg.database_crawler.db_url
        db_table = self.cfg.database_crawler.db_table

        if select_condition:
            query = f'SELECT {",".join(all_columns)} FROM {db_table} WHERE {select_condition}'
        else:
            query = f'SELECT {",".join(all_columns)} FROM {db_table}'

        conn = sqlalchemy.create_engine(db_url).connect()
        df = pd.read_sql_query(sqlalchemy.text(query), conn)

        # make sure all ID columns are a string type
        df[doc_id_columns] = df[doc_id_columns].astype(str)

        logging.info(f"indexing {len(df)} rows from the database using query: '{query}'")
        rows_per_chunk = int(self.cfg.database_crawler.get("rows_per_chunk", 500) if 'database_crawler' in self.cfg else 500)
        ray_workers = self.cfg.database_crawler.get("ray_workers", 0)
        self.index_dataframe(df, text_columns, title_column, metadata_columns, doc_id_columns, rows_per_chunk, source='database', ray_workers=ray_workers)
