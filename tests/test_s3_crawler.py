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

from crawlers import s3_crawler


def _cfg(**s3_overrides):
    return OmegaConf.create({
        "vectara": {},
        "s3_crawler": s3_overrides,
    })


class TestCreateS3Client(unittest.TestCase):
    """Regression tests for create_s3_client credential handling.

    The crawler previously raised ValueError unless both access key and secret
    were set, which contradicted the documented "boto3 default credential
    chain" fallback (env vars, ~/.aws/credentials, IAM role). These tests pin
    the documented behavior so it does not regress again.
    """

    def test_both_keys_passed_through_explicitly(self):
        with patch.object(s3_crawler.boto3, "client") as mock_client:
            s3_crawler.create_s3_client(_cfg(
                aws_access_key_id="AKIA_TEST",
                aws_secret_access_key="secret_test",
            ))
            _, kwargs = mock_client.call_args
            self.assertEqual(kwargs["aws_access_key_id"], "AKIA_TEST")
            self.assertEqual(kwargs["aws_secret_access_key"], "secret_test")

    def test_no_credentials_defers_to_boto3_chain(self):
        # The crucial regression test: with no creds in config, the client must
        # be created without explicit credential kwargs so boto3 resolves from
        # env vars / shared config / IAM role.
        with patch.object(s3_crawler.boto3, "client") as mock_client:
            s3_crawler.create_s3_client(_cfg())
            _, kwargs = mock_client.call_args
            self.assertNotIn("aws_access_key_id", kwargs)
            self.assertNotIn("aws_secret_access_key", kwargs)

    def test_only_access_key_set_raises(self):
        # Half-configured creds are a user mistake — fail loud with a clear
        # message rather than silently dropping to the boto3 chain.
        with self.assertRaises(ValueError) as ctx:
            s3_crawler.create_s3_client(_cfg(aws_access_key_id="AKIA_TEST"))
        self.assertIn("must be set together", str(ctx.exception))

    def test_only_secret_set_raises(self):
        with self.assertRaises(ValueError) as ctx:
            s3_crawler.create_s3_client(_cfg(aws_secret_access_key="secret_test"))
        self.assertIn("must be set together", str(ctx.exception))

    def test_endpoint_url_passed_through(self):
        with patch.object(s3_crawler.boto3, "client") as mock_client:
            s3_crawler.create_s3_client(_cfg(endpoint_url="https://minio.example.com"))
            _, kwargs = mock_client.call_args
            self.assertEqual(kwargs["endpoint_url"], "https://minio.example.com")


if __name__ == "__main__":
    unittest.main()
