import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
import json
from core.utils import create_session_with_retries, html_to_text, configure_session_for_ssl
from typing import List, Dict, Any
from datetime import datetime

def datetime_to_date(datetime_str: str) -> str:
    date_obj = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    date_str = date_obj.strftime('%Y-%m-%d')
    return date_str


class DiscourseCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.discourse_base_url = self.cfg.discourse_crawler.base_url
        self.discourse_api_key = self.cfg.discourse_crawler.discourse_api_key
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.discourse_crawler)

    # function to fetch the topics from the Discourse API
    def get_topics(self) -> List[Dict[str, Any]]:
        url = self.discourse_base_url + '/latest.json'
        topics = []
        params = { 'api_key': self.discourse_api_key, 'api_username': 'ofer@vectara.com', 'page': '0'}
        page = 0
        while True:
            response = self.session.get(url, params=params)
            if response.status_code != 200:
                raise Exception(f'Failed to fetch topics from Discourse, exception = {response.status_code}, {response.text}')
            new_topics = list(json.loads(response.text)['topic_list']['topics'])
            if len(new_topics) == 0:
                break
            topics += new_topics
            page += 1
            params['page'] = str(page)

        return topics

    # function to fetch the posts for a topic from the Discourse API
    def index_posts(self, topic: Dict[str, Any]) -> List[Any]:
        topic_id = topic["id"]
        url_json = self.discourse_base_url + '/t/' + str(topic_id) + '.json'
        params = { 'api_key': self.discourse_api_key, 'api_username': 'ofer@vectara.com'}
        response = self.session.get(url_json, params=params)
        if response.status_code != 200:
            raise Exception('Failed to fetch posts for topic ' + str(topic_id) + ' from Discourse')

        # parse the response JSON
        posts = list(json.loads(response.text)['post_stream']['posts'])
        document = {
            'id': 'topic-' + str(topic_id),
            'title': topic['title'],
            'metadata': {
                'created_at': datetime_to_date(topic['created_at']),
                'last_updated': datetime_to_date(topic['last_posted_at']),
                'source': 'discourse',
                'url': self.discourse_base_url + '/t/' + str(topic_id)
            },
            'sections': []
        }
        for post in posts:
            section = {
                'text': html_to_text(post['cooked']),
                'metadata': {
                    'created_at': datetime_to_date(post['created_at']),
                    'last_updated': datetime_to_date(post['updated_at']),
                    'poster': post['username'],
                    'poster_name': post['name'],
                    'source': 'discourse',
                    'url': self.discourse_base_url + '/p/' + str(post['id'])
                },
            }
            if 'title' in post:
                section['title'] = post['title']
            document['sections'].append(section)

        self.indexer.index_document(document)
        return posts

    def crawl(self) -> None:
        topics = self.get_topics()
        logging.info(f"Indexing {len(topics)} topics from Discourse")
        for topic in topics:
            posts = self.index_posts(topic)
            logging.info(f"Indexed {len(posts)} posts for topic {topic['id']} from Discourse")
