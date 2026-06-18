import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

from core.contextual import ContextualChunker


class TestContextualChunker(unittest.TestCase):

    def setUp(self):
        self.chunker = ContextualChunker(OmegaConf.create({}), {}, "the whole document")

    def test_transform_appends_context(self):
        with patch("core.contextual.generate", return_value="some context"):
            self.assertEqual(self.chunker.transform("chunk text"),
                             "chunk text\nsome context")

    def test_transform_failure_returns_original_chunk(self):
        # Regression: transform used to return "" on failure, silently
        # discarding the entire chunk text.
        with patch("core.contextual.generate", side_effect=RuntimeError("llm down")):
            self.assertEqual(self.chunker.transform("chunk text"), "chunk text")

    def test_parallel_transform_failure_keeps_original_text(self):
        def fake_generate(cfg, system_prompt, prompt, model_cfg):
            if "bad chunk" in prompt:
                raise RuntimeError("llm down")
            return "ctx"

        with patch("core.contextual.generate", side_effect=fake_generate):
            results = self.chunker.parallel_transform(["good chunk", "bad chunk"])

        self.assertEqual(results, ["good chunk\nctx", "bad chunk"])

    def test_parallel_transform_replaces_none_results(self):
        # Regression: a future that raised used to leave None in the results list.
        with patch.object(ContextualChunker, "transform", side_effect=RuntimeError("boom")):
            results = self.chunker.parallel_transform(["a", "b"])

        self.assertEqual(results, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
