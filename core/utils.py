from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urlunparse, ParseResult
from langdetect import detect
import logging

img_extensions = ["gif", "jpeg", "jpg", "mp3", "mp4", "png", "svg", "bmp", "eps", "ico"]
doc_extensions = ["doc", "docx", "ppt", "pptx", "xls", "xlsx", "pdf", "ps"]
archive_extensions = ["zip", "gz", "tar", "bz2", "7z", "rar"]
binary_extensions = archive_extensions + img_extensions + doc_extensions

def html_to_text(html):
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()

def create_session_with_retries(retries: int = 3):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def remove_anchor(url):
    parsed = urlparse(url)
    url_without_anchor = urlunparse(parsed._replace(fragment=""))
    return url_without_anchor


def normalize_url(url):
    """Normalize a URL by removing 'www', and query parameters."""    
    # Prepend with 'http://' if URL has no scheme
    if '://' not in url:
        url = 'http://' + url
    p = urlparse(url)
    
    # Remove 'www.'
    netloc = p.netloc.replace('www.', '')
    
    # Remove query parameters
    path = p.path.split('?', 1)[0]

    # Reconstruct URL with scheme, without 'www', and query parameters
    return ParseResult(p.scheme, netloc, path, '', '', '').geturl()

def clean_urls(urls):
    return list(set(normalize_url(url) for url in urls))

def detect_language(text):
    try:
        lang = detect(text)
        if lang == "ar":
            return "ar"  # Arabic
        elif lang == "ko":
            return "ko"  # Korean
        elif lang == "zh-cn" or lang == "zh-tw":
            return "zh"  # Chinese (simplified and traditional)
        else:
            return "en"  # Default to English if no specific language detected
    except Exception as e:
        print(f"Language detection failed with error: {e}")
        return "en"  # Default to English in case of errors




