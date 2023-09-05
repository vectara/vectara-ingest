import logging
import json
import urllib.parse
import time
from datetime import datetime, timedelta  
from mwviews.api import PageviewsClient

from core.crawler import Crawler
from core.utils import create_session_with_retries

class MediawikiCrawler(Crawler):

    def crawl(self) -> None:
        api_url = self.cfg.mediawiki_crawler.api_url
        project = self.cfg.mediawiki_crawler.project
        n_pages = self.cfg.mediawiki_crawler.n_pages
        session = create_session_with_retries()
        if n_pages > 1000:
            n_pages = 1000
            logging.info(f"n_pages is too large, setting to 1000")
        metrics_date = datetime.now() - timedelta(days=7)

        # Get most viewed pages
        p = PageviewsClient(user_agent="crawler@example.com")
        year, month, day = metrics_date.strftime("%Y-%m-%d").split("-")
        titles = [v['article'] for v in p.top_articles(project, limit=n_pages, year=year, month=month, day=day)]
        logging.info(f"indexing {len(titles)} top titles from {project}")

        # Process the pages in batches
        for title in titles:
            time.sleep(1)
            params = {'action': 'query', 'prop': 'info|revisions', 'titles': title, 'inprop': 'url', 'rvprop': 'timestamp', 'format': 'json'}
            response = session.get(api_url, params=params).json()
            page_id = list(response['query']['pages'].keys())[0]
            if int(page_id) <= 0:
                continue
            page_url = response['query']['pages'][page_id]['fullurl']
            last_revision = response['query']['pages'][page_id]['revisions'][0]
            last_editor = last_revision.get('user', 'unknown')
            last_edited_at = last_revision['timestamp']

            params = {'action': 'query', 'prop': 'extracts', 'titles': title, 'format': 'json', 'explaintext': 1}
            response = session.get(api_url, params=params).json()
            page_id = list(response["query"]["pages"].keys())[0]
            page_content = response["query"]["pages"][page_id]["extract"]

            if page_content is None or len(page_content) < 3:
                continue                    # skip pages without content

            logging.info(f"Indexing page with {title}: url={page_url}")

            # Index the page into Vectara
            document = {
                "documentId": title,
                "title": title,
                "description": "",
                "metadataJson": json.dumps({
                    "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}",
                    "last_edit_time": last_edited_at,
                    "last_edit_user": last_editor,
                    "source": "mediawiki",
                }),
                "section": [
                    {
                        "text": page_content,
                    }
                ]
            }
            succeeded = self.indexer.index_document(document)
            if not succeeded:
                logging.info(f"Failed to index page {page_id}: url={page_url}, title={title}")
