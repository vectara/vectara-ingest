import logging
import os
import sys
import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, call, patch
import pandas as pd
from omegaconf import DictConfig, OmegaConf

# Mock cairosvg before it's imported by other modules
sys.modules['cairosvg'] = MagicMock()

from core.dataframe_parser import (
    determine_dataframe_type,
    DataframeParser,
    generate_dfs_to_index,
    supported_by_dataframe_parser,
    get_separator_by_file_name,
)
from core.indexer import Indexer
from core.summary import TableSummarizer
from core.utils import setup_logging, load_config

def _load_config(*parts: str) -> DictConfig:
    if not parts:
        raise ValueError("At least one path part is required")
    config_path = os.path.join(*parts)
    return load_config(config_path)

@dataclass
class ExpectedIndexSegmentsCall:
    doc_id: str
    doc_metadata: dict[str, str]
    doc_title: str
    tables: list[dict]
    texts: list[str]
    metadatas: list[dict[str, Any]]
    titles: Any

@dataclass
class DataframeTestCase:
    doc_id: str | None
    doc_metadata: dict[str, Any] | None
    input_path: list[str]
    expected_index_segments_calls: list[ExpectedIndexSegmentsCall]

class TestDataFrameParser(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        setup_logging('DEBUG')

    def test_determine_dataframe_type(self):
        self.assertEqual("csv", determine_dataframe_type("test.csv"))
        self.assertEqual("csv", determine_dataframe_type("test.tsv"))
        self.assertEqual("xls", determine_dataframe_type("test.xls"))
        self.assertEqual("xls", determine_dataframe_type("test.xlsx"))
        self.assertIsNone(determine_dataframe_type("test.txt"))

    def test_supported_by_dataframe_parser(self):
        self.assertTrue(supported_by_dataframe_parser('test.csv'))
        self.assertTrue(supported_by_dataframe_parser('test.tsv'))
        self.assertTrue(supported_by_dataframe_parser('test.xls'))
        self.assertTrue(supported_by_dataframe_parser('test.xlsx'))
        self.assertFalse(supported_by_dataframe_parser('test.pdf'))

    def run_dataframe_parser_test(self, *test_config_path: str):
        config = _load_config(*test_config_path)
        self.assertIn('test', config, "Test configuration is missing 'test' element.")

        dataframe_testcase = OmegaConf.structured(DataframeTestCase)
        OmegaConf.merge(dataframe_testcase, config.get('test'))
        test_config = OmegaConf.to_object(config.get('test'))

        expected_calls_data = test_config.get('expected_index_segments_calls')
        doc_id_base = test_config.get('doc_id', 'test_doc')
        doc_metadata = test_config.get('doc_metadata', {})
        input_path = os.path.join(*test_config.get('input_path'))
        
        parser_config = config.get("csv_parser") or config.get("folder_crawler") or config.get("dataframe_processing")

        mock_indexer = MagicMock(spec=Indexer)
        mock_table_summarizer = MagicMock(spec=TableSummarizer)
        
        summaries = [
            table.get('summary') 
            for c in expected_calls_data 
            for table in c.get("tables", []) 
            if table.get('summary')
        ]
        if summaries:
            mock_table_summarizer.summarize_table_text.side_effect = summaries

        parser = DataframeParser(config, parser_config, mock_indexer, mock_table_summarizer)

        file_type = determine_dataframe_type(input_path)
        doc_title = os.path.basename(input_path)

        if file_type == 'csv':
            separator = get_separator_by_file_name(input_path)
            df = pd.read_csv(input_path, sep=separator)
            parser.process_dataframe(df, doc_id=doc_id_base, doc_title=doc_title, metadata=doc_metadata)
        
        elif file_type == 'xls':
            xls = pd.ExcelFile(input_path)
            sheet_names = parser_config.get("sheet_names", xls.sheet_names)
            for sheet_name in sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                # For element mode, use original file name; for table mode, include sheet name
                if parser_config.get("mode", "table") == "element":
                    sheet_doc_title = os.path.basename(input_path)
                else:
                    sheet_doc_title = f"{os.path.basename(input_path)} - {sheet_name}"
                doc_id = config.test.doc_id
                parser.process_dataframe(df, doc_id=f"{doc_id}_{sheet_name}", doc_title=sheet_doc_title, metadata=doc_metadata)

        expected_calls = [call(**params) for params in expected_calls_data]
        mock_indexer.index_segments.assert_has_calls(expected_calls, any_order=True)

    # --- Test Cases ---
    def test_dataframe_parser_csv_table_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_table_mode.yml')

    def test_dataframe_parser_csv_table_mode_select_condition(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_table_mode_select_condition.yml')

    def test_dataframe_parser_csv_element_mode_select_condition(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_element_mode_select_condition.yml')

    def test_dataframe_parser_tsv_table_mode_default(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_tsv_table_mode.yml')

    def test_dataframe_parser_pipe_table_mode_default(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_pipe_table_mode.yml')

    def test_dataframe_parser_xlsx_table_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_xlsx_table_mode.yml')

    def test_dataframe_parser_csv_element_mode_column_datatypes(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_element_mode_column_datatypes.yml')

    def test_dataframe_parser_xlsx_element_mode_column_datatypes(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_xlsx_element_mode_column_datatypes.yml')

    def test_dataframe_parser_csv_table_mode_truncate(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_table_mode_should_truncate.yml')

    def test_dataframe_parser_csv_element_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_element_mode.yml')

    def test_dataframe_parser_xlsx_element_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_xlsx_element_mode.yml')

    def test_generate_dfs_to_index_by_rows(self):
        input_df = pd.read_csv(os.path.join('tests', 'data', 'dataframe', 'fdic-failed-banks.csv'))
        output_chunks = list(generate_dfs_to_index(input_df, None, 50))
        
        self.assertEqual(12, len(output_chunks))
        self.assertEqual(50, len(output_chunks[0][1]))
        self.assertEqual(21, len(output_chunks[-1][1]))
        self.assertEqual('rows 0-49', output_chunks[0][0])

    def test_generate_dfs_to_index_by_columns(self):
        input_df = pd.read_csv(os.path.join('tests', 'data', 'dataframe', 'fdic-failed-banks.csv'))
        output_chunks = dict(generate_dfs_to_index(input_df, ['City', 'State'], 500))

        self.assertEqual(1, len(output_chunks['Austin - TX']))
        self.assertEqual(4, len(output_chunks['Alpharetta - GA']))
        self.assertEqual(10, len(output_chunks['Atlanta - GA']))

if __name__ == '__main__':
    unittest.main()
