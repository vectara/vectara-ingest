import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Mock cairosvg before it's imported by other modules (same as test_doc_parser.py)
sys.modules.setdefault('cairosvg', MagicMock())

from omegaconf import OmegaConf

from core.doc_parser import DocupandaDocumentParser, LlamaParseDocumentParser


def _make_parser():
    return DocupandaDocumentParser(cfg=OmegaConf.create({}), docupanda_api_key="test-key")


def _response(status_code=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    if json_data is None:
        r.json.side_effect = ValueError("not json")
    else:
        r.json.return_value = json_data
    r.text = text
    return r


class TestDocupandaParser(unittest.TestCase):

    def setUp(self):
        fd, self.filename = tempfile.mkstemp(suffix=".pdf")
        with os.fdopen(fd, "wb") as f:
            f.write(b"fake pdf bytes")

    def tearDown(self):
        os.remove(self.filename)

    def test_post_failure_with_non_json_body_returns_empty_doc(self):
        # Regression: the error path called response.json(), which raises on a
        # non-JSON error body (e.g. an HTML 502 page), masking the real failure.
        parser = _make_parser()
        with patch("core.doc_parser.requests.post",
                   return_value=_response(500, json_data=None, text="Bad Gateway")), \
             patch("core.doc_parser.extract_document_title", return_value="t"):
            result = parser.parse(self.filename)
        self.assertEqual(result.content_stream, [])
        self.assertEqual(result.tables, [])

    def test_polling_non_200_does_not_crash(self):
        # Regression: the polling loop read .json()['status'] without checking
        # the status code, so a transient 5xx raised instead of being retried.
        parser = _make_parser()
        post_resp = _response(200, json_data={"documentId": "d1"})
        poll_resp = _response(503, json_data=None, text="unavailable")
        with patch("core.doc_parser.requests.post", return_value=post_resp), \
             patch("core.doc_parser.requests.get", return_value=poll_resp), \
             patch("core.doc_parser.time.sleep"), \
             patch("core.doc_parser.time.time", side_effect=[0, 0, 0, 61, 61, 61]), \
             patch("core.doc_parser.extract_document_title", return_value="t"):
            result = parser.parse(self.filename)
        self.assertEqual(result.content_stream, [])


class TestLlamaParseImageFolder(unittest.TestCase):

    def test_images_download_to_temp_dir_not_root(self):
        # Regression: images were downloaded to a hardcoded '/images' directory
        # created at the filesystem root and never cleaned up.
        fd, filename = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            with patch("core.doc_parser.LlamaParse"):
                parser = LlamaParseDocumentParser(
                    cfg=OmegaConf.create({}), llama_parse_api_key="k",
                    summarize_images=True)
            parser.parser.get_json_result.return_value = [{"pages": []}]
            parser.parser.get_images.return_value = []

            with patch("core.doc_parser.extract_document_title", return_value="t"):
                parser.parse(filename)

            download_path = parser.parser.get_images.call_args.kwargs["download_path"]
            self.assertNotEqual(download_path, "/images")
        finally:
            os.remove(filename)


if __name__ == "__main__":
    unittest.main()
