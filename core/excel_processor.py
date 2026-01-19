"""
Excel Processor for handling multi-sheet Excel files (.xls, .xlsx, .xlsb, .xlsm)

This module provides enhanced Excel processing with:
- Support for all Excel formats including binary (.xlsb) and macro-enabled (.xlsm)
- Multi-sheet processing with individual sheet indexing
- Smart content detection for forms, tables, and mixed content
- LLM-based summarization for complex Excel data
"""

import logging
import os
import pandas as pd
from typing import Dict, List, Optional, Any
from omegaconf import DictConfig

logger = logging.getLogger(__name__)

# Excel format support mapping
EXCEL_EXTENSIONS = {
    '.xls': 'xlrd',      # Excel 97-2003 (legacy)
    '.xlsx': 'openpyxl', # Excel 2007+ (default)
    '.xlsb': 'pyxlsb',   # Excel Binary Workbook
    '.xlsm': 'openpyxl', # Excel Macro-Enabled Workbook
}


class ExcelProcessor:
    """
    Enhanced Excel processor that handles all Excel formats with multi-sheet support.

    This processor is specifically designed for:
    - Multi-sheet Excel workbooks
    - Form-based Excel files (setup forms, request forms, etc.)
    - Mixed content (tables, text, metadata)
    - Complex structured data requiring LLM summarization
    """

    def __init__(self, config: DictConfig):
        """
        Initialize the Excel processor.

        Args:
            config: Configuration object containing processing settings
        """
        self.config = config
        self.df_config = config.get('dataframe_processing', {})

    @staticmethod
    def supports_file(file_path: str) -> bool:
        """
        Check if this processor supports the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file extension is supported, False otherwise
        """
        ext = os.path.splitext(file_path)[1].lower()
        return ext in EXCEL_EXTENSIONS

    @staticmethod
    def get_engine_for_file(file_path: str) -> str:
        """
        Get the appropriate pandas engine for reading the Excel file.

        Args:
            file_path: Path to the Excel file

        Returns:
            Engine name for pandas.read_excel()

        Raises:
            ValueError: If file extension is not supported
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in EXCEL_EXTENSIONS:
            raise ValueError(f"Unsupported Excel extension: {ext}")
        return EXCEL_EXTENSIONS[ext]

    def process_excel_file(
        self,
        file_path: str,
        doc_id: str,
        doc_title: str,
        df_metadata: Dict[str, Any],
        df_parser: Any
    ) -> bool:
        """
        Process an Excel file with multi-sheet support.

        This method:
        1. Detects the Excel format and uses appropriate engine
        2. Iterates through all sheets (or configured subset)
        3. Processes each sheet as a separate document
        4. Adds sheet-specific metadata

        Args:
            file_path: Path to the Excel file
            doc_id: Base document ID
            doc_title: Base document title
            df_metadata: Base metadata dictionary
            df_parser: DataframeParser instance for processing dataframes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get appropriate engine for this Excel format
            engine = self.get_engine_for_file(file_path)

            logger.info(f"Processing Excel file: {file_path} (engine: {engine})")

            # Open Excel file
            xls = pd.ExcelFile(file_path, engine=engine)

            # Get sheet names to process
            sheet_names = self._get_sheets_to_process(xls)

            logger.info(f"Found {len(xls.sheet_names)} sheets, processing {len(sheet_names)} sheets")

            # Process each sheet
            for sheet_name in sheet_names:
                if sheet_name not in xls.sheet_names:
                    logger.warning(f"Sheet '{sheet_name}' not found in '{file_path}'. Skipping.")
                    continue

                try:
                    self._process_sheet(
                        xls=xls,
                        sheet_name=sheet_name,
                        base_doc_id=doc_id,
                        base_doc_title=doc_title,
                        base_metadata=df_metadata,
                        df_parser=df_parser,
                        engine=engine
                    )
                except Exception as e:
                    logger.error(f"Error processing sheet '{sheet_name}' in {file_path}: {e}")
                    # Continue with other sheets
                    continue

            return True

        except Exception as e:
            logger.error(f"Error processing Excel file {file_path}: {e}")
            return False

    def _get_sheets_to_process(self, xls: pd.ExcelFile) -> List[str]:
        """
        Get list of sheet names to process based on configuration.

        Args:
            xls: Pandas ExcelFile object

        Returns:
            List of sheet names to process
        """
        configured_sheets = self.df_config.get("sheet_names")

        # If sheet_names is not specified or is None, process all sheets
        if configured_sheets is None:
            return xls.sheet_names

        return configured_sheets

    def _is_legend_or_footer(self, text: str) -> bool:
        """
        Check if a text row is a legend or footer explaining color coding or status.

        These rows are not useful for indexing since we don't preserve color information.

        Args:
            text: Text content of the row

        Returns:
            True if this looks like a legend/footer row
        """
        text_lower = text.lower()

        # Common legend/footer patterns
        legend_patterns = [
            'coverage:',
            'result:',
            'variance',
            'achieved or exceeded',
            'under counted',
            'missed',
            'target',
            'within',
            'limits',
            'exceeded',
            'consecutive',
            'status',
            'color',
            'legend',
            'note:',
            'footer',
        ]

        # Check if text contains multiple legend patterns
        pattern_count = sum(1 for pattern in legend_patterns if pattern in text_lower)

        # If 2+ patterns match, likely a legend row
        if pattern_count >= 2:
            return True

        # Check for specific legend formats like "Coverage: X" or "Result: Y"
        if any(text_lower.startswith(pattern) for pattern in ['coverage:', 'result:', 'note:']):
            # But make sure it's not actual data (e.g., "Coverage: 95%" with numbers)
            # Legend rows typically don't have many numbers
            import re
            numbers = re.findall(r'\d+', text)
            if len(numbers) <= 2:  # Legend rows have few numbers
                return True

        return False

    def _analyze_sheet_structure(self, df_raw: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze sheet structure to identify tables and independent rows.

        Returns:
            Dictionary with structure information:
            {
                'has_tables': bool,
                'table_regions': [(header_row, start_row, end_row), ...],
                'independent_rows': [row_idx, ...]
            }
        """
        structure = {
            'has_tables': False,
            'table_regions': [],
            'independent_rows': []
        }

        # Find potential header rows (rows with many cells, mostly text)
        potential_headers = []
        for idx, row in df_raw.iterrows():
            non_empty = row.notna().sum()
            if non_empty >= 5:  # At least 5 filled cells
                non_empty_values = row[row.notna()].values
                text_count = sum(1 for val in non_empty_values if isinstance(val, str))
                if text_count / non_empty >= 0.7:  # 70%+ text cells
                    potential_headers.append(idx)

        if not potential_headers:
            # No tables found - all rows are independent
            for idx in range(len(df_raw)):
                if df_raw.iloc[idx].notna().sum() > 0:
                    structure['independent_rows'].append(idx)
            return structure

        structure['has_tables'] = True

        # For each header, find its data rows
        for i, header_idx in enumerate(potential_headers):
            # Find where this table ends (next header or end of sheet)
            if i + 1 < len(potential_headers):
                end_idx = potential_headers[i + 1] - 1
            else:
                end_idx = len(df_raw) - 1

            # Find first non-empty data row after header
            start_row = None
            for row_idx in range(header_idx + 1, end_idx + 1):
                if df_raw.iloc[row_idx].notna().sum() >= 3:  # At least 3 filled cells
                    start_row = row_idx
                    break

            if start_row is not None:
                # Find last non-empty row
                last_row = start_row
                for row_idx in range(start_row + 1, end_idx + 1):
                    if df_raw.iloc[row_idx].notna().sum() >= 3:
                        last_row = row_idx

                structure['table_regions'].append((header_idx, start_row, last_row))

        # Identify independent rows (rows not in any table region)
        table_row_indices = set()
        for header_idx, start_row, end_row in structure['table_regions']:
            table_row_indices.update(range(header_idx, end_row + 1))

        for idx in range(len(df_raw)):
            if idx not in table_row_indices and df_raw.iloc[idx].notna().sum() > 0:
                structure['independent_rows'].append(idx)

        logger.info(f"Found {len(structure['table_regions'])} tables and {len(structure['independent_rows'])} independent rows")

        return structure

    def _index_multi_section(
        self,
        df_raw: pd.DataFrame,
        structure: Dict[str, Any],
        xls: pd.ExcelFile,
        sheet_name: str,
        engine: str,
        doc_id: str,
        doc_title: str,
        metadata: Dict[str, Any],
        df_parser: Any
    ) -> None:
        """
        Index sheet with multiple sections (independent rows + tables).

        Everything is indexed in a single document with:
        - Text sections for independent metadata rows
        - Table sections for detected table regions
        """
        texts = []
        tables = []

        # Process independent rows as text sections (skip legend/footer)
        for row_idx in structure['independent_rows']:
            row = df_raw.iloc[row_idx]
            non_empty_values = row[row.notna()].values
            if len(non_empty_values) > 0:
                text = ' '.join([str(v) for v in non_empty_values])

                # Skip legend/footer rows (rows that explain color coding, status, etc.)
                if self._is_legend_or_footer(text):
                    logger.info(f"Skipping legend/footer row {row_idx}: {text[:50]}...")
                    continue

                texts.append(text)

        # Process each table region - build table dictionaries manually
        for table_idx, (header_idx, start_row, end_row) in enumerate(structure['table_regions']):
            logger.info(f"Processing table {table_idx + 1}: header row {header_idx}, data rows {start_row}-{end_row}")

            # Get the header row - get ALL columns that have headers
            header_row_data = df_raw.iloc[header_idx]

            # Find which columns have headers
            header_columns = []
            headers = []
            for col_idx, val in enumerate(header_row_data):
                if pd.notna(val):
                    header_columns.append(col_idx)
                    headers.append(str(val))

            logger.info(f"Table has {len(headers)} columns with headers")
            logger.info(f"Headers: {headers[:5]}...")  # Log first 5 headers

            # Read data rows - only columns that have headers
            data_rows = []
            for row_idx in range(start_row, end_row + 1):
                row = df_raw.iloc[row_idx]

                # Extract only the columns that have headers
                row_data = []
                for col_idx in header_columns:
                    val = row.iloc[col_idx] if col_idx < len(row) else None
                    row_data.append(str(val) if pd.notna(val) else '')

                # Only include rows with at least 3 non-empty cells
                if sum(1 for cell in row_data if cell) >= 3:
                    data_rows.append(row_data)

            logger.info(f"Table has {len(headers)} columns and {len(data_rows)} data rows")

            if headers and data_rows:
                # Generate summary using LLM if enabled
                if df_parser.summarize:
                    # Create a temporary dataframe for this table to generate summary
                    temp_df = pd.DataFrame(data_rows, columns=headers)
                    table_summary = df_parser.table_summarizer.summarize_table_text(temp_df)
                    logger.info(f"Generated LLM summary for table {table_idx + 1}: {table_summary[:100]}...")
                else:
                    # No summary - just index the table data without any label
                    table_summary = ""
                    logger.info(f"Skipping summary for table {table_idx + 1} (summarize=False)")

                table_dict = {
                    "headers": [headers],  # Single header row
                    "rows": data_rows,
                    "summary": table_summary
                }
                tables.append(table_dict)

        # Index everything in a single document (text sections + tables)
        logger.info(f"Indexing single document with {len(texts)} text sections and {len(tables)} tables")
        df_parser.indexer.index_segments(
            doc_id=doc_id,
            doc_title=doc_title,
            doc_metadata=metadata,
            texts=texts,
            tables=tables
        )

    def _detect_header_row(self, xls: pd.ExcelFile, sheet_name: str, engine: str, max_rows: int = 20) -> Optional[int]:
        """
        Detect the actual header row in an Excel sheet.

        Many Excel files have metadata rows at the top before the actual table header.
        This method scans the first N rows to find the row that looks most like a header.

        Strategy:
        1. Read first max_rows rows without header inference
        2. For each row, score it based on:
           - Number of non-empty cells
           - Lack of repeated characters (metadata often has "U U U U")
           - Presence of text (not numbers)
        3. Return the row with highest score, or None if no clear header

        Args:
            xls: Pandas ExcelFile object
            sheet_name: Name of the sheet
            engine: Pandas engine to use
            max_rows: Maximum rows to scan for header (default: 20)

        Returns:
            Row index of detected header, or None if no clear header found
        """
        import re

        try:
            # Read first max_rows without header inference
            df_raw = pd.read_excel(xls, sheet_name=sheet_name, engine=engine, header=None, nrows=max_rows)

            if df_raw.empty:
                return None

            best_row = None
            best_score = 0

            for row_idx in range(min(max_rows, len(df_raw))):
                row = df_raw.iloc[row_idx]

                # Count non-empty cells
                non_empty = row.notna().sum()

                if non_empty == 0:
                    continue  # Skip completely empty rows

                # Score this row
                score = 0

                # 1. More non-empty cells = better header candidate
                score += non_empty * 2

                # 2. Check for repeated characters (indicates metadata, not header)
                has_repeated_chars = False
                for cell in row:
                    if pd.notna(cell):
                        cell_str = str(cell)
                        # Check for patterns like "U U U U" or "n n n n"
                        if re.search(r'(\w)\s+\1', cell_str):
                            has_repeated_chars = True
                            break

                if has_repeated_chars:
                    score -= 10  # Penalize rows with repeated characters

                # 3. Check if cells are mostly text (not numbers)
                text_cells = 0
                for cell in row:
                    if pd.notna(cell):
                        # Check if it's a string (not number)
                        if isinstance(cell, str):
                            text_cells += 1
                        # Also check if numeric cell has text-like properties
                        elif not isinstance(cell, (int, float)):
                            text_cells += 1

                score += text_cells

                # 4. Prefer rows that come after some empty/metadata rows
                # Headers are often not in the first row
                if row_idx > 0:
                    score += 1

                # 5. Check for common header patterns
                for cell in row:
                    if pd.notna(cell):
                        cell_str = str(cell).lower()
                        # Common header words
                        if any(word in cell_str for word in ['code', 'name', 'date', 'description', 'id', 'number', 'type', 'status']):
                            score += 2

                logger.debug(f"Row {row_idx}: {non_empty} non-empty cells, score={score}")

                # Update best row if this score is higher
                if score > best_score:
                    best_score = score
                    best_row = row_idx

            # Only return a header row if we found a reasonably good candidate
            # (at least 3 non-empty cells and positive score)
            if best_row is not None and best_score > 5:
                return best_row

            return None

        except Exception as e:
            logger.warning(f"Error detecting header row: {e}")
            return None

    def _process_sheet(
        self,
        xls: pd.ExcelFile,
        sheet_name: str,
        base_doc_id: str,
        base_doc_title: str,
        base_metadata: Dict[str, Any],
        df_parser: Any,
        engine: str
    ) -> None:
        """
        Process a single Excel sheet.

        For .xlsb files: Uses multi-section approach (independent rows + tables)
        For other formats: Uses standard approach (single table)

        Args:
            xls: Pandas ExcelFile object
            sheet_name: Name of the sheet to process
            base_doc_id: Base document ID
            base_doc_title: Base document title
            base_metadata: Base metadata dictionary
            df_parser: DataframeParser instance
            engine: Pandas engine being used
        """
        logger.info(f"Processing sheet: '{sheet_name}'")

        # Generate document IDs
        sheet_doc_id = f"{base_doc_id}_{sheet_name}"
        sheet_doc_title = f"{base_doc_title} - {sheet_name}"

        # Create sheet-specific metadata
        sheet_metadata = base_metadata.copy()
        sheet_metadata['sheet_name'] = sheet_name

        # Use multi-section approach ONLY for .xlsb files
        if engine == 'pyxlsb':
            logger.info(f"Using multi-section approach for .xlsb file")
            self._process_sheet_xlsb(
                xls=xls,
                sheet_name=sheet_name,
                engine=engine,
                doc_id=sheet_doc_id,
                doc_title=sheet_doc_title,
                metadata=sheet_metadata,
                df_parser=df_parser
            )
        else:
            # Standard approach for .xlsx, .xlsm, .xls
            logger.info(f"Using standard approach for {engine} file")
            self._process_sheet_standard(
                xls=xls,
                sheet_name=sheet_name,
                engine=engine,
                doc_id=sheet_doc_id,
                doc_title=sheet_doc_title,
                metadata=sheet_metadata,
                df_parser=df_parser
            )

    def _process_sheet_xlsb(
        self,
        xls: pd.ExcelFile,
        sheet_name: str,
        engine: str,
        doc_id: str,
        doc_title: str,
        metadata: Dict[str, Any],
        df_parser: Any
    ) -> None:
        """
        Process .xlsb sheet with multi-section approach.
        Separates independent rows (metadata) from tables.
        """
        # Read raw sheet to analyze structure
        df_raw = pd.read_excel(xls, sheet_name=sheet_name, engine=engine, header=None)

        if df_raw.empty:
            logger.warning(f"Sheet '{sheet_name}' is empty. Skipping.")
            return

        # Analyze sheet structure
        structure = self._analyze_sheet_structure(df_raw)

        # Process based on structure
        if structure['has_tables']:
            # Multi-section approach: independent rows + tables
            self._index_multi_section(
                df_raw=df_raw,
                structure=structure,
                xls=xls,
                sheet_name=sheet_name,
                engine=engine,
                doc_id=doc_id,
                doc_title=doc_title,
                metadata=metadata,
                df_parser=df_parser
            )
        else:
            # No clear tables - treat as text content
            logger.info(f"No tables detected in sheet '{sheet_name}', processing as text")
            text_lines = []
            for idx, row in df_raw.iterrows():
                non_empty_values = row[row.notna()].values
                if len(non_empty_values) > 0:
                    text_lines.append(' '.join([str(v) for v in non_empty_values]))

            if text_lines:
                text_content = '\n'.join(text_lines)
                df_parser.indexer.index_segments(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    doc_metadata=metadata,
                    texts=[text_content],
                    tables=[]
                )

    def _process_sheet_standard(
        self,
        xls: pd.ExcelFile,
        sheet_name: str,
        engine: str,
        doc_id: str,
        doc_title: str,
        metadata: Dict[str, Any],
        df_parser: Any
    ) -> None:
        """
        Process Excel sheet with standard approach (for .xlsx, .xlsm, .xls).
        Uses header detection and single table processing.
        """
        # Detect the header row
        header_row = self._detect_header_row(xls, sheet_name, engine)

        if header_row is not None:
            logger.info(f"Detected header at row {header_row}")
            df = pd.read_excel(xls, sheet_name=sheet_name, engine=engine, header=header_row)
        else:
            logger.info(f"No clear header detected, using default (row 0)")
            df = pd.read_excel(xls, sheet_name=sheet_name, engine=engine)

        logger.info(f"Sheet '{sheet_name}': {df.shape[0]} rows x {df.shape[1]} columns")

        if df.empty:
            logger.warning(f"Sheet '{sheet_name}' is empty. Skipping.")
            return

        metadata['sheet_rows'] = df.shape[0]
        metadata['sheet_columns'] = df.shape[1]

        # Process the dataframe using existing DataframeParser
        df_parser.process_dataframe(
            df=df,
            doc_id=doc_id,
            doc_title=doc_title,
            metadata=metadata
        )

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean the dataframe by removing completely empty rows and columns,
        and cleaning up special characters from Excel formatting artifacts.

        Excel files often have many empty rows/columns due to formatting,
        and repeated special characters from merged cells.

        Args:
            df: Input dataframe

        Returns:
            Cleaned dataframe
        """
        import re

        # Remove rows that are completely empty (all NaN)
        df = df.dropna(how='all')

        # Remove columns that are completely empty (all NaN)
        df = df.dropna(axis=1, how='all')

        # Clean column names (headers) as well
        def clean_column_name(col_name):
            if pd.isna(col_name):
                return col_name

            col_str = str(col_name)

            # Special case: if column is just "Unnamed: N", keep it as is for now
            if col_str.startswith('Unnamed:'):
                return col_str

            # Remove repeated special characters (e.g., ": : : :" -> ":")
            col_str = re.sub(r'(\W)\s*\1+', r'\1', col_str)

            # Remove repeated letters/digits with spaces (e.g., "U U U U" -> "U", "0 0 0" -> "0")
            col_str = re.sub(r'(\w)\s+\1+(?:\s+\1)*', r'\1', col_str)

            # Remove excessive whitespace
            col_str = re.sub(r'\s+', ' ', col_str).strip()

            # If column name is just a single character or whitespace after cleaning, mark as unnamed
            if len(col_str) <= 1 or not col_str.strip():
                return 'Unnamed'

            return col_str

        # Clean column names
        original_columns = df.columns.tolist()
        df.columns = [clean_column_name(col) for col in df.columns]
        cleaned_columns = df.columns.tolist()

        # Log column cleaning if any changed
        if original_columns != cleaned_columns:
            logger.info(f"Cleaned column names: {len([i for i, (o, c) in enumerate(zip(original_columns, cleaned_columns)) if o != c])} columns modified")

        # Remove columns that are unnamed or just formatting artifacts
        cols_to_drop = []
        for col in df.columns:
            col_str = str(col)
            # Drop if it's unnamed or just a single character after cleaning
            if col_str == 'Unnamed' or (len(col_str) == 1 and col_str in ':-;,.'):
                cols_to_drop.append(col)

        if cols_to_drop:
            logger.info(f"Dropping {len(cols_to_drop)} unnamed/formatting columns")
            df = df.drop(columns=cols_to_drop)

        # Clean cell values: remove repeated special characters and formatting artifacts
        def clean_cell_value(value):
            if pd.isna(value):
                return value

            # Convert to string
            value_str = str(value)

            # Remove repeated special characters (e.g., "U U U U U" -> "U")
            # This handles merged cell artifacts
            value_str = re.sub(r'(\W)\s*\1+', r'\1', value_str)

            # Remove repeated letters with spaces (e.g., "n n n n n" -> "n")
            value_str = re.sub(r'(\w)\s+\1+(?:\s+\1)*', r'\1', value_str)

            # Remove excessive whitespace
            value_str = re.sub(r'\s+', ' ', value_str).strip()

            # Remove lines that are just repeated single characters
            if len(set(value_str.replace(' ', ''))) == 1 and len(value_str) > 3:
                return None

            return value_str if value_str else None

        # Apply cleaning to all cells
        # Use map() for newer pandas versions (applymap is deprecated)
        try:
            df = df.map(clean_cell_value)
        except AttributeError:
            # Fallback for older pandas versions
            df = df.applymap(clean_cell_value)

        # Remove rows that became empty after cleaning
        df = df.dropna(how='all')

        # Remove columns that became empty after cleaning
        df = df.dropna(axis=1, how='all')

        return df

    def _detect_content_type(self, df: pd.DataFrame) -> Optional[str]:
        """
        Detect the type of content in the sheet (form, table, mixed).

        This is a simple heuristic-based detection. Can be enhanced with ML/LLM.

        Args:
            df: Dataframe to analyze

        Returns:
            Content type string: 'form', 'table', 'mixed', or None
        """
        if df.empty:
            return None

        rows, cols = df.shape

        # Heuristic: If many columns (>10) and many rows (>10), likely a table
        if cols > 10 and rows > 10:
            return 'table'

        # Heuristic: If few columns (<=3) and many values, likely a form
        if cols <= 3 and rows > 5:
            # Check if it looks like key-value pairs
            non_null_ratio = df.notna().sum().sum() / (rows * cols)
            if non_null_ratio < 0.7:  # Many empty cells indicate form structure
                return 'form'

        # Heuristic: If moderate size, likely mixed content
        if 3 < cols <= 10 and rows > 3:
            return 'mixed'

        return 'table'  # Default to table


def process_excel_file_enhanced(
    file_path: str,
    doc_id: str,
    doc_title: str,
    df_metadata: Dict[str, Any],
    df_parser: Any,
    config: DictConfig
) -> bool:
    """
    Enhanced Excel file processing function.

    This function serves as the entry point for enhanced Excel processing.
    It creates an ExcelProcessor instance and delegates to it.

    Args:
        file_path: Path to the Excel file
        doc_id: Base document ID
        doc_title: Base document title
        df_metadata: Base metadata dictionary
        df_parser: DataframeParser instance
        config: Configuration object

    Returns:
        True if successful, False otherwise
    """
    processor = ExcelProcessor(config)
    return processor.process_excel_file(
        file_path=file_path,
        doc_id=doc_id,
        doc_title=doc_title,
        df_metadata=df_metadata,
        df_parser=df_parser
    )
