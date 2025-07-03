import logging

logger = logging.getLogger(__name__)
from core.crawler import Crawler
from core.dataframe_parser import supported_by_dataframe_parser, load_dataframe_metadata, DataframeParser, \
    DataFrameMetadata, determine_dataframe_type
from core.utils import get_docker_or_local_path
from core.summary import TableSummarizer
from dataclasses import dataclass, field


@dataclass
class CsvCrawlerConfig:
    chunk_size: int = 100
    chunk_overlap: int = 20
    file_path: str = ""
    max_rows: int = 1000000
    max_columns: int = 1000000
    mode: str = 'table'
    doc_id_columns: list[str] | None = None
    text_columns: list[str] = field(default_factory=list)
    metadata_columns: list[str] = field(default_factory=list)
    title_column: str | None = None


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
            data_frame_type = determine_dataframe_type(orig_file_path)
            df_metadata: DataFrameMetadata = load_dataframe_metadata(file_path, data_frame_type=data_frame_type)
            df_parser.parse(df_metadata, file_path, metadata)
        else:
            raise Exception(f"'{orig_file_path}' is not supported by DataframeParser")
