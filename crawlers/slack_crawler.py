import time
import re
import json
import logging
import datetime
from omegaconf import OmegaConf
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from http.client import IncompleteRead
from core.crawler import Crawler


def get_timestamp(days_past):
    """
    Creates an epoch time from a datetime. Subtract the days past fom the current datetime
    and calculate the epoch time stamp
    Checkout slack docs for more information: https://api.slack.com/messaging/retrieving
    :param days_past: up to how many number of days messages should be fetched
    :return:
    """
    # return the epoch timestamp by subtracting the days_past from current data
    current_date = datetime.datetime.now()
    # Subtract number of days
    previous_date = current_date - datetime.timedelta(days=days_past)
    previous_date = previous_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get epoch time of previous date
    epoch_time = int(previous_date.timestamp())
    return epoch_time


def construct_url_of_message(message, channel_id):
    """
    Creates a link for of Slack message based on the channel id and message timestamp
    :param message: a Slack message
    :param channel_id: ID of the channel where message was sent
    :return:
    """
    timestamp = message["ts"]
    message_link = f"https://vectara.slack.com/archives/{channel_id}/p{timestamp}"
    return message_link


def get_datetime_from_epoch(epoch_time):
    """
    Message timestamp[ts] is an epoch time that we convert to datatime format.
    Example:
        input: 123456789
        output: 2021-07-27 15:00:00
    :param epoch_time: timestamp of a message.
    """
    return datetime.datetime.fromtimestamp(float(epoch_time)).strftime('%Y-%m-%d %H:%M')


def get_doc_metadata(channel, message, users_info):
    """
    Creates a metadata for the document that would be indexed in the vectara.

    Example output: {
        "channel": "development",
        "author": "vectara",
        "message_time": "2021-07-27 15:00:00",
        "url": https://vectara.slack.com/archives/12345/p12345678,
        "latest_reply": "2021-07-27 15:00:00",
        "no_of_users_involved": 3
        }

    :param channel: contains a list of channels
    :param message: Slack message
    :param users_info: list of slack users for a workspace
    :return:
    """
    metadata = {}
    try:
        metadata.update({
            "source": "slack",
            "channel": channel["name"],
            "author": users_info.get(message.get("user"), "bot"),
            "message_time": get_datetime_from_epoch(message["ts"]),
            "url": construct_url_of_message(message, channel["id"])
        })
        if message.get("latest_reply"):
            metadata["latest_reply_time"] = get_datetime_from_epoch(message["latest_reply"])
        if message.get("reply_users_count"):
            metadata["no_of_users_involved"] = message["reply_users_count"]
    except KeyError as e:
        logging.error(f"Error while creating the metadata: {e}")

    return json.dumps(metadata)


def replace_user_id_with_user_handler(messages, users_info):
    """
    Replace user id's with user handlers in the  Slack messages.

    Example:
    <@U01A9GZQ3LZ> posted about GenAI.
    Output would be, @vectara posted about the GenAI
    :param messages: list of a Slack channel  messages
    :param users_info: list of slack users for a workspace
    """
    try:
        for message in messages:
            text = message.get("text", "")
            # Replace user IDs with usernames if mentioned in the message
            if "<@" in text:
                for uid in users_info:
                    if uid in text:
                        username = users_info[uid]
                        text = text.replace(f"<@{uid}>", f"@{username}")
                        message["text"] = text
    except KeyError as e:
        logging.error(f"Error replacing user id's with user handlers: {e}")


def get_document(channel, message, users_info):
    """
    Returns the document to indexed in vectara

    Example output : {
        "documentId": "vectara_123_1234556",
        "metadataJson": {"author": "Vectara"},
        "section": [{"text": "Slack messages info"},
        {"text": "Messages has replies", "metadata": "{"author": "Vectara"}"}]
    }

   To create a unique doc id workspace name, channel id and message timestamp are being used.
   Because slack claims the message timestamp with in a channel would be unique.
   Docs: https://api.slack.com/messaging/retrieving

    :param channel:
    :param message:
    :param users_info:
    :return:
    """

    doc_text = message.get("text", '')
    doc_id = f'vectara_{channel["id"]}_{message["ts"]}'
    message_date = datetime.datetime.fromtimestamp(float(message["ts"])).strftime('%Y-%m-%d')
    title = f'{users_info.get(message.get("user"), "bot")}@{channel["name"]} - {message_date}'
    doc_metadata = get_doc_metadata(channel, message, users_info)
    sections = []

    if doc_text == '':
        if message.get("subtype") == "bot_message":
            previous_messages = []  # using to avoid appending duplicate messages in the document
            for attachment in message.get("attachments", []):
                doc_text = f'{attachment.get("text", "")}\n'
                if doc_text not in previous_messages:
                    sections.append({"text": doc_text})
                    previous_messages.append(doc_text)

        else:
            return None
    else:
        sections.append({"text": doc_text})
        if message.get("replies_content"):
            for reply in message.get("replies_content"):
                try:
                    sections.append({
                        "text": reply.get("text"),
                        "metadataJson": json.dumps({
                            "replier": users_info[reply["user"]],
                            "reply_time": get_datetime_from_epoch(reply["ts"])
                        })
                    })
                except KeyError:
                    continue

    return {
        "documentId": doc_id,
        "title": title,
        "metadataJson": doc_metadata,
        "section": sections
    }


def handle_ratelimit_error(api_name, error, retry_delay=60):
    logging.error(f"rate limit error occurred: {error}")
    logging.info(f"Will retry to fetch the {api_name} after 60 seconds")
    time.sleep(retry_delay)  # wait for 60 seconds before sending another request


def handle_incomplete_request_error(api_name, error, retry_delay=30):
    logging.error(f"IncompleteRead error occurred: {error}")
    logging.info(f"Will retry to fetch the {api_name} after 30 seconds")
    time.sleep(retry_delay)  # wait for 30 seconds before sending another request


def replace_ampersand(message):
    if "&amp;" in message:
        text = message.get("text").replace("&amp;", "&")
        message["text"] = text


def remove_duplicate_urls(message):
    """
    Slack messages show urls multiple times in the text, so we are removing duplicates
    to make the text cleaner.
    Example:
        input text:  Apple &amp; Grok LLM news, plus this knowledge processing unit (KPU) thing.
        \n<https://x.com/rowancheung/status/1769509530776338895?s=46
        |https://x.com/rowancheung/status/1769509530776338895?s=46>

        output text:  Apple &amp; Grok LLM news, plus this knowledge processing unit (KPU) thing.
        \n<https://x.com/rowancheung/status/1769509530776338895?s=46>

    :return:
    """
    for attachment in message.get('attachments', []):
        if attachment.get("original_url", None):
            url = attachment["original_url"]
            message["text"] = message["text"].replace(f"|{url}", "")


def contains_url(message):
    # Regular expression pattern to match URLs
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    # Search for URLs in the message
    match = re.search(url_pattern, message)
    # Return True if a URL is found, False otherwise
    return bool(match)


class SlackCrawler(Crawler):
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str):
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.user_token = self.cfg.slack_crawler.slack_user_token
        self.client = WebClient(token=self.user_token)
        self.days_past = self.cfg.slack_crawler.get("days_past", None)
        self.channels_to_skip = self.cfg.slack_crawler.get("channels_to_skip", [])
        self.retries = self.cfg.slack_crawler.get("retries", 5)

    def get_users_info(self):
        """
        Returns the list of the users of the workspace.
        API docs: https://api.slack.com/methods/users.list
        """
        for _ in range(self.retries):
            try:
                users_info = {}
                users_response = self.client.users_list()
                users = users_response["members"]
                for user in users:
                    users_info[user["id"]] = user["profile"]["display_name_normalized"]

                logging.info("Users information retrieved")
                return users_info

            except IncompleteRead as e:
                handle_incomplete_request_error("users", e)

            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    handle_ratelimit_error("users", e)
                else:
                    logging.error(f"Error while fetching the users: {e}")

            except KeyError as e:
                logging.error(f"Error while fetching the users info: {e}")

    def get_channels(self):
        """
        Returns the list of the channels of the workspace.
        API docs: https://api.slack.com/methods/conversations.list
        """

        channels = []
        for _ in range(self.retries):
            try:
                for result in self.client.conversations_list():

                    for channel in result["channels"]:
                        channels.append(channel)

                logging.info("channels retrieved")
                return channels

            except IncompleteRead as e:
                handle_incomplete_request_error("channels", e)

            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    handle_ratelimit_error("channels", e)
                else:
                    logging.error(f"Error while fetching the messages: {e}")

    def get_messages_of_channel(self, channel, users_info):
        """
        Retrieves messages of a channel.
        API docs: https://api.slack.com/methods/conversations.history
        :param channel: channel to retrieve messages
        :param users_info: users information
        :return:
        """
        messages = []
        cursor = None
        last_message_timestamp = None
        response = None
        if self.days_past is not None:
            last_message_timestamp = str(get_timestamp(self.days_past))

        while True:
            for _ in range(self.retries):
                try:

                    # limit represent number of messages to return in a request. Default value is 100 and
                    # max is 999. Slack recommends no more than 200 results at a time.
                    # Check API docs for more detail.
                    response = self.client.conversations_history(channel=channel["id"], oldest=last_message_timestamp,
                                                                 cursor=cursor,
                                                                 limit=200)
                except IncompleteRead as e:
                    handle_incomplete_request_error("messages", e)

                except SlackApiError as e:
                    if e.response["error"] == "ratelimited":
                        handle_ratelimit_error("messages", e)
                    else:
                        logging.error(f"Error while fetching the messages: {e}")

            if response is not None:
                messages += response["messages"]
                # Check if there are more messages to retrieve
                if not response["has_more"]:
                    break
                cursor = response["response_metadata"]["next_cursor"]

        logging.info(f"messages fetched successfully for channel `{channel['name']}`")

        # fetch the threaded messages for each message
        for msg in messages:
            replace_ampersand(msg)
            if contains_url(msg.get("text")):
                remove_duplicate_urls(msg)
            if 'reply_count' in msg:
                replies = self.get_message_replies(channel["id"], msg["ts"], users_info)
                msg["replies_content"] = replies

        replace_user_id_with_user_handler(messages, users_info)

        return messages

    def get_message_replies(self, channel_id, message_ts, users_info):
        """
        Slack provides a separate API to get the replies of a message.
        Call the replies API and return the replies/threaded message.
        API docs: https://api.slack.com/methods/conversations.replies
        :param channel_id: ID of a channel
        :param message_ts: timestamp of a message
        :param users_info: list of Slack users
        :return:
        """
        for _ in range(self.retries):
            try:
                replies_response = self.client.conversations_replies(channel=channel_id, ts=message_ts)
                replies = replies_response["messages"][1:]  # skipping the 1st message since it's a parent message
                replace_user_id_with_user_handler(replies, users_info)
                return replies

            except IncompleteRead as e:
                handle_incomplete_request_error("threaded messages", e)

            except SlackApiError as e:
                if e.response["error"] == "ratelimited":
                    handle_ratelimit_error("threaded messages", e)
                else:
                    logging.error(f"Error while fetching the threaded messages: {e}")

    def crawl(self) -> None:
        """
        crawl the Slack messages in the following sequence.
        Retrieve all the users and their information.
        Retrieve all channels and their messages.
        Construct document that we are going to index in vectara

        :return:
        """
        users_info = self.get_users_info()
        channels = self.get_channels()

        for channel in channels:
            channel_id = channel["id"]
            if channel["name"] in self.channels_to_skip:
                continue

            messages = self.get_messages_of_channel(channel, users_info)
            for msg in messages:
                document = get_document(channel, msg, users_info)
                if document is not None:
                    self.indexer.index_document(document)
                else:
                    link = construct_url_of_message(msg, channel_id)
                    logging.info(f"Unable to find  text fot the message: {link}")
