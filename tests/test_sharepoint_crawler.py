import sys
import importlib.machinery
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

# office365 is not installed in the test env; the except clause needs a real
# exception class, not a MagicMock attribute.
class _ClientRequestException(Exception):
    pass


_o365_exc = MagicMock()
_o365_exc.ClientRequestException = _ClientRequestException
sys.modules.setdefault("office365", MagicMock())
sys.modules.setdefault("office365.runtime", MagicMock())
sys.modules.setdefault("office365.runtime.client_request_exception", _o365_exc)
sys.modules.setdefault("office365.sharepoint", MagicMock())
sys.modules.setdefault("office365.sharepoint.client_context", MagicMock())

from crawlers.sharepoint_crawler import SharepointCrawler


def _make_self(retry_attempts=3, retry_delay=0, auto_refresh_session=True):
    cfg_values = {
        "retry_attempts": retry_attempts,
        "retry_delay": retry_delay,
        "auto_refresh_session": auto_refresh_session,
    }
    return SimpleNamespace(
        cfg=SimpleNamespace(
            sharepoint_crawler=SimpleNamespace(
                get=lambda key, default=None: cfg_values.get(key, default))),
        refresh_sharepoint_session=MagicMock(),
    )


def _failing_func(error):
    func = MagicMock()
    func.execute_query.side_effect = error
    return func


class TestExecuteWithRetry(unittest.TestCase):
    # Regression: a 401 on the last attempt (or any 401 with auto-refresh
    # disabled) was swallowed — execute_with_retry implicitly returned None
    # instead of raising, so persistent auth failures looked like successful
    # crawls with empty results.

    def test_success_returns_result(self):
        fake_self = _make_self()
        func = MagicMock()
        func.execute_query.return_value = "result"
        self.assertEqual(SharepointCrawler.execute_with_retry(fake_self, func), "result")
        self.assertEqual(func.execute_query.call_count, 1)

    def test_persistent_401_raises_instead_of_returning_none(self):
        fake_self = _make_self()
        error = Exception("401 Client Error: Unauthorized")
        func = _failing_func(error)
        with self.assertRaises(Exception) as ctx:
            SharepointCrawler.execute_with_retry(fake_self, func)
        self.assertIs(ctx.exception, error)
        self.assertEqual(func.execute_query.call_count, 3)

    def test_persistent_401_with_auto_refresh_disabled_raises(self):
        fake_self = _make_self(auto_refresh_session=False)
        func = _failing_func(Exception("401 unauthorized"))
        with self.assertRaises(Exception):
            SharepointCrawler.execute_with_retry(fake_self, func)
        fake_self.refresh_sharepoint_session.assert_not_called()

    def test_401_refresh_then_success(self):
        fake_self = _make_self()
        func = MagicMock()
        func.execute_query.side_effect = [Exception("401 unauthorized"), "result"]
        self.assertEqual(SharepointCrawler.execute_with_retry(fake_self, func), "result")
        fake_self.refresh_sharepoint_session.assert_called_once()

    def test_non_401_error_still_raises_after_retries(self):
        fake_self = _make_self()
        error = Exception("503 Service Unavailable")
        func = _failing_func(error)
        with self.assertRaises(Exception) as ctx:
            SharepointCrawler.execute_with_retry(fake_self, func)
        self.assertIs(ctx.exception, error)
        self.assertEqual(func.execute_query.call_count, 3)

    def test_401_attempts_sleep_between_retries(self):
        # Regression: the 401 branch retried with no backoff at all.
        fake_self = _make_self(retry_delay=5)
        func = _failing_func(Exception("401 unauthorized"))
        with patch("crawlers.sharepoint_crawler.time.sleep") as mock_sleep:
            with self.assertRaises(Exception):
                SharepointCrawler.execute_with_retry(fake_self, func)
        # 3 attempts -> 2 sleeps between them
        self.assertEqual(mock_sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
