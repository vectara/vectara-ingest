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
        self.assertEqual(len(chunks), 4)
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
    """Tests for auto-splitting in _build_structured_document."""

    def setUp(self):
        self.builder = DocumentBuilder({})

    def test_small_section_not_split(self):
        doc = {"id": "test", "metadata": {}}
        result = self.builder._build_structured_document(
            doc, ["short text"], ["title"], [{}], "Doc", []
        )
        self.assertEqual(len(result["sections"]), 1)
        self.assertEqual(result["sections"][0]["text"], "short text")

    def test_large_section_auto_split(self):
        doc = {"id": "test", "metadata": {}}
        big_text = "word " * 5000  # ~25000 chars
        result = self.builder._build_structured_document(
            doc, [big_text], ["title"], [{}], "Doc", []
        )
        self.assertGreater(len(result["sections"]), 1)
        self.assertTrue(all(len(s["text"]) <= MAX_SECTION_CHARS for s in result["sections"]))
        for s in result["sections"]:
            self.assertEqual(s["title"], "title")
            self.assertEqual(s["metadata"], {})


if __name__ == "__main__":
    unittest.main()
