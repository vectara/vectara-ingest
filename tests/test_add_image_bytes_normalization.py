"""Regression: the add_image_bytes path must normalize text/metadata like DocumentBuilder.

When add_image_bytes attaches binary image data it rebuilds `document_parts` (and the
image `description`) from the raw `texts`/`metadatas` passed to index_segments, bypassing
DocumentBuilder._build_core_document's normalize_text/normalize_value. That produced parts
whose text was not Unicode-normalized (NFD) and, when cfg.vectara.mask_pii is on, not masked
— inconsistent with every other core document. These tests pin the normalization.

NFD is used as the observable, dependency-free normalization: normalize_text always applies
unicodedata.normalize('NFD', ...) regardless of mask_pii, so a composed 'é' (U+00E9) must
come out decomposed as 'e' + U+0301.
"""
import json
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from omegaconf import OmegaConf

from core.indexer import Indexer

COMPOSED = "caf\u00e9"      # 'café' with a single composed é (U+00E9)
DECOMPOSED = "cafe\u0301"    # NFD: 'cafe' + combining acute accent (U+0301)


def _cfg() -> OmegaConf:
    return OmegaConf.create({
        'vectara': {'verbose': False},
        'crawling': {'crawler_type': 'test'},
        'doc_processing': {},
    })


def _make_indexer() -> Indexer:
    ix = Indexer.__new__(Indexer)
    ix.api_url = "https://api.example.test"
    ix.corpus_key = "c"
    ix.api_key = "k"
    ix.x_source = "vectara-ingest-test"
    ix.cfg = _cfg()
    ix.session = MagicMock()
    ix.verbose = False
    ix.store_docs = False
    ix.reindex = False
    ix.incremental = False
    ix.static_metadata = None
    ix.add_image_bytes = True
    ix.use_core_indexing = False
    ix._init_processors = MagicMock()
    posted = MagicMock()
    posted.status_code = 201
    ix.session.post.return_value = posted
    return ix


class TestAddImageBytesNormalization(unittest.TestCase):
    def _index(self, texts, metadatas, image_bytes):
        ix = _make_indexer()
        ok = ix.index_segments(
            doc_id="doc1",
            texts=texts,
            metadatas=metadatas,
            doc_metadata={'url': 'https://example.test/p'},
            doc_title="Page",
            image_bytes=image_bytes,
        )
        self.assertTrue(ok)
        return json.loads(ix.session.post.call_args.kwargs['data'])

    def test_image_part_and_description_are_normalized(self):
        image_id = "web_page_image_0"
        body = self._index(
            texts=[COMPOSED],
            metadatas=[{'element_type': 'image', 'image_id': image_id}],
            image_bytes=[(image_id, b"\x89PNG\r\n\x1a\n stub bytes")],
        )
        self.assertEqual(body['type'], 'core')
        image_part = next(p for p in body['document_parts'] if p.get('image_id') == image_id)
        self.assertEqual(image_part['text'], DECOMPOSED)
        self.assertEqual(body['images'][0]['description'], DECOMPOSED)

    def test_plain_text_part_is_normalized(self):
        image_id = "web_page_image_0"
        body = self._index(
            texts=[COMPOSED, "a picture"],
            metadatas=[
                {'element_type': 'text'},
                {'element_type': 'image', 'image_id': image_id},
            ],
            image_bytes=[(image_id, b"\x89PNG\r\n\x1a\n stub bytes")],
        )
        text_part = next(p for p in body['document_parts']
                         if p.get('metadata', {}).get('element_type') == 'text')
        self.assertEqual(text_part['text'], DECOMPOSED)

    def test_metadata_values_are_normalized(self):
        image_id = "web_page_image_0"
        body = self._index(
            texts=["a picture"],
            metadatas=[{'element_type': 'image', 'image_id': image_id, 'alt_text': COMPOSED}],
            image_bytes=[(image_id, b"\x89PNG\r\n\x1a\n stub bytes")],
        )
        image_part = next(p for p in body['document_parts'] if p.get('image_id') == image_id)
        self.assertEqual(image_part['metadata']['alt_text'], DECOMPOSED)


if __name__ == "__main__":
    unittest.main()
