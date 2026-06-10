import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

import ingest


class TestUpdateOmegaConfMasking(unittest.TestCase):
    # Regression: update_omega_conf used to log credential values verbatim at
    # DEBUG level when env vars like HUBSPOT_API_KEY were applied to the config.

    def test_sensitive_values_masked_in_debug_log(self):
        cfg = OmegaConf.create({"hubspot_crawler": {}})
        with self.assertLogs("ingest", level="DEBUG") as cm:
            ingest.update_omega_conf(
                cfg, "env:HUBSPOT_API_KEY",
                "hubspot_crawler.hubspot_api_key", "sk-secret-123")
        log_output = "\n".join(cm.output)
        self.assertNotIn("sk-secret-123", log_output)
        self.assertIn("***", log_output)
        # The config itself must still receive the real value.
        self.assertEqual(cfg.hubspot_crawler.hubspot_api_key, "sk-secret-123")

    def test_password_and_token_keys_masked(self):
        for key in ("jira.password", "github.token", "auth.client_secret"):
            cfg = OmegaConf.create({})
            with self.assertLogs("ingest", level="DEBUG") as cm:
                ingest.update_omega_conf(cfg, "test", key, "hunter2")
            self.assertNotIn("hunter2", "\n".join(cm.output),
                             f"value for {key} leaked into the log")

    def test_non_sensitive_values_still_logged(self):
        cfg = OmegaConf.create({})
        with self.assertLogs("ingest", level="DEBUG") as cm:
            ingest.update_omega_conf(cfg, "test", "crawling.crawler_type", "website")
        self.assertIn("website", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
