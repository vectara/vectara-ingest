import unittest
import os
import yaml
import logging
from core.utils import load_config
from core.config_schema import check_config

test_config_directories = [
    'config',
    'config-private'
]



logger = logging.getLogger(__name__)


class TestStructuredConfig(unittest.TestCase):
    pass

def create_test_method(filepath):
    def test_method(self):
        config = load_config(filepath)
        logger.info(f"Loaded config: {config}")
        # Add assertions here based on the loaded config
        # For now, just assert that the config is not empty
        self.assertIsNotNone(config)
        check_config(config)

    return test_method

for test_directory in test_config_directories:
    if os.path.exists(test_directory):
        for filename in os.listdir(test_directory):
            if filename.endswith(('.yml', '.yaml')):
                filepath = os.path.join(test_directory, filename)
                test_name = f"test_config_{os.path.splitext(filename)[0]}"
                setattr(TestStructuredConfig, test_name, create_test_method(filepath))
