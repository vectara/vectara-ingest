import logging

logger = logging.getLogger(__name__)
import os
import pandas as pd
from omegaconf import DictConfig
from core.summary import TableSummarizer
from core.utils import html_table_to_header_and_rows
from core.indexer import Indexer

class DataFrameMetadata(object):
    def __init__(self, sheet_names: list[str] | None):
        self.sheet_names = sheet_names

    def title(self):
        raise NotImplementedError('Method not implemented')

class SimpleDataFrameMetadata(DataFrameMetadata):
    def __init__(self, sheet_names: list[str] | None):
        super().__init__(sheet_names)

class CsvDataFrameMetadata(SimpleDataFrameMetadata):
    def __init__(self, file_path: str):
        self.file_path = file_path
        super().__init__(None)

    def title(self):
        return os.path.basename(self.file_path)

    def open_dataframe(self, sheet_name: str = None):
        if not sheet_name is None:
            logger.warning(
                f"CsvDataFrameMetadata:Sheet Name '{sheet_name}' requested for csv '{self.file_path}'. Ignoring")

        logger.debug(
            f"CsvDataFrameMetadata:open_dataframe(sheet_name='{sheet_name}') - Opening '{self.file_path}' with .read_csv.")
        return pd.read_csv(self.file_path)


class SheetBasedDataFrameMetadata(DataFrameMetadata):
    def __init__(self, sheet_names: list[str] | None):
        super().__init__(sheet_names)


class XlsBasedDataFrameMetadata(SheetBasedDataFrameMetadata):
    def __init__(self, file_path: str):
        self.file_path = file_path
        logger.debug(
            f"XlsBasedDataFrameMetadata:__init__('{file_path}') - Loading as pd.ExcelFile to retrieve sheet names.")
        xls = pd.ExcelFile(file_path)
        super().__init__(xls.sheet_names)

    def open_dataframe(self, sheet_name: str = None):
        logger.debug(
            f"XlsBasedDataFrameMetadata:open_dataframe(sheet_name='{sheet_name}') - Opening '{self.file_path}' with .read_excel.")
        return pd.read_excel(self.file_path, sheet_name=sheet_name)

    def title(self):
        return os.path.basename(self.file_path)

supported_dataframe_extensions = {
    '.csv': 'csv',
    '.tsv': 'csv',
    '.xls': 'xls',
    '.xlsx': 'xls',
}


def is_dataframe_supported(file_path: str):
    _, extension = os.path.splitext(file_path)
    return extension in supported_dataframe_extensions


def determine_dataframe_type(file_path: str):
    logger.debug(f"determine_dataframe_type('{file_path}') - determining dataframe type.")
    _, extension = os.path.splitext(file_path)

    if extension in supported_dataframe_extensions:
        return supported_dataframe_extensions[extension]
    else:
        logger.warning(f"determine_dataframe_type('{file_path}) - Extension '{extension}' not supported.")
        return None


def load_dataframe_metadata(file_path: str, data_frame_type: str | None = None):
    if not data_frame_type:
        data_frame_type = determine_dataframe_type(file_path)
    else:
        logger.debug(
            f"load_dataframe_metadata('{file_path}) - using caller supplied data_frame_type='{data_frame_type}'")

    logger.debug(f"load_dataframe_metadata('{file_path}) - Loading as '{data_frame_type}'")

    if 'csv' == data_frame_type:
        return CsvDataFrameMetadata(file_path)
    elif 'xls' == data_frame_type:
        return XlsBasedDataFrameMetadata(file_path)
    else:
        raise ValueError(f"Unsupported dataframe type of '{data_frame_type}'")


class DataframeParser(object):

    def __init__(self, cfg: DictConfig, parser_config: DictConfig, indexer:Indexer, table_summarizer:TableSummarizer):
        self.cfg: DictConfig = cfg
        self.parser_config: DictConfig = parser_config
        self.truncate_table_if_over_max = self.parser_config.get("truncate_table_if_over_max", True)
        self.max_rows = int(self.parser_config.get("max_rows", 500))  ### TEMP 10000
        self.max_cols = int(self.parser_config.get("max_cols", 20))  ### TEMP 500
        self.sheet_names = self.parser_config.get("sheet_names", [])
        self.mode = self.parser_config.get("mode", "table")
        self.indexer:Indexer = indexer
        self.table_summarizer:TableSummarizer = table_summarizer

    def parse_table_dataframe(self, df:pd.DataFrame, name:str):
        if self.truncate_table_if_over_max:
            if df.shape[0] > self.max_rows or df.shape[1] > self.max_cols:
                logging.warning(
                    f"Table size is too large for {name} in 'table' mode. "
                    f"Table will be truncated to no more than {self.max_rows} rows and {self.max_cols} columns."
                )
                df = df.iloc[:self.max_rows, :self.max_cols]

        table_summary = self.table_summarizer.summarize_table_text(df)
        if table_summary:
            cols, rows = html_table_to_header_and_rows(df.to_html(index=False))
            cols_not_empty = any(col for col in cols)
            rows_not_empty = any(any(cell for cell in row) for row in rows)
            logger.info(f"Table '{name}' has {len(cols)} columns and {len(rows)} rows. Summary: {table_summary}")
            if rows_not_empty and cols_not_empty:
                table_dict = {'headers': cols, 'rows': rows, 'summary': table_summary}
                return table_summary, table_dict
            else:
                return None
        else:
            logger.warning(f"Table summarization failed for the table with {df.shape[0]} rows and {df.shape[1]} columns.")
            return None


    def parse_element_dataframe(self, df:pd.DataFrame):
        pass

    def parse_table(self, dataframe_metadata: DataFrameMetadata, doc_id:str, metadata:dict[str, str]):
        tables = []
        texts = []

        if isinstance(dataframe_metadata, SimpleDataFrameMetadata):
            df = dataframe_metadata.open_dataframe()
            parse_table_result = self.parse_table_dataframe(df, dataframe_metadata.title())
            if parse_table_result:
                text, table = parse_table_result
                tables.append(table)
                texts.append(text)
        elif isinstance(dataframe_metadata, SheetBasedDataFrameMetadata):
            all_sheet_names = None
            if self.sheet_names:
                all_sheet_names = self.sheet_names
            else:
                all_sheet_names = dataframe_metadata.sheet_names
            for sheet_name in all_sheet_names:
                logger.info(f"parse_table() - processing {sheet_name}")
                df = dataframe_metadata.open_dataframe(sheet_name)
                parse_table_result = self.parse_table_dataframe(df, sheet_name)
                if parse_table_result:
                    text, table = parse_table_result
                    tables.append(table)
                    texts.append(text)
        else:
            raise ValueError(f'Unsupported {dataframe_metadata}')

        self.indexer.index_segments(
            doc_id=doc_id,
            texts=texts,
            tables=tables,
            doc_title=dataframe_metadata.title(),
            doc_metadata=metadata
        )



    def parse(self, dataframe_metadata: DataFrameMetadata, doc_id:str, metadata:dict[str, str]):
        if self.mode == 'table':
            self.parse_table(dataframe_metadata, doc_id, metadata)
        elif self.mode == 'element':
            self.parse_element(dataframe_metadata, doc_id, metadata)



