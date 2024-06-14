import requests
from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse, ParseResult
from pathlib import Path

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

import re
from typing import List, Set
import os
import sys
import shutil

import time
import threading
import logging

from langdetect import detect
from openai import OpenAI

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
except ImportError:
    logging.info("Presidio is not installed. if PII detection and masking is requested - it will not work.")


img_extensions = [".gif", ".jpeg", ".jpg", ".mp3", ".mp4", ".png", ".svg", ".bmp", ".eps", ".ico"]
doc_extensions = [".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".pdf", ".ps"]
archive_extensions = [".zip", ".gz", ".tar", ".bz2", ".7z", ".rar"]
binary_extensions = archive_extensions + img_extensions + doc_extensions

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

def remove_code_from_html(html: str) -> str:
    """Remove code and script tags from HTML."""
    soup = BeautifulSoup(html, 'html5lib')
    for element in soup.find_all(['code']):
        element.decompose()
    return str(soup)

def html_to_text(html: str, remove_code: bool = False, html_processing: dict = {}) -> str:
    """Convert HTML to text, optionally removing code blocks."""

    # Remove code blocks if specified
    if remove_code:
        html = remove_code_from_html(html)

    # Initialize BeautifulSoup
    soup = BeautifulSoup(html, 'html5lib')

    # Remove unwanted HTML elements
    for element in soup.find_all(['script', 'style']):
        element.decompose()

    # remove any HTML items with the specified IDs
    ids_to_remove = html_processing.get('ids_to_remove', [])
    for id in ids_to_remove:
        element = soup.find(id=id)
        if element:
            element.decompose()

    # remove any HTML tags
    tags_to_remove = html_processing.get('tags_to_remove', [])
    for tag in tags_to_remove:
        for element in soup.find_all(tag):
            element.decompose()

    text = soup.get_text(" ", strip=True).replace('\n', ' ')
    return text


def create_session_with_retries(retries: int = 3) -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 430, 500, 502, 503, 504],  # A set of integer HTTP status codes that we should force a retry on.
        backoff_factor=1,
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def remove_anchor(url: str) -> str:
    """Remove the anchor from a URL."""
    parsed = urlparse(url)
    url_without_anchor = urlunparse(parsed._replace(fragment=""))
    return url_without_anchor

def normalize_url(url: str, keep_query_params: bool = False) -> str:
    """Normalize a URL by removing query parameters."""    
    # Prepend with 'http://' if URL has no scheme
    if '://' not in url:
        url = 'http://' + url
    p = urlparse(url)
    query = p.query if keep_query_params else ''
    return ParseResult(p.scheme, p.netloc, p.path, '', query, '').geturl()

def clean_urls(urls: Set[str], keep_query_params: bool = False) -> List[str]:
    return list(set(normalize_url(url, keep_query_params) for url in urls))

def clean_email_text(text: str) -> str:
    """
    Clean the text email by removing any unnecessary characters and indentation.
    This function can be extended to clean emails in other ways.
    """    
    cleaned_text = text.strip()
    cleaned_text = re.sub(r"[<>]+", "", cleaned_text, flags=re.MULTILINE)
    return cleaned_text

def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        return str(lang)
    except Exception as e:
        logging.info(f"Language detection failed with error: {e}")
        return "en"  # Default to English in case of errors

def get_file_size_in_MB(file_path: str) -> float:
    file_size_bytes = os.path.getsize(file_path)
    file_size_MB = file_size_bytes / (1024 * 1024)    
    return file_size_MB

def get_file_extension(url):
    # Parse the URL to get the path component
    path = urlparse(url).path
    # Use pathlib to extract the file extension
    return Path(path).suffix.lower()

def ensure_empty_folder(folder_name):
    # Check if the folder exists
    if os.path.exists(folder_name):
        # Remove the folder and all its contents
        shutil.rmtree(folder_name)
    # Create the folder anew
    os.makedirs(folder_name)

class TableSummarizer():
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)

    def summarize_table_text(self, text: str):
        response = self.client.chat.completions.create(
            model="gpt-4o",   # GPT4o
            messages=[
                {"role": "system", "content": "You are a helpful assistant tasked with summarizing tables."},
                {"role": "user", "content": f"""
                    Adopt the perspective of a data analyst. 
                    Summarize the key results reported in this table without omitting critical details.
                    Make sure your summary is concise, informative and comprehensive.
                    Table chunk: {text} 
                 """
                }
            ],
            temperature=0
        )
        return response.choices[0].message.content

def mask_pii(text: str) -> str:
    # Analyze and anonymize PII data in the text
    results = analyzer.analyze(
        text=text,
        entities=["PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "PERSON", 
                  "US_BANK_NUMBER", "US_PASSPORT", "US_SSN", "LOCATION"],
        language='en')    
    anonymized_text = anonymizer.anonymize(text=text, analyzer_results=results)
    return str(anonymized_text.text)

# Rate Limiter class
# Existing packages are not well maintained so we create our own (using ChatGPT)
class RateLimiter:
    def __init__(self, max_rate):
        self.max_rate = max_rate
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.num_executions = 0
        self.start_time = time.time()

    def __enter__(self):
        with self.lock:
            current_time = time.time()
            elapsed_time = current_time - self.start_time

            if elapsed_time >= 1:
                # Reset counter and timer after a second
                self.num_executions = 0
                self.start_time = current_time
            else:
                if self.num_executions >= self.max_rate:
                    # Wait until the second is up if limit is reached
                    time_to_wait = 1 - elapsed_time
                    self.condition.wait(timeout=time_to_wait)
                    # Reset after waiting
                    self.num_executions = 0
                    self.start_time = time.time()

            # Increment the count of executions
            self.num_executions += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        with self.lock:
            self.condition.notify()

def get_urls_from_sitemap(homepage_url):
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    # Helper function to fetch and parse XML
    def fetch_sitemap(sitemap_url):
        try:
            response = requests.get(sitemap_url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'xml')
            return soup
        except requests.exceptions.RequestException as e:
            logging.warning(f"Failed to fetch sitemap: {sitemap_url} due to {e}")
            return None
    
    # Step 1: Check for standard sitemap.xml
    sitemap_url = urljoin(homepage_url, 'sitemap.xml')
    soup = fetch_sitemap(sitemap_url)
    
    sitemaps = []
    if soup:
        sitemaps.append(sitemap_url)
    
    # Step 2: Check for sitemaps in robots.txt
    robots_url = urljoin(homepage_url, 'robots.txt')
    try:
        response = requests.get(robots_url, headers=headers)
        response.raise_for_status()
        for line in response.text.split('\n'):
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                sitemaps.append(sitemap_url)
    except requests.exceptions.RequestException as e:
        logging.info(f"Failed to fetch robots.txt: {robots_url} due to {e}")
    
    # Step 3: Extract URLs from all found sitemaps
    urls = set()
    for sitemap in sitemaps:
        soup = fetch_sitemap(sitemap)
        if soup:
            for loc in soup.find_all('loc'):
                urls.add(loc.text.strip())
    
    return list(urls)