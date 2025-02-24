import json
import logging
import os.path
import tempfile

import requests
from furl import furl

from core.crawler import Crawler


import json
import logging
import os.path
import tempfile

import requests
from furl import furl

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl


def raise_for_status(response: requests.Response):
    """
    Raise an exception if the HTTP status code indicates an error.

    If the status code is 400 (Bad Request), logs the response body before raising.

    Args:
        response (requests.Response): The HTTP response object to evaluate.

    Raises:
        requests.exceptions.HTTPError: If the response indicates an HTTP error status.
    """
    if response.status_code == 400:
        logging.error(f"Bad Request: \n {response.json()}")
    response.raise_for_status()


def get_content(page_data: dict[str, any]) -> str:
    """
    Extract the HTML content from the Confluence page data if available.

    Args:
        page_data (dict[str, any]): A dictionary containing Confluence page details.

    Returns:
        str: The HTML content if found; otherwise, None.
    """
    result = None
    if 'body' in page_data:
        if 'anonymous_export_view' in page_data['body']:
            result = page_data['body']['anonymous_export_view']['value']
    return result


def append_links(metadata: dict[str, any], page_data: dict[str, any]):
    """
    Append relevant links to the metadata dictionary.

    This uses the Confluence '_links' property, constructing URLs for paths
    like 'editui', 'webui', 'edituiv2', and 'tinyui'.

    Args:
        metadata (dict[str, any]): A dictionary to augment with link info.
        page_data (dict[str, any]): Confluence page data, expected to contain '_links'.
    """
    if page_data['_links']:
        links = {}
        for path_name in ['editui', 'webui', 'edituiv2', 'tinyui']:
            path_part = page_data['_links'][path_name]
            base_url = furl(page_data['_links']['base'])
            base_url.path = os.path.join(str(base_url.path), path_part[1:])
            links[path_name] = base_url.url
        metadata['links'] = links


def append_labels(metadata: dict[str, any], page_data: dict[str, any]):
    """
    Append label-related information to the metadata dictionary.

    Extracts labels from the page's metadata and stores them as 'labels',
    'label_names', and 'label_ids'.

    Args:
        metadata (dict[str, any]): A dictionary to augment with label info.
        page_data (dict[str, any]): Confluence page data, expected to include 'metadata' with 'labels'.
    """
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
            metadata['label_ids'] = label_ids


class ConfluenceCrawler(Crawler):
    """
    A crawler to retrieve and index pages, blogposts, and attachments from Confluence.
    """

    def append_users(self, metadata: dict[str, any], page_data: dict[str, any])->None:
        """
        Add user information (author, last owner, owner) to the metadata.

        Looks up any user IDs found in the page data and replaces them
        with the corresponding user details from Confluence.

        Args:
            metadata (dict[str, any]): A dictionary to update with user info.
            page_data (dict[str, any]): Confluence page data that may contain user IDs.
        """
        user_ids = set()

        properties = [
            'authorId',
            'lastOwnerId',
            'ownerId'
        ]
        for property in properties:
            if property in page_data:
                value = page_data[property]
                if value is not None:
                    user_ids.add(value)

        user_lookup = self.find_users(user_ids)
        for property in properties:
            if property in page_data:
                value = page_data[property]
                if value is not None:
                    if value in user_lookup:
                        metadata[property] = user_lookup[value]

    def find_users(self, user_ids: set[str])->dict[str, dict[str,str]]:
        """
        Retrieve user details for the given set of user IDs.

        Uses a cached lookup if available; otherwise, queries Confluence's
        'api/v2/users-bulk' endpoint.

        Args:
            user_ids (set[str]): Set of user account IDs to look up.

        Returns:
            dict: A mapping of user account IDs to user detail dictionaries.
        """
        result = {}

        users = set()
        for userid in user_ids:
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
        raise_for_status(users_response)
        users_data = users_response.json()

        for user_result in users_data['results']:
            self.user_cache[user_result['accountId']] = user_result

        for userid in user_ids:
            if userid in self.user_cache:
                result[userid] = self.user_cache[userid]
            else:
                logging.warning(f"Could not locate user: {userid}")

        return result

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

    def process_page(self, page_id: str, metadata: dict[str, any])-> str:
        """
        Retrieve a Confluence page by ID and update metadata.

        Fetches page data (labels, links, etc.), processes it, and returns the page's HTML content.

        Args:
            page_id (str): The ID of the Confluence page.
            metadata (dict[str, any]): Dictionary to store page metadata.

        Returns:
            str: The page's HTML content, or None if it could not be found.
        """
        confluence_page_url = self.new_url("api/v2/pages", page_id)
        confluence_page_url.args['include-labels'] = 'true'
        confluence_page_url.args['include-properties'] = 'true'
        confluence_page_url.args['include-likes'] = 'true'
        confluence_page_url.args['include-operations'] = 'true'
        confluence_page_url.args['include-version'] = 'true'
        confluence_page_url.args['body-format'] = 'anonymous_export_view'
        logging.info(f"Fetching content for {confluence_page_url.url}")
        confluence_page_response = self.session.get(confluence_page_url.url, headers=self.confluence_headers,
                                                    auth=self.confluence_auth)
        raise_for_status(confluence_page_response)
        confluence_page_data = confluence_page_response.json()
        append_labels(metadata, confluence_page_data)
        append_links(metadata, confluence_page_data)
        self.append_users(metadata, confluence_page_data)
        metadata.update(
            {k: confluence_page_data[k] for k in ('title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType')
             if k in confluence_page_data})
        return get_content(confluence_page_data)

    def process_blogpost(self, blogpost_id: str, metadata: dict[str, any])-> str:
        """
        Retrieve a Confluence blogpost by ID and update metadata.

        Similar to process_page, but targets blogposts specifically.

        Args:
            blogpost_id (str): The ID of the Confluence blogpost.
            metadata (dict[str, any]): Dictionary to store blogpost metadata.

        Returns:
            str: The blogpost's HTML content, or None if it could not be found.
        """
        confluence_page_url = self.new_url("api/v2/blogposts", blogpost_id)
        confluence_page_url.args['include-labels'] = 'true'
        confluence_page_url.args['include-properties'] = 'true'
        confluence_page_url.args['include-likes'] = 'true'
        confluence_page_url.args['include-operations'] = 'true'
        confluence_page_url.args['include-version'] = 'true'
        confluence_page_url.args['body-format'] = 'anonymous_export_view'
        logging.info(f"Fetching content for {confluence_page_url.url}")
        confluence_page_response = self.session.get(confluence_page_url.url, headers=self.confluence_headers,
                                                    auth=self.confluence_auth)
        raise_for_status(confluence_page_response)
        confluence_page_data = confluence_page_response.json()
        append_labels(metadata, confluence_page_data)
        append_links(metadata, confluence_page_data)
        self.append_users(metadata, confluence_page_data)
        metadata.update(
            {k: confluence_page_data[k] for k in ('title', 'spaceId', 'status', 'createdAt', 'parentId', 'parentType')
             if k in confluence_page_data})
        return get_content(confluence_page_data)

    def process_attachments(self, confluence_id:str, metadata: dict[str, any])-> None:
        """
        Retrieve and index attachments for a Confluence page or blogpost.

        Downloads attachments if their file extension is supported, then
        passes each file to the indexer for processing.

        Args:
            confluence_id (str): ID in confluence
            metadata (dict[str, any]): Metadata containing 'type' and 'id' 
                that identifies the page or blogpost.
        """
        attachment_url = self.new_url('api/v2', f"{metadata['type']}s", confluence_id, 'attachments')
        attachment_response = self.session.get(attachment_url.url, headers=self.confluence_headers,
                                               auth=self.confluence_auth)
        raise_for_status(attachment_response)
        attachment_data = attachment_response.json()

        supported_extensions = {
            '.pdf', '.md', '.odt', '.doc', '.docx', '.ppt',
            '.pptx', '.txt', '.html', '.htm', '.lxml',
            '.rtf', '.epub'
        }

        for result in attachment_data['results']:
            title = result['title']
            filename, file_extension = os.path.splitext(title)
            if file_extension not in supported_extensions:
                logging.warning(f"Extension not supported, skipping. '{file_extension}' title:{title}")
                continue
            attachment_metadata = {}

            attachment_metadata.update(
                {k: result[k] for k in ('title', 'pageId', 'blogPostId', 'fileId', 'comment', 'mediaType', 'status') if k in result}
            )
            attachment_id = f"{metadata['id']}-{result['id']}"
            download_stub = furl(result['downloadLink'][1:])
            download_url = self.new_url(download_stub.path)
            download_url.args.update(
                {k: download_stub.args[k] for k in ('version', 'modificationDate', 'cacheVersion', 'api')
                 if k in download_stub.args}
            )
            attachment_metadata['links'] = {'download':download_url.url}
            logging.info(f"Downloading Attachment {result['id']} - {download_url.url}")
            download_response = self.session.get(download_url.url, headers=self.confluence_headers,
                                                 auth=self.confluence_auth)
            raise_for_status(download_response)
            with tempfile.NamedTemporaryFile(suffix=file_extension, mode='wb', delete=False) as f:
                logging.debug(f"Writing content for {attachment_id} to {f.name}")
                for chunk in download_response.iter_content(chunk_size=32000):
                    f.write(chunk)
                f.flush()
                f.close()
                try:
                    succeeded = self.indexer.index_file(f.name, download_url.url, attachment_metadata, attachment_id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

                if not succeeded:
                    logging.error(f"Error indexing {result['id']} - {download_url.url}")

    def lookup_space(self, space_id:str)->dict[str,any]:
        """
        Retrieve and cache Confluence space information by ID.

        If the requested space information is already cached, the cached data is returned.
        Otherwise, a GET request is made to the Confluence 'api/v2/spaces/<space_id>' endpoint,
        and the retrieved data is cached before being returned.

        Args:
            space_id (str): The ID of the Confluence space to retrieve.

        Returns:
            dict[str, any]: A dictionary containing the space's information as returned by the Confluence API.
        """
        if space_id in self.space_cache:
            return self.space_cache[space_id]

        confluece_space_url = self.new_url('api/v2/spaces', space_id)
        logging.info(f"Retrieving Space information: {confluece_space_url.url}")
        confluence_space_response = self.session.get(
            confluece_space_url.url,
            headers=self.confluence_headers,
            auth=self.confluence_auth
        )
        raise_for_status(confluence_space_response)
        confluence_space_data = confluence_space_response.json()
        self.space_cache[space_id] = confluence_space_data
        return confluence_space_data


    def crawl(self) -> None:
        """
        Execute the Confluence crawl process.

        1. Configures the session and authentication.
        2. Executes a Confluence CQL query to find pages/blogposts.
        3. Fetches their content and processes attachments (if enabled).
        4. Passes all content to the indexer for indexing.

        This method loops over paginated search results until exhausted.
        """
        self.confluence_headers = {"Accept": "application/json"}
        self.confluence_auth = (
            self.cfg.confluence_crawler.confluence_username,
            self.cfg.confluence_crawler.confluence_password
        )
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.confluence_crawler)
        self.base_url = furl(self.cfg.confluence_crawler.confluence_base_url)
        self.user_cache = {}
        self.space_cache = {}

        confluence_search_url = self.new_url('rest/api/content/search')
        confluence_search_url.args["cql"] = self.cfg.confluence_crawler.confluence_cql

        limit = 25
        confluence_search_url.args['limit'] = limit
        confluence_search_url.args['next'] = 'true'
        count = 0
        while True:
            logging.info(f"Searching Confluence: {confluence_search_url.url}")
            confluence_search_response = self.session.get(
                confluence_search_url.url,
                headers=self.confluence_headers,
                auth=self.confluence_auth
            )
            raise_for_status(confluence_search_response)
            confluence_search_data = confluence_search_response.json()

            for search_result in confluence_search_data['results']:
                confluence_id = search_result['id']
                doc_id = f"{search_result['type']}{confluence_id}"
                metadata = {'id':doc_id}
                metadata.update({k: search_result[k] for k in ('type', 'status') if k in search_result})
                content = None
                if search_result['type'] == 'page':
                    content = self.process_page(confluence_id, metadata)
                elif search_result['type'] == 'blogpost':
                    content = self.process_blogpost(confluence_id, metadata)
                else:
                    logging.error(f"Unsupported type: {search_result['type']} id: {search_result['id']}")
                    continue

                if content is None:
                    logging.warning(f"Could not find content for id:{search_result['id']} type:{search_result['type']}")
                    continue

                if 'spaceId' in metadata:
                    space_data = self.lookup_space(metadata['spaceId'])
                    metadata['spaceName'] = space_data['name']

                url = metadata['links']['webui'] if 'links' in metadata and 'webui' in metadata['links'] else doc_id
                with tempfile.NamedTemporaryFile(suffix=".html", mode='w', delete=False) as f:
                    logging.debug(f"Writing content for {doc_id} to {f.name}")
                    f.write(content)
                    f.flush()
                    f.close()
                    try:
                        succeeded = self.indexer.index_file(f.name, url, metadata, doc_id)
                    finally:
                        if os.path.exists(f.name):
                            os.remove(f.name)

                if self.cfg.confluence_crawler.confluence_include_attachments:
                    self.process_attachments(confluence_id, metadata)

                if succeeded:
                    count += 1
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
