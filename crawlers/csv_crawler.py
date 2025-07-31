import logging
import os
import pandas as pd
from core.crawler import Crawler
from core.dataframe_parser import (
    supported_by_dataframe_parser, 
    DataframeParser, 
    get_separator_by_file_name,
    determine_dataframe_type
)
from core.utils import get_docker_or_local_path
from core.summary import TableSummarizer

logger = logging.getLogger(__name__)

class CsvCrawler(Crawler):

    def crawl(self) -> None:
        orig_file_path = self.cfg.csv_crawler.file_path
        file_name = os.path.basename(orig_file_path)
        docker_path = f'/home/vectara/data/{file_name}'

        file_path = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=orig_file_path
        )

        if not supported_by_dataframe_parser(orig_file_path):
            raise Exception(f"'{orig_file_path}' is not supported by DataframeParser")

        logger.info(f"Indexing {orig_file_path}")
        
        # Initialize parser
        table_summarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
        df_parser = DataframeParser(self.cfg, self.cfg.csv_crawler, self.indexer, table_summarizer)

        # Load and process the dataframe
        file_type = determine_dataframe_type(orig_file_path)
        doc_title = os.path.basename(file_path)
        metadata = {'source': 'csv', 'file_path': orig_file_path}

        if file_type == 'csv':
            separator = get_separator_by_file_name(file_path)
            df = pd.read_csv(file_path, sep=separator)
            df_parser.process_dataframe(df, doc_id=orig_file_path, doc_title=doc_title, metadata=metadata)

        elif file_type == 'xls':
            xls = pd.ExcelFile(file_path)
            sheet_names = self.cfg.csv_crawler.get("sheet_names", xls.sheet_names)
            for sheet_name in sheet_names:
                if sheet_name not in xls.sheet_names:
                    logger.warning(f"Sheet '{sheet_name}' not found in '{orig_file_path}'. Skipping.")
                    continue
                
                df = pd.read_excel(xls, sheet_name=sheet_name)
                sheet_doc_id = f"{orig_file_path}_{sheet_name}"
                sheet_doc_title = f"{doc_title} - {sheet_name}"
                df_parser.process_dataframe(df, doc_id=sheet_doc_id, doc_title=sheet_doc_title, metadata=metadata)
