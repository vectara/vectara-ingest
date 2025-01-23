import logging
import os.path

from furl import furl

from core.crawler import Crawler
from core.utils import create_session_with_retries
import json
import tempfile

class ConfluenceCrawler(Crawler):

    def copy_properties(self, source, target, properties):
        for property in properties:
            if property in source:
                value = source[property]
                if value is not None:
                    target[property] = value

    def append_links(self, metadata, page_data):
        if page_data['_links']:
            links = {}
            for path_name in ['editui', 'webui', 'edituiv2', 'tinyui']:
                path_part = page_data['_links'][path_name]
                base_url = furl(page_data['_links']['base'])
                base_url.path = os.path.join(str(base_url.path), path_part[1:])
                links[path_name] = base_url.url
            metadata['links'] = links

    def append_labels(self, metadata, page_data):
        if 'metadata' in page_data:
            if 'labels' in page_data['metadata']:
                labels = []
                label_names = []
                label_ids = []
                for label in page_data['metadata']['labels']:
                    labels.append(label['label'])
                    label_names.append(label['name'])
                    label_ids.append(label['id'])
                metadata['labels'] = labels
                metadata['label_names'] = label_names
                metadata['label_ids'] = label_names

    # def find_user(self, session, user_cache, user_id):

    def find_users(self, userids):
        result = {}

        users = set()
        for userid in userids:
            if userid in self.user_cache:
                result[userid] = self.user_cache[userid]
            else:
                users.add(userid)

        lookup_body = {
            'accountIds': list(users)
        }

        lookup_url = self.new_url('api/v2/users-bulk')
        headers = self.confluence_headers.copy()
        headers['Content-Type'] = 'application/json'
        users_response = self.session.post(lookup_url.url, headers=headers,
                         auth=self.confluence_auth, data=json.dumps(lookup_body))
        self.raise_for_status(users_response)
        users_data = users_response.json()

        for user_result in users_data['results']:
            self.user_cache[user_result['accountId']] = user_result

        for userid in userids:
            if userid in self.user_cache:
                result[userid] = self.user_cache[userid]
            else:
                logging.warning(f"Could not locate user: {userid}")

        return result

    def append_users(self, metadata, page_data):
        users = set()

        properties = [
            'authorId',
            'lastOwnerId',
            'ownerId'
        ]
        for property in properties:
            if property in page_data:
                value = page_data[property]
                if value is not None:
                    users.add(value)

        user_lookup = self.find_users(users)
        for property in properties:
            if property in page_data:
                value = page_data[property]
                if value is not None:
                    if value in user_lookup:
                        metadata[property] = user_lookup[value]


    def raise_for_status(self, response):
        if response.status_code == 400:
            logging.error(f"Bad Request: \n {response.json()}")
        response.raise_for_status()


    def new_url(self, /, *paths):
        result = self.base_url.copy()
        for p in paths:
            result.path = os.path.join(str(result.path), str(p))
        return result

    def get_content(self, page_data):
        result = None
        if 'body' in page_data:
            if 'anonymous_export_view' in page_data['body']:
                result = page_data['body']['anonymous_export_view']['value']
        return result


    def process_page(self, id, metadata):
        confluence_page_url = self.new_url("api/v2/pages", id)
        confluence_page_url.args['include-labels'] = 'true'
        confluence_page_url.args['include-properties'] = 'true'
        confluence_page_url.args['include-likes'] = 'true'
        confluence_page_url.args['include-operations'] = 'true'
        confluence_page_url.args['include-version'] = 'true'
        confluence_page_url.args['body-format'] = 'anonymous_export_view'
        logging.info(f"Fetching content for {confluence_page_url.url}")
        confluence_page_response = self.session.get(confluence_page_url.url, headers=self.confluence_headers,
                                           auth=self.confluence_auth)
        self.raise_for_status(confluence_page_response)
        confluence_page_data = confluence_page_response.json()
        self.append_labels(metadata, confluence_page_data)
        self.append_links(metadata, confluence_page_data)
        self.append_users(metadata, confluence_page_data)
        self.copy_properties(confluence_page_data, metadata, ['title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType'])
        return self.get_content(confluence_page_data)

    def process_blogpost(self, id, metadata):
        confluence_page_url = self.new_url("api/v2/blogposts", id)
        confluence_page_url.args['include-labels'] = 'true'
        confluence_page_url.args['include-properties'] = 'true'
        confluence_page_url.args['include-likes'] = 'true'
        confluence_page_url.args['include-operations'] = 'true'
        confluence_page_url.args['include-version'] = 'true'
        confluence_page_url.args['body-format'] = 'anonymous_export_view'
        logging.info(f"Fetching content for {confluence_page_url.url}")
        confluence_page_response = self.session.get(confluence_page_url.url, headers=self.confluence_headers,
                                           auth=self.confluence_auth)
        self.raise_for_status(confluence_page_response)
        confluence_page_data = confluence_page_response.json()
        self.append_labels(metadata, confluence_page_data)
        self.append_links(metadata, confluence_page_data)
        self.append_users(metadata, confluence_page_data)
    
        self.copy_properties(confluence_page_data, metadata, ['title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType'])
        return self.get_content(confluence_page_data)

    def process_attachments(self, metadata):
        attachment_url = self.new_url('api/v2', f"{metadata['type']}s", metadata['id'], 'attachments')
        attachment_response = self.session.get(attachment_url.url, headers=self.confluence_headers,
                                               auth=self.confluence_auth)
        self.raise_for_status(attachment_response)
        attachment_data = attachment_response.json()

        supported_extensions = {'.pdf', '.md', '.odt', '.doc', '.docx', '.ppt',
                                '.pptx', '.txt', '.html', '.htm', '.lxml',
                                '.rtf', '.epub'
                                }


        for result in attachment_data['results']:
            title = result['title']
            filename, file_extension = os.path.splitext(title)
            if file_extension not in supported_extensions:
                logging.warning(f"Extension not supported, skipping. '{file_extension}' title:{title}")
                continue
            attachment_metadata={}

            self.copy_properties(result, attachment_metadata, ['title', 'pageId', 'fileId', 'comment', 'mediaType', 'status'])
            id = f"{metadata['id']}/{result['id']}"
            download_stub = furl(result['downloadLink'][1:])
            download_url = self.new_url(download_stub.path)
            self.copy_properties(download_stub.args, download_url.args, ['version', 'modificationDate', 'cacheVersion', 'api'])
            logging.info(f"Downloading Attachment {result['id']} - {download_url.url}")
            download_response = self.session.get(download_url.url, headers=self.confluence_headers,
                                                   auth=self.confluence_auth)
            self.raise_for_status(download_response)
            with tempfile.NamedTemporaryFile(suffix=file_extension, mode='wb', delete=False) as f:
                logging.debug(f"Writing content for {id} to {f.name}")
                for chunk in download_response.iter_content(chunk_size=32000):  # Read in chunks
                    f.write(chunk)
                f.write(download_response.content)
                f.flush()
                f.close()
                try:
                    succeeded = self.indexer.index_file(f.name, download_url.url, attachment_metadata, id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

                if not succeeded:
                    logging.error(f"Error indexing {result['id']} - {download_url.url}")


    def crawl(self) -> None:
        self.confluence_headers = {"Accept": "application/json"}
        self.confluence_auth = (self.cfg.confluence_crawler.confluence_username, self.cfg.confluence_crawler.confluence_password)
        self.session = create_session_with_retries()
        self.base_url = furl(self.cfg.confluence_crawler.confluence_base_url)
        self.user_cache = {}

        confluence_search_url = self.new_url('rest/api/content/search')
        confluence_search_url.args["cql"] = self.cfg.confluence_crawler.confluence_cql

        limit = 25
        confluence_search_url.args['limit'] = limit
        confluence_search_url.args['next'] = 'true'
        count = 0
        while True:
            logging.info(f"Searching Confluence: {confluence_search_url.url}")

            confluence_search_response = self.session.get(confluence_search_url.url, headers=self.confluence_headers,
                                                     auth=self.confluence_auth)
            self.raise_for_status(confluence_search_response)

            confluence_search_data = confluence_search_response.json()

            for search_result in confluence_search_data['results']:
                id = search_result['id']
                metadata = {

                }
                self.copy_properties(search_result, metadata, ['type', 'status', 'id'])
                content = None

                if search_result['type'] == 'page':
                    content = self.process_page(id, metadata)
                elif search_result['type'] == 'blogpost':
                    content = self.process_blogpost(id, metadata)
                else:
                    logging.error(f"Unsupported type: {search_result['type']} id: {search_result['id']}")
                    continue
                    
                if content is None:
                    logging.warning(f"Could not find content for id:{search_result['id']} type:{search_result['type']}")
                    continue

                url = metadata['links']['webui'] if 'links' in metadata and 'webui' in metadata['links'] else id
                with tempfile.NamedTemporaryFile(suffix=".html", mode='w', delete=False) as f:
                    logging.debug(f"Writing content for {id} to {f.name}")
                    f.write(content)
                    f.flush()
                    f.close()
                    try:
                        succeeded = self.indexer.index_file(f.name, url, metadata, id)
                    finally:
                        if os.path.exists(f.name):
                            os.remove(f.name)

                if self.cfg.confluence_crawler.confluence_include_attachments:
                    self.process_attachments(metadata)

                if succeeded:
                    # logging.info(f"Indexed {search_result['type']} {search_result['id']}")
                    count+=1
                else:
                    logging.info(f"Error indexing {search_result['type']} {search_result['id']}")

            if 'next' in confluence_search_data['_links']:
                base_url = furl(confluence_search_data['_links']['base'])
                next_url = furl(confluence_search_data['_links']['next'])
                base_url.path = os.path.join(str(base_url.path), str(next_url.path)[1:])
                base_url.args = next_url.args
                confluence_search_url = base_url
            else:
                logging.debug('No next in _links so exiting')
                break

        logging.info(f"Index {count} item(s)")


