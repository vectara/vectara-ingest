import logging
import sqlalchemy
import pandas as pd
from core.crawler import Crawler
from core.dataframe_parser import DataframeParser
from core.summary import TableSummarizer

logger = logging.getLogger(__name__)

class DatabaseCrawler(Crawler):

    def crawl(self) -> None:
        # Configuration extraction
        db_config = self.cfg.database_crawler
        text_columns = list(db_config.get("text_columns", []))
        title_column = db_config.get("title_column", None)
        metadata_columns = list(db_config.get("metadata_columns", []))
        doc_id_columns = list(db_config.get("doc_id_columns", []))
        
        all_columns = text_columns + metadata_columns + doc_id_columns
        if title_column and title_column not in all_columns:
            all_columns.append(title_column)
        
        db_url = db_config.db_url
        db_table = db_config.db_table
        select_condition = db_config.get("select_condition", None)

        # Build and execute query
        query = f'SELECT {",".join(all_columns)} FROM {db_table}'
        if select_condition:
            query += f' WHERE {select_condition}'

        logger.info(f"Executing query: '{query}'")
        conn = sqlalchemy.create_engine(db_url).connect()
        df = pd.read_sql_query(sqlalchemy.text(query), conn)

        # Ensure ID columns are strings
        if doc_id_columns:
            df[doc_id_columns] = df[doc_id_columns].astype(str)

        logger.info(f"Indexing {len(df)} rows from the database.")

        # Initialize parser and process the DataFrame
        table_summarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
        df_parser = DataframeParser(self.cfg, db_config, self.indexer, table_summarizer)
        
        metadata = {'source': 'database'}
        df_parser.process_dataframe(df, doc_id=db_table, doc_title=db_table, metadata=metadata)
