import logging

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl
import os.path
import json
import tempfile

from furl import furl

def is_supported_file(file_name:str)->bool:
    supported_extensions = {
        '.pdf', '.md', '.odt', '.doc', '.docx', '.ppt',
        '.pptx', '.txt', '.html', '.htm', '.lxml',
        '.rtf', '.epub'
    }
    filename, file_extension = os.path.splitext(file_name)
    return file_extension.lower() in supported_extensions


class ServicenowCrawler(Crawler):
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

    def crawl(self) -> None:
        """
        Crawl a ServiceNow Knowledge Base and index its articles (and optionally attachments).

        This method connects to a configured ServiceNow instance using the provided credentials
        and retrieves records from the `kb_knowledge` table in paginated batches. For each
        article, it writes the article's HTML content to a temporary file along with relevant
        metadata, then passes it to the `Indexer` for indexing. If configured to do so, it will
        also fetch all supported file attachments for each article and index them as well.

        Workflow:
            1. Retrieve and parse a list of KB articles from ServiceNow.
            2. Generate temporary HTML files for each article containing its text and metadata.
            3. Index each temporary file using `self.indexer.index_file`.
            4. (Optional) If `servicenow_process_attachments` is enabled:
               - Fetch all attachments related to each article from the `sys_attachment` table.
               - For attachments with supported file types, download them to temporary files
                 and index them.
            5. Progress through subsequent pages of results until no more articles are returned.

        Returns:
            None: This method performs side effects (indexing) only and does not return a value.
        """
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.servicenow_crawler)
        self.base_url = furl(self.cfg.servicenow_crawler.servicenow_instance_url)
        self.servicenow_headers = {"Accept": "application/json"}
        self.servicenow_auth = (
            self.cfg.servicenow_crawler.servicenow_username,
            self.cfg.servicenow_crawler.servicenow_password
        )
        self.user_cache = {}

        skip_fields = self.cfg.servicenow_crawler.get('servicenow_ignore_fields', {'text', 'short_description'})
        page_size = self.cfg.servicenow_crawler.get('servicenow_pagesize', 100)

        table = 'kb_knowledge'
        kb_url = self.new_url('/kb_view.do')
        list_articles_url = self.new_url('/api/now/table', table)
        if 'servicenow_query' in self.cfg.servicenow_crawler:
            list_articles_url.args['sysparm_query']= self.cfg.servicenow_crawler.get('servicenow_query')

        offset = 0
        list_articles_url.args['sysparm_offset'] = 0
        list_articles_url.args['sysparm_limit'] = page_size

        while True:
            list_articles_url.args['sysparm_offset'] = offset
            logging.info(f"Fetching list of articles: {list_articles_url.url}")

            list_articles_response = self.session.get(
                list_articles_url.url,
                headers=self.servicenow_headers,
                auth=self.servicenow_auth
            )
            list_articles_response.raise_for_status()
            list_articles_data = list_articles_response.json()

            if not 'result' in list_articles_data:
                break
            result = list_articles_data['result']

            if len(result) == 0:
                break
            articles = {}

            for article in result:
                article_sys_id = article['sys_id']
                article_doc_id = article['number']
                text = article['text']
                kb_url.args['sysparm_article'] = article_doc_id
                metadata = {
                    'url': kb_url.url,
                    'table': table
                }
                metadata.update(
                    {k: article[k] for k in article.keys()
                     if article[k] and k not in skip_fields})
                succeeded = False

                with tempfile.NamedTemporaryFile(suffix=".html", mode='w', delete=False) as f:
                    logging.debug(f"Writing content for {article_doc_id} to {f.name}")
                    f.write('<html>\n')
                    if 'short_description' in article:
                        f.write('<head>\n')
                        f.write(f"<title>{article['short_description'].strip()}</title>\n")
                        f.write('</head>\n')
                    f.write("<body>\n")
                    f.write(text)
                    f.write('</body>\n</html>')
                    f.flush()
                    f.close()
                    try:
                        succeeded = self.indexer.index_file(f.name, kb_url.url, metadata, article_doc_id)
                    finally:
                        if os.path.exists(f.name):
                            os.remove(f.name)
                if succeeded:
                    articles[article_sys_id] = article_doc_id


            if len(articles) > 0 and self.cfg.servicenow_crawler.servicenow_process_attachments:
                attachments_url = self.new_url('/api/now/table/sys_attachment')
                attachments_url.args['sysparm_query'] = f"table_name={table}^table_sys_idIN{ ','.join(articles.keys()) }"

                attachments_response = self.session.get(
                    attachments_url.url,
                    headers=self.servicenow_headers,
                    auth=self.servicenow_auth
                )
                attachments_response.raise_for_status()
                attachments_data = attachments_response.json()
                attachment_results = attachments_data.get("result", [])

                for attachment_result in attachment_results:
                    attachment_table_sysid = attachment_result['table_sys_id']
                    attachment_sys_id = attachment_result['sys_id']
                    article_doc_id = articles[attachment_table_sysid]
                    attachment_doc_id = f"{article_doc_id}.{attachment_sys_id}"
                    file_name = attachment_result['file_name']
                    if not is_supported_file(file_name):
                        logging.debug(f"Skipping {attachment_sys_id}:{file_name} because it's not a supported file type")
                        continue

                    attachment_download_url = self.new_url('/api/now/attachment/', attachment_sys_id, 'file')
                    logging.info(f"Downloading attachment for {attachment_sys_id}: {attachment_download_url.url}")
                    attachment_ui_url = self.new_url('/sys_attachment.do')
                    attachment_ui_url.args['sys_id'] = attachment_sys_id

                    attachment_metadata ={
                        'url': attachment_ui_url.url
                    }
                    attachment_metadata.update(
                        {k: attachment_result[k] for k in attachment_result.keys()
                         if attachment_result[k] and k not in skip_fields}
                    )

                    attachment_download_response = self.session.get(attachment_download_url.url, headers=self.servicenow_headers,
                                                         auth=self.servicenow_auth)
                    attachment_download_response.raise_for_status()
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
                        logging.debug(f"Writing content for {attachment_sys_id} to {f.name}")
                        for chunk in attachment_download_response.iter_content(chunk_size=32000):
                            f.write(chunk)
                        f.flush()
                        f.close()
                        try:
                            succeeded = self.indexer.index_file(f.name, attachment_download_url.url, attachment_metadata, attachment_doc_id)
                        finally:
                            if os.path.exists(f.name):
                                os.remove(f.name)

                        if not succeeded:
                            logging.error(f"Error indexing {attachment_sys_id} - {attachment_download_url.url}")


            offset += page_size