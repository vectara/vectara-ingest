import json
import logging
import os
import tempfile
from importlib.metadata import metadata
from furl import furl
from requests import Response

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
            self._process_attachment(content, metadata, doc_id)
        else:
            self._process_non_attachment(content, metadata, doc_id)

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
            logging.warning(f"Extension not supported, skipping. '{file_extension}' title: {title}")
            return

        attachment_url = furl(metadata["url"])
        logging.info(f"Downloading Attachment {doc_id} - {attachment_url}")

        download_response = self.session.get(
            attachment_url.url, headers=self.confluence_headers, auth=self.confluence_auth
        )

        with tempfile.NamedTemporaryFile(suffix=file_extension, mode="wb", delete=False) as f:
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
                logging.debug(f"Writing content for {doc_id} to {f.name}")
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
                    succeeded = self.indexer.index_file(f.name, metadata["url"], metadata, doc_id)
                finally:
                    if os.path.exists(f.name):
                        os.remove(f.name)

    def crawl(self) -> None:
        """
        Initiates the crawling process for Confluence content.
        """
        self.base_url = furl(self.cfg.confluencedatacenter.base_url)
        logging.info(f"Starting base_url = '{self.base_url}'")

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

        logging.info(f"Searching Confluence {search_url.url}")

        while True:
            search_url.args["start"] = start
            start += limit
            search_url_response = self.session.get(
                search_url.url, headers=self.confluence_headers, auth=self.confluence_auth
            )

            if search_url_response.status_code == 500:
                logging.warning(
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
                    logging.debug("next not found in _links, going again.")
            else:
                logging.warning("_links was not found in the response. Exiting to prevent an infinite loop.")
                break