import logging
logger = logging.getLogger(__name__)
import os
import tempfile

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl


class JiraCrawler(Crawler):

    def process_attachments(
        self,
        issue_key: str,
        base_metadata: dict,
        attachments: list,
        jira_auth: tuple,
        session
    ) -> None:
        """
        Process and index image attachments from a Jira issue.

        Downloads image attachments and passes them to the indexer for processing.
        If image summarization is enabled in config, the indexer will generate
        AI-powered descriptions of the images.

        Args:
            issue_key (str): The Jira issue key (e.g., 'PROJ-123')
            base_metadata (dict): Base metadata from the parent issue
            attachments (list): List of attachment objects from Jira API
            jira_auth (tuple): Authentication tuple (username, password)
            session: HTTP session for making requests
        """
        if not attachments:
            logger.debug(f"No attachments found for issue {issue_key}")
            return

        # Get configuration for attachment processing
        include_images = self.cfg.jira_crawler.get("include_image_attachments", True)
        include_documents = self.cfg.jira_crawler.get("include_document_attachments", False)

        if not include_images and not include_documents:
            logger.debug(f"Attachment processing disabled for issue {issue_key}")
            return

        # Define supported file extensions
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp', '.tiff', '.tif'}
        document_extensions = {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md'}

        attachment_count = 0

        for attachment in attachments:
            filename = attachment.get("filename", "")
            if not filename:
                logger.warning(f"Attachment without filename in issue {issue_key}, skipping")
                continue

            file_ext = os.path.splitext(filename)[1].lower()

            # Determine if we should process this attachment
            is_image = file_ext in image_extensions
            is_document = file_ext in document_extensions

            if is_image and not include_images:
                logger.debug(f"Skipping image attachment (disabled): {filename}")
                continue

            if is_document and not include_documents:
                logger.debug(f"Skipping document attachment (disabled): {filename}")
                continue

            if not is_image and not is_document:
                logger.debug(f"Skipping unsupported attachment type: {filename}")
                continue

            logger.info(f"Processing attachment: {filename} for issue {issue_key}")

            try:
                # Get attachment content URL
                content_url = attachment.get("content")
                if not content_url:
                    logger.warning(f"No content URL for attachment {filename}, skipping")
                    continue

                # Download attachment
                download_response = session.get(
                    content_url,
                    auth=jira_auth,
                    headers={"Accept": "application/octet-stream"},
                    stream=True
                )
                download_response.raise_for_status()

                # Save to temporary file
                with tempfile.NamedTemporaryFile(
                    suffix=file_ext,
                    delete=False
                ) as temp_file:
                    for chunk in download_response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)
                    temp_path = temp_file.name

                try:
                    # Prepare attachment metadata
                    attachment_metadata = base_metadata.copy()
                    attachment_metadata.update({
                        "attachment_id": attachment.get("id", ""),
                        "filename": filename,
                        "mime_type": attachment.get("mimeType", ""),
                        "file_size": attachment.get("size", 0),
                        "created": attachment.get("created", ""),
                        "source": "jira_attachment",
                        "parent_issue": issue_key,
                        "attachment_type": "image" if is_image else "document"
                    })

                    # Add author information if available
                    if "author" in attachment:
                        author = attachment["author"]
                        attachment_metadata["attachment_author"] = author.get("displayName", "")

                    # Index the attachment file
                    # The indexer will handle image summarization if enabled in config
                    doc_id = f"{issue_key}-attachment-{attachment.get('id', attachment_count)}"
                    succeeded = self.indexer.index_file(
                        temp_path,
                        content_url,
                        attachment_metadata,
                        doc_id
                    )

                    if succeeded:
                        logger.info(f"Successfully indexed attachment: {filename}")
                        attachment_count += 1
                    else:
                        logger.error(f"Failed to index attachment: {filename}")

                finally:
                    # Always cleanup temporary file
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

            except Exception as e:
                logger.error(f"Error processing attachment {filename} for issue {issue_key}: {e}")
                continue

        if attachment_count > 0:
            logger.info(f"Processed {attachment_count} attachment(s) for issue {issue_key}")

    def crawl(self) -> None:
        base_url = self.cfg.jira_crawler.jira_base_url.rstrip("/")
        jql = self.cfg.jira_crawler.jira_jql
        jira_headers = { "Accept": "application/json" }
        jira_auth = (self.cfg.jira_crawler.jira_username, self.cfg.jira_crawler.jira_password)
        session = create_session_with_retries()
        configure_session_for_ssl(session, self.cfg.jira_crawler)

        wanted_fields = [
            "summary","project","issuetype","status","priority","reporter","assignee",
            "created","updated","resolutiondate","labels","comment","description","attachment"
        ]

        api_version = getattr(self.cfg.jira_crawler, 'api_version', '3')
        api_endpoint = getattr(self.cfg.jira_crawler, 'api_endpoint', 'search')
        fields = getattr(self.cfg.jira_crawler, 'fields', wanted_fields)
        max_results = getattr(self.cfg.jira_crawler, 'max_results', 100)
        initial_start_at = getattr(self.cfg.jira_crawler, 'start_at', 0)

        issue_count = 0
        start_at = initial_start_at
        res_cnt = max_results
        while True:
            params = {
                "jql": jql,                       # let requests encode
                "fields": ",".join(fields),
                "maxResults": res_cnt,
                "startAt": start_at,
            }
            if api_version == 2:
                url = f"{base_url}/rest/api/{api_version}/{api_endpoint}"
            elif api_version == 3:
                url = f"{base_url}/rest/api/{api_version}/{api_endpoint}/jql"
            else:
                raise ValueError(f"Unsupported Jira API version {api_version}")
            jira_response = session.get(url, headers=jira_headers, auth=jira_auth, params=params)
            jira_response.raise_for_status()
            jira_data = jira_response.json()

            actual_cnt = len(jira_data["issues"])
            if actual_cnt > 0:
                for issue in jira_data["issues"]:
                    # Collect as much metadata as possible
                    metadata = {}
                    metadata["project"] = issue["fields"]["project"]["name"]
                    metadata["issueType"] = issue["fields"]["issuetype"]["name"]
                    metadata["status"] = issue["fields"]["status"]["name"]
                    metadata["priority"] = issue["fields"]["priority"]["name"]
                    metadata["reporter"] = issue["fields"]["reporter"]["displayName"]
                    metadata["assignee"] = issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else None
                    metadata["created"] = issue["fields"]["created"]
                    metadata["last_updated"] = issue["fields"]["updated"]
                    metadata["resolved"] = issue["fields"]["resolutiondate"] if "resolutiondate" in issue["fields"] else None
                    metadata["labels"] = issue["fields"]["labels"]
                    metadata["source"] = "jira"
                    metadata["url"] = f"{self.cfg.jira_crawler.jira_base_url}/browse/{issue['key']}"

                    # Create a Vectara document with the metadata and the issue fields
                    title = issue["fields"]["summary"]
                    document = {
                        "id": issue["key"],
                        "title": title,
                        "metadata": metadata,
                        "sections": []
                    }
                    comments_data = issue["fields"]["comment"]["comments"]
                    comments = []
                    for comment in comments_data:
                        author = comment["author"]["displayName"]
                        try:
                            comment_body = comment["body"]["content"][0]["content"][0]["text"]
                            comments.append(f'{author}: {comment_body}')
                        except Exception as e:
                            continue

                    try:
                        description = issue["fields"]["description"]["content"][0]["content"][0]["text"]
                    except Exception as e:
                        description = str(issue['key'])

                    document["sections"] = [
                        {
                            "title": "Comments",
                            "text": "\n\n".join(comments)
                        },
                        {
                            "title": "Description",
                            "text": description
                        },
                        {
                            "title": "Status",
                            "text": f'Issue {title} is {issue["fields"]["status"]["name"]}'
                        }
                    ]

                    succeeded = self.indexer.index_document(document)
                    if succeeded:
                        logger.info(f"Indexed issue {document['id']}")
                        issue_count += 1

                        # Process attachments if they exist
                        attachments = issue["fields"].get("attachment", [])
                        if attachments:
                            try:
                                self.process_attachments(
                                    issue_key=issue["key"],
                                    base_metadata=metadata,
                                    attachments=attachments,
                                    jira_auth=jira_auth,
                                    session=session
                                )
                            except Exception as e:
                                logger.error(f"Error processing attachments for issue {issue['key']}: {e}")
                    else:
                        logger.info(f"Error indexing issue {document['id']}")
                start_at = start_at + actual_cnt
            else:
                break

        logger.info(f"Finished indexing all issues (total={issue_count})")
