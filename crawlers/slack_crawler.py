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
    return datetime.datetime.fromtimestamp(float(epoch_time)).strftime('%Y-%m-%d %H:%M:%S')


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


class SlackCrawler(Crawler):
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str):
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.user_token = self.cfg.slack_crawler.slack_user_token
        self.client = WebClient(token=self.user_token)
        self.days_past = self.cfg.slack_crawler.get("days_past", None)
        self.channels_to_skip = self.cfg.slack_crawler.get("channels_to_skip", [])
        self.connection_retries = self.cfg.slack_crawlers.get("connection_retries", 5)

    def get_users_info(self):
        """
        Returns the list of the users of the workspace.
        API docs: https://api.slack.com/methods/users.list
        """
        try:
            for _ in range(self.connection_retries):
                try:
                    users_info = {}
                    users_response = self.client.users_list()
                    users = users_response["members"]
                    for user in users:
                        users_info[user["id"]] = user["profile"]["display_name_normalized"]

                    return users_info
                except IncompleteRead as e:
                    logging.error(f"Error: {e}")
        except KeyError as e:
            logging.error(f"Error while fetching the users info: {e}")

    def get_channels(self):
        """
        Returns the list of the channels of the workspace.
        API docs: https://api.slack.com/methods/conversations.list
        """

        channels = []
        for _ in range(self.connection_retries):
            try:
                for result in self.client.conversations_list():

                    for channel in result["channels"]:
                        channels.append(channel)

                return channels
            except IncompleteRead as e:
                logging.error(f"Error: {e}")

    def get_messages_of_channel(self, channel_id, users_info):
        """
        Retrieves messages of a channel.
        API docs: https://api.slack.com/methods/conversations.history
        :param channel_id:
        :param users_info:
        :return:
        """
        messages = []
        cursor = None
        last_message_timestamp = None
        response = None
        if self.days_past is not None:
            last_message_timestamp = str(get_timestamp(self.days_past))

        while True:
            for _ in range(self.connection_retries):
                try:

                    # limit represent number of messages to return in a request. Default value is 100 and
                    # max is 999. Slack recommends no more than 200 results at a time.
                    # Check API docs for more detail.
                    response = self.client.conversations_history(channel=channel_id, oldest=last_message_timestamp,
                                                                 cursor=cursor,
                                                                 limit=200)
                except IncompleteRead as e:
                    logging.error(f"IncompleteRead error occurred: {e}")

            if response is not None:
                messages += response["messages"]
                # Check if there are more messages to retrieve
                if not response["has_more"]:
                    break
                cursor = response["response_metadata"]["next_cursor"]

        # fetch the threaded messages for each message
        for msg in messages:
            if 'reply_count' in msg:
                replies = self.get_message_replies(channel_id, msg["ts"], users_info)
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
        for _ in range(self.connection_retries):
            try:
                replies_response = self.client.conversations_replies(channel=channel_id, ts=message_ts)
                replies = replies_response["messages"]
                replace_user_id_with_user_handler(replies, users_info)
                return replies
            except IncompleteRead as e:
                logging.error(f"IncompleteRead error occurred: {e}")

    def crawl(self) -> None:
        try:
            users_info = self.get_users_info()
            channels = self.get_channels()
            for channel in channels:
                channel_id = channel["id"]
                if channel["name"] in self.channels_to_skip:
                    continue

                messages = self.get_messages_of_channel(channel_id, users_info)
                for msg in messages:
                    doc_text = msg.get("text", "")
                    doc_id = f'vectara_{channel_id}_{msg["ts"]}'
                    doc_metadata = get_doc_metadata(channel, msg, users_info)

                    sections = []
                    if msg.get("replies_content"):
                        for reply in msg.get("replies_content"):
                            try:
                                sections.append({
                                    "text": reply.get("text"),
                                    "metadata": json.dumps({
                                        "replier": users_info[reply["user"]],
                                        "reply_time": get_datetime_from_epoch(reply["ts"])
                                    })
                                })
                            except KeyError:
                                continue

                    if doc_text is None and msg.get("subtype") == "bot_message":
                        for attachment in msg.get("attachments", []):
                            doc_text = f'{attachment.get("text", "")}\n'

                    document = {
                        "documentId": doc_id,
                        "metadataJson": doc_metadata,
                        "description": doc_text,
                    }
                    if len(sections) > 0:
                        document["sections"] = sections

                    self.indexer.index_document(document)
        except SlackApiError as e:
            logging.error(f"Error: {e}")
