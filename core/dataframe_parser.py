import logging
import os
import pandas as pd
from typing import List, Optional, Dict, Tuple, Iterator
from omegaconf import DictConfig
from core.summary import TableSummarizer
from core.utils import html_table_to_header_and_rows
from core.indexer import Indexer
import unicodedata

logger = logging.getLogger(__name__)


# Custom exception classes
class DataFrameParserError(Exception):
    """Base exception for DataFrame parser errors"""
    pass


class InvalidFileError(DataFrameParserError):
    """Raised when file is invalid or inaccessible"""
    pass


class InvalidConfigurationError(DataFrameParserError):
    """Raised when configuration is invalid"""
    pass


separator_by_extension: Dict[str, str] = {".csv": ",", ".tsv": "	", ".psv": "|", ".pipe": "|"}
supported_dataframe_extensions: Dict[str, str] = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xls": "xls",
    ".xlsx": "xls",
    ".pipe": "csv",
    ".psv": "csv",
}


def generate_dfs_to_index(df: pd.DataFrame, doc_id_columns: Optional[List[str]], rows_per_chunk: int) -> Iterator[Tuple[str, pd.DataFrame]]:
    """
    Generates dataframes to be indexed based on the provided DataFrame, document ID columns,
    and the desired number of rows per chunk.

    Args:
        df: The input pandas DataFrame.
        doc_id_columns: A list of column names to use for grouping and generating document IDs.
                        If None or empty, the DataFrame will be chunked by `rows_per_chunk`.
        rows_per_chunk: The maximum number of rows in each chunk when `doc_id_columns` is not provided.

    Yields:
        A tuple containing the generated document ID and the corresponding DataFrame chunk.
        
    Raises:
        InvalidConfigurationError: If rows_per_chunk is not positive or doc_id_columns don't exist.
    """
    # Validate inputs
    if df.empty:
        logger.warning("Empty DataFrame provided to generate_dfs_to_index")
        return
    
    if rows_per_chunk <= 0:
        raise InvalidConfigurationError(f"rows_per_chunk must be positive, got {rows_per_chunk}")
    
    if doc_id_columns:
        # Validate that all doc_id_columns exist in the DataFrame
        missing_cols = [col for col in doc_id_columns if col not in df.columns]
        if missing_cols:
            raise InvalidConfigurationError(f"doc_id_columns {missing_cols} not found in DataFrame columns: {list(df.columns)}")
    
    if doc_id_columns:
        grouped = df.groupby(doc_id_columns)
        for name, group in grouped:
            if isinstance(name, str):
                doc_id = name
            else:
                doc_id = " - ".join([str(x) for x in name if x])
            yield (doc_id, group)
    else:
        if rows_per_chunk > len(df):
            rows_per_chunk = len(df)
        for inx in range(0, df.shape[0], rows_per_chunk):
            sub_df = df[inx: inx+rows_per_chunk]
            if rows_per_chunk > 1:
                name = f'rows {inx}-{inx+rows_per_chunk-1}'
            else:
                name = f'row {inx}'
            yield (name, sub_df)


def get_separator_by_file_name(file_name: str) -> str:
    """
    Determines the appropriate separator character based on the file extension.

    Args:
        file_name: The name of the file.

    Returns:
        The separator character for the given file extension, defaulting to ',' if the extension is unknown.
    """
    _, extension = os.path.splitext(file_name)
    extension = extension.lower()
    if extension in separator_by_extension:
        return separator_by_extension[extension]
    else:
        logger.warning(
            f"get_separator_by_file_name(file_name = '{file_name}') - Unknown extension '{extension}' defaulting to ','"
        )
        return ","


def supported_by_dataframe_parser(file_path: str) -> bool:
    """
    Checks if the file extension of the given file path is supported for dataframe parsing.

    Args:
        file_path: The path to the file.

    Returns:
        True if the file extension is supported, False otherwise.
    """
    _, extension = os.path.splitext(file_path)
    return extension in supported_dataframe_extensions


def determine_dataframe_type(file_path: str) -> Optional[str]:
    """
    Determines the type of the dataframe based on the file extension.

    Args:
        file_path: The path to the file.

    Returns: The dataframe type ('csv' or 'xls') if supported, None otherwise.
    
    Raises:
        InvalidFileError: If file_path is empty or invalid.
    """
    if not file_path or not file_path.strip():
        raise InvalidFileError("file_path cannot be empty")
    
    logger.debug(
        f"determine_dataframe_type('{file_path}') - determining dataframe type."
    )
    _, extension = os.path.splitext(file_path)

    if extension in supported_dataframe_extensions:
        return supported_dataframe_extensions[extension]
    else:
        logger.warning(
            f"determine_dataframe_type('{file_path}') - Extension '{extension}' not supported."
        )
        return None


class DataframeParser:
    """
    Parses dataframes and indexes their content based on the configured mode ('table' or 'element').
    """

    def __init__(
        self,
        cfg: DictConfig,
        crawler_config: DictConfig,
        indexer: Indexer,
        table_summarizer: TableSummarizer,
    ):
        self.cfg: DictConfig = cfg

        if crawler_config is None:
            logger.debug("crawler_config is none, defaulting to dataframe_processing.")
            self.crawler_config: DictConfig = cfg.dataframe_processing
        else:
            self.crawler_config: DictConfig = crawler_config
        self.truncate_table_if_over_max: bool = self.crawler_config.get("truncate_table_if_over_max", True)
        self.max_rows: int = int(self.crawler_config.get("max_rows", 500))
        self.max_cols: int = int(self.crawler_config.get("max_cols", 20))
        self.mode: str = self.crawler_config.get("mode", "table")
        self.indexer: Indexer = indexer
        self.table_summarizer: TableSummarizer = table_summarizer
        self.select_condition = self.crawler_config.get("select_condition", None)

    def process_dataframe(self, df: pd.DataFrame, doc_id: str, doc_title: str, metadata: dict):
        """
        Primary entry point. Receives a single DataFrame and processes it
        based on the configured mode.
        """
        # Apply column type conversions if specified
        column_types = self.crawler_config.get("column_types", None)
        if column_types:
            for col, dtype in column_types.items():
                if col in df.columns:
                    try:
                        df[col] = df[col].astype(dtype)
                    except Exception as e:
                        logger.warning(f"Could not convert column {col} to {dtype}: {e}")

        if self.select_condition:
            logger.info(f"Querying dataframe with {self.select_condition}")
            df = df.query(self.select_condition)

        if self.mode == "table":
            self._parse_as_table(df, doc_id, doc_title, metadata)
        elif self.mode == "element":
            self._parse_as_elements(df, doc_id, doc_title, metadata)

    def _summarize_table(self, df: pd.DataFrame, name: str) -> Optional[Tuple[str, dict]]:
        """
        Summarizes a dataframe and prepares it for indexing.
        """
        if self.truncate_table_if_over_max:
            if df.shape[0] > self.max_rows or df.shape[1] > self.max_cols:
                logger.warning(
                    f"Table size is too large for {name} in 'table' mode. "
                    f"Table will be truncated to no more than {self.max_rows} rows and {self.max_cols} columns."
                )
                df = df.iloc[: self.max_rows, : self.max_cols]

        table_summary = self.table_summarizer.summarize_table_text(df)
        if table_summary:
            cols, rows = html_table_to_header_and_rows(df.to_html(index=False))
            cols_not_empty = any(col for col in cols)
            rows_not_empty = any(any(cell for cell in row) for row in rows)
            logger.info(
                f"Table '{name}' has {len(cols)} columns and {len(rows)} rows. Summary: {table_summary}"
            )
            if rows_not_empty and cols_not_empty:
                table_dict = {"headers": cols, "rows": rows, "summary": table_summary}
                return table_summary, table_dict
            else:
                return None
        else:
            logger.warning(
                f"Table summarization failed for the table with {df.shape[0]} rows and {df.shape[1]} columns."
            )
            return None

    def _parse_as_table(self, df: pd.DataFrame, doc_id: str, doc_title: str, metadata: dict):
        """
        Handles 'table' mode logic for a single DataFrame.
        """
        summarize_result = self._summarize_table(df, doc_title)
        if summarize_result:
            table_summary, table_dict = summarize_result
            self.indexer.index_segments(
                doc_id=doc_id,
                doc_title=doc_title,
                doc_metadata=metadata,
                tables=[table_dict],
                texts=[table_summary]
            )

    def _parse_as_elements(self, df: pd.DataFrame, doc_id_prefix: str, doc_title: str, metadata: dict):
        """
        Handles 'element' mode logic for a single DataFrame.
        """
        doc_id_columns = self.crawler_config.get("doc_id_columns", [])
        if doc_id_columns:
            doc_id_columns = list(doc_id_columns)
        rows_per_chunk = self.crawler_config.get("rows_per_chunk", 500)

        for chunk_id, child_df in generate_dfs_to_index(df, doc_id_columns, rows_per_chunk):
            final_doc_id = f"{doc_id_prefix}-{chunk_id}" if doc_id_columns else doc_id_prefix
            self._process_element_chunk(child_df, final_doc_id, doc_title, metadata)

    def _process_element_chunk(self, df_chunk: pd.DataFrame, doc_id: str, doc_title: str, metadata: dict):
        """
        Parses a single dataframe chunk in 'element' mode, extracting text, titles, and metadata from specified columns.
        """
        texts = []
        titles = []
        metadatas = []

        title_column: str = self.crawler_config.get("title_column", None)
        text_columns: list[str] = list(self.crawler_config.get("text_columns", []))
        metadata_columns: list[str] = list(
            self.crawler_config.get("metadata_columns", [])
        )
        for _, row in df_chunk.iterrows():
            if title_column:
                titles.append(str(row[title_column]))
            text = " - ".join(
                str(row[col]) for col in text_columns if pd.notnull(row[col])
            )
            texts.append(unicodedata.normalize("NFD", text))
            md = {
                column: row[column]
                for column in metadata_columns
                if pd.notnull(row[column])
            }
            metadatas.append(md)
        if len(titles) == 0:
            titles = None
        doc_metadata = metadata.copy()

        for column in metadata_columns:
            if len(df_chunk[column].unique()) == 1 and not pd.isnull(df_chunk[column].iloc[0]):
                value = df_chunk[column].iloc[0]
                # Convert numpy types to native Python types for JSON serialization
                if hasattr(value, 'item'):
                    value = value.item()
                doc_metadata[column] = value
        
        final_title = titles[0] if titles else doc_title
        logger.debug(f"Indexing {len(df_chunk)} rows for doc_id '{doc_id}'")

        self.indexer.index_segments(
            doc_id=doc_id,
            doc_metadata=doc_metadata,
            doc_title=final_title,
            metadatas=metadatas,
            texts=texts,
            titles=titles,
        )
