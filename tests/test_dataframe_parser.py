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

    def test_determine_dataframe_type_uppercase_extension(self):
        # Files arriving from sources that preserve case (e.g. Google Drive,
        # raw S3 keys) must route the same as their lowercase siblings.
        self.assertEqual("csv", determine_dataframe_type("test.CSV"))
        self.assertEqual("xls", determine_dataframe_type("test.XLSX"))
        self.assertEqual("csv", determine_dataframe_type("Quarterly.TSV"))

    def test_supported_by_dataframe_parser(self):
        self.assertTrue(supported_by_dataframe_parser('test.csv'))
        self.assertTrue(supported_by_dataframe_parser('test.tsv'))
        self.assertTrue(supported_by_dataframe_parser('test.xls'))
        self.assertTrue(supported_by_dataframe_parser('test.xlsx'))
        self.assertFalse(supported_by_dataframe_parser('test.pdf'))

    def test_supported_by_dataframe_parser_uppercase_extension(self):
        self.assertTrue(supported_by_dataframe_parser('test.CSV'))
        self.assertTrue(supported_by_dataframe_parser('test.Xlsx'))
        self.assertTrue(supported_by_dataframe_parser('Sales.TSV'))
        self.assertFalse(supported_by_dataframe_parser('test.PDF'))

    def test_process_dataframe_file_sets_last_error_on_unsupported_ext(self):
        # When process_dataframe_file rejects a file as unsupported, df_parser.last_error
        # must be populated so callers can surface the reason in their drop records.
        from core.dataframe_parser import process_dataframe_file
        df_parser = MagicMock()
        df_parser.last_error = "stale value should be cleared"

        ok = process_dataframe_file(
            file_path="/tmp/whatever.pdf",
            metadata={},
            doc_id="X",
            df_parser=df_parser,
            df_config={},
        )

        self.assertFalse(ok)
        self.assertIsNotNone(df_parser.last_error)
        self.assertIn("unsupported extension", df_parser.last_error)

    def test_process_dataframe_file_clears_last_error_at_start(self):
        # Stale errors from prior calls must not leak into the current call when
        # the parser fails early for a non-exception reason.
        from core.dataframe_parser import process_dataframe_file
        df_parser = MagicMock()
        df_parser.last_error = None

        ok = process_dataframe_file(
            file_path="/tmp/whatever.pdf",  # unsupported - fails the early check
            metadata={},
            doc_id="X",
            df_parser=df_parser,
            df_config={},
        )

        # last_error must be set (not None) so the failure is diagnosable.
        self.assertFalse(ok)
        self.assertIsNotNone(df_parser.last_error)

    def test_open_excel_uses_default_engine_when_it_succeeds(self):
        # Happy path: the default pandas engine works, so the calamine fallback
        # must NOT be invoked (avoid changing behavior for files that already
        # parse fine).
        from core import dataframe_parser as dfp

        sentinel = object()
        calls: list[dict] = []

        def fake_excel_file(path, engine=None):
            calls.append({"path": path, "engine": engine})
            return sentinel

        with patch.object(dfp.pd, "ExcelFile", side_effect=fake_excel_file):
            result = dfp.open_excel_with_fallback("/tmp/healthy.xlsx")

        self.assertIs(result, sentinel)
        self.assertEqual([{"path": "/tmp/healthy.xlsx", "engine": None}], calls)

    def test_open_excel_falls_back_to_calamine_when_default_engine_raises(self):
        # When openpyxl raises (e.g. the "expected <class 'openpyxl.styles.fills.Fill'>"
        # error on workbooks with malformed styles), the helper must retry with
        # engine='calamine' and return the calamine-opened ExcelFile.
        from core import dataframe_parser as dfp

        sentinel = object()
        calls: list[dict] = []

        def fake_excel_file(path, engine=None):
            calls.append({"path": path, "engine": engine})
            if engine is None:
                raise TypeError("expected <class 'openpyxl.styles.fills.Fill'>")
            return sentinel

        with patch.object(dfp.pd, "ExcelFile", side_effect=fake_excel_file):
            result = dfp.open_excel_with_fallback("/tmp/broken.xlsx")

        self.assertIs(result, sentinel)
        self.assertEqual(
            [
                {"path": "/tmp/broken.xlsx", "engine": None},
                {"path": "/tmp/broken.xlsx", "engine": "calamine"},
            ],
            calls,
        )

    def test_open_excel_reraises_os_errors_without_calamine_fallback(self):
        # File-access failures (missing file, permissions) are not engine
        # problems — calamine can't help. The helper must re-raise immediately
        # and NOT attempt a second (misleading) calamine open.
        from core import dataframe_parser as dfp

        calls: list[dict] = []

        def fake_excel_file(path, engine=None):
            calls.append({"path": path, "engine": engine})
            raise FileNotFoundError(path)

        with patch.object(dfp.pd, "ExcelFile", side_effect=fake_excel_file):
            with self.assertRaises(FileNotFoundError):
                dfp.open_excel_with_fallback("/tmp/missing.xlsx")

        self.assertEqual([{"path": "/tmp/missing.xlsx", "engine": None}], calls)

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

        # index_segments now always receives the incremental signals (None here — these
        # YAML cases don't run incremental); inject them so expectations match the real call.
        expected_calls = [
            call(**params, prior_fingerprint=None, content_hash_override=None)
            for params in expected_calls_data
        ]
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

    def test_incremental_signals_threaded_to_index_segments_table_mode(self):
        # gdrive native Sheets: the per-doc_id prior fingerprint and a stable content_hash
        # override (Drive modifiedTime) must reach index_segments so the document can skip —
        # the LLM table summary is not stable enough to key the skip off the section text.
        cfg = OmegaConf.create({"vectara": {}, "doc_processing": {}})
        parser_config = OmegaConf.create({"mode": "table"})
        mock_indexer = MagicMock(spec=Indexer)
        mock_summarizer = MagicMock(spec=TableSummarizer)
        mock_summarizer.summarize_table_text.return_value = "a summary"
        parser = DataframeParser(cfg, parser_config, mock_indexer, mock_summarizer)

        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        parser.process_dataframe(
            df, doc_id="file123", doc_title="t", metadata={"url": "u"},
            prior_fingerprints={"file123": "fp-123"},
            content_hash_override="gdrive-native:2024-01-01",
        )
        _, kwargs = mock_indexer.index_segments.call_args
        self.assertEqual(kwargs["prior_fingerprint"], "fp-123")
        self.assertEqual(kwargs["content_hash_override"], "gdrive-native:2024-01-01")

    def test_incremental_prior_fingerprint_looked_up_per_chunk_element_mode(self):
        # element mode emits one doc per chunk (doc_id = "<prefix>-<chunk>"); each chunk must
        # get its own prior fingerprint, while the content override (the file's signal) is shared.
        cfg = OmegaConf.create({"vectara": {}, "doc_processing": {}})
        parser_config = OmegaConf.create(
            {"mode": "element", "doc_id_columns": ["k"], "text_columns": ["v"]})
        mock_indexer = MagicMock(spec=Indexer)
        parser = DataframeParser(cfg, parser_config, mock_indexer, MagicMock(spec=TableSummarizer))

        df = pd.DataFrame({"k": ["x", "y"], "v": ["v1", "v2"]})
        parser.process_dataframe(
            df, doc_id="file9", doc_title="t", metadata={"url": "u"},
            prior_fingerprints={"file9-x": "fp-x", "file9-y": "fp-y"},
            content_hash_override="sig",
        )
        by_doc = {c.kwargs["doc_id"]: c.kwargs for c in mock_indexer.index_segments.call_args_list}
        self.assertEqual(by_doc["file9-x"]["prior_fingerprint"], "fp-x")
        self.assertEqual(by_doc["file9-y"]["prior_fingerprint"], "fp-y")
        self.assertEqual(by_doc["file9-x"]["content_hash_override"], "sig")

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
