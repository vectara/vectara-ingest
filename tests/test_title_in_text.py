"""doc_processing.title_in_text: index the document title as the first text part of core documents.

Chunked (core) documents have no title field, so the title lives in metadata only and a query
for the document's name finds nothing. With title_in_text on, DocumentBuilder prepends a part
holding the title (crawler metadata title first, parser title as fallback). Structured documents
already carry the title in their "title" field and are left alone.
"""
import unittest

from omegaconf import OmegaConf

from core.document_builder import DocumentBuilder


def _builder(title_in_text):
    cfg = OmegaConf.create({'vectara': {}, 'doc_processing': {'title_in_text': title_in_text}})
    return DocumentBuilder(cfg, normalize_text_func=lambda t: t)


def _core(builder, **kw):
    args = dict(doc_id='d1', texts=['body one', 'body two'], metadatas=[{'page': 1}, {'page': 2}],
                doc_metadata={'title': 'August 22 HRIS Feature release.pdf', 'url': 'https://x/1'},
                doc_title='PowerPoint Presentation', use_core_indexing=True)
    args.update(kw)
    return builder.build_document(**args)


class TestTitleInText(unittest.TestCase):

    def test_off_by_default_keeps_parts_unchanged(self):
        doc = _core(_builder(False))
        self.assertEqual([p['text'] for p in doc['document_parts']], ['body one', 'body two'])

    def test_on_prepends_metadata_title_part(self):
        doc = _core(_builder(True))
        parts = doc['document_parts']
        self.assertEqual(parts[0], {'text': 'August 22 HRIS Feature release.pdf', 'metadata': {'element_type': 'title'}})
        self.assertEqual([p['text'] for p in parts[1:]], ['body one', 'body two'])
        self.assertEqual([p['metadata'] for p in parts[1:]], [{'page': 1}, {'page': 2}])

    def test_metadata_title_preferred_over_parser_title(self):
        doc = _core(_builder(True))
        self.assertEqual(doc['document_parts'][0]['text'], 'August 22 HRIS Feature release.pdf')

    def test_parser_title_used_when_metadata_has_none(self):
        doc = _core(_builder(True), doc_metadata={'url': 'https://x/1'}, doc_title='Benefit Summary')
        self.assertEqual(doc['document_parts'][0]['text'], 'Benefit Summary')

    def test_no_title_anywhere_adds_nothing(self):
        doc = _core(_builder(True), doc_metadata={'url': 'https://x/1'}, doc_title='')
        self.assertEqual([p['text'] for p in doc['document_parts']], ['body one', 'body two'])

    def test_document_metadata_unchanged(self):
        doc = _core(_builder(True))
        self.assertEqual(doc['metadata']['title'], 'August 22 HRIS Feature release.pdf')
        self.assertEqual(doc['metadata']['url'], 'https://x/1')

    def test_structured_documents_untouched(self):
        doc = _core(_builder(True), use_core_indexing=False)
        self.assertNotIn('document_parts', doc)
        self.assertEqual(doc['title'], 'PowerPoint Presentation')
        self.assertEqual([s['text'] for s in doc['sections']], ['body one', 'body two'])


if __name__ == '__main__':
    unittest.main()
