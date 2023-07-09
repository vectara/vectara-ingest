from bs4 import BeautifulSoup
import requests
from urllib.parse import urlparse, urlunparse, ParseResult

img_extensions = ["gif", "jpeg", "jpg", "mp3", "mp4", "png", "svg", "bmp", "eps", "ico", "ps"]
doc_extensionss = ["doc", "docx", "ppt", "pptx", "xls", "xlsx", "pdf"]
binary_extensions = ["zip"] + img_extensions + doc_extensionss

def html_to_text(html):
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()

def create_session_with_retries(retries: int = 3):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
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

