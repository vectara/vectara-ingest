import os
import tempfile
import unittest
from unittest.mock import MagicMock

import yaml
import pandas as pd
from omegaconf import DictConfig, OmegaConf
from dataclasses import dataclass

from core.dataframe_parser import determine_dataframe_type, load_dataframe_metadata, DataframeParser
from core.indexer import Indexer
from core.summary import TableSummarizer
from core.utils import setup_logging, load_config


def test_load_config(*parts:str) -> DictConfig:
    config_path = os.path.join(*parts)
    return load_config(config_path)

@dataclass
class ExpectedIndexSegmentsCall:
    doc_id: str
    doc_metadata: dict[str, str]
    doc_title: str
    tables: list[dict]
    texts: list[str]

@dataclass
class DataframeTestCase:
    input_path: list[str]
    expected_index_segments_call: ExpectedIndexSegmentsCall

class TestDataFrameParser(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        setup_logging('DEBUG')

    def test_determine_dataframe_type_csv(self):
        dataframe_type = determine_dataframe_type("/test/foo/testing.csv")
        self.assertEqual("csv", dataframe_type, 'Expected csv for .csv file')

    def test_determine_dataframe_type_tsv(self):
        dataframe_type = determine_dataframe_type("/test/foo/testing.tsv")
        self.assertEqual("csv", dataframe_type, 'Expected csv for .tsv file')

    def test_determine_dataframe_type_xls(self):
        dataframe_type = determine_dataframe_type("/test/foo/testing.xls")
        self.assertEqual("xls", dataframe_type, 'Expected xls for .xls file')

    def test_determine_dataframe_type_xlsx(self):
        dataframe_type = determine_dataframe_type("/test/foo/testing.xlsx")
        self.assertEqual("xls", dataframe_type, 'Expected xls for .xlsx file')

    def test_load_dataframe_metadata_csv(self):
        input_path = os.path.join('data', 'dataframe', 'test.csv')
        self.assertTrue(os.path.exists(input_path), 'Test file should exist')

        metadata = load_dataframe_metadata(input_path)
        self.assertIsNotNone(metadata, 'metadata should have been returned')
        self.assertIsNone(metadata.sheet_names)

    def test_load_dataframe_metadata_xls(self):
        # Ensure you have a 'test.xls' file in the 'data/dataframe/' directory for this test
        input_path = os.path.join('data', 'dataframe', 'test.xlsx')
        self.assertTrue(os.path.exists(input_path),
                        f'Test file {input_path} should exist. Please create a dummy test.xls file.')

        metadata = load_dataframe_metadata(input_path)
        self.assertIsNotNone(metadata, 'metadata should have been returned for XLS file')
        self.assertIsNotNone(metadata.sheet_names, 'sheet_names should be populated for XLS files')
        self.assertIsInstance(metadata.sheet_names, list, 'sheet_names should be a list')

        expected_sheet_names = [
            'aerosmith',
            'bon jovi'
        ]

        for expected_sheet_name in expected_sheet_names:
            self.assertIn(expected_sheet_name, metadata.sheet_names)
            df = metadata.open_dataframe(expected_sheet_name)
            self.assertIsNotNone(df, f'Expected df with sheet {expected_sheet_name}')


    def run_dataframe_parser_test(self, *test_config_path:str):
        config = test_load_config(*test_config_path)
        self.assertIn('test', config, f"Test configuration is missing 'test' element.")

        # Validate against the test schema
        dataframe_testcase:OmegaConf = OmegaConf.structured(DataframeTestCase)
        OmegaConf.merge(dataframe_testcase, config.get('test'))

        test_config = OmegaConf.to_object(config.get('test'))

        expected_index_segments_call: dict = test_config.get('expected_index_segments_call')
        expected_doc_id = expected_index_segments_call.get('doc_id')
        expected_metadata = expected_index_segments_call.get('doc_metadata')

        # expected_doc_title = 'test.tsv'
        input_path_parts = test_config.get('input_path')
        input_path = os.path.join(*input_path_parts)
        metadata = load_dataframe_metadata(input_path)
        parser_config: DictConfig = config.get("csv_parser")

        mock_indexer: Indexer = MagicMock()
        mock_table_summarizer: TableSummarizer = MagicMock()
        mock_table_summarizer.summarize_table_text.side_effect=expected_index_segments_call['texts']

        parser: DataframeParser = DataframeParser(config, parser_config, mock_indexer, mock_table_summarizer)
        parser.parse(metadata, expected_doc_id, expected_metadata)

        mock_indexer.index_segments.assert_called_once_with(**dict(sorted(expected_index_segments_call.items())))


    def test_dataframe_parser_csv_table_mode(self):
        self.run_dataframe_parser_test('data', 'dataframe', 'config', 'test_dataframe_parser_csv_table_mode.yml')

    def test_dataframe_parser_tsv_table_mode_default(self):
        self.run_dataframe_parser_test('data', 'dataframe', 'config', 'test_dataframe_parser_tsv_table_mode.yml')

    def test_dataframe_parser_pipe_table_mode_default(self):
        self.run_dataframe_parser_test('data', 'dataframe', 'config', 'test_dataframe_parser_pipe_table_mode.yml')

    def test_dataframe_parser_xlsx_table_mode(self):
        self.run_dataframe_parser_test('data', 'dataframe', 'config', 'test_dataframe_parser_xlsx_table_mode.yml')

    def test_dataframe_parser_csv_table_mode_truncate(self):
        self.run_dataframe_parser_test('data', 'dataframe', 'config', 'test_dataframe_parser_csv_table_mode_should_truncate.yml')




