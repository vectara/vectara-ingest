import json
import logging
import datetime
from omegaconf import OmegaConf
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from http.client import IncompleteRead
from core.crawler import Crawler


def get_timestamp(days_past):
    # return the epoch timestamp by subtracting the days_past from current data
    current_date = datetime.datetime.now()
    # Subtract number of days
    previous_date = current_date - datetime.timedelta(days=days_past)
    previous_date = previous_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Get epoch time of previous date
    epoch_time = int(previous_date.timestamp())
    return epoch_time


def construct_url_of_message(message, channel_id):
    timestamp = message["ts"]
    message_link = f"https://vectara.slack.com/archives/{channel_id}/p{timestamp}"
    return message_link


def get_datetime_from_epoch(epoch_time):
    return datetime.datetime.fromtimestamp(float(epoch_time)).strftime('%Y-%m-%d %H:%M:%S')


def get_doc_metadata(channel, message, users_info):
    metadata = {
        "channel": channel["name"],
        "author": users_info.get(message.get("user"), "bot"),
        "message_time": get_datetime_from_epoch(message["ts"]),
        "url": construct_url_of_message(message, channel["id"])
    }
    if message.get("latest_reply"):
        metadata["latest_reply_time"] = get_datetime_from_epoch(message["latest_reply"])
    if message.get("reply_users_count"):
        metadata["no_of_users_involved"] = message["reply_users_count"]

    return json.dumps(metadata)


def replace_user_id_with_user_handler(messages, users_info):
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
    except SlackApiError as e:
        logging.error(f"Error replacing user id's with user handlers: {e}")


class SlackCrawler(Crawler):
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str):
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.user_token = self.cfg.slack_crawler.slack_user_token
        self.client = WebClient(token=self.user_token)
        self.days_past = self.cfg.slack_crawler.days_past
        self.channels_to_skip = self.cfg.slack_crawler.channels_to_skip

    def get_users_info(self):
        while True:
            try:
                users_info = {}
                users_response = self.client.users_list()
                users = users_response["members"]
                for user in users:
                    users_info[user["id"]] = user["profile"]["display_name_normalized"]

                return users_info
            except IncompleteRead as e:
                logging.error(f"Error: {e}")

    def get_channels(self):
        """Returns the list of the channels of the workspace."""

        channels = []
        while True:
            try:
                for result in self.client.conversations_list():

                    for channel in result["channels"]:
                        channels.append(channel)

                return channels
            except IncompleteRead as e:
                logging.error(f"Error: {e}")

    def get_messages_of_channel(self, channel_id, users_info):
        messages = []
        cursor = None
        last_message_timestamp = None
        if self.days_past is not None:
            last_message_timestamp = str(get_timestamp(self.days_past))
        while True:
            try:
                response = self.client.conversations_history(channel=channel_id, oldest=last_message_timestamp,
                                                             cursor=cursor,
                                                             limit=200)
                messages += response["messages"]
                # Check if there are more messages to retrieve
                if not response["has_more"]:
                    break
                cursor = response["response_metadata"]["next_cursor"]
            except IncompleteRead as e:
                logging.error(f"IncompleteRead error occurred: {e}")
            # Retry the request
            continue

        for msg in messages:
            if 'reply_count' in msg:
                replies = self.get_message_replies(channel_id, msg["ts"], users_info)
                msg["replies_content"] = replies

        replace_user_id_with_user_handler(messages, users_info)

        return messages

    def get_message_replies(self, channel_id, message_ts, users_info):
        replies_response = self.client.conversations_replies(channel=channel_id, ts=message_ts)
        replies = replies_response["messages"]
        replace_user_id_with_user_handler(replies, users_info)

        return replies

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
