import logging
logger = logging.getLogger(__name__)
import os
import tempfile
from pathlib import Path

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl, IMG_EXTENSIONS, DOC_EXTENSIONS


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

        # Use centralized file extension constants from utils
        image_extensions = set(IMG_EXTENSIONS)
        # Add additional text-based document extensions not in DOC_EXTENSIONS
        document_extensions = set(DOC_EXTENSIONS + ['.txt', '.md'])

        attachment_count = 0

        for attachment in attachments:
            filename = attachment.get("filename", "")
            if not filename:
                logger.warning(f"Attachment without filename in issue {issue_key}, skipping")
                continue

            file_ext = Path(filename).suffix.lower()

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
                # Note: Don't set Accept header for Jira attachment downloads
                # Jira Cloud returns 406 if Accept header is too restrictive
                download_response = session.get(
                    content_url,
                    auth=jira_auth,
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

        api_version = getattr(self.cfg.jira_crawler, 'api_version', 3)
        api_endpoint = getattr(self.cfg.jira_crawler, 'api_endpoint', 'search')
        fields = getattr(self.cfg.jira_crawler, 'fields', wanted_fields)
        max_results = getattr(self.cfg.jira_crawler, 'max_results', 100)

        issue_count = 0
        res_cnt = max_results

        # API v3 uses token-based pagination, v2 uses offset-based
        next_page_token = None
        start_at = 0

        while True:
            # Build request parameters based on API version
            if api_version == 2:
                url = f"{base_url}/rest/api/{api_version}/{api_endpoint}"
                params = {
                    "jql": jql,
                    "fields": ",".join(fields),
                    "maxResults": res_cnt,
                    "startAt": start_at,
                }
                logger.info(f"Fetching issues (API v2): startAt={start_at}, maxResults={res_cnt}")
            elif api_version == 3:
                url = f"{base_url}/rest/api/{api_version}/{api_endpoint}/jql"
                params = {
                    "jql": jql,
                    "fields": ",".join(fields),
                    "maxResults": res_cnt,
                }
                if next_page_token:
                    params["nextPageToken"] = next_page_token
                    logger.info(f"Fetching issues (API v3): nextPageToken={next_page_token[:20]}..., maxResults={res_cnt}")
                else:
                    logger.info(f"Fetching issues (API v3): first page, maxResults={res_cnt}")
            else:
                raise ValueError(f"Unsupported Jira API version {api_version}")

            jira_response = session.get(url, headers=jira_headers, auth=jira_auth, params=params)
            jira_response.raise_for_status()
            jira_data = jira_response.json()

            actual_cnt = len(jira_data["issues"])
            if actual_cnt > 0:
                for issue in jira_data["issues"]:
                    # Collect as much metadata as possible
                    # Use safe navigation to handle None values
                    metadata = {}
                    metadata["project"] = issue["fields"]["project"]["name"] if issue["fields"].get("project") else None
                    metadata["issueType"] = issue["fields"]["issuetype"]["name"] if issue["fields"].get("issuetype") else None
                    metadata["status"] = issue["fields"]["status"]["name"] if issue["fields"].get("status") else None
                    metadata["priority"] = issue["fields"]["priority"]["name"] if issue["fields"].get("priority") else None
                    metadata["reporter"] = issue["fields"]["reporter"]["displayName"] if issue["fields"].get("reporter") else None
                    metadata["assignee"] = issue["fields"]["assignee"]["displayName"] if issue["fields"].get("assignee") else None
                    metadata["created"] = issue["fields"].get("created")
                    metadata["last_updated"] = issue["fields"].get("updated")
                    metadata["resolved"] = issue["fields"].get("resolutiondate")
                    metadata["labels"] = issue["fields"].get("labels", [])
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

                # Handle pagination based on API version
                if api_version == 2:
                    start_at = start_at + actual_cnt
                elif api_version == 3:
                    # Check if there are more pages
                    is_last = jira_data.get("isLast", True)
                    if is_last:
                        logger.info("Reached last page of results (isLast=true)")
                        break
                    next_page_token = jira_data.get("nextPageToken")
                    if not next_page_token:
                        logger.info("No nextPageToken found, stopping pagination")
                        break
            else:
                break

        logger.info(f"Finished indexing all issues (total={issue_count})")
