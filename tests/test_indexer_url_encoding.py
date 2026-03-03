import unittest
from unittest.mock import patch, MagicMock
from collections import OrderedDict


class TestDocIdUrlEncoding(unittest.TestCase):

    def _make_indexer(self):
        with patch("core.indexer.Indexer.__init__", return_value=None):
            from core.indexer import Indexer
            indexer = Indexer.__new__(Indexer)
            indexer.api_url = "https://api.vectara.io"
            indexer.corpus_key = "test-corpus"
            indexer.api_key = "test-key"
            indexer.x_source = "test"
            indexer.session = MagicMock()
            indexer._doc_exists_cache = OrderedDict()
            indexer._max_cache_size = 1000
            return indexer

    def _get_requested_url(self, indexer):
        return indexer.session.method_calls[-1].args[0]

    def test_delete_plain_id(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("simple-doc")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/simple-doc", url)

    def test_delete_id_with_spaces(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("doc with spaces.pdf")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/doc%20with%20spaces.pdf", url)

    def test_delete_already_encoded_id_no_double_encoding(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("doc%20with%20spaces.pdf")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/doc%20with%20spaces.pdf", url)
        self.assertNotIn("%2520", url)

    def test_delete_double_encoded_id_decodes_one_layer(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("doc%2520with%2520spaces.pdf")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/doc%2520with%2520spaces.pdf", url)

    def test_delete_id_with_slash(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("path/to/doc")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/path%2Fto%2Fdoc", url)

    def test_delete_id_with_literal_plus(self):
        indexer = self._make_indexer()
        indexer.session.delete.return_value = MagicMock(status_code=204)
        indexer.delete_doc("doc+name")
        url = indexer.session.delete.call_args[0][0]
        self.assertIn("/documents/doc%2Bname", url)

    def test_exists_already_encoded_id_no_double_encoding(self):
        indexer = self._make_indexer()
        indexer.session.get.return_value = MagicMock(status_code=200)
        indexer._does_doc_exist("doc%20with%20spaces.pdf")
        url = indexer.session.get.call_args[0][0]
        self.assertIn("/documents/doc%20with%20spaces.pdf", url)
        self.assertNotIn("%2520", url)

    def test_exists_id_with_literal_plus(self):
        indexer = self._make_indexer()
        indexer.session.get.return_value = MagicMock(status_code=200)
        indexer._does_doc_exist("doc+name")
        url = indexer.session.get.call_args[0][0]
        self.assertIn("/documents/doc%2Bname", url)


if __name__ == "__main__":
    unittest.main()
