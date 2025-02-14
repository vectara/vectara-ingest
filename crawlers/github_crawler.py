import json
from typing import List, Any
from datetime import datetime
import logging
import base64

from box import Box
from omegaconf import OmegaConf

import requests
import markdown

from core.crawler import Crawler
from core.utils import create_session_with_retries, html_to_text, RateLimiter

def clean_empty_sections(doc: dict) -> dict:
    len_before = len(doc['sections'])
    doc['sections'] = [section for section in doc['sections'] if section['text']]
    len_after = len(doc['sections'])
    if len_after < len_before:
        logging.info(f"Removed {len_before-len_after} empty sections for doc {doc['id']}")
    return doc

def convert_date(date_str: str) -> str:
    # Remove the 'Z' at the end and parse the date string to a datetime object
    date_obj = datetime.fromisoformat(date_str.replace("Z", ""))
    
    # Format the datetime object to a string in the format YYYY-MM-DD
    normal_date = date_obj.strftime("%Y-%m-%d")
    
    return normal_date

class Github(object):
    def __init__(self, repo: str, owner: str, token: str) -> None:
        self.repo = repo
        self.owner = owner
        self.token = token
        self.session = create_session_with_retries()

    def get_issues(self, state: str) -> List[Any]:
        # state can be "open", "closed", or "all"
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues?state={state}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return list(response.json())
        else:
            logging.info(f"Error retrieving issues: {response.status_code}, {response.text}")
            return []

    def get_issue_comments(self, issue_number: str) -> List[Any]:
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return list(response.json())
        else:
            logging.info(f"Error retrieving comments: {response.status_code}, {response.text}")
            return []
        
    def get_pull_requests(self, state: str) -> List[Any]:
        # state can be "open", "closed", "all", or "merged"
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls?state={state}"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return list(response.json())
        else:
            logging.info(f"Error retrieving pull requests: {response.status_code}, {response.text}")
            return []        

    def get_pr_comments(self, pull_number: int) -> List[Any]:
        api_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{pull_number}/comments"
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        response = self.session.get(api_url, headers=headers)
        if response.status_code == 200:
            return list(response.json())
        else:
            logging.info(f"Error retrieving comments for pull request #{pull_number}: {response.status_code}, {response.text}")
            return []

class GithubCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.github_token = self.cfg.github_crawler.get("github_token", None)
        self.owner = self.cfg.github_crawler.owner
        self.repos = self.cfg.github_crawler.repos
        self.crawl_code = self.cfg.github_crawler.crawl_code
        self.rate_limiter = RateLimiter(self.cfg.github_crawler.get("num_per_second", 2))
        self.session = create_session_with_retries()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def crawl_code_folder(self, base_url: str, repo: str, path: str = "") -> None:
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

                    text_content = html_to_text(markdown.markdown(file_content))
                    metadata = {'file': fname, 'source': 'github', 'url': url}
                    code_doc = {
                        'id': f'github-{repo}-{item["path"]}',
                        'title': item["name"],
                        'description': f'Markdown of {fname}',
                        'metadata': metadata,
                        'sections': [{
                            'title': 'markdown',
                            'text': text_content,
                        }]
                    }

                    logging.info(f"Indexing codebase markdown: {item['path']}")
                    self.indexer.index_document(code_doc)
            elif item["type"] == "dir":
                self.crawl_code_folder(base_url, repo=repo, path=item["path"])

    def add_comments(self, doc: dict, comments: List[Any]) -> None:
        for d_comment in comments:
            comment = Box(d_comment)
            metadata = {
                'id': comment.id, 'url': comment.html_url, 'source': 'github',
                'author': comment.user.login, 'created_at': convert_date(comment.created_at), 'last_modified': convert_date(comment.updated_at)
            }
            doc['sections'].append({
                'title': f'comment by {comment.user.login}',
                'text': comment.body,
                'metadata': metadata,
            })

    def crawl_repo(self, repo: str, owner: str, token: str) -> None:

        # create github object
        g = Github(repo, owner, token)

        # Extract and index pull requests
        prs = g.get_pull_requests("all")
        for d_pr in prs:
            pr = Box(d_pr)
            doc_metadata = {
                'source': 'github',
                'id': pr.id, 
                'number': pr.number,
                'url': pr.html_url, 
                'title': pr.title,
                'state': pr.state,
                'author': pr.user.login,
                'created_at': convert_date(pr.created_at),
                'last_modified': convert_date(pr.updated_at)
            }
            pr_doc = {
                'id': f'github-{repo}-pr-{pr.number}',
                'title': pr.title,
                'metadata': doc_metadata,
                'sections': [{
                    'title': pr.title,
                    'text': pr.body if pr.body else "",
                }]
            }

            comments = g.get_pr_comments(pr.number)
            if len(comments)>0:
                logging.info(f"Adding {len(comments)} comments for repo {repo}, PR {pr.number}")
                self.add_comments(pr_doc, comments)
            else:
                logging.info(f"No comments for repo {repo}, PR {pr.number}")

            # remove any empty text sections
            pr_doc = clean_empty_sections(pr_doc)
            if len(pr_doc['sections']) == 0:
                logging.info(f"No text sections for repo {repo}, PR {pr.number}")
                continue

            # index everything
            try:
                self.indexer.index_document(pr_doc)
            except Exception as e:
                logging.info(f"Error {e} indexing comment for repo {repo} document {pr_doc}")
                continue

        # Extract and index issues and comments
        issues = g.get_issues("all")
        for d_issue in issues:
            # Extract issue metadata
            issue = Box(d_issue)
            title = issue.title
            description = issue.body
            created_at = convert_date(issue.created_at)
            updated_at = convert_date(issue.updated_at)
            labels = [label.name for label in issue.labels]
            author = issue.user.login
            metadata = {'issue_number': issue.number, 'labels': labels, 'source': 'github', 'url': issue.html_url, 'state': issue.state}

            issue_doc = {
                'id': f'github-{repo}-issue-{issue.number}',
                'title': title,
                'description': description,
                'metadata': metadata,
                'sections': [{
                    'title': 'issue',
                    'text': description,
                    'metadata': {
                        'author': author,
                        'created_at': created_at,
                        'last_modified': updated_at
                    }
                }]
            }

            # Extract comments
            comments = g.get_issue_comments(issue.number)
            if len(comments)>0:
                logging.info(f"Adding {len(comments)} comments for repo {repo} issue {issue.number}")
                self.add_comments(issue_doc, comments)
            else:
                logging.info(f"No comments for repo {repo}, issue {issue.number}")

            issue_doc = clean_empty_sections(issue_doc)
            if len(pr_doc['sections']) == 0:
                logging.info(f"No text sections for repo {repo}, issue {issue.number}")
                continue

            # index everything
            logging.info(f"Indexing issue: {issue.number}")
            try:
                self.indexer.index_document(issue_doc)
            except Exception as e:
                logging.info(f"Error {e} indexing repo {repo}, comment document {issue_doc}")
                continue


        # Extract and index codebase if requested
        if self.crawl_code:
            base_url = f"https://api.github.com/repos/{owner}/{repo}"
            self.crawl_code_folder(base_url, repo)

    def crawl(self) -> None:
        for repo in self.repos:
            logging.info(f"Crawling repo {repo}")
            self.crawl_repo(repo, self.owner, self.github_token)
