import logging

logger = logging.getLogger(__name__)
from core.crawler import Crawler
from core.dataframe_parser import supported_by_dataframe_parser, load_dataframe_metadata, DataframeParser, \
    DataFrameMetadata
from core.utils import get_docker_or_local_path
from core.summary import TableSummarizer


class CsvCrawler(Crawler):

    def crawl(self) -> None:
        orig_file_path = self.cfg.csv_crawler.file_path
        docker_path = '/home/vectara/data/file'

        file_path = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=orig_file_path
        )

        metadata = {}
        if supported_by_dataframe_parser(orig_file_path):
            logger.info(f"Indexing {orig_file_path}")
            table_summarizer: TableSummarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
            df_parser: DataframeParser = DataframeParser(self.cfg, self.cfg.csv_crawler, self.indexer, table_summarizer)
            df_metadata: DataFrameMetadata = load_dataframe_metadata(file_path)
            df_parser.parse(df_metadata, file_path, metadata)
        else:
            raise Exception(f"'{orig_file_path}' is not supported by DataframeParser")
