import logging
import requests
from core.crawler import Crawler
from omegaconf import OmegaConf
import requests
import json
from html.parser import HTMLParser
from io import StringIO
from core.utils import create_session_with_retries

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = StringIO()
    def handle_data(self, d):
        self.text.write(d)
    def get_data(self):
        return self.text.getvalue()

def strip_html(text: str):
    """
    Strip HTML tags from text
    """
    s = MLStripper()
    s.feed(text)
    return s.get_data()

class DiscourseCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.discourse_base_url = self.cfg.discourse_crawler.base_url
        self.discourse_api_key = self.cfg.discourse_crawler.discourse_api_key
        self.session = create_session_with_retries()

    # function to fetch the topics from the Discourse API
    def index_topics(self):
        url = self.discourse_base_url + '/latest.json'
        params = { 'api_key': self.discourse_api_key, 'api_username': 'ofer@vectara.com', 'page': '0'}
        response = self.session.get(url, params=params)
        if response.status_code != 200:
            raise Exception(f'Failed to fetch topics from Discourse, exception = {response.status_code}, {response.text}')

        # index all topics
        topics = json.loads(response.text)['topic_list']['topics']
        for topic in topics:
            topic_id = topic['id']
            logging.info(f"Indexing topic {topic_id}")
            url = self.discourse_base_url + '/t/' + str(topic_id)
            document = {
                'documentId': 'topic-' + str(topic_id),
                'title': topic['title'],
                'metadataJson': json.dumps({
                    'created_at': topic['created_at'],
                    'views': topic['views'],
                    'like_count': topic['like_count'],
                    'last_poster': topic['last_poster_username'],
                    'source': 'discourse',
                    'url': url
                }),
                'section': [
                    {
                        'text': topic['fancy_title'],
                    }
                ]
            }
            self.indexer.index_document(document)
        return topics

    # function to fetch the posts for a topic from the Discourse API
    def index_posts(self, topic):
        topic_id = topic["id"]
        url_json = self.discourse_base_url + '/t/' + str(topic_id) + '.json'
        params = { 'api_key': self.discourse_api_key, 'api_username': 'ofer@vectara.com'}
        response = self.session.get(url_json, params=params)
        if response.status_code != 200:
            raise Exception('Failed to fetch posts for topic ' + str(topic_id) + ' from Discourse')

        # parse the response JSON
        posts = json.loads(response.text)['post_stream']['posts']
        for post in posts:
            post_id = post['id']
            logging.info(f"Indexing post {post_id}")
            document = {
                'documentId': 'post-' + str(post_id),
                'title': topic['title'],
                'metadataJson': json.dumps({
                    'created_at': post['created_at'],
                    'updated_at': post['updated_at'],
                    'poster': post['username'],
                    'poster_name': post['name'],
                    'source': 'discourse',
                    'url': self.discourse_base_url + '/p/' + str(post_id)
                }),
                'section': [
                    {
                        'text': strip_html(post['cooked'])
                    }
                ]
            }
            self.indexer.index_document(document)
        return posts

    def crawl(self):
        topics = self.index_topics()
        logging.info(f"Indexed {len(topics)} topics from Discourse")
        for topic in topics:
            posts = self.index_posts(topic)
            logging.info(f"Indexed {len(posts)} posts for topic {topic['id']} from Discourse")
