from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urlunparse, ParseResult
import re
from langdetect import detect
from typing import List, Set
import os

img_extensions = ["gif", "jpeg", "jpg", "mp3", "mp4", "png", "svg", "bmp", "eps", "ico"]
doc_extensions = ["doc", "docx", "ppt", "pptx", "xls", "xlsx", "pdf", "ps"]
archive_extensions = ["zip", "gz", "tar", "bz2", "7z", "rar"]
binary_extensions = archive_extensions + img_extensions + doc_extensions

def remove_code_from_html(html_text: str) -> str:
    """Remove code and script tags from HTML."""
    soup = BeautifulSoup(html_text, 'html.parser')
    for tag in soup.find_all(['code', 'script']):
        tag.decompose()
    return str(soup)

def html_to_text(html: str, include_code: bool = True) -> str:
    """Convert HTML to text."""
    if not include_code:
        html = remove_code_from_html(html)
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()

def create_session_with_retries(retries: int = 3) -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def remove_anchor(url: str) -> str:
    """Remove the anchor from a URL."""
    parsed = urlparse(url)
    url_without_anchor = urlunparse(parsed._replace(fragment=""))
    return url_without_anchor

def normalize_url(url: str) -> str:
    """Normalize a URL by removing query parameters."""    
    # Prepend with 'http://' if URL has no scheme
    if '://' not in url:
        url = 'http://' + url
    p = urlparse(url)
        
    # Remove query parameters
    path = p.path.split('?', 1)[0]

    # Reconstruct URL with scheme, without 'www', and query parameters
    return ParseResult(p.scheme, p.netloc, path, '', '', '').geturl()

def clean_urls(urls: Set[str]) -> List[str]:
    return list(set(normalize_url(url) for url in urls))

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
        print(f"Language detection failed with error: {e}")
        return "en"  # Default to English in case of errors

def get_file_size_in_MB(file_path: str) -> float:
    file_size_bytes = os.path.getsize(file_path)
    file_size_MB = file_size_bytes / (1024 * 1024)    
    return file_size_MB

