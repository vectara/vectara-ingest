import logging
import requests
import json
from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl


class JiraCrawler(Crawler):

    def crawl(self) -> None:
        self.jira_headers = { "Accept": "application/json" }
        self.jira_auth = (self.cfg.jira_crawler.jira_username, self.cfg.jira_crawler.jira_password)
        session = create_session_with_retries()
        configure_session_for_ssl(session, self.cfg.jira_crawler)

        issue_count = 0
        startAt = 0
        res_cnt = 100
        while True:
            jira_query_url = f"{self.cfg.jira_crawler.jira_base_url}/rest/api/3/search?jql={self.cfg.jira_crawler.jira_jql}&fields=*all&maxResults={res_cnt}&startAt={startAt}"

            jira_response = session.get(jira_query_url, headers=self.jira_headers, auth=self.jira_auth)
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
                        logging.info(f"Indexed issue {document['id']}")
                        issue_count += 1
                    else:
                        logging.info(f"Error indexing issue {document['id']}")
                startAt = startAt + actual_cnt
            else:
                break

        logging.info(f"Finished indexing all issues (total={issue_count})")
