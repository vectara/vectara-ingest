from bs4 import BeautifulSoup
import requests

def html_to_text(html):
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()

def create_session_with_retries(retries: int = 3):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=5)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

