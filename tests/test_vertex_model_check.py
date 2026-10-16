"""Vertex AI has no API key: the model-dependency check must not disable table summaries,
contextual chunking and metadata extraction when the provider is `vertex`.

get_api_key() returns None for `vertex` by design (it uses project_id/location and a
credentials file). Indexer._validate_model_dependencies treated that None as "no model" and
switched the features off at start-up with "model API key not found".
"""
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from omegaconf import OmegaConf

from core.indexer import Indexer


def _cfg(provider, **doc_processing):
    model = {'provider': provider, 'model_name': 'm'}
    if provider == 'vertex':
        model.update({'project_id': 'p', 'location': 'global', 'credentials_file': '/tmp/sa.json'})
    return OmegaConf.create({
        'vectara': {'verbose': False},
        'crawling': {'crawler_type': 'test'},
        'doc_processing': {'model_config': {'text': model, 'vision': model}, **doc_processing},
    })


def _indexer(cfg):
    return Indexer(cfg, api_url="https://api.example.test", corpus_key="c", api_key="k")


class TestVertexModelCheck(unittest.TestCase):

    def test_vertex_keeps_table_parsing(self):
        ix = _indexer(_cfg('vertex', parse_tables=True, process_locally=True))
        self.assertTrue(ix.parse_tables)

    def test_vertex_keeps_contextual_chunking_and_image_summaries(self):
        ix = _indexer(_cfg('vertex', contextual_chunking=True, summarize_images=True))
        self.assertTrue(ix.contextual_chunking)
        self.assertTrue(ix.summarize_images)

    def test_keyless_openai_still_disables_table_parsing(self):
        ix = _indexer(_cfg('openai', parse_tables=True, process_locally=True))
        self.assertFalse(ix.parse_tables)

    def test_model_available_helper(self):
        cfg = _cfg('vertex')
        self.assertTrue(Indexer._model_available({'provider': 'vertex'}, cfg))
        self.assertFalse(Indexer._model_available({'provider': 'openai'}, cfg))
        self.assertFalse(Indexer._model_available({}, cfg))
        self.assertFalse(Indexer._model_available(None, cfg))


if __name__ == '__main__':
    unittest.main()
