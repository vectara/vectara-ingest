import logging
from bs4 import BeautifulSoup

def html_to_text(html):
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()
