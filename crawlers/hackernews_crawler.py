
import json
from omegaconf import OmegaConf
import logging
from core.crawler import Crawler
from core.utils import html_to_text, create_session_with_retries, configure_session_for_ssl
import datetime
from typing import List

class HackernewsCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.N_ARTICLES = self.cfg.hackernews_crawler.max_articles
        self.days_back = self.cfg.hackernews_crawler.get("days_back", 3)
        self.days_back_comprehensive = self.cfg.hackernews_crawler.get("days_back_comprehensive", False)
        self.indexer.reindex = True     # always reindex with hackernews, since it depends on comments
        self.db_url = 'https://hacker-news.firebaseio.com/v0/'
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.hackernews_crawler)

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
            if comment is not None and comment.get('type', '') == 'comment' and not comment.get('dead', False):
                comments.append(comment)
                comments += self.get_comments(comment)
        return comments

    def index_story(self, id: str) -> None:
        url = f'https://news.ycombinator.com/item?id={id}'
        story = self.session.get(self.db_url + 'item/{}.json'.format(id)).json()
        doc_id = 'hn_story_' + str(story['id'])
        doc_title = html_to_text(story.get('title', ''))
        doc_text = html_to_text(story.get('text', ''))
        story_date = datetime.datetime.fromtimestamp(story['time']).strftime('%Y-%m-%d')
        doc_metadata = {'source': 'hackernews', 'title': doc_title, 'url': url, 
                        'story_url': story.get('url', ''), 'date': story_date, 'by': story.get('by', '')}

        texts = []
        titles = []
        times = []
        metadatas = []
        if len(doc_text) > 0:
            texts = [doc_text]
            titles = [doc_title]
            times = [datetime.datetime.fromtimestamp(story.get('time', 0)).date()]
            metadatas.append({})
        
        comments = self.get_comments(story)
        for comment in comments:
            texts.append(html_to_text(comment.get('text', '')))
            titles.append(html_to_text(comment.get('title', '')))
            comment_date = datetime.datetime.fromtimestamp(comment.get('time', 0)).date()
            comment_author = comment.get('by', '')
            times.append(comment_date)
            metadatas.append({'by': comment_author, 'date': comment_date.strftime('%Y-%m-%d'), 
                              'url': url + f'#{comment["id"]}'})

        # if most recent comment is older than days_back, don't index
        if len(times)>0 and max(times) < datetime.datetime.now().date() - datetime.timedelta(days=self.days_back):
            logging.info(f"Skipping story {id} from date {story_date} because most recent comment is older than {self.days_back} days")
            return
            
        if len(texts) == 0:
            if self.verbose:
                logging.info(f"Skipping story {id} from date {story_date} because it has no text")
            return
        
        self.indexer.index_segments(doc_id=doc_id, 
                                    texts=texts, titles=titles, metadatas=metadatas,
                                    doc_metadata=doc_metadata, doc_title=None)

    def fetch_stories_before_n_days(self, days: int = 7):
        # Find the current highest item ID
        max_item_response = self.session.get("https://hacker-news.firebaseio.com/v0/maxitem.json")
        max_item_id = max_item_response.json()

        # Calculate the cutoff timestamp
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        logging.info(f"Fetching stories from the last {days} days, cutoff date is {cutoff_date.date()}")
        
        # List to hold IDs of stories before and up to N days ago
        stories_ids = []
        
        # Iterate backwards from the current highest ID
        for inx, item_id in enumerate(range(max_item_id, 0, -1)):
            item_response = self.session.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json")
            item = item_response.json()
            if item is None:
                continue
            item_date = datetime.datetime.fromtimestamp(item.get("time"))
            if inx % 100 == 0:
                logging.info(f"Checked {inx} items so far, latest item with date {item_date.strftime('%Y-%m-%d')}")

            # Check if item is a story and was published within the desired time frame
            if item and item.get("type") == "story":
                if item_date >= cutoff_date:
                    stories_ids.append(item_id)
                else:
                    # Once you reach an item older than the desired range, break the loop
                    break                    
        return stories_ids

    def crawl(self) -> None:
        # Retrieve the IDs of the top N_ARTICLES stories
        resp1 = self.session.get(self.db_url + 'topstories.json')
        resp2 = self.session.get(self.db_url + 'newstories.json')
        resp3 = self.session.get(self.db_url + 'beststories.json')
        resp4 = self.session.get(self.db_url + 'showstories.json')
        resp5 = self.session.get(self.db_url + 'askstories.json')
        stories_by_list = list(set(list(resp1.json()) + list(resp2.json()) + list(resp3.json()) + 
                           list(resp4.json()) + list(resp5.json())))
        logging.info(f"Retrieved {len(stories_by_list)} top, new, best, show, and ask stories")
        self.verbose = self.cfg.vectara.get("verbose", False)

        if self.days_back_comprehensive:
            stories_by_date = self.fetch_stories_before_n_days(self.days_back)
            logging.info(f"Retrieved {len(stories_by_date)} stories from the last {self.days_back} days")
        else:
            stories_by_date = []

        top_ids = list(set(list(stories_by_list) + list(stories_by_date)))[:self.N_ARTICLES]
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
