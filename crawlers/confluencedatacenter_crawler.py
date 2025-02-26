import json
import logging
from importlib.metadata import metadata

from core.crawler import Crawler
from core.utils import create_session_with_retries
from furl import furl
import os
from requests import Response
import tempfile

class ConfluencedatacenterCrawler(Crawler):



    def new_url(self, /, *paths)-> furl:
        """
        Construct a new URL by copying the base_url and appending additional path segments.

        Args:
            *paths: One or more path segments (strings) to append.

        Returns:
            furl.furl: A new furl object representing the resulting URL.
        """
        result = self.base_url.copy()
        for p in paths:
            result.path = os.path.join(str(result.path), str(p))
        return result

    def process_content(self, content: dict[str, any]) -> None:
        # print(json.dumps(content, indent=4))
        id = content['id']
        type = content['type']
        doc_id = f"{type}-{id}"
        metadata = {
            'type': type,
            'id': id
        }

        url_part = None

        if '_links' in content:
            if type == 'attachment' and 'download' in content['_links']:
                url_part = furl(content['_links']['download'])
            elif 'webui' in content['_links']:
                url_part = furl(content['_links']['webui'])

        if url_part:
            viewer_url = self.new_url(url_part.pathstr)
            for k,v in url_part.args.items():
                viewer_url.args[k] = v
            metadata['url'] = viewer_url.url

        if type == 'attachment':
            supported_extensions = {
                '.pdf', '.md', '.odt', '.doc', '.docx', '.ppt',
                '.pptx', '.txt', '.html', '.htm', '.lxml',
                '.rtf', '.epub'
            }
            title = content['title']
            filename, file_extension = os.path.splitext(title)
            if file_extension not in supported_extensions:
                logging.warning(f"Extension not supported, skipping. '{file_extension}' title:{title}")
                return

            attachment_url = furl(metadata['url'])

            logging.info(f"Downloading Attachment {doc_id} - {attachment_url}")
            download_response = self.session.get(attachment_url.url, headers=self.confluence_headers,
                                                 auth=self.confluence_auth)

            with tempfile.NamedTemporaryFile(suffix=file_extension, mode='wb', delete=False) as f:
                logging.debug(f"Writing content for {doc_id} to {f.name}")
                for chunk in download_response.iter_content(chunk_size=32000):
                    f.write(chunk)
                f.flush()
                f.close()
                try:
                    succeeded = self.indexer.index_file(f.name, attachment_url.url, metadata, doc_id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

                if not succeeded:
                    logging.error(f"Error indexing {doc_id} - {attachment_url}")
        else:
            if 'body' in content:
                if 'storage' in content['body']:
                    body = content['body']['storage']['value']
                    title = content['title']
                    with tempfile.NamedTemporaryFile(suffix=".html", mode='w', delete=False) as f:
                        logging.debug(f"Writing content for {doc_id} to {f.name}")
                        f.write("<html>")
                        if 'title' in content:
                            f.write('<head><title>')
                            f.write(content['title'])
                            f.write('</title></head>')
                        f.write('<body>')
                        f.write(body)
                        f.write('</body>')
                        f.write('</html>')
                        f.flush()
                        f.close()
                        try:
                            succeeded = self.indexer.index_file(f.name, metadata['url'], metadata, doc_id)
                        finally:
                            if os.path.exists(f.name):
                                os.remove(f.name)




    def crawl(self) -> None:
        self.base_url = furl(self.cfg.confluencedatacenter.base_url)
        logging.info(f"Starting base_url = '{self.base_url}'")
        self.confluence_headers = {"Accept": "application/json"}
        self.confluence_auth = (
            self.cfg.confluencedatacenter.confluence_datacenter_username,
            self.cfg.confluencedatacenter.confluence_datacenter_password
        )
        self.session = create_session_with_retries()
        limit = int(self.cfg.confluencedatacenter.get('limit', '25'))
        start = 0
        search_url = self.new_url('rest/api/content/search')
        search_url.args['cql'] = self.cfg.confluencedatacenter.confluence_cql
        search_url.args['expand'] = "body.storage"
        search_url.args['limit'] = limit

        logging.info(f"Searching Confluence {search_url.url}")

        while True:
            search_url.args['start'] = start
            start += limit
            search_url_response = self.session.get(search_url.url, headers=self.confluence_headers,
                                                        auth=self.confluence_auth)
            if search_url_response.status_code == 500:
                logging.warning("500 returned by rest api. This could be due to a mismatch with the space name in your query.")
            search_url_response.raise_for_status()
            search_url_data = search_url_response.json()

            search_results = search_url_data['results']


            for search_result in search_results:
                if 'content' in search_result:
                    self.process_content(search_result['content'])
                else:
                    self.process_content(search_result)

            if '_links' in search_url_data:
                if not 'next' in search_url_data['_links']:
                    break
                else:
                    logging.debug("next not found in _links, going again.")
            else:
                logging.warning("_links was not found in the response. Exiting so we don't sit in a loop.")
                break








