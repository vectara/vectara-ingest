import logging
import time
from datetime import datetime, timedelta
from collections import deque
from urllib.parse import urlparse, unquote, quote
from mwviews.api import PageviewsClient

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl


class MediawikiCrawler(Crawler):
    def crawl(self) -> None:
        api_url = self.cfg.mediawiki_crawler.api_url
        depth = self.cfg.mediawiki_crawler.depth
        source_urls = self.cfg.mediawiki_crawler.source_urls  # List of full wiki URLs
        n_pages = min(self.cfg.mediawiki_crawler.n_pages, 1000)

        session = create_session_with_retries()
        configure_session_for_ssl(session, self.cfg.mediawiki_crawler)

        session.headers.update({
            "User-Agent": "MyCrawler/1.0 (you@example.com)",
            "Authorization": f"Bearer {self.cfg.mediawiki_api_key}"
        })

        # Initialize BFS queue and seen set (track title+domain)
        queue = deque()
        seen = set()
        for url in source_urls:
            parsed = urlparse(url)
            domain = parsed.netloc
            title = unquote(parsed.path.rsplit('/', 1)[-1])
            if title:
                queue.append((title, 0, domain))
                seen.add((title, domain))
        logging.info(f"Starting crawl from {len(source_urls)} sources to depth={depth}, max pages={n_pages}")

        indexed_count = 0
        # Process the queue
        while queue and indexed_count < n_pages:
            title, current_depth, root_domain = queue.popleft()
            time.sleep(1)  # polite crawling

            result = self._fetch_page_and_links(session, api_url, title)
            if result is None:
                continue

            doc, link_titles = result
            page_url = doc['metadata'].get('url', '')
            page_domain = urlparse(page_url).netloc

            # Enforce same-domain restriction
            if page_domain != root_domain:
                logging.debug(f"Skipping {title}: domain {page_domain} != root {root_domain}")
                continue

            # Index the page
            if self.indexer.index_document(doc):
                indexed_count += 1
            else:
                logging.warning(f"Failed to index page {title}")

            logging.info(f"Indexed {page_url} ({indexed_count}/{n_pages})")

            # Enqueue linked pages if within depth
            if current_depth < depth:
                for link in link_titles:
                    if (link, root_domain) not in seen and len(seen) < n_pages:
                        queue.append((link, current_depth + 1, root_domain))
                        seen.add((link, root_domain))

    def _fetch_page_and_links(self, session, api_url: str, title: str):
        
        # 1) Fetch page info, last revision, and extract text
        info_params = {
            'action': 'query',
            'prop': 'info|revisions|extracts',
            'titles': title,
            'inprop': 'url',
            'rvprop': 'timestamp|user',
            'explaintext': 1,
            'format': 'json'
        }
        resp = session.get(api_url, params=info_params).json()
        page = next(iter(resp.get('query', {}).get('pages', {}).values()), None)
        if not page or 'extract' not in page or len(page['extract']) < 10:
            return None

        page_url = page.get('fullurl')
        if 'revisions' not in page or not page['revisions']:  
            revision = page['revisions'][0]
            last_editor = revision.get('user', 'unknown')
            last_edited_at = revision['timestamp']
        else:
            last_editor = 'unknown'
            last_edited_at = page.get('touched', datetime.now().isoformat())

        doc = {
            'id': title,
            'title': title,
            'description': '',
            'metadata': {
                'url': page_url,
                'last_edit_time': last_edited_at,
                'last_edit_user': last_editor,
                'source': 'mediawiki',
            },
            'sections': [{ 'text': page['extract'] }]
        }

        # 2) Fetch linked articles (namespace 0)
        links = []
        plcontinue = None
        while True:
            link_params = {
                'action': 'query',
                'prop': 'links',
                'titles': title,
                'pllimit': 'max',
                'format': 'json'
            }
            if plcontinue:
                link_params['plcontinue'] = plcontinue
            link_resp = session.get(api_url, params=link_params).json()

            pages = link_resp.get('query', {}).get('pages', {})
            page_links = next(iter(pages.values()), {}).get('links', [])
            for l in page_links:
                if l.get('ns') == 0:
                    links.append(l['title'])

            if 'continue' in link_resp:
                plcontinue = link_resp['continue'].get('plcontinue')
            else:
                break

        return doc, links
