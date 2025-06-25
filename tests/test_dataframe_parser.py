import os
import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, call

import pandas as pd
from omegaconf import DictConfig, OmegaConf

from core.dataframe_parser import determine_dataframe_type, load_dataframe_metadata, DataframeParser, \
    generate_dfs_to_index, supported_by_dataframe_parser
from core.indexer import Indexer
from core.summary import TableSummarizer
from core.utils import setup_logging, load_config


def test_load_config(*parts: str) -> DictConfig:
    config_path = os.path.join(*parts)
    return load_config(config_path)


@dataclass
class ExpectedIndexSegmentsCall:
    """
    Defines the expected keyword arguments for a single call to the
    `Indexer.index_segments` method.

    This class is used to specify the precise data that a test expects
    the DataframeParser to send to the indexing mechanism after processing
    a dataframe. Each field corresponds to a parameter of the
    `index_segments` method.

    Attributes:
        doc_id (str): The expected document ID.
        doc_metadata (dict[str, str]): The expected document-level metadata.
        doc_title (str): The expected document title.
        tables (list[dict]): A list of dictionaries, where each dictionary
                             represents a table extracted from the dataframe,
                             likely containing 'headers', 'rows', and 'summary'.
        texts (list[str]): A list of text segments extracted or generated
                           from the dataframe, often including summaries.
    """
    doc_id: str
    doc_metadata: dict[str, str]
    doc_title: str
    tables: list[dict]
    texts: list[str]
    metadatas: list[dict[str, Any]]
    titles: Any


@dataclass
class DataframeTestCase:
    """
    Represents the configuration for a single dataframe parser test case.

    This class is used as a schema with OmegaConf to load and validate
    test configurations from YAML files. It encapsulates the input data
    for the parser and the expected outcome in terms of what should be
    passed to the indexer.

    Attributes:
        input_path (list[str]): A list of path components that, when joined,
                                form the full path to the input dataframe file
                                (e.g., a CSV, TSV, or XLSX file).
        expected_index_segments_call (ExpectedIndexSegmentsCall):
                                An instance defining the expected arguments
                                for the call to `Indexer.index_segments`.
    """
    doc_id: str | None
    doc_metadata: dict[str, Any] | None
    input_path: list[str]
    expected_index_segments_calls: list[ExpectedIndexSegmentsCall]


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
        input_path = os.path.join('tests','data', 'dataframe', 'test.csv')
        self.assertTrue(os.path.exists(input_path), 'Test file should exist')

        metadata = load_dataframe_metadata(input_path)
        self.assertIsNotNone(metadata, 'metadata should have been returned')
        self.assertIsNone(metadata.sheet_names)

    def test_load_dataframe_metadata_xls(self):
        # Ensure you have a 'test.xls' file in the 'data/dataframe/' directory for this test
        input_path = os.path.join('tests','data', 'dataframe', 'test.xlsx')
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

        parser_config:DictConfig = OmegaConf.create({})


        for expected_sheet_name in expected_sheet_names:
            self.assertIn(expected_sheet_name, metadata.sheet_names)
            df = metadata.open_dataframe(parser_config, sheet_name=expected_sheet_name)
            self.assertIsNotNone(df, f'Expected df with sheet {expected_sheet_name}')

    def test_supported_by_dataframe_parser(self):
        self.assertTrue(supported_by_dataframe_parser('test.csv'))
        self.assertTrue(supported_by_dataframe_parser('test.tsv'))
        self.assertTrue(supported_by_dataframe_parser('test.xls'))
        self.assertTrue(supported_by_dataframe_parser('test.xlsx'))
        self.assertFalse(supported_by_dataframe_parser('test.pdf'))
        self.assertFalse(supported_by_dataframe_parser('test.mp3'))

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
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config',
                                       'test_dataframe_parser_csv_table_mode_should_truncate.yml')



    def run_dataframe_parser_test(self, *test_config_path: str):
        config = test_load_config(*test_config_path)
        self.assertIn('test', config, f"Test configuration is missing 'test' element.")

        # Validate against the test schema
        dataframe_testcase: OmegaConf = OmegaConf.structured(DataframeTestCase)
        OmegaConf.merge(dataframe_testcase, config.get('test'))

        test_config = OmegaConf.to_object(config.get('test'))

        expected_index_segments_calls: list[dict] = test_config.get('expected_index_segments_calls')
        expected_doc_id = test_config.get('doc_id', None)
        expected_metadata = test_config.get('doc_metadata', {})

        # expected_doc_title = 'test.tsv'
        input_path_parts = test_config.get('input_path')
        input_path = os.path.join(*input_path_parts)
        metadata = load_dataframe_metadata(input_path)
        parser_config: DictConfig = config.get("csv_parser")

        mock_indexer: Indexer = MagicMock()
        mock_table_summarizer: TableSummarizer = MagicMock()
        summaries = [table.get('summary') for c in expected_index_segments_calls for table in c.get("tables", []) if
                     table.get('summary')]
        mock_table_summarizer.summarize_table_text.side_effect = summaries

        parser: DataframeParser = DataframeParser(config, parser_config, mock_indexer, mock_table_summarizer)
        parser.parse(metadata, expected_doc_id, expected_metadata)
        calls = [call(**params) for params in expected_index_segments_calls]
        mock_indexer.index_segments.assert_has_calls(calls, any_order=True)

    def test_dataframe_parser_csv_element_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_csv_element_mode.yml')

    def test_dataframe_parser_xlsx_element_mode(self):
        self.run_dataframe_parser_test('tests', 'data', 'dataframe', 'config', 'test_dataframe_parser_xlsx_element_mode.yml')

    def test_generate_dfs_to_index_failed_banks(self):
        document_id_columns = ['City', 'State']
        rows_per_chunk = 500
        input_path = os.path.join('tests', 'data', 'dataframe', 'fdic-failed-banks.csv')
        input_df = pd.read_csv(input_path)
        output = generate_dfs_to_index(input_df, document_id_columns, rows_per_chunk)
        self.assertIsNotNone(output)
        df_by_city_state = dict(output)
        self.assertIsNotNone(df_by_city_state)
        assertions = [
            ('Austin - TX', 1),
            ('Alpharetta - GA', 4),
            ('Atlanta - GA', 10),
            ('Bradenton - FL', 4),
            ('Las Vegas - NV', 4),
            ('Los Angeles - CA', 4),
        ]

        for city_state, count in assertions:
            self.assertIn(city_state, df_by_city_state, f"Should have an entry for '{city_state}'.")
            df = df_by_city_state[city_state]
            self.assertEqual(count, df.shape[0], f"Row count for '{city_state}' does not match.")
