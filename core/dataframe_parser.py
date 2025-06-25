import logging
import os
import pandas as pd
from omegaconf import DictConfig
from core.summary import TableSummarizer
from core.utils import html_table_to_header_and_rows
from core.indexer import Indexer
import unicodedata

logger = logging.getLogger(__name__)


class DataFrameMetadata(object):
    """
    Abstract base class for DataFrame metadata.
    """

    def __init__(self, sheet_names: list[str] | None):
        """
        Initializes the DataFrameMetadata with optional sheet names.

        Args:
            sheet_names: A list of sheet names if the dataframe is sheet-based, otherwise None.
        """
        self.sheet_names = sheet_names

    def title(self):
        """
        Returns the title of the dataframe.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Method not implemented")

    def open_dataframe(self, parser_config: DictConfig, sheet_name: str = None):
        raise NotImplementedError("Method not implemented")


class SimpleDataFrameMetadata(DataFrameMetadata):
    def __init__(self, sheet_names: list[str] | None):
        """
        Initializes the SimpleDataFrameMetadata.

        This class is a base class for DataFrames that are not sheet-based.

        Args:
            sheet_names: A list of sheet names (should be None for simple dataframes).
                         This argument is kept for compatibility with the base class.
        """
        super().__init__(sheet_names)


separator_by_extension = {".csv": ",", ".tsv": "\t", ".psv": "|", ".pipe": "|"}
supported_dataframe_extensions = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xls": "xls",
    ".xlsx": "xls",
    ".pipe": "csv",
    ".psv": "csv",
}


def generate_dfs_to_index(df: pd.DataFrame, doc_id_columns, rows_per_chunk: int):
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
    """
    if doc_id_columns:
        grouped = df.groupby(doc_id_columns)
        for name, group in grouped:
            if isinstance(name, str):
                doc_id = name
            else:
                doc_id = " - ".join([str(x) for x in name if x])
            yield (doc_id, group)
    else:
        if rows_per_chunk < len(df):
            rows_per_chunk = len(df)
        for inx in range(0, df.shape[0], rows_per_chunk):
            sub_df = df[inx : inx + rows_per_chunk]
            name = f"rows {inx}-{inx+rows_per_chunk-1}"
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


def supported_by_dataframe_parser(file_path: str):
    """
    Checks if the file extension of the given file path is supported for dataframe parsing.

    Args:
        file_path: The path to the file.

    Returns:
        True if the file extension is supported, False otherwise.
    """
    _, extension = os.path.splitext(file_path)
    return extension in supported_dataframe_extensions


def determine_dataframe_type(file_path: str):
    """
    Determines the type of the dataframe based on the file extension.

    Args:
        file_path: The path to the file.

    Returns: The dataframe type ('csv' or 'xls') if supported, None otherwise."""
    logger.debug(
        f"determine_dataframe_type('{file_path}') - determining dataframe type."
    )
    _, extension = os.path.splitext(file_path)

    if extension in supported_dataframe_extensions:
        return supported_dataframe_extensions[extension]
    else:
        logger.warning(
            f"determine_dataframe_type('{file_path}) - Extension '{extension}' not supported."
        )
        return None


class CsvDataFrameMetadata(SimpleDataFrameMetadata):
    """
    Metadata class for CSV dataframes.
    """

    def __init__(self, file_path: str):
        """
        Initializes the CsvDataFrameMetadata with the file path.

        Args:
            file_path: The path to the CSV file.
        """
        self.file_path = file_path
        super().__init__(None)

    def title(self):
        """
        Returns the title of the CSV dataframe, which is the base name of the file.

        Returns:
            The base name of the CSV file.
        """
        return os.path.basename(self.file_path)

    def open_dataframe(self, parser_config: DictConfig, sheet_name: str = None):
        separator: str = parser_config.get("separator", None)
        column_types: dict[str, str] = parser_config.get("column_types", None)

        if not separator:
            separator = get_separator_by_file_name(self.file_path)

        if sheet_name is not None:
            logger.warning(
                f"CsvDataFrameMetadata:Sheet Name '{sheet_name}' requested for csv '{self.file_path}'. Ignoring"
            )

        logger.debug(
            f"CsvDataFrameMetadata:open_dataframe(sheet_name='{sheet_name}') - Opening '{self.file_path}' with .read_csv."
        )
        params = {
            'sep': separator
        }
        if column_types:
            params['dtype']={}
            for column, column_type in column_types.items():
                params['dtype'][column] = column_type

        df = pd.read_csv(self.file_path, **params)
        df = df.astype(object)

        return df


class SheetBasedDataFrameMetadata(DataFrameMetadata):
    """
    Abstract base class for sheet-based DataFrame metadata (e.g., Excel files).
    """

    def __init__(self, sheet_names: list[str] | None):
        """
        Initializes the SheetBasedDataFrameMetadata with sheet names.

        Args:
            sheet_names: A list of sheet names in the dataframe file.
        """
        super().__init__(sheet_names)


class XlsBasedDataFrameMetadata(SheetBasedDataFrameMetadata):
    """
    Metadata class for Excel dataframes (XLS and XLSX).
    """

    def __init__(self, file_path: str):
        """
        Initializes the XlsBasedDataFrameMetadata with the file path and loads sheet names.

        Args:
            file_path: The path to the Excel file.
        """
        self.file_path = file_path
        logger.debug(
            f"XlsBasedDataFrameMetadata:__init__('{file_path}') - Loading as pd.ExcelFile to retrieve sheet names."
        )
        xls = pd.ExcelFile(file_path)
        super().__init__(xls.sheet_names)

    def open_dataframe(self, parser_config: DictConfig, sheet_name: str = None):
        """
        Opens and returns a pandas DataFrame from the specified sheet in the Excel file.

        Args:
            parser_config: The configuration dictionary for the parser.
            sheet_name: The name of the sheet to open. If None, the first sheet is opened.

        Returns:
            A pandas DataFrame representing the specified sheet.
        """
        column_types: dict[str, str] = parser_config.get("column_types", None)
        logger.debug(
            f"XlsBasedDataFrameMetadata:open_dataframe(sheet_name='{sheet_name}') - Opening '{self.file_path}' with .read_excel."
        )
        params = {
            'sheet_name': sheet_name
        }
        if column_types:
            params['dtype']={}
            for column, column_type in column_types.items():
                params['dtype'][column] = column_type
        df = pd.read_excel(self.file_path, **params)
        # df = df.astype(object)
        return df

    def title(self):
        """
        Returns the title of the Excel dataframe, which is the base name of the file.
        """
        return os.path.basename(self.file_path)


def load_dataframe_metadata(file_path: str, data_frame_type: str | None = None):
    """
    Loads the appropriate DataFrameMetadata based on the file path and optional dataframe type.

    Args:
        file_path: The path to the dataframe file.
        data_frame_type: The type of the dataframe ('csv' or 'xls'). If None, it is determined from the file extension.

    Returns:
        An instance of the appropriate DataFrameMetadata subclass.
    """
    if not data_frame_type:
        data_frame_type = determine_dataframe_type(file_path)
    else:
        logger.debug(
            f"load_dataframe_metadata('{file_path}) - using caller supplied data_frame_type='{data_frame_type}'"
        )

    logger.debug(
        f"load_dataframe_metadata('{file_path}) - Loading as '{data_frame_type}'"
    )

    if "csv" == data_frame_type:
        return CsvDataFrameMetadata(file_path)
    elif "xls" == data_frame_type:
        return XlsBasedDataFrameMetadata(file_path)
    else:
        raise ValueError(f"Unsupported dataframe type of '{data_frame_type}'")


class DataframeParser(object):
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
        self.max_cols: int = int(self.crawler_config.get("max_cols", 20))  ### TEMP 500
        self.sheet_names: list[str] = self.crawler_config.get("sheet_names", [])
        self.mode: str = self.crawler_config.get("mode", "table")
        self.indexer: Indexer = indexer
        self.table_summarizer: TableSummarizer = table_summarizer
        self.select_condition = self.crawler_config.get("select_condition", None)

    def parse_table_dataframe(self, df: pd.DataFrame, name: str):
        """
        Parses a single dataframe as a table, summarizes it, and prepares it for indexing.

        Args:
            df: The pandas DataFrame to parse.
            name: A name for the table (e.g., file name or sheet name).

        Returns: A tuple containing the table summary text and a dictionary representation of the table, or None if summarization fails or the table is empty.
        """

        if self.select_condition:
            logger.info(f"Querying dataframe with {self.select_condition}")
            df = df.query(self.select_condition)

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

    def parse_table(
        self,
        dataframe_metadata: DataFrameMetadata,
        doc_id: str,
        metadata: dict[str, str],
    ):
        """
        Parses a dataframe file in 'table' mode, processing each sheet (if applicable) as a separate table.

        Args:
            dataframe_metadata: The metadata for the dataframe file.
            doc_id: The document ID to use for indexing.
            metadata: Additional metadata for the document.
        """

        tables = []
        texts = []

        if isinstance(dataframe_metadata, SimpleDataFrameMetadata):
            df = dataframe_metadata.open_dataframe(self.crawler_config)
            parse_table_result = self.parse_table_dataframe(
                df, dataframe_metadata.title()
            )
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
                df = dataframe_metadata.open_dataframe(self.crawler_config, sheet_name)
                parse_table_result = self.parse_table_dataframe(df, sheet_name)
                if parse_table_result:
                    text, table = parse_table_result
                    tables.append(table)
                    texts.append(text)
        else:
            raise ValueError(f"Unsupported {dataframe_metadata}")

        self.indexer.index_segments(
            doc_id=doc_id,
            doc_metadata=metadata,
            doc_title=dataframe_metadata.title(),
            tables=tables,
            texts=texts,
        )

    def parse_element_dataframe(
        self, doc_id: str, df: pd.DataFrame, metadata: dict[str, str]
    ):
        """
        Parses a single dataframe chunk in 'element' mode, extracting text, titles, and metadata from specified columns.

        Args:
            doc_id: The document ID for the chunk.
            df: The pandas DataFrame chunk to parse.
            metadata: Additional metadata for the document.
        """
        texts = []
        titles = []
        metadatas = []

        title_column: str = self.crawler_config.get("title_column", None)
        text_columns: list[str] = list(self.crawler_config.get("text_columns", []))
        metadata_columns: list[str] = list(
            self.crawler_config.get("metadata_columns", [])
        )
        for _, row in df.iterrows():
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
            if len(df[column].unique()) == 1 and not pd.isnull(df[column].iloc[0]):
                doc_metadata[column] = df[column].iloc[0]
        title = titles[0] if titles else doc_id
        logger.debug(f"Indexing {len(df)} rows for doc_id '{doc_id}'")

        self.indexer.index_segments(
            doc_id=doc_id,
            doc_metadata=doc_metadata,
            doc_title=title,
            metadatas=metadatas,
            texts=texts,
            titles=titles,
        )

    def parse_element(
        self, dataframe_metadata: DataFrameMetadata, metadata: dict[str, str]
    ):
        """
        Parses a dataframe file in 'element' mode, chunking the dataframe and processing each chunk as a separate document.

        Args:
            dataframe_metadata: The metadata for the dataframe file.
            metadata: Additional metadata for the document.
        """
        doc_id_columns: list[str] = list(self.crawler_config.get("doc_id_columns", []))
        rows_per_chunk: int = self.crawler_config.get("rows_per_chunk", 500)

        if isinstance(dataframe_metadata, SimpleDataFrameMetadata):
            df = dataframe_metadata.open_dataframe(self.crawler_config)
            if self.select_condition:
                logger.info(f"Querying dataframe with {self.select_condition}")
                df = df.query(self.select_condition)
            for doc_id, child_df in generate_dfs_to_index(df, doc_id_columns, rows_per_chunk):
                self.parse_element_dataframe(doc_id, child_df, metadata)

        elif isinstance(dataframe_metadata, SheetBasedDataFrameMetadata):
            all_sheet_names = None
            if self.sheet_names:
                all_sheet_names = self.sheet_names
            else:
                all_sheet_names = dataframe_metadata.sheet_names
            for sheet_name in all_sheet_names:
                logger.info(f"parse_element() - processing {sheet_name}")
                df = dataframe_metadata.open_dataframe(self.crawler_config, sheet_name)
                if self.select_condition:
                    logger.info(f"Querying dataframe with {self.select_condition}")
                    df = df.query(self.select_condition)
                for doc_id, child_df in generate_dfs_to_index(df, doc_id_columns, rows_per_chunk):
                    self.parse_element_dataframe(doc_id, child_df, metadata)
        else:
            raise ValueError(f"Unsupported {dataframe_metadata}")
        pass

    def parse(
        self,
        dataframe_metadata: DataFrameMetadata,
        doc_id: str,
        metadata: dict[str, str],
    ):
        """
        Parses the dataframe based on the configured mode ('table' or 'element').

        Args:
            dataframe_metadata: The metadata for the dataframe file.
            doc_id: The document ID to use for indexing (relevant in 'table' mode).
            metadata: Additional metadata for the document.
        """

        if self.mode == "table":
            self.parse_table(dataframe_metadata, doc_id, metadata)
        elif self.mode == "element":
            self.parse_element(dataframe_metadata, metadata)
