import os
from core.crawler import Crawler
from git import Repo
import logging
from pathlib import Path
import fnmatch
from omegaconf import OmegaConf
from markdown import markdown
from bs4 import BeautifulSoup

def find_files_with_extension(extension, root_dir='.'):
    matches = []
    # Make sure the extension starts with a dot
    if not extension.startswith('.'):
        extension = '.' + extension
    for root, _, filenames in os.walk(root_dir):
        for filename in fnmatch.filter(filenames, '*' + extension):
            matches.append(os.path.join(root, filename))
    return matches

def md_to_text(md):
    html = markdown(md)
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()

class DocusaurusCrawler(Crawler):
    
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.repo_url = self.cfg.docusaurus_crawler.docs_repo
        self.docs_homepage = self.cfg.docusaurus_crawler.docs_homepage
        path_in_repo = self.cfg.docusaurus_crawler.get("docs_path", "")
        local_folder = 'tmp/docs_repo/'
        os.makedirs(local_folder, exist_ok=True)
        Repo.clone_from(self.repo_url, local_folder)
        self.base_path = local_folder
        self.docs_path = os.path.join(local_folder, path_in_repo)
        
    def crawl(self):
        markdown_files = find_files_with_extension('.md', self.docs_path) + find_files_with_extension('.mdx', self.docs_path)
        for file_path in markdown_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            fname = Path(file_path).name

            if '---' in content and 'id:' in content and 'title:' in content:
                dh = content.split('---')[1]
                id_str = dh.split('id:')[1].split('\n')[0].strip()
                title = dh.split('title:')[1].split('\n')[0].strip()
                if 'slug:' in dh:
                    slug_str = dh.split('slug:')[1].split('\n')[0].strip()
                    source_path = os.path.join(self.docs_homepage, str(Path(file_path).relative_to(self.docs_path)))
                    if slug_str == '/':
                        source_path = source_path.replace(fname, '')
                    else:
                        source_path = source_path.replace(fname, slug_str)
                else:
                    source_path = os.path.join(self.docs_homepage, str(Path(file_path).relative_to(self.docs_path)).replace(fname, id_str))                
            else:
                source_path = os.path.join(self.docs_homepage, str(Path(file_path).relative_to(self.docs_path)))
                title = fname

            logging.info(f"Indexing {file_path} with source path {source_path}, title={title}")

            fname = 'doc_text.txt'
            with open(fname, 'w') as f:
                f.write(md_to_text(content))

            metadata = {'title': title, 'source': 'docusaurus', 'url': source_path}
            self.indexer.index_file(fname, uri=source_path, metadata=metadata)
