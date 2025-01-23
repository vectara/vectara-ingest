import logging
import os.path

from furl import furl

from core.crawler import Crawler
from core.utils import create_session_with_retries
import json

class ConfluenceCrawler(Crawler):

    def copy_properties(self, source, target, properties):
        for property in properties:
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


    def append_content(self, document, page_data):
        section = None
        if 'body' in page_data:
            if 'anonymous_export_view' in page_data['body']:
                section =  {
                    'title': 'Contents',
                    'text': page_data['body']['anonymous_export_view']['value'],
                    'metadata': {
                        'representation': page_data['body']['anonymous_export_view']['representation']
                    }
                }

        if section != None:
            document['sections'].append(section)


    def raise_for_status(self, response):
        if response.status_code == 400:
            logging.error(f"Bad Request: \n {response.json()}")
        response.raise_for_status()


    def new_url(self, /, *paths):
        result = self.base_url.copy()
        for p in paths:
            result.path = os.path.join(str(result.path), str(p))
        return result



    def process_page(self, id, document):
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
        self.append_labels(document['metadata'], confluence_page_data)
        self.append_links(document['metadata'], confluence_page_data)
        self.append_users(document['metadata'], confluence_page_data)
        self.append_content(document, confluence_page_data)
        self.copy_properties(confluence_page_data, document['metadata'], ['title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType'])

    def process_blogpost(self, id, document):
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
        self.append_labels(document['metadata'], confluence_page_data)
        self.append_links(document['metadata'], confluence_page_data)
        self.append_users(document['metadata'], confluence_page_data)
        self.append_content(document, confluence_page_data)
        self.copy_properties(confluence_page_data, document['metadata'], ['title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType'])


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
                document = {
                    'id': id,
                    'sections': [],
                    'metadata': {}
                }

                if search_result['type'] == 'page':
                    self.process_page(id, document)
                elif search_result['type'] == 'blogpost':
                    self.process_blogpost(id, document)
                else:
                    logging.error(f"Unsupported type: {search_result['type']} id: {search_result['id']}")

                succeeded = self.indexer.index_document(document)

                if succeeded:
                    logging.info(f"Indexed page {document['id']}")
                    count+=1
                else:
                    logging.info(f"Error indexing issue {document['id']}")

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


