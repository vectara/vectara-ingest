"""A document whose only content is tables must be indexed (summaries as text), not dropped as 'no content'."""
import unittest

from omegaconf import OmegaConf

from core.document_builder import DocumentBuilder

CAL = {"headers": ["Month", "Cut-off", "Pay day"], "rows": [["Jan", "15 Jan", "24 Jan"], ["Feb", "17 Feb", "26 Feb"]],
       "summary": "2026 payroll calendar: cut-off and pay dates per month.", "title": ""}
NOSUM = {"headers": ["A", "B"], "rows": [[1, 2], [None, "x"]], "summary": "", "title": ""}


def _builder():
    return DocumentBuilder(OmegaConf.create({'vectara': {}, 'doc_processing': {}}), normalize_text_func=lambda t: t)


class TestTableOnlyDocuments(unittest.TestCase):

    def test_structured_tables_only_document_is_built(self):
        doc = _builder().build_document(doc_id='d1', texts=[], doc_title='UK Payroll Calendar', tables=[CAL],
                                        doc_metadata={'title': 'UK Payroll Calendar.pdf'}, use_core_indexing=False)
        self.assertIsNotNone(doc)
        text_sections = [s for s in doc['sections'] if s['text']]  # the builder adds a text-less section per table
        self.assertEqual([s['text'] for s in text_sections], [CAL['summary']])
        self.assertEqual(text_sections[0]['metadata'], {'element_type': 'table_summary'})
        self.assertEqual(doc['title'], 'UK Payroll Calendar')
        # structured documents carry tables as table sections, not a top-level tables array
        self.assertEqual(len(doc['sections']) - len(text_sections), 1)

    def test_core_tables_only_document_is_built(self):
        doc = _builder().build_document(doc_id='d2', texts=[], tables=[CAL], use_core_indexing=True)
        self.assertEqual([p['text'] for p in doc['document_parts']], [CAL['summary']])
        self.assertEqual(len(doc['tables']), 1)

    def test_table_without_summary_falls_back_to_rows(self):
        self.assertEqual(DocumentBuilder._table_texts([NOSUM]), ["A | B\n1 | 2\n | x"])

    def test_truly_empty_document_is_still_dropped(self):
        self.assertIsNone(_builder().build_document(doc_id='d3', texts=['  '], tables=[]))
        self.assertIsNone(_builder().build_document(doc_id='d4', texts=[], tables=[{'headers': [], 'rows': [], 'summary': ''}]))

    def test_document_with_text_is_unchanged(self):
        doc = _builder().build_document(doc_id='d5', texts=['body'], tables=[CAL], use_core_indexing=False)
        self.assertEqual([s['text'] for s in doc['sections'] if s['text']], ['body'])


if __name__ == '__main__':
    unittest.main()
