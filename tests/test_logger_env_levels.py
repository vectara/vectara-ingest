"""LOGGER_<NAME>_LEVEL must be able to name any logger and must reach the output."""

import io
import logging
import os
import unittest
from unittest.mock import patch

from core.utils import setup_logging


class TestLoggerEnvLevels(unittest.TestCase):

    def setUp(self):
        root = logging.getLogger()
        saved = (root.handlers[:], root.level)
        root.handlers[:] = []

        def restore():
            root.handlers[:] = saved[0]
            root.setLevel(saved[1])

        self.addCleanup(restore)

    def _setup(self, **env):
        with patch.dict(os.environ, env):
            setup_logging()
        for name in ("core.indexer", "core.web_content_extractor"):
            self.addCleanup(logging.getLogger(name).setLevel, logging.NOTSET)

    def test_single_underscore_is_a_dot(self):
        self._setup(LOGGER_CORE_INDEXER_LEVEL="DEBUG")
        self.assertEqual(logging.getLogger("core.indexer").level, logging.DEBUG)

    def test_double_underscore_is_a_literal_underscore(self):
        self._setup(LOGGER_CORE_WEB__CONTENT__EXTRACTOR_LEVEL="DEBUG")
        self.assertEqual(logging.getLogger("core.web_content_extractor").level, logging.DEBUG)

    def test_logger_override_reaches_the_handler_while_root_stays_info(self):
        self._setup(LOGGER_CORE_INDEXER_LEVEL="DEBUG")
        stream = io.StringIO()
        handler = logging.getLogger().handlers[0]
        handler.setStream(stream)
        logging.getLogger("core.indexer").debug("wanted")
        logging.getLogger("core.other").debug("unwanted")
        self.assertIn("wanted", stream.getvalue())
        self.assertNotIn("unwanted", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
