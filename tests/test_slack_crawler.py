import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock

# Mock only third-party deps that may be missing in the test env (same pattern
# as test_wolken_crawler.py). `nbconvert` calls find_spec("playwright") at
# import time, so the playwright mock needs a real ModuleSpec.
for mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(mod, MagicMock())
_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from slack_sdk.errors import SlackApiError

from crawlers.slack_crawler import SlackCrawler


CHANNEL = {"id": "C1", "name": "general"}


def _api_error():
    """A SlackApiError whose status is not 429, so retry handling doesn't sleep."""
    response = MagicMock()
    response.status_code = 500
    return SlackApiError("boom", response)


def _make_crawler(retries=2):
    crawler = SlackCrawler.__new__(SlackCrawler)
    crawler.client = MagicMock()
    crawler.retries = retries
    crawler.days_past = None
    crawler.channels_to_skip = []
    crawler.workspace_url = "https://example.slack.com"
    return crawler


class TestGetMessagesOfChannel(unittest.TestCase):

    def test_success_makes_one_api_call_per_page(self):
        # Regression: the retry loop used to call the API self.retries times
        # per page even when the first call succeeded.
        crawler = _make_crawler(retries=5)
        page1 = {"messages": [{"text": "m1", "ts": "1"}], "has_more": True,
                 "response_metadata": {"next_cursor": "cur1"}}
        page2 = {"messages": [{"text": "m2", "ts": "2"}], "has_more": False}
        crawler.client.conversations_history.side_effect = [page1, page2]

        messages = crawler.get_messages_of_channel(CHANNEL, {})

        self.assertEqual(crawler.client.conversations_history.call_count, 2)
        self.assertEqual([m["text"] for m in messages], ["m1", "m2"])

    def test_persistent_failure_terminates_without_hanging(self):
        # Regression: when every attempt failed, `while True` used to spin forever.
        crawler = _make_crawler(retries=3)
        crawler.client.conversations_history.side_effect = _api_error()

        messages = crawler.get_messages_of_channel(CHANNEL, {})

        self.assertEqual(messages, [])
        self.assertEqual(crawler.client.conversations_history.call_count, 3)

    def test_later_page_failure_does_not_duplicate_messages(self):
        # Regression: when page 2 failed, the stale page-1 response was
        # re-appended on every loop iteration.
        crawler = _make_crawler(retries=2)
        page1 = {"messages": [{"text": "m1", "ts": "1"}], "has_more": True,
                 "response_metadata": {"next_cursor": "cur1"}}
        crawler.client.conversations_history.side_effect = [
            page1, _api_error(), _api_error()]

        messages = crawler.get_messages_of_channel(CHANNEL, {})

        self.assertEqual([m["text"] for m in messages], ["m1"])


class TestRetryExhaustion(unittest.TestCase):
    # Regression: these methods used to return implicit None when all retries
    # failed, crashing callers that iterate or call .get() on the result.

    def test_get_channels_returns_empty_list(self):
        crawler = _make_crawler(retries=2)
        crawler.client.conversations_list.side_effect = _api_error()
        self.assertEqual(crawler.get_channels(), [])
        self.assertEqual(crawler.client.conversations_list.call_count, 2)

    def test_get_users_info_returns_empty_dict(self):
        crawler = _make_crawler(retries=2)
        crawler.client.users_list.side_effect = _api_error()
        self.assertEqual(crawler.get_users_info(), {})

    def test_get_message_replies_returns_empty_list(self):
        crawler = _make_crawler(retries=2)
        crawler.client.conversations_replies.side_effect = _api_error()
        self.assertEqual(crawler.get_message_replies("C1", "1", {}), [])


if __name__ == "__main__":
    unittest.main()
