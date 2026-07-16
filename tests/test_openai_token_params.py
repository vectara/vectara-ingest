"""Regression tests for OpenAI token/temperature parameter selection.

GPT-5 series and o-series reasoning models reject `max_tokens` (they require
`max_completion_tokens`) and reject a non-default `temperature`. Older models
(gpt-4o, gpt-4.1) require the classic `max_tokens` + `temperature=0`. The helper
`_openai_token_params` in core/models.py picks the right kwargs by model name.
"""
import unittest

from core.models import _openai_token_params


class TestOpenAITokenParams(unittest.TestCase):
    def test_new_models_use_max_completion_tokens_and_omit_temperature(self):
        for name in [
            "gpt-5.4-mini", "gpt-5", "GPT-5.4-Mini",
            "o1", "o1-mini", "o3", "o3-mini", "o4-mini",
        ]:
            with self.subTest(model=name):
                params = _openai_token_params(name, 1234)
                self.assertEqual(params, {"max_completion_tokens": 1234})
                self.assertNotIn("temperature", params)
                self.assertNotIn("max_tokens", params)

    def test_legacy_models_use_max_tokens_and_temperature_zero(self):
        for name in ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "gpt-4-turbo"]:
            with self.subTest(model=name):
                params = _openai_token_params(name, 2048)
                self.assertEqual(params, {"max_tokens": 2048, "temperature": 0})
                self.assertNotIn("max_completion_tokens", params)


if __name__ == "__main__":
    unittest.main()
