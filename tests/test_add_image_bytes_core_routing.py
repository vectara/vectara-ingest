"""Regression tests: add_image_bytes must produce *core* documents, not structured.

Binary image data (the `images` / `document_parts` fields) is only valid on Vectara
v2 *core* documents. When `add_image_bytes` is enabled, image-bearing documents were
being sent to the *structured* endpoint, which rejects the payload with
``UnrecognizedPropertyException: Unrecognized field "images"`` — a 400 that silently
dropped the whole document (text + images). See the three fixes in core/indexer.py:

  * Fix 1 - index_segments forces core when it attaches image bytes.
  * Fix 2 - __init__ defaults docling chunking to 'hierarchical' under add_image_bytes,
            which (via _is_chunking_enabled) auto-enables core indexing.
  * Fix 3 - index_url routes image-bearing web pages through the local docling parser
            (index_file) instead of the always-structured inline path.
"""
import json
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from omegaconf import OmegaConf

from core.document_builder import MAX_PART_SIZE
from core.indexer import Indexer


def _base_cfg(doc_processing: dict) -> OmegaConf:
    return OmegaConf.create({
        'vectara': {'verbose': False},
        'crawling': {'crawler_type': 'test'},
        'doc_processing': doc_processing,
    })


class TestFix2ChunkingDefault(unittest.TestCase):
    """add_image_bytes + docling + chunking 'none' -> forced to 'hierarchical' + core."""

    def test_defaults_to_hierarchical_and_enables_core(self):
        cfg = _base_cfg({
            'doc_parser': 'docling',
            'add_image_bytes': True,
            'summarize_images': False,
            'docling_config': {'chunking_strategy': 'none'},
        })
        ix = Indexer(cfg, api_url="https://api.example.test", corpus_key="c", api_key="k")

        self.assertEqual(ix.docling_config['chunking_strategy'], 'hierarchical')
        self.assertTrue(ix.use_core_indexing)
        # The shared cfg must be updated too, so the lazily-built FileProcessor
        # (which reads cfg.doc_processing.docling_config) sees the same value.
        self.assertEqual(cfg.doc_processing.docling_config.chunking_strategy, 'hierarchical')

    def test_explicit_strategy_is_not_overridden(self):
        cfg = _base_cfg({
            'doc_parser': 'docling',
            'add_image_bytes': True,
            'docling_config': {'chunking_strategy': 'hybrid', 'chunk_size': 512},
        })
        ix = Indexer(cfg, api_url="https://api.example.test", corpus_key="c", api_key="k")
        self.assertEqual(ix.docling_config['chunking_strategy'], 'hybrid')

    def test_other_docling_keys_are_preserved(self):
        # Defaulting chunking_strategy must not drop unrelated user-set docling keys.
        cfg = _base_cfg({
            'doc_parser': 'docling',
            'add_image_bytes': True,
            'docling_config': {'chunking_strategy': 'none', 'image_scale': 3,
                               'do_formula_enrichment': True},
        })
        ix = Indexer(cfg, api_url="https://api.example.test", corpus_key="c", api_key="k")
        self.assertEqual(ix.docling_config['chunking_strategy'], 'hierarchical')
        self.assertEqual(ix.docling_config['image_scale'], 3)
        self.assertTrue(ix.docling_config['do_formula_enrichment'])
        # The shared cfg (read by the lazily-built FileProcessor) keeps them too.
        self.assertEqual(cfg.doc_processing.docling_config.image_scale, 3)
        self.assertTrue(cfg.doc_processing.docling_config.do_formula_enrichment)

    def test_no_change_without_add_image_bytes(self):
        cfg = _base_cfg({
            'doc_parser': 'docling',
            'add_image_bytes': False,
            'docling_config': {'chunking_strategy': 'none'},
        })
        ix = Indexer(cfg, api_url="https://api.example.test", corpus_key="c", api_key="k")
        self.assertEqual(ix.docling_config['chunking_strategy'], 'none')
        self.assertFalse(ix.use_core_indexing)


class TestFix1IndexSegmentsForcesCore(unittest.TestCase):
    """index_segments must POST type=core (not structured) when it attaches images."""

    def _make_indexer(self):
        ix = Indexer.__new__(Indexer)
        ix.api_url = "https://api.example.test"
        ix.corpus_key = "c"
        ix.api_key = "k"
        ix.x_source = "vectara-ingest-test"
        ix.cfg = _base_cfg({})
        ix.session = MagicMock()
        ix.verbose = False
        ix.store_docs = False
        ix.reindex = False
        ix.incremental = False
        ix.static_metadata = None
        ix.add_image_bytes = True
        # Instance flag deliberately False: prove the per-call decision alone flips
        # the document to core purely because image bytes were attached.
        ix.use_core_indexing = False
        ix._init_processors = MagicMock()
        return ix

    def test_image_bytes_document_is_posted_as_core(self):
        ix = self._make_indexer()
        posted = MagicMock()
        posted.status_code = 201
        ix.session.post.return_value = posted

        image_id = "web_page_image_0"
        ok = ix.index_segments(
            doc_id="doc1",
            texts=["a picture of a cat"],
            metadatas=[{'element_type': 'image', 'image_id': image_id}],
            doc_metadata={'url': 'https://example.test/p'},
            doc_title="Page",
            image_bytes=[(image_id, b"\x89PNG\r\n\x1a\n stub bytes")],
        )

        self.assertTrue(ok)
        ix.session.post.assert_called_once()
        body = json.loads(ix.session.post.call_args.kwargs['data'])
        self.assertEqual(body['type'], 'core')
        self.assertIn('images', body)
        self.assertEqual(body['images'][0]['id'], image_id)
        # Must be built in *core* shape — not a structured/core mongrel. The API
        # rejects a core doc that still carries the structured-only 'title'/'sections'
        # ("body.title Unknown property"), so those must be absent and document_parts
        # present.
        self.assertIn('document_parts', body)
        self.assertNotIn('sections', body)
        self.assertNotIn('title', body)

    def test_oversized_text_part_is_split_in_core_image_doc(self):
        # A large text element must be split to stay under the core part-size limit,
        # just like _build_core_document does. The image-attach path used to overwrite
        # the split parts with unsplit ones -> "Document part text is too large" 400.
        ix = self._make_indexer()
        posted = MagicMock()
        posted.status_code = 201
        ix.session.post.return_value = posted

        image_id = "web_page_image_0"
        ok = ix.index_segments(
            doc_id="doc1",
            texts=["a" * (MAX_PART_SIZE + 5000), "a picture of a cat"],
            metadatas=[
                {'element_type': 'text'},
                {'element_type': 'image', 'image_id': image_id},
            ],
            doc_metadata={'url': 'https://example.test/p'},
            doc_title="Page",
            image_bytes=[(image_id, b"\x89PNG\r\n\x1a\n stub bytes")],
        )

        self.assertTrue(ok)
        body = json.loads(ix.session.post.call_args.kwargs['data'])
        self.assertEqual(body['type'], 'core')
        # Every part must be within the core size limit.
        for part in body['document_parts']:
            self.assertLessEqual(len(part['text']), MAX_PART_SIZE)
        # The big text was actually split into multiple parts.
        self.assertGreater(len(body['document_parts']), 2)
        # The image part still carries its image_id and the image is attached.
        self.assertTrue(any(p.get('image_id') == image_id for p in body['document_parts']))
        self.assertEqual(body['images'][0]['id'], image_id)


class TestFix3WebRouting(unittest.TestCase):
    """index_url routes image-bearing pages through index_file (docling), and stays
    on the fast web path when there are no images to attach."""

    def _make_indexer(self, res):
        ix = Indexer.__new__(Indexer)
        ix.cfg = _base_cfg({})
        ix.incremental = False
        ix.add_image_bytes = True
        ix.summarize_images = True
        ix.process_locally = False
        ix.remove_boilerplate = False
        ix.parse_tables = False
        ix.remove_code = True
        ix.detected_language = 'en'
        ix.extract_metadata = []
        ix.timeout = 90
        ix.last_skip_reason = None
        ix.verbose = False
        ix.model_config = MagicMock()
        ix.file_processor = MagicMock()
        ix.file_processor.inline_images = True
        ix.url_triggers_download = MagicMock(return_value=False)
        ix.check_download_or_pdf = MagicMock(return_value={"type": "page"})
        ix.fetch_page_contents = MagicMock(return_value=res)
        ix.index_file = MagicMock(return_value=True)
        ix.index_segments = MagicMock(return_value=True)
        return ix

    def test_page_with_images_routes_to_index_file(self):
        res = {
            'html': '<html><body><p>hi</p><img src="a.png"></body></html>',
            'text': 'hi there this is a page',
            'title': 'T',
            'url': 'https://example.test/p',
            'images': [{'src': 'https://example.test/a.png', 'alt': ''}],
        }
        ix = self._make_indexer(res)

        ix.index_url('https://example.test/p', metadata={'url': 'https://example.test/p'})

        ix.index_file.assert_called_once()
        self.assertIn('extra_image_urls', ix.index_file.call_args.kwargs)
        self.assertEqual(ix.index_file.call_args.kwargs['extra_image_urls'], res['images'])
        # Must force local processing: the source URI has no file extension, so
        # index_file's should_process_locally() heuristic would otherwise send the
        # temp .html down the raw upload path and drop the image bytes.
        self.assertTrue(ix.index_file.call_args.kwargs.get('force_local_processing'))
        ix.index_segments.assert_not_called()

    def test_page_without_images_stays_on_web_path(self):
        res = {
            'html': '<html><body><p>hi</p></body></html>',
            'text': 'hi there this is a page',
            'title': 'T',
            'url': 'https://example.test/p',
            # no 'images' key -> nothing to attach -> must not route to index_file
        }
        ix = self._make_indexer(res)

        ix.index_url('https://example.test/p', metadata={'url': 'https://example.test/p'})

        ix.index_file.assert_not_called()
        ix.index_segments.assert_called_once()


if __name__ == "__main__":
    unittest.main()
