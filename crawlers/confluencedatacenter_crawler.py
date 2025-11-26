import logging
logger = logging.getLogger(__name__)
import os
import tempfile
import pandas as pd
from pathlib import Path
from furl import furl

from core.crawler import Crawler
from core.utils import create_session_with_retries, IMG_EXTENSIONS, DOC_EXTENSIONS
from core.dataframe_parser import (
    DataframeParser,
    supported_by_dataframe_parser,
    determine_dataframe_type,
    get_separator_by_file_name
)

# Supported extensions for dataframe processing (CSV/Excel)
SUPPORTED_DATAFRAME_EXTENSIONS = {".csv", ".xlsx", ".xls"}


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
        Handles processing and indexing of attachments including images, documents, and dataframes (CSV/Excel).

        Args:
            content (dict): The content dictionary retrieved from Confluence.
            metadata (dict): Metadata associated with the document.
            doc_id (str): The unique document identifier.
        """
        # Get configuration for attachment processing
        include_images = self.cfg.confluencedatacenter.get("include_image_attachments", False)
        include_documents = self.cfg.confluencedatacenter.get("include_document_attachments", True)

        if not include_images and not include_documents:
            logger.debug(f"Attachment processing disabled for {doc_id}")
            return

        title = content["title"]
        file_extension = Path(title).suffix.lower()

        # Use centralized file extension constants from utils
        image_extensions = set(IMG_EXTENSIONS)
        # Document extensions: standard docs plus text-based formats (excluding CSV/Excel)
        document_extensions = set(DOC_EXTENSIONS + ['.txt', '.md', '.html', '.htm', '.rtf', '.epub', '.odt', '.lxml']) - SUPPORTED_DATAFRAME_EXTENSIONS
        # Dataframe extensions: CSV and Excel files
        dataframe_extensions = SUPPORTED_DATAFRAME_EXTENSIONS

        # Determine if we should process this attachment
        is_image = file_extension in image_extensions
        is_document = file_extension in document_extensions
        is_dataframe = file_extension in dataframe_extensions

        if is_image and not include_images:
            logger.debug(f"Skipping image attachment (disabled): {title}")
            return

        if is_document and not include_documents:
            logger.debug(f"Skipping document attachment (disabled): {title}")
            return

        if is_dataframe and not self.df_parser:
            logger.debug(f"Skipping dataframe attachment (DataframeParser not configured): {title}")
            return

        if not is_image and not is_document and not is_dataframe:
            logger.warning(f"Extension not supported, skipping. '{file_extension}' title: {title}")
            return

        if "url" not in metadata:
            logger.error(f"No URL found in metadata for attachment {doc_id}")
            return

        attachment_url = furl(metadata["url"])
        file_type = "image" if is_image else ("dataframe" if is_dataframe else "document")
        logger.info(f"Downloading {file_type} attachment {doc_id} - {attachment_url}")

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
            temp_path = f.name

        try:
            # Enhance metadata with attachment information
            attachment_metadata = metadata.copy()
            attachment_metadata.update({
                "filename": title,
                "attachment_type": file_type,
                "source": "confluence_attachment"
            })

            # Route to appropriate processor
            if is_dataframe:
                # Process CSV/Excel files with DataframeParser
                succeeded = self.process_dataframe_file(temp_path, attachment_metadata, doc_id)
            else:
                # Process images and regular documents with indexer
                succeeded = self.indexer.index_file(temp_path, attachment_url.url, attachment_metadata, doc_id)

            if succeeded:
                logger.info(f"Successfully indexed {file_type} attachment: {title}")
            else:
                logger.error(f"Failed to index attachment {doc_id} - {attachment_url}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

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

    def process_dataframe_file(self, file_path: str, metadata: dict, doc_id: str) -> bool:
        """
        Process CSV or Excel files using the DataframeParser.
        Similar to SharePoint crawler approach.

        Args:
            file_path: Path to the CSV/Excel file
            metadata: Existing metadata dictionary
            doc_id: Document ID for indexing

        Returns:
            bool: Success status
        """
        if not self.df_parser:
            logger.error("DataframeParser not initialized. Cannot process dataframe file.")
            return False

        try:
            if not supported_by_dataframe_parser(file_path):
                logger.error(f"'{file_path}' is not supported by DataframeParser.")
                return False

            logger.info(f"Processing dataframe file: {file_path}")

            file_type = determine_dataframe_type(file_path)
            doc_title = os.path.basename(file_path)

            # Add Confluence-specific metadata
            df_metadata = metadata.copy()
            df_metadata['source'] = 'confluence_attachment'
            df_metadata['file_type'] = file_type

            # Get dataframe processing config
            df_config = self.cfg.confluencedatacenter.get('dataframe_processing', {})

            if file_type == 'csv':
                separator = get_separator_by_file_name(file_path)
                encoding = df_config.get('csv_encoding', 'utf-8')
                try:
                    df = pd.read_csv(file_path, sep=separator, encoding=encoding)
                except Exception as e:
                    logger.warning(f"Failed to read CSV with encoding {encoding}: {e}. Trying with 'latin-1'")
                    df = pd.read_csv(file_path, sep=separator, encoding='latin-1')

                self.df_parser.process_dataframe(
                    df=df,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    metadata=df_metadata
                )

            elif file_type in ['xls', 'xlsx']:
                xls = pd.ExcelFile(file_path)
                sheet_names = df_config.get("sheet_names")

                # If sheet_names is not specified or is None, process all sheets
                if sheet_names is None:
                    sheet_names = xls.sheet_names

                for sheet_name in sheet_names:
                    if sheet_name not in xls.sheet_names:
                        logger.warning(f"Sheet '{sheet_name}' not found in '{file_path}'. Skipping.")
                        continue

                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    sheet_doc_id = f"{doc_id}_{sheet_name}"
                    sheet_doc_title = f"{doc_title} - {sheet_name}"
                    sheet_metadata = df_metadata.copy()
                    sheet_metadata['sheet_name'] = sheet_name

                    self.df_parser.process_dataframe(
                        df=df,
                        doc_id=sheet_doc_id,
                        doc_title=sheet_doc_title,
                        metadata=sheet_metadata
                    )

            return True

        except Exception as e:
            logger.error(f"Error processing dataframe file {file_path}: {e}")
            return False

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

        # Initialize DataframeParser for CSV/Excel processing
        self.df_parser = None
        if hasattr(self.cfg.confluencedatacenter, 'dataframe_processing'):
            df_config = self.cfg.confluencedatacenter.dataframe_processing
            self.df_parser = DataframeParser(
                cfg=self.cfg,
                indexer=self.indexer,
                mode=df_config.get('mode', 'table')
            )
            logger.info(f"DataframeParser initialized with mode: {df_config.get('mode', 'table')}")

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