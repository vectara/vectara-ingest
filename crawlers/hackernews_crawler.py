
import requests
import logging
from core.crawler import Crawler
import os
from slugify import slugify         # type: ignore
from core.utils import html_to_text

def get_comments(kids, entrypoint):
    comments = []
    for kid in kids:
        try:
            response = requests.get(entrypoint + 'item/{}.json'.format(kid))
            comment = response.json()
        except Exception as e:
            logging.info(f"Error retrieving comment {kid}, e={e}")
            comment = None
        if comment is not None and comment.get('type', '') == 'comment':
            comments.append(html_to_text(comment.get('text', '')))
            sub_kids = comment.get('kids', [])
            if len(sub_kids)>0:
                comments += get_comments(sub_kids, entrypoint)
    return comments

class HackernewsCrawler(Crawler):

    def crawl(self):
        N_ARTICLES = self.cfg.hackernews_crawler.max_articles

        # URL for the Hacker News API
        entrypoint = 'https://hacker-news.firebaseio.com/v0/'

        # Retrieve the IDs of the top N_ARTICLES stories
        resp1= requests.get(entrypoint + 'topstories.json')
        resp2 = requests.get(entrypoint + 'newstories.json')
        resp3 = requests.get(entrypoint + 'beststories.json')

        top_ids = list(set(list(resp1.json()) + list(resp2.json()) + list(resp3.json())))[:N_ARTICLES]
        num_ids = len(top_ids)
        logging.info(f"Crawling {num_ids} stories")

        # Retrieve the details of each story
        for n_id, id in enumerate(top_ids):
            if n_id % 20 == 0:
                logging.info(f"Crawled {n_id} stories so far")
            try:
                response = requests.get(entrypoint + 'item/{}.json'.format(id))
                story = response.json()
                url = story.get('url', None)
                if url is None:
                    continue
                title = html_to_text(story.get('title', ''))
                text = story.get('text', None)
                if text:
                    fname = slugify(url) + ".html"
                    with open(fname, 'w') as f:
                        f.write(text)
                    self.indexer.index_file(fname, uri=url, metadata={'title': title})
                    os.remove(fname)
                else:
                    metadata = {'source': 'hackernews', 'title': title}
                    self.indexer.index_url(url, metadata=metadata)
            except Exception as e:
                import traceback
                logging.error(f"Error crawling story {url}, error={e}, traceback={traceback.format_exc()}")
