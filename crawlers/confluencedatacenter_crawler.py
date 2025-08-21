import logging
logger = logging.getLogger(__name__)
import os
import tempfile
from furl import furl

from core.crawler import Crawler
from core.utils import create_session_with_retries


class ConfluencedatacenterCrawler(Crawler):
    """
    A crawler for Confluence Data Center that fetches and processes content
    from Confluence using the REST API.
    """

    def new_url(self, /, *paths) -> furl:
        """
        Constructs a new URL by copying the base URL and appending additional path segments.

        Args:
            *paths (str): One or more path segments to append.

        Returns:
            furl.furl: A new furl object representing the resulting URL.
        """
        result = self.base_url.copy()
        for p in paths:
            result.path = os.path.join(str(result.path), str(p))
        return result

    def process_content(self, content: dict[str, any]) -> None:
        """
        Processes Confluence content and indexes it if applicable.

        Args:
            content (dict): The content dictionary retrieved from Confluence.
        """
        id = content["id"]
        type = content["type"]
        doc_id = f"{type}-{id}"
        metadata = {"type": type, "id": id}

        if "version" in content:
            if "when" in content["version"]:
                metadata["last_updates"] = content["version"]["when"]
            if "number" in content["version"]:
                metadata["version"] = content["version"]["number"]
            if "by" in content["version"]:
                metadata["updated_by"] = {
                    "username": content["version"]["by"]["username"],
                    "userKey": content["version"]["by"]["userKey"],
                }

        if "space" in content:
            metadata["space"] = {
                k: content["space"][k] for k in ("id", "key", "name") if k in content["space"]
            }

        url_part = None

        if "_links" in content:
            if type == "attachment" and "download" in content["_links"]:
                url_part = furl(content["_links"]["download"])
            elif "webui" in content["_links"]:
                url_part = furl(content["_links"]["webui"])

        if url_part:
            viewer_url = self.new_url(url_part.pathstr)
            for k, v in url_part.args.items():
                viewer_url.args[k] = v
            metadata["url"] = viewer_url.url

        if type == "attachment":
            # Check if attachments should be processed
            include_attachments = self.cfg.confluencedatacenter.get("confluence_include_attachments", False)
            if include_attachments:
                self._process_attachment(content, metadata, doc_id)
            else:
                logger.debug(f"Skipping attachment {doc_id} - confluence_include_attachments is disabled")
        else:
            self._process_non_attachment(content, metadata, doc_id)
            
            # If attachments are enabled, also process attachments for this content
            include_attachments = self.cfg.confluencedatacenter.get("confluence_include_attachments", False)
            if include_attachments:
                logger.debug(f"Processing attachments for {doc_id} (confluence_include_attachments=True)")
                self._process_content_attachments(id, metadata)
            else:
                logger.debug(f"Skipping attachments for {doc_id} (confluence_include_attachments=False)")

    def _process_attachment(self, content: dict, metadata: dict, doc_id: str) -> None:
        """
        Handles processing and indexing of attachments.

        Args:
            content (dict): The content dictionary retrieved from Confluence.
            metadata (dict): Metadata associated with the document.
            doc_id (str): The unique document identifier.
        """
        supported_extensions = {
            ".pdf", ".md", ".odt", ".doc", ".docx", ".ppt",
            ".pptx", ".txt", ".html", ".htm", ".lxml",
            ".rtf", ".epub"
        }
        title = content["title"]
        filename, file_extension = os.path.splitext(title)

        if file_extension not in supported_extensions:
            logger.warning(f"Extension not supported, skipping. '{file_extension}' title: {title}")
            return

        if "url" not in metadata:
            logger.error(f"No URL found in metadata for attachment {doc_id}")
            return
            
        attachment_url = furl(metadata["url"])
        logger.info(f"Downloading Attachment {doc_id} - {attachment_url}")

        download_response = self.session.get(
            attachment_url.url, headers=self.confluence_headers, auth=self.confluence_auth
        )
        
        if not download_response.ok:
            logger.error(f"Failed to download attachment {doc_id}: {download_response.status_code} - {download_response.text}")
            return

        with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
            logger.debug(f"Writing content for {doc_id} to {f.name}")
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
                logger.error(f"Error indexing {doc_id} - {attachment_url}")

    def _process_non_attachment(self, content: dict, metadata: dict, doc_id: str) -> None:
        """
        Handles processing and indexing of non-attachment content.

        Args:
            content (dict): The content dictionary retrieved from Confluence.
            metadata (dict): Metadata associated with the document.
            doc_id (str): The unique document identifier.
        """
        if "body" in content and self.body_view in content["body"]:
            body = content["body"][self.body_view]["value"]
            with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False) as f:
                logger.debug(f"Writing content for {doc_id} to {f.name}")
                f.write("<html>")
                if "title" in content:
                    f.write("<head><title>")
                    f.write(content["title"])
                    f.write("</title></head>")
                f.write("<body>")
                f.write(body)
                f.write("</body>")
                f.write("</html>")
                f.flush()
                f.close()

                try:
                    # Use metadata URL if available, otherwise construct a basic URL
                    url = metadata.get("url", f"{self.base_url}/pages/viewpage.action?pageId={content['id']}")
                    succeeded = self.indexer.index_file(f.name, url, metadata, doc_id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

    def _process_content_attachments(self, content_id: str, content_metadata: dict) -> None:
        """
        Retrieve and process attachments for a specific piece of content.
        Similar to the regular confluence crawler's process_attachments method.
        
        Args:
            content_id (str): The ID of the content to fetch attachments for
            content_metadata (dict): Metadata of the parent content
        """
        try:
            # Construct URL to fetch attachments for this content
            # Using Confluence Data Center REST API: /rest/api/content/{id}/child/attachment
            attachments_url = self.new_url("rest/api/content", content_id, "child", "attachment")
            attachments_url.args["expand"] = "version,space"
            attachments_url.args["limit"] = "200"  # Increase limit to get more attachments
            
            logger.debug(f"Fetching attachments for content {content_id}: {attachments_url.url}")
            
            response = self.session.get(
                attachments_url.url, 
                headers=self.confluence_headers, 
                auth=self.confluence_auth
            )
            
            if response.status_code == 404:
                logger.debug(f"No attachments found for content {content_id}")
                return
                
            response.raise_for_status()
            attachments_data = response.json()
            
            if "results" in attachments_data and attachments_data["results"]:
                logger.info(f"Found {len(attachments_data['results'])} attachments for content {content_id}")
                for attachment in attachments_data["results"]:
                    # Process each attachment using the existing process_content method
                    # This ensures consistent processing logic
                    self.process_content(attachment)
            else:
                logger.debug(f"No attachments in results for content {content_id}")
                    
        except Exception as e:
            logger.warning(f"Error fetching attachments for content {content_id}: {e}")

    def crawl(self) -> None:
        """
        Initiates the crawling process for Confluence content.
        """
        self.base_url = furl(self.cfg.confluencedatacenter.base_url)
        logger.info(f"Starting base_url = '{self.base_url}'")

        self.confluence_headers = {"Accept": "application/json"}
        self.confluence_auth = (
            self.cfg.confluencedatacenter.confluence_datacenter_username,
            self.cfg.confluencedatacenter.confluence_datacenter_password,
        )
        self.body_view = self.cfg.confluencedatacenter.get("body_view", "export_view")
        self.session = create_session_with_retries()
        limit = int(self.cfg.confluencedatacenter.get("limit", "25"))
        start = 0

        search_url = self.new_url("rest/api/content/search")
        search_url.args["cql"] = self.cfg.confluencedatacenter.confluence_cql
        search_url.args["expand"] = ",".join(
            [
                f"body.{self.body_view}",
                "content",
                "space",
                "version",
                "metadata.labels",
                "metadata.properties",
            ]
        )
        search_url.args["limit"] = limit

        logger.info(f"Searching Confluence {search_url.url}")

        while True:
            search_url.args["start"] = start
            start += limit
            search_url_response = self.session.get(
                search_url.url, headers=self.confluence_headers, auth=self.confluence_auth
            )

            if search_url_response.status_code == 500:
                logger.warning(
                    "500 returned by REST API. This could be due to a mismatch with the space name in your query."
                )

            search_url_response.raise_for_status()
            search_url_data = search_url_response.json()

            search_results = search_url_data["results"]

            for search_result in search_results:
                if "content" in search_result:
                    self.process_content(search_result["content"])
                else:
                    self.process_content(search_result)

            if "_links" in search_url_data:
                if "next" not in search_url_data["_links"]:
                    break
                else:
                    logger.debug("next not found in _links, going again.")
            else:
                logger.warning("_links was not found in the response. Exiting to prevent an infinite loop.")
                break