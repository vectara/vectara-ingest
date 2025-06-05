import os
import re
import sys
import requests
from requests.adapters import HTTPAdapter
from requests.models import Response, PreparedRequest
from typing import List, Set, Any, Dict

from urllib3.util.retry import Retry
from urllib.parse import urlparse, urlunparse, ParseResult, urljoin
from pathlib import Path

from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from slugify import slugify

import base64
import magic

import shutil
import pandas as pd
from io import StringIO

import time
import threading
import logging
import glob

from langdetect import detect
from omegaconf import DictConfig

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
    log_level_str = os.getenv("LOGGING_LEVEL", "INFO").upper()

    # Map string to logging level, fallback to INFO if invalid
    log_level = getattr(logging, log_level_str, logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
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
        logging.info("Removing code blocks from HTML")
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


class LoggingAdapter(HTTPAdapter):
    def send(self, request: PreparedRequest, **kwargs) -> Response:
        response = super().send(request, **kwargs)

        log_message = f"""
=== HTTP Request & Response ===
> {request.method} {request.url}
> Headers:
{request.headers}
> Body:
{request.body if request.body else '<empty>'}

< Status: {response.status_code}
< Headers:
{response.headers}
< Body (truncated to 500 chars):
{response.text[:500]}
===============================
"""
        logging.debug(log_message)
        return response

def create_session_with_retries(retries: int = 5) -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 430, 443, 500, 502, 503, 504],  # A set of integer HTTP status codes that we should force a retry on.
        backoff_factor=1,
        raise_on_status=False,
        respect_retry_after_header=True,
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )
    logging_adapter = LoggingAdapter(max_retries=retry_strategy)
    session.mount('http://', logging_adapter)
    session.mount('https://', logging_adapter)
    return session

def configure_session_for_ssl(session: requests.Session, config: DictConfig) -> None:
    """
    Configure SSL settings for a requests session.

    This function updates the SSL verification settings of the provided `requests.Session`
    based on the configuration provided. It allows disabling SSL verification for
    debugging purposes or specifying a custom CA certificate.

    Parameters:
    -----------
    session : requests.Session
        The requests session to configure with SSL settings.

    config : DictConfig
        A dictionary-like object containing SSL-related configuration:
        - "ssl_verify" (bool or str, optional):
          - If `False`, SSL verification is disabled (not recommended for production).
          - If a string, it is treated as the path to a custom CA certificate file or directory.
          - If `True` or not provided, default SSL verification is used.
    """
    ssl_verify = config.get("ssl_verify", None)
    
    if ssl_verify is False or (isinstance(ssl_verify, str) and ssl_verify.lower() in ("false", "0")):
        logging.warning("Disabling ssl verification for session.")
        session.verify = False
        return
    
    if ssl_verify is True or (isinstance(ssl_verify, str) and ssl_verify.lower() in ("true", "1")):
        logging.debug("SSL verify using default system certificates")
        return
    
    if isinstance(ssl_verify, str):
        try:
            # First try direct path (works in Docker and absolute paths)
            if os.path.exists(ssl_verify):
                logging.info(f"Using certificate path: {ssl_verify}")
                session.verify = ssl_verify
                return
        except Exception as e:
            logging.debug(f"Direct path check failed: {e}")
        
        try:
            # Then try expanded path (works with ~)
            ca_path = os.path.expanduser(ssl_verify)
            if os.path.exists(ca_path):
                logging.info(f"Using expanded certificate path: {ca_path}")
                session.verify = ca_path
                return
        except Exception as e:
            logging.debug(f"Expanded path check failed: {e}")
            
        # If we get here, neither path worked
        raise FileNotFoundError(f"Certificate path '{ssl_verify}' could not be found or accessed.")

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
            
            # Replace NaN with an empty string
            if pd.isna(label_at_level):
                label_at_level = ""
            
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
        if isinstance(item, tuple):   # Tuple of (colname, colspan)
            val = '' if pd.isnull(item[0]) else item[0]
            extra_colspan = item[1] - 1
            res.extend([{'text_value': val}] + [{'text_value':''} for _ in range(extra_colspan)])
        elif isinstance(item, str) or isinstance(item, int) or isinstance(item, float) or isinstance(item, bool):
            res.append({'text_value': str(item)})
        else:
            logging.info(f"Create_row_items: unsupported type {type(item)} for item {item}")
    return res

def _expand_table(table_tag):
    """
    Return a list of rows (list of strings), expanding any rowspan/colspan.
    """
    rows_data = []
    # Occupied map tracks which (row, col) positions are already filled
    occupied = {}

    # Gather all <tr>
    all_tr = table_tag.find_all('tr')
    
    for row_idx, tr in enumerate(all_tr):
        # Ensure we have a sublist for this row
        if len(rows_data) <= row_idx:
            rows_data.append([])
        
        # Current column position
        col_idx = 0
        
        # Move over any positions occupied by row-spans from previous rows
        while (row_idx, col_idx) in occupied:
            col_idx += 1

        cells = tr.find_all(['td','th'])
        for cell in cells:
            # Skip forward if the current position is occupied
            while (row_idx, col_idx) in occupied:
                col_idx += 1
            
            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))
            text = cell.get_text(strip=True)
            
            # Expand rows_data if needed
            while len(rows_data[row_idx]) < col_idx:
                rows_data[row_idx].append('')
            # Make sure the current row has enough columns
            while len(rows_data[row_idx]) < col_idx + colspan:
                rows_data[row_idx].append('')
            
            # Place text in all spanned columns of the current row
            for c in range(colspan):
                rows_data[row_idx][col_idx + c] = text
            
            # If there's a rowspan > 1, mark those positions as occupied
            # so we duplicate the text in subsequent rows
            for r in range(1, rowspan):
                rpos = row_idx + r
                # Ensure rows_data has enough rows
                while len(rows_data) <= rpos:
                    rows_data.append([])
                for c in range(colspan):
                    # Expand that row's columns if needed
                    while len(rows_data[rpos]) < col_idx + c:
                        rows_data[rpos].append('')
                    rows_data[rpos].append('')
                    # Mark the future cell as occupied with the same text
                    occupied[(rpos, col_idx + c)] = text
            
            col_idx += colspan
    
    # Normalize all rows to the same length
    max_cols = max(len(r) for r in rows_data) if rows_data else 0
    for r in rows_data:
        while len(r) < max_cols:
            r.append('')
    return rows_data

def html_table_to_header_and_rows(html):
    """
    Parse the FIRST <table> from 'html' into a header row + data rows.
    All 'rowspan'/'colspan' cells are expanded (duplicated) so each row
    in the final output has the same number of columns.
    
    Returns:
      (header, rows)
    where
      header: list of cell texts for the first row
      rows: list of lists of cell texts for subsequent rows
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table')
    if not table:
        return [], []

    # Expand into a full 2D list of rows
    matrix = _expand_table(table)
    if not matrix:
        return [], []
    
    # First row is the "header"
    header = matrix[0]
    rows = matrix[1:]

    return header, rows

def get_media_type_from_base64(base64_data: str) -> str:
    file_bytes = base64.b64decode(base64_data)
    media_type = magic.Magic(mime=True).from_buffer(file_bytes)    
    return media_type


def get_docker_or_local_path(docker_path: str, output_dir: str = "vectara_ingest_output", should_delete_existing: bool = False, config_path: str = None) -> str:
    """
    Get appropriate path for storing files or reading data.
    
    Args:
        docker_path: Legacy parameter, kept for backwards compatibility
        output_dir: Output directory name for local path (can include subdirectories). Defaults to "vectara_ingest_output".
        should_delete_existing: Whether to delete existing directory if it exists
        config_path: Optional config path to try if docker path not found
        
    Returns:
        str: The resolved path (Docker, config, or local)
        
    Raises:
        FileNotFoundError: If config_path is provided but doesn't exist
    """
    # Try Docker path first
    if os.path.exists(docker_path):
        logging.info(f"Using Docker path: {docker_path}")
        return docker_path
        
    # Try config path if provided
    if config_path:
        if os.path.exists(config_path):
            logging.info(f"Using config path: {config_path}")
            return config_path
        else:
            raise FileNotFoundError(f"Config path '{config_path}' was specified but could not be found.")
        
    # Fall back to local path
    local_path = os.path.join(os.getcwd(), output_dir)
    
    # Delete existing directory if requested
    if should_delete_existing and os.path.exists(local_path):
        shutil.rmtree(local_path)
            
    # Create directory (and parent directories) if it doesn't exist
    os.makedirs(local_path, exist_ok=True)
            
    logging.info(f"Using local path: {local_path}")
    return local_path
