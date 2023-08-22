import json
from core.crawler import Crawler
from omegaconf import OmegaConf
import requests
from attrdict import AttrDict
import logging
import base64

from ratelimiter import RateLimiter
from core.utils import create_session_with_retries

class Github(object):
    def __init__(self, repo: str, owner: str, token: str) -> None:
        self.repo = repo
        self.owner = owner
        self.token = token
        self.session = create_session_with_retries()


    def get_issues(self, state: str):
        # state can be "open", "closed", or "all"
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues?state={state}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logging.info(f"Error retrieving issues: {response.status_code}, {response.text}")
            return []

    def get_comments(self, issue_number: str):
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logging.info(f"Error retrieving comments: {response.status_code}, {response.text}")
            return []


class GithubCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.github_token = self.cfg.github_crawler.get("github_token", None)
        self.owner = self.cfg.github_crawler.owner
        self.repos = self.cfg.github_crawler.repos
        self.crawl_code = self.cfg.github_crawler.crawl_code
        self.rate_limiter = RateLimiter(max_calls=1, period=1)
        self.session = create_session_with_retries()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def crawl_code_folder(self, base_url, path=""):
        headers = { "Accept": "application/vnd.github+json"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        with self.rate_limiter:
            response = self.session.get( f"{base_url}/contents/{path}", headers=headers)
        if response.status_code != 200:
            logging.info(f"Error fetching {base_url}/contents/{path}: {response.text}")
            return

        for item in response.json():
            if item["type"] == "file":
                fname = item["path"]
                url = item["html_url"]
                if url.lower().endswith(".md") or url.lower().endswith(".mdx"):     # Only index markdown files from the code, not the code itself
                    try:
                        file_response = self.session.get(item["url"], headers={"Authorization": f"token {self.github_token}"})
                        file_content = base64.b64decode(file_response.json()["content"]).decode("utf-8")
                    except Exception as e:
                        logging.info(f"Failed to retrieve content for {fname} with url {url}: {e}")
                        continue

                    metadata = {'file': fname, 'source': 'github', 'url': url}
                    code_doc = {
                        'documentId': f'github-{item["path"]}',
                        'title': item["name"],
                        'description': f'Markdown of {fname}',
                        'metadataJson': json.dumps(metadata),
                        'section': [{
                            'title': 'markdown',
                            'text': file_content,
                        }]
                    }
                    logging.info(f"Indexing codebase markdown: {item['path']}")
                    self.indexer.index_document(code_doc)
            elif item["type"] == "dir":
                self.crawl_code_folder(base_url, path=item["path"])

    def crawl_repo(self, repo, owner, token):

        g = Github(repo, owner, token)
        issues = g.get_issues("all")

        for d_issue in issues:
            # Extract issue metadata
            issue = AttrDict(d_issue)
            issue_id = f'github-issue-{issue.id}'
            title = issue.title
            description = issue.body
            created_at = str(issue.created_at)
            updated_at = str(issue.updated_at)
            labels = [label.name for label in issue.labels]
            author = issue.user.login
            metadata = {'issue_number': issue.number, 'labels': labels, 'source': 'github', 'url': issue.html_url, 'state': issue.state}

            issue_doc = {
                'documentId': f'github-issue-{issue_id}',
                'title': title,
                'description': description,
                'metadataJson': json.dumps(metadata),
                'section': [{
                    'title': 'issue',
                    'text': description,
                    'metadataJson': json.dumps({
                        'author': author,
                        'created_at': created_at,
                        'updated_at': updated_at
                    })
                }]
            }
            logging.info(f"Indexing issue: {issue.id}")
            self.indexer.index_document(issue_doc)

            # Extract and index comments
            comments = g.get_comments(issue.number)
            if len(comments)>0:
                logging.info(f"Indexing {len(comments)} comments for issue {issue.number}")
            else:
                logging.info(f"No comments for issue {issue.number}")
            
            for d_comment in comments:
                comment = AttrDict(d_comment)
                comment_id = comment.id
                comment_text = comment.body
                comment_author = comment.user.login
                comment_created_at = str(comment.created_at)
                metadata = {'comment_id': comment.id, 'url': comment.html_url, 'source': 'github'}

                comment_doc = {
                    'documentId': f'github-comment-{comment_id}',
                    'title': title,
                    'description': comment_text,
                    'metadataJson': json.dumps(metadata),
                    'section': [{
                        'title': 'comment',
                        'text': comment_text,
                        'metadataJson': json.dumps({
                            'author': comment_author,
                            'created_at': comment_created_at,
                            'updated_at': updated_at
                        })
                    }]
                }
                try:
                    self.indexer.index_document(comment_doc)
                except Exception as e:
                    logging.info(f"Error {e} indexing comment document {comment_doc}")
                    continue

        if self.crawl_code:
            base_url = f"https://api.github.com/repos/{owner}/{repo}"
            self.crawl_code_folder(base_url)


    def crawl(self):
        for repo in self.repos:
            logging.info(f"Crawling repo {repo}")
            self.crawl_repo(repo, self.owner, self.github_token)

