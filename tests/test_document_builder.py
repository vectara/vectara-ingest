import unittest
from core.document_builder import DocumentBuilder, MAX_SECTION_CHARS


class TestSplitText(unittest.TestCase):
    """Tests for DocumentBuilder._split_text and _split_by_sentences."""

    def test_short_text_unchanged(self):
        chunks = DocumentBuilder._split_text("hello world", MAX_SECTION_CHARS)
        self.assertEqual(chunks, ["hello world"])

    def test_split_on_paragraph_boundaries(self):
        para = "A" * 10000
        text = para + "\n\n" + para
        chunks = DocumentBuilder._split_text(text, MAX_SECTION_CHARS)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= MAX_SECTION_CHARS for c in chunks))

    def test_single_newline_fallback(self):
        line = "B" * 10000
        text = line + "\n" + line
        chunks = DocumentBuilder._split_text(text, MAX_SECTION_CHARS)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= MAX_SECTION_CHARS for c in chunks))

    def test_split_on_sentence_boundaries(self):
        sentences = ". ".join(["Sentence number " + str(i) for i in range(1000)])
        chunks = DocumentBuilder._split_text(sentences, MAX_SECTION_CHARS)
        self.assertTrue(all(len(c) <= MAX_SECTION_CHARS for c in chunks))
        self.assertGreater(len(chunks), 1)

    def test_hard_cut_fallback(self):
        text = "A" * 50000
        chunks = DocumentBuilder._split_text(text, MAX_SECTION_CHARS)
        expected_chunks = (50000 + MAX_SECTION_CHARS - 1) // MAX_SECTION_CHARS
        self.assertEqual(len(chunks), expected_chunks)
        self.assertTrue(all(len(c) <= MAX_SECTION_CHARS for c in chunks))
        self.assertEqual("".join(chunks), text)

    def test_content_preserved_after_paragraph_split(self):
        para1 = "X" * 10000
        para2 = "Y" * 10000
        para3 = "Z" * 5000
        text = para1 + "\n\n" + para2 + "\n\n" + para3
        chunks = DocumentBuilder._split_text(text, MAX_SECTION_CHARS)
        self.assertTrue(all(len(c) <= MAX_SECTION_CHARS for c in chunks))
        joined = "\n\n".join(chunks)
        self.assertIn(para1, joined)
        self.assertIn(para2, joined)
        self.assertIn(para3, joined)

    def test_small_paragraphs_grouped(self):
        paras = ["Para " + str(i) for i in range(10)]
        text = "\n\n".join(paras)
        chunks = DocumentBuilder._split_text(text, MAX_SECTION_CHARS)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)


class TestBuildStructuredDocument(unittest.TestCase):
    """Tests for _build_structured_document with split_oversized flag."""

    def setUp(self):
        self.builder = DocumentBuilder({}, normalize_text_func=lambda t: t)

    def test_small_section_not_split(self):
        doc = {"id": "test", "metadata": {}}
        result = self.builder._build_structured_document(
            doc, ["short text"], ["title"], [{}], "Doc", []
        )
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(result["sections"][0]["text"], "short text")

    def test_large_section_not_split_without_flag(self):
        doc = {"id": "test", "metadata": {}}
        big_text = "word " * 5000  # ~25000 chars
        result = self.builder._build_structured_document(
            doc, [big_text], ["title"], [{}], "Doc", []
        )
        self.assertEqual(len(result["sections"]), 1)

    def test_large_section_split_with_flag(self):
        doc = {"id": "test", "metadata": {}}
        big_text = "word " * 5000  # ~25000 chars
        result = self.builder._build_structured_document(
            doc, [big_text], ["title"], [{}], "Doc", [],
            split_oversized=True
        )
        self.assertGreater(len(result["sections"]), 1)
        self.assertTrue(all(len(s["text"]) <= MAX_SECTION_CHARS for s in result["sections"]))

    def test_tables_bundled_without_flag(self):
        tables = [
            {'id': 'table_0', 'title': '', 'data': {'headers': [], 'rows': []}, 'description': 'T1'},
            {'id': 'table_1', 'title': '', 'data': {'headers': [], 'rows': []}, 'description': 'T2'},
        ]
        doc = {"id": "test", "metadata": {}}
        result = self.builder._build_structured_document(
            doc, ["text"], [""], [{}], "", tables
        )
        table_sections = [s for s in result["sections"] if "tables" in s]
        self.assertEqual(len(table_sections), 1)
        self.assertEqual(len(table_sections[0]["tables"]), 2)

    def test_tables_split_per_table_with_flag(self):
        tables = [
            {'id': 'table_0', 'title': '', 'data': {'headers': [], 'rows': []}, 'description': 'T1'},
            {'id': 'table_1', 'title': '', 'data': {'headers': [], 'rows': []}, 'description': 'T2'},
        ]
        doc = {"id": "test", "metadata": {}}
        result = self.builder._build_structured_document(
            doc, ["text"], [""], [{}], "", tables,
            split_oversized=True
        )
        table_sections = [s for s in result["sections"] if "tables" in s]
        self.assertEqual(len(table_sections), 2)
        for ts in table_sections:
            self.assertEqual(len(ts["tables"]), 1)


class TestSplitTable(unittest.TestCase):
    """Tests for table splitting."""

    def test_small_table_not_split(self):
        table = {
            'id': 'table_0',
            'title': 'Small table',
            'data': {
                'headers': [[{'text_value': 'Col1'}, {'text_value': 'Col2'}]],
                'rows': [[{'text_value': 'a'}, {'text_value': 'b'}]] * 5
            },
            'description': 'A small table'
        }
        result = DocumentBuilder._split_table_if_needed(table)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], table)

    def test_large_table_split_by_rows(self):
        row = [{'text_value': 'CVE-2024-12345'}, {'text_value': 'Critical'},
               {'text_value': 'Buffer overflow in component'}, {'text_value': '9.8'}]
        table = {
            'id': 'table_0',
            'title': 'CVE Table',
            'data': {
                'headers': [[{'text_value': 'CVE'}, {'text_value': 'Severity'},
                             {'text_value': 'Description'}, {'text_value': 'Score'}]],
                'rows': [row] * 500
            },
            'description': 'CVE listing'
        }
        result = DocumentBuilder._split_table_if_needed(table)
        self.assertGreater(len(result), 1)
        total_rows = sum(len(t['data']['rows']) for t in result)
        self.assertEqual(total_rows, 500)
        for t in result:
            self.assertEqual(t['data']['headers'], table['data']['headers'])

    def test_all_chunks_have_description(self):
        row = [{'text_value': 'CVE-2024-12345'}, {'text_value': 'Critical'},
               {'text_value': 'Buffer overflow in component'}, {'text_value': '9.8'}]
        table = {
            'id': 'table_0',
            'title': 'CVE Table',
            'data': {
                'headers': [[{'text_value': 'CVE'}, {'text_value': 'Severity'},
                             {'text_value': 'Description'}, {'text_value': 'Score'}]],
                'rows': [row] * 500
            },
            'description': 'CVE listing'
        }
        result = DocumentBuilder._split_table_if_needed(table)
        self.assertGreater(len(result), 1)
        for t in result:
            self.assertEqual(t['description'], 'CVE listing')


    def test_uneven_rows_all_chunks_under_limit(self):
        import json
        small_row = [{'text_value': 'CVE-2024-00001'}, {'text_value': 'Low'}]
        huge_row = [{'text_value': ', '.join(f'CVE-2024-{i:05d}' for i in range(1200))},
                    {'text_value': 'Critical'}]
        table = {
            'id': 'table_0',
            'title': 'Mixed CVE Table',
            'data': {
                'headers': [[{'text_value': 'CVEs'}, {'text_value': 'Severity'}]],
                'rows': [small_row] * 3 + [huge_row] + [small_row] * 3
            },
            'description': 'Mixed size rows'
        }
        result = DocumentBuilder._split_table_if_needed(table)
        self.assertGreater(len(result), 1)
        for t in result:
            chunk_size = len(json.dumps(t['data']))
            self.assertLessEqual(chunk_size, MAX_SECTION_CHARS,
                                 f"Chunk has {len(t['data']['rows'])} rows, {chunk_size} chars")

    def test_oversized_row_split(self):
        import json
        huge_row = [{'text_value': 'A' * 20000}, {'text_value': 'Critical'}]
        result = DocumentBuilder._split_oversized_row(huge_row, 12800)
        self.assertGreater(len(result), 1)
        for row in result:
            self.assertEqual(len(row), 2)
        self.assertEqual(result[0][1]['text_value'], 'Critical')
        self.assertEqual(result[1][1]['text_value'], '')


if __name__ == "__main__":
    unittest.main()
