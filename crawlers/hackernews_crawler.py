
import json
from omegaconf import OmegaConf
import logging
from core.crawler import Crawler
from core.utils import html_to_text, create_session_with_retries
import datetime
from typing import List

class HackernewsCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.N_ARTICLES = self.cfg.hackernews_crawler.max_articles
        self.days_back = self.cfg.hackernews_crawler.get("days_back", 3)
        self.indexer.reindex = True     # always reindex with hackernews, since it depends on comments
        self.db_url = 'https://hacker-news.firebaseio.com/v0/'
        self.session = create_session_with_retries()

    def get_comments(self, story: dict) -> List[str]:
        comments = []
        kids = [str(k) for k in story.get('kids', [])]
        for kid in kids:
            try:
                response = self.session.get(self.db_url + 'item/{}.json'.format(kid))
                comment = response.json()
            except Exception as e:
                logging.info(f"Error retrieving comment {kid}, e={e}")
                comment = None
            if comment is not None and comment.get('type', '') == 'comment':
                comments.append(comment)
                comments += self.get_comments(comment)
        return comments

    def index_story(self, id: str) -> None:
        url = f'https://news.ycombinator.com/item?id={id}'
        story = self.session.get(self.db_url + 'item/{}.json'.format(id)).json()
        doc_id = str(story['id'])
        doc_title = html_to_text(story.get('title', ''))
        doc_text = html_to_text(story.get('text', ''))
        doc_metadata = {'source': 'hackernews', 'title': doc_title, 'url': url}
        texts = [] if len(doc_text) == 0 else [doc_text]
        titles = ['']
        times = [datetime.datetime.fromtimestamp(story.get('time', 0)).date()]
        comments = self.get_comments(story)
        for comment in comments:
            texts.append(html_to_text(comment.get('text', '')))
            titles.append(html_to_text(comment.get('title', '')))
            times.append(datetime.datetime.fromtimestamp(comment.get('time', 0)).date())
        
        # if most recent comment is older than days_back, don't index
        if max(times) < datetime.datetime.now().date() - datetime.timedelta(days=self.days_back):
            logging.info(f"Skipping story {id} because most recent comment is older than {self.days_back} days")
            return
            
        self.indexer.index_segments(doc_id=doc_id, 
                                    texts=texts, titles=titles, metadatas=None,
                                    doc_metadata=doc_metadata, doc_title=doc_title)

    def crawl(self) -> None:
        # Retrieve the IDs of the top N_ARTICLES stories
        resp1= self.session.get(self.db_url + 'topstories.json')
        resp2 = self.session.get(self.db_url + 'newstories.json')
        resp3 = self.session.get(self.db_url + 'beststories.json')
        top_ids = list(set(list(resp1.json()) + list(resp2.json()) + list(resp3.json())))[:self.N_ARTICLES]
        num_ids = len(top_ids)
        logging.info(f"Crawling {num_ids} stories")

        # Retrieve the details of each story
        for n_id, id in enumerate(top_ids):
            if n_id % 20 == 0:
                logging.info(f"Crawled {n_id} stories so far")
            try:
                self.index_story(str(id))
            except Exception as e:
                import traceback
                logging.error(f"Error crawling story {id}, error={e}, traceback={traceback.format_exc()}")
