import os
import unittest
from unittest.mock import MagicMock

from omegaconf import DictConfig, OmegaConf

from core.dataframe_parser import determine_dataframe_type, load_dataframe_metadata, DataframeParser
from core.indexer import Indexer
from core.summary import TableSummarizer
from core.utils import setup_logging


def load_config(*parts) -> DictConfig:
    config_path = os.path.join(*parts)
    return DictConfig(OmegaConf.load(config_path))


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

    def test_dataframe_parser_csv(self):
        cfg: DictConfig = load_config('data', 'dataframe', 'config', 'test_dataframe_parser_csv.yml')
        input_path = os.path.join('data', 'dataframe', 'test.csv')
        metadata = load_dataframe_metadata(input_path)
        parser_config: DictConfig = cfg.get("csv_parser")

        mock_indexer: Indexer = MagicMock()
        mock_table_summarizer: TableSummarizer = MagicMock()

        expected_doc_id = "asdf9asdfa3"
        expected_texts = [
            "This is a summary."
        ]
        mock_table_summarizer.summarize_table_text.side_effect = expected_texts
        expected_metadata = {
            'source': __name__
        }
        expected_doc_title = "name"  # TODO: Fix this it's absolutely not correct
        expected_tables = [
            {
                'headers': ['first_name', 'last_name', 'description'],
                'rows': [
                    ['example', 'user', 'this is an example user'],
                    ['admin', 'user', 'this is an admin user']
                ],
                'summary': 'This is a summary.'
            }
        ]

        parser: DataframeParser = DataframeParser(cfg, parser_config, mock_indexer, mock_table_summarizer)
        parser.parse(metadata, expected_doc_id, expected_metadata)

        mock_indexer.index_segments.assert_called_once_with(
            doc_id=expected_doc_id,
            texts=expected_texts,
            tables=expected_tables,
            doc_title=expected_doc_title,
            doc_metadata=expected_metadata
        )

    def test_dataframe_parser_xlsx(self):
        cfg: DictConfig = load_config('data', 'dataframe', 'config', 'test_dataframe_parser_xlsx.yml')
        input_path = os.path.join('data', 'dataframe', 'test.xlsx')
        metadata = load_dataframe_metadata(input_path)
        parser_config: DictConfig = cfg.get("csv_parser")

        mock_indexer: Indexer = MagicMock()
        mock_table_summarizer: TableSummarizer = MagicMock()

        expected_doc_id = "asdf9asdfa3"
        expected_texts = [
            "This is a table about the band Aerosmith.",
            "This is a table about the band Bon Jovi."
        ]
        mock_table_summarizer.summarize_table_text.side_effect = expected_texts
        expected_metadata = {
            'source': __name__
        }
        expected_doc_title = "name"  # TODO: Fix this it's absolutely not correct
        expected_tables = [
            {
                'headers': ['first_name', 'last_name', 'instrument'],
                'rows': [
                    ['steven', 'tyler', 'piano'],
                    ['joe', 'perry', 'guitar'],
                    ['brad', 'whitford', 'guitar'],
                    ['joey', 'kramer', 'drummer'],
                    ['tom', 'hamilton', 'guitar']
                ],
                'summary': 'This is a table about the band Aerosmith.'
            },
            {
                'headers': ['first_name', 'last_name', 'instrument'],
                'rows': [
                    ['jon', 'bon jovi', 'guitar'],
                    ['richie', 'ssambora', 'guitar'],
                    ['dave', 'sabo', 'guitar'],
                    ['tico', 'torres', 'drummer']
                ],
                'summary': 'This is a table about the band Bon Jovi.'
            }
        ]

        parser: DataframeParser = DataframeParser(cfg, parser_config, mock_indexer, mock_table_summarizer)
        parser.parse(metadata, expected_doc_id, expected_metadata)

        mock_indexer.index_segments.assert_called_once_with(
            doc_id=expected_doc_id,
            texts=expected_texts,
            tables=expected_tables,
            doc_title=expected_doc_title,
            doc_metadata=expected_metadata
        )
