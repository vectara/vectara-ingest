# Standard library imports
import base64
import logging
import os
import re
import shutil
import sys
import threading
import time
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import List, Set, Any, Dict
from urllib.parse import urlparse, urlunparse, ParseResult, urljoin, unquote

# Third-party imports
import magic
import pandas as pd
import requests
from bs4 import BeautifulSoup
from langdetect import detect
from omegaconf import DictConfig, OmegaConf
from requests.adapters import HTTPAdapter
from requests.models import Response, PreparedRequest
from slugify import slugify
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# File extensions
IMG_EXTENSIONS = [".gif", ".jpeg", ".jpg", ".png", ".svg", ".bmp", ".eps", ".ico", ".webp", ".tiff", ".tif"]
AUDIO_EXTENSIONS = [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"]
VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".webm", ".mkv", ".wmv", ".flv", ".mpeg", ".mpg", ".m4v", ".3gp", ".f4v"]
# Document extensions: binary documents + text-based formats (excluding dataframes)
DOC_EXTENSIONS = [".doc", ".docx", ".ppt", ".pptx", ".pdf", ".ps", ".txt", ".md", ".html", ".htm", ".rtf", ".epub", ".odt", ".lxml"]
# Dataframe extensions: CSV and Excel files (handled separately with DataframeParser)
DATAFRAME_EXTENSIONS = [".csv", ".xls", ".xlsx"]
ARCHIVE_EXTENSIONS = [".zip", ".gz", ".tar", ".bz2", ".7z", ".rar"]
BINARY_EXTENSIONS = ARCHIVE_EXTENSIONS + IMG_EXTENSIONS + AUDIO_EXTENSIONS + VIDEO_EXTENSIONS + DOC_EXTENSIONS

# HTTP configurations
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Retry configurations
DEFAULT_RETRY_ATTEMPTS = 5
DEFAULT_RETRY_STATUS_CODES = [429, 430, 443, 500, 502, 503, 504]
DEFAULT_RETRY_BACKOFF_FACTOR = 1
DEFAULT_RETRY_METHODS = ["HEAD", "GET", "OPTIONS", "POST"]

# MIME types
AMBIGUOUS_MIME_TYPES = ['text/html', 'application/xml', 'text/xml', 'application/xhtml+xml']

# PII detection entities
PII_ENTITIES = [
    "PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "PERSON",
    "US_BANK_NUMBER", "US_PASSPORT", "US_SSN", "LOCATION"
]

# Regex patterns (compiled at module level for performance)
LOGGER_ENV_PATTERN = re.compile(r'^LOGGER_([A-Z0-9_]+)_LEVEL$')
SITEMAP_PATTERN = re.compile(r'^sitemap:', re.IGNORECASE)

# =============================================================================
# PRESIDIO INITIALIZATION
# =============================================================================

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    PRESIDIO_AVAILABLE = True
except ImportError:
    logger.info("Presidio is not installed. PII masking will be skipped.")
    analyzer = None
    anonymizer = None
    PRESIDIO_AVAILABLE = False

# Legacy constants for backward compatibility
img_extensions = IMG_EXTENSIONS
audio_extensions = AUDIO_EXTENSIONS
video_extensions = VIDEO_EXTENSIONS
doc_extensions = DOC_EXTENSIONS
archive_extensions = ARCHIVE_EXTENSIONS
binary_extensions = BINARY_EXTENSIONS
dataframe_extensions = DATAFRAME_EXTENSIONS
spreadsheet_extensions = DATAFRAME_EXTENSIONS  # Deprecated: use DATAFRAME_EXTENSIONS instead

# =============================================================================
# LOGGING UTILITIES
# =============================================================================

def setup_logging(level='INFO'):
    log_level_str = os.getenv("LOGGING_LEVEL", level).upper()

    # Map string to logging level, fallback to INFO if invalid
    log_level = getattr(logging, log_level_str, logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    
    # Only add handler if none exists to prevent duplicates
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        root.addHandler(handler)

    logger.debug("Setting logging levels")
    # Configure specific loggers based on environment variables
    for env_key, log_level_str in os.environ.items():
        match = LOGGER_ENV_PATTERN.match(env_key)
        if match:
            logger_name = match.group(1).lower().replace('_', '.')
            level_name = log_level_str.upper()
            level = getattr(logging, level_name, None)
            if level:
                logger.debug(f"Changing logging level for {logger_name} to {level_name}:{level}.")
                logging.getLogger(logger_name).setLevel(level)
            else:
                logger.warning(f"Could not change logger {logger_name} to unknown level {level_name}.")

# =============================================================================
# FILE UTILITIES
# =============================================================================

def url_to_filename(url):
    """
    Convert a URL to a safe filename by extracting the path and slugifying it.
    
    Args:
        url (str): The URL to convert to a filename
        
    Returns:
        str: A safe filename based on the URL path
    """
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    last_part = path_parts[-1]
    # URL-decode the filename to handle %20 and other encoded characters properly
    decoded_part = unquote(last_part)
    name, ext = os.path.splitext(decoded_part)
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
    if mime_type in AMBIGUOUS_MIME_TYPES:
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
        logger.info("Removing code blocks from HTML")
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
    """
    Safely remove a file, logging warnings if removal fails.
    
    Args:
        file_path (str): Path to the file to remove
    """
    try:
        os.remove(file_path)
    except Exception as e:
        logger.warning(f"Failed to remove file: {file_path} due to {e}")

# =============================================================================
# HTTP UTILITIES
# =============================================================================

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
        logger.debug(log_message)
        return response

def create_session_with_retries(retries: int = DEFAULT_RETRY_ATTEMPTS) -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        status_forcelist=DEFAULT_RETRY_STATUS_CODES,
        backoff_factor=DEFAULT_RETRY_BACKOFF_FACTOR,
        raise_on_status=False,
        respect_retry_after_header=True,
        allowed_methods=DEFAULT_RETRY_METHODS,
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
        logger.warning("Disabling ssl verification for session.")
        session.verify = False
        return

    if ssl_verify is True or (isinstance(ssl_verify, str) and ssl_verify.lower() in ("true", "1")):
        logger.debug("SSL verify using default system certificates")
        return

    if isinstance(ssl_verify, str):
        try:
            # First try direct path (works in Docker and absolute paths)
            if os.path.exists(ssl_verify):
                logger.info(f"Using certificate path: {ssl_verify}")
                session.verify = ssl_verify
                return
        except Exception as e:
            logger.debug(f"Direct path check failed: {e}")

        try:
            # Then try expanded path (works with ~)
            ca_path = os.path.expanduser(ssl_verify)
            if os.path.exists(ca_path):
                logger.info(f"Using expanded certificate path: {ca_path}")
                session.verify = ca_path
                return
        except Exception as e:
            logger.debug(f"Expanded path check failed: {e}")

        # If we get here, neither path worked
        raise FileNotFoundError(f"Certificate path '{ssl_verify}' could not be found or accessed.")

# =============================================================================
# URL UTILITIES
# =============================================================================


def normalize_url(url: str, keep_query_params: bool = False) -> str:
    """
    Normalize a URL by removing query parameters and standardizing format.
    
    Args:
        url (str): URL to normalize
        keep_query_params (bool): Whether to preserve query parameters
        
    Returns:
        str: Normalized URL
    """
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
    """
    Clean and normalize a set of URLs.
    
    Args:
        urls (Set[str]): Set of URLs to clean
        keep_query_params (bool): Whether to preserve query parameters
        
    Returns:
        List[str]: List of cleaned URLs
    """
    normalized_set = set()
    for url in urls:
        normalized_url = normalize_url(url, keep_query_params)
        normalized_set.add(normalized_url)
    return list(normalized_set)

# =============================================================================
# TEXT UTILITIES
# =============================================================================

def clean_email_text(text: str) -> str:
    """
    Clean email text by removing unnecessary characters and indentation.
    
    Args:
        text (str): Email text to clean
        
    Returns:
        str: Cleaned email text
    """
    """
    Clean the text email by removing any unnecessary characters and indentation.
    This function can be extended to clean emails in other ways.
    """
    cleaned_text = text.strip()
    cleaned_text = re.sub(r"[<>]+", "", cleaned_text, flags=re.MULTILINE)
    return cleaned_text

def detect_language(text: str) -> str:
    """
    Detect the language of the given text using langdetect.
    
    Args:
        text (str): Text to analyze for language
        
    Returns:
        str: Language code (defaults to 'en' if detection fails)
    """
    try:
        lang = detect(text)
        return str(lang)
    except Exception as e:
        logger.warning(f"Language detection failed with error: {e}")
        return "en"  # Default to English in case of errors

def get_file_size_in_MB(file_path: str) -> float:
    """
    Get the file size in megabytes.
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        float: File size in MB
    """
    file_size_bytes = os.path.getsize(file_path)
    file_size_MB = file_size_bytes / (1024 * 1024)
    return file_size_MB

def get_file_extension(url):
    """
    Extract the file extension from a URL.
    
    Args:
        url (str): URL to extract extension from
        
    Returns:
        str: File extension in lowercase
    """
    # Parse the URL to get the path component
    path = urlparse(url).path
    # Use pathlib to extract the file extension
    return Path(path).suffix.lower()


def mask_pii(text: str) -> str:
    """
    Mask personally identifiable information (PII) in text using Presidio.

    If Presidio is not installed, returns the original text unchanged and logs a warning once.

    Args:
        text (str): Text to analyze and mask PII

    Returns:
        str: Text with PII masked if Presidio is available, otherwise original text
    """
    if not PRESIDIO_AVAILABLE:
        # Log warning only once to avoid spamming logs
        if not hasattr(mask_pii, '_warning_logged'):
            logger.warning("Presidio is not installed. PII masking is disabled. Install presidio-analyzer and presidio-anonymizer to enable PII masking.")
            mask_pii._warning_logged = True
        return text

    try:
        # Analyze and anonymize PII data in the text
        results = analyzer.analyze(
            text=text,
            entities=PII_ENTITIES,
            language='en')
        anonymized_text = anonymizer.anonymize(text=text, analyzer_results=results)
        return str(anonymized_text.text)
    except Exception as e:
        logger.error(f"Error during PII masking: {e}. Returning original text.")
        return text


def normalize_text(text: str, cfg: OmegaConf) -> str:
    """
    Normalize text by applying Unicode normalization and optional PII masking.
    
    Args:
        text (str): The text to normalize
        cfg (OmegaConf): Configuration object containing vectara settings
        
    Returns:
        str: Normalized text
    """
    import unicodedata
    import pandas as pd
    
    if pd.isnull(text) or len(text) == 0:
        return text
    
    if cfg.vectara.get("mask_pii", False):
        text = mask_pii(text)
    
    text = unicodedata.normalize('NFD', text)
    return text


def normalize_value(value, cfg: OmegaConf):
    """
    Normalize a value by applying text normalization if it's a string.
    
    Args:
        value: The value to normalize
        cfg (OmegaConf): Configuration object containing vectara settings
        
    Returns:
        The normalized value
    """
    if isinstance(value, str):
        return normalize_text(value, cfg)
    return value

# =============================================================================
# CONCURRENCY UTILITIES
# =============================================================================

# Rate Limiter class
# Existing packages are not well maintained so we create our own (using ChatGPT)
class RateLimiter:
    """
    A thread-safe rate limiter using sliding window approach.
    
    Args:
        max_rate (int): Maximum number of executions per second
        window_size (float): Time window in seconds (default: 1.0)
    """
    
    def __init__(self, max_rate: int, window_size: float = 1.0):
        self.max_rate = max_rate
        self.window_size = window_size
        self.lock = threading.RLock()  # Use RLock for better performance
        self.executions = []  # Store timestamps of recent executions
        
    def __enter__(self):
        with self.lock:
            current_time = time.time()
            
            # Remove old executions outside the window
            cutoff_time = current_time - self.window_size
            self.executions = [t for t in self.executions if t > cutoff_time]
            
            # Check if we've exceeded the rate limit
            if len(self.executions) >= self.max_rate:
                # Calculate how long to wait
                oldest_execution = self.executions[0]
                wait_time = oldest_execution + self.window_size - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
                    # Clean up again after waiting
                    current_time = time.time()
                    cutoff_time = current_time - self.window_size
                    self.executions = [t for t in self.executions if t > cutoff_time]
            
            # Record this execution
            self.executions.append(current_time)
            
    def __exit__(self, exc_type, exc_val, exc_tb):
        # No need to do anything on exit with this implementation
        pass

# =============================================================================
# DATA PROCESSING UTILITIES
# =============================================================================

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
    """
    Extract and clean filename from URL for file storage.
    
    Args:
        url (str): URL to extract filename from
        
    Returns:
        str: Cleaned filename suitable for storage
    """
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
    """
    Convert markdown table to pandas DataFrame.
    
    Args:
        markdown_table (str): Markdown table string
        
    Returns:
        pd.DataFrame: DataFrame representation of the table
    """
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
    """
    Convert a list of items to row format for table processing.
    
    Args:
        items (List[Any]): List of items to convert
        
    Returns:
        List[Dict[str, Any]]: List of row items with text_value keys
    """
    res = []
    for item in items:
        if isinstance(item, tuple):   # Tuple of (colname, colspan)
            val = '' if pd.isnull(item[0]) else item[0]
            extra_colspan = item[1] - 1
            res.extend([{'text_value': val}] + [{'text_value':''} for _ in range(extra_colspan)])
        elif isinstance(item, str) or isinstance(item, int) or isinstance(item, float) or isinstance(item, bool):
            res.append({'text_value': str(item)})
        else:
            logger.warning(f"Create_row_items: unsupported type {type(item)} for item {item}")
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
    Parse HTML table into header and rows, handling colspan/rowspan.
    
    Args:
        html (str): HTML containing table
        
    Returns:
        Tuple[List[str], List[List[str]]]: (header, rows)
    """
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
    """
    Determine media type from base64 encoded data.
    
    Args:
        base64_data (str): Base64 encoded data
        
    Returns:
        str: MIME type of the data
    """
    file_bytes = base64.b64decode(base64_data)
    media_type = magic.Magic(mime=True).from_buffer(file_bytes)
    return media_type

# =============================================================================
# SYSTEM UTILITIES
# =============================================================================

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
        logger.info(f"Using Docker path: {docker_path}")
        return docker_path

    # Try config path if provided
    if config_path:
        if os.path.exists(config_path):
            logger.info(f"Using config path: {config_path}")
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

    logger.info(f"Using local path: {local_path}")
    return local_path


config_defaults = {
    'vectara': {
        'endpoint': "https://api.vectara.io",
        'auth_url': "https://auth.vectara.io"
    },
    'doc_processing': {
        'model_config': {
            'text':{
                'provider': 'openai',
                'model_name': 'gpt-4o',
                'base_url': 'https://api.openai.com/v1'
            },
            'image':{
                'provider': 'openai',
                'model_name': 'gpt-4o',
                'base_url': 'https://api.openai.com/v1'
            },
        },
        'easy_ocr_config': {
            'force_full_page_ocr': True
        }
    },
    'dataframe_processing': {
        'mode': 'table'
    }
}

def load_config(*config_files:str):
    """
    Loads and merges multiple configuration files into a single OmegaConf DictConfig object.

    The function starts by creating a base configuration from `config_defaults`.
    Then, it iterates through the provided `config_files` (in the order they are given),
    loading each one and merging its contents into the evolving configuration.
    Later files in the sequence will override values from earlier files or the defaults
    if there are conflicting keys.

    Args:
        *config_files: A variable number of string arguments, where each string is a
                       path to a configuration file (e.g., YAML or .py file,
                       depending on OmegaConf's capabilities).

    Returns:
        DictConfig: An OmegaConf DictConfig object representing the merged
                    configuration from all provided files and the initial defaults.
    """
    configs = [
        OmegaConf.create(config_defaults)
    ]
    for config_file in config_files:
        logger.info(f'load_config() - Loading config {config_file}')
        config = OmegaConf.load(config_file)
        configs.append(config)

    return OmegaConf.merge(*configs)

# =============================================================================
# PATTERN MATCHING UTILITIES
# =============================================================================

def url_matches_patterns(url, pos_patterns, neg_patterns):
    """
    Check if URL matches positive patterns and doesn't match negative patterns.
    
    Args:
        url (str): URL to check
        pos_patterns (List[Pattern]): Positive regex patterns
        neg_patterns (List[Pattern]): Negative regex patterns
        
    Returns:
        bool: True if URL matches criteria
    """
    pos_match = len(pos_patterns)==0 or any([r.match(url) for r in pos_patterns])
    neg_match = len(neg_patterns)==0 or not any([r.match(url) for r in neg_patterns])
    return pos_match and neg_match


def get_headers(cfg):
    """
    Get HTTP headers from configuration.
    
    Args:
        cfg: Configuration object
        
    Returns:
        Dict[str, str]: HTTP headers dictionary
    """
    user_agent = cfg.vectara.get("user_agent", DEFAULT_USER_AGENT)
    headers = DEFAULT_HEADERS.copy()
    headers["User-Agent"] = user_agent
    return headers


def normalize_vectara_endpoint(endpoint_config: str, default_host: str = "api.vectara.io") -> str:
    """
    Normalize Vectara API endpoint configuration to a valid URL.
    
    Handles various input formats:
    - Full URLs: "https://api.vectara.dev" -> "https://api.vectara.dev"
    - Hostnames: "api.vectara.dev" -> "https://api.vectara.dev"
    - Empty/None: None -> "https://api.vectara.io"
    
    Args:
        endpoint_config: Endpoint from config (can be URL or hostname)
        default_host: Default hostname if endpoint_config is empty
        
    Returns:
        str: Normalized HTTPS URL
        
    Raises:
        ValueError: If the resulting URL is invalid
    """
    from urllib.parse import urlparse
    
    # Use default if not provided
    if not endpoint_config:
        endpoint_config = default_host
    
    # If it already looks like a URL, validate and return
    if endpoint_config.startswith(("http://", "https://")):
        parsed = urlparse(endpoint_config)
        if not all([parsed.scheme in ("http", "https"), parsed.netloc]):
            raise ValueError(f"Invalid endpoint URL: {endpoint_config}")
        return endpoint_config
    
    # Otherwise treat as hostname and add https://
    normalized = f"https://{endpoint_config}"
    parsed = urlparse(normalized)
    if not parsed.netloc or parsed.netloc != endpoint_config:
        raise ValueError(f"Invalid endpoint hostname: {endpoint_config}")
    
    return normalized

