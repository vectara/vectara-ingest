import os
import re
import sys
import requests
from typing import List, Set, Any, Dict

from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse, ParseResult, urljoin
from pathlib import Path

from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from slugify import slugify
import magic

import shutil
import pandas as pd
from io import StringIO

import time
import threading
import logging

from langdetect import detect

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

def url_to_filename(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    last_part = path_parts[-1]
    name, ext = os.path.splitext(last_part)
    slugified_name = slugify(name)
    return f"{slugified_name}{ext}"

def detect_file_type(file_path):
    """
    Detect the type of a file using the `magic` library and further analysis.
    
    Returns:
        str: The detected MIME type, e.g., 'text/html', 'application/xml', etc.
    """
    # Initialize magic for MIME type detection
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(file_path)
    
    # Define MIME types that require further inspection
    ambiguous_mime_types = ['text/html', 'application/xml', 'text/xml', 'application/xhtml+xml']    
    if mime_type in ambiguous_mime_types:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except UnicodeDecodeError:
            # If the file isn't UTF-8 encoded, it might not be HTML or XML
            return mime_type
        
        stripped_content = content.lstrip()
        if stripped_content.startswith('<?xml'):
            return 'application/xml'
        
        # Use BeautifulSoup to parse as HTML
        soup = BeautifulSoup(content, 'html.parser')
        if soup.find('html'):
            return 'text/html'
        
        # Attempt to parse as XML
        try:
            ET.fromstring(content)
            return 'application/xml'
        except ET.ParseError:
            pass  # Not well-formed XML
        
        # Fallback to magic-detected MIME type if unsure
    return mime_type
    
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
        for element in soup.find_all(id=id):
            element.decompose()

    # remove any HTML tags in the list
    tags_to_remove = html_processing.get('tags_to_remove', [])
    for tag in tags_to_remove:
        for element in soup.find_all(tag):
            element.decompose()

    # remove any elements with these classes
    classes_to_remove = html_processing.get('classes_to_remove', [])
    for class_name in classes_to_remove:
        for element in soup.find_all(class_=class_name):
            element.decompose()
        
    text = soup.get_text(' ', strip=True).replace('\n', ' ')
    return text

def safe_remove_file(file_path: str):
    try:
        os.remove(file_path)
    except Exception as e:
        logging.info(f"Failed to remove file: {file_path} due to {e}")

def create_session_with_retries(retries: int = 5) -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 430, 443, 500, 502, 503, 504],  # A set of integer HTTP status codes that we should force a retry on.
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
    netloc = p.netloc[4:] if p.netloc.startswith('www.') else p.netloc
    path = p.path if p.path and p.path != '/' else '/'
    query = p.query if keep_query_params else ''
    return ParseResult(p.scheme, netloc, path, '', query, '').geturl()

def clean_urls(urls: Set[str], keep_query_params: bool = False) -> List[str]:
    normalized_set = set()
    for url in urls:
        normalized_url = normalize_url(url, keep_query_params)
        normalized_set.add(normalized_url)
    return list(normalized_set)

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

def df_cols_to_headers(df: pd.DataFrame):
    """
    Returns the columns of a pandas dataframe.
    1. If it's a simple header - return a list with a single list of column names.
    2. If it's a MultiIndex, return a list of headers with colspans
    
    Parameters
    ----------
    df : pd.DataFrame
        The input Dataframe

    Returns
    -------
    List[str] or List[List[Tuple[str, int]]]
    """
    columns = df.columns
    if not isinstance(columns, pd.MultiIndex):
        return [list(columns)]
    
    n_levels = columns.nlevels
    rows = []

    # For each level i, we scan the columns in order
    # and group consecutive columns with the same label at that level.
    for level in range(n_levels):
        row = []
        
        current_label = None
        current_colspan = 0
        
        # Iterate over each column's tuple
        for col_tuple in columns:
            label_at_level = col_tuple[level]
            
            if label_at_level == current_label:
                # Same label → increase the colspan
                current_colspan += 1
            else:
                # Different label → push the previous label/colspan to row
                if current_label is not None:
                    row.append((current_label, current_colspan))
                
                # Start a new group
                current_label = label_at_level
                current_colspan = 1
        
        # Don't forget the last one
        if current_label is not None:
            row.append((current_label, current_colspan))
        
        rows.append(row)

    return rows

def get_file_path_from_url(url):
    path = urlparse(url).path
    # Get the file name (last segment of path)
    filename = os.path.basename(path)
    # Strip off any trailing query string if present
    filename = filename.split("?")[0]
    
    # Split into name + extension
    name_part, ext = os.path.splitext(filename)
    
    # Slugify the name part only
    slugified_name = slugify(name_part)
    
    # Construct new filename
    new_filename = f"{slugified_name}{ext}"
    return new_filename

def markdown_to_df(markdown_table):
    table_io = StringIO(markdown_table.strip())
    lines = table_io.readlines()
    
    if not lines:
        return pd.DataFrame()
    
    # Read header and clean it
    header = [col.strip() for col in lines[0].strip().split('|')]
    # Remove empty strings at start/end if present
    header = [col for col in header if col]
    
    # Check if the second row is a separator row
    if len(lines) > 1 and all(col.strip('- ') == '' for col in lines[1].strip().split('|') if col):
        data_lines = lines[2:]
    else:
        data_lines = lines[1:]
    
    # Parse data rows
    rows = []
    for line in data_lines:
        # Split and clean each row
        row = [cell.strip() for cell in line.strip().split('|')]
        # Remove empty strings at start/end if present
        row = [cell for cell in row if cell]
        rows.append(row)
    
    if not rows:
        return pd.DataFrame(columns=header)
    
    # Find the maximum number of columns
    max_cols = max(len(header), max(len(row) for row in rows))
    
    # Extend header if necessary
    if len(header) < max_cols:
        header.extend([f'Column_{i+1}' for i in range(len(header), max_cols)])
    
    # Extend rows if necessary
    cleaned_rows = [row + [''] * (max_cols - len(row)) for row in rows]
    
    # Create DataFrame
    df = pd.DataFrame(cleaned_rows, columns=header[:max_cols])
    return df

def create_row_items(items: List[Any]) -> List[Dict[str, Any]]:
    res = []
    for item in items:
        if isinstance(item, str):
            res.append({'text_value': item})
        elif isinstance(item, int):
            res.append({'int_value': item})
        elif isinstance(item, float):
            res.append({'float_value': item})
        elif isinstance(item, bool):
            res.append({'bool_value': item})
        else:
            logging.info(f"Unsupported type {type(item)} for item {item}")
    return res

