import logging
logger = logging.getLogger(__name__)
from typing import Tuple

from goose3 import Goose
from goose3.text import StopWordsArabic, StopWordsKorean, StopWordsChinese
from core.utils import remove_code_from_html

import justext
from bs4 import BeautifulSoup

# This module implements the get_article_content() utility function
# This extracts the most important text from an HTML text segment, trying to reduce the amount of boilerplate text and ad links
# uses both Goose3 and Justext to get the best of both worlds.

language_stopwords_Goose = {
    'en': None,  # English stopwords are the default
    'ar': StopWordsArabic,  # Use Arabic stopwords
    'zh-cn': StopWordsChinese,  # Use Chinese stopwords
    'zh-tw': StopWordsChinese,  # Use Chinese stopwords
    'ko': StopWordsKorean  # Use Korean stopwords
        }

language_stopwords_JusText = {
    'en': None,  # English stopwords are the default
    'ar': 'Arabic',  # Use Arabic stopwords
    'ko': 'Korean' , # Use Korean stopwords
    'ur': 'Urdu' ,  # Use urdu stopwords
    'hi': 'Hindi' ,  # Use Hindi stopwords
    'fa': 'Persian',  # Use Persian stopwords
    'ja': 'Japanese',  # Use Japanese stopwords
    'bg': 'Bulgarian',  # Use Bulgarian stopwords
    'sv': 'Swedish',  # Use Swedish stopwords
    'lv': 'Latvian',  # Use Latvian stopwords
    'sr': 'Serbian',  # Use Serbian stopwords
    'sq': 'Albanian',  # Use Albanian stopwords
    'es': 'Spanish',  # Use Spanish stopwords
    'ka': 'Gerogian',  # Use Georgian stopwords
    'de': 'German',  # Use German stopwords
    'el': 'Greek',  # Use Greek stopwords
    'ga': 'Irish',  # Use Irish stopwords
    'vi': 'Vietnamese',  # Use Vietnamese stopwords
    'hu': 'Hungarian',  # Use Hungarian stopwords
    'pt': 'Portuguese',  # Use Portuguese stopwords
    'pl': 'Polish',  # Use Polish stopwords
    'it': 'Italian',  # Use Italian stopwords
    'la': 'Latin',  # Use Latin stopwords
    'tr': 'Turkish',  # Use Turkish stopwords
    'id': 'Indonesian',  # Use Indonesian stopwords
    'hr': 'Croatian',  # Use Croatian stopwords
    'be': 'Belarusian',  # Use Belarusian stopwords
    'ru': 'Russian',  # Use Russian stopwords
    'et': 'Estonian',  # Use Estonian stopwords
    'uk': 'Ukranian',  # Use Ukranian stopwords
    'ro': 'Romanian',  # Use Romanian stowords
    'cs': 'Czech',  # Use Czech stopwords
    'ml': 'Malyalam',  # Use Malyalam stopwords
    'sk': 'Slovak',  # Use Slovak stopwords
    'fi': 'Finnish',  # Use Finnish stopwords
    'da': 'Danish',  # Use Danish stopwords
    'ms': 'Malay',  # Use Malay stopwords
    'ca': 'Catalan',  # Use Catalan stopwords
    'eo': 'Esperanto',  # Use Esperanto stopwords
    'nb': 'Norwegian_Bokmal',  # Use Norwegian_Bokmal stopwords
    'he': "Hebrew",
    'nn': 'Norwegian_Nynorsk'  # Use Norwegian_Nynorsk stopwords
    # Add more languages and their stopwords keywords here
}



def get_content_with_justext(html_content: str, detected_language: str) -> Tuple[str, str]:
    if detected_language == 'en':
        paragraphs = justext.justext(html_content, justext.get_stoplist("English"))
    else:
        stopwords_keyword = language_stopwords_JusText.get(detected_language, 'English')
        # Extract paragraphs using the selected stoplist
        paragraphs = justext.justext(html_content, justext.get_stoplist(stopwords_keyword))

    text = '\n'.join([p.text for p in paragraphs if not p.is_boilerplate])
    soup = BeautifulSoup(html_content, 'html.parser')
    stitle = soup.find('title')
    if stitle:
        title = stitle.text
    else:
        title = ''
    return text, title

def get_content_with_goose3(html_content: str, url: str, detected_language: str) -> Tuple[str, str]:
    try:
        if detected_language in language_stopwords_Goose:
            stopwords_class = language_stopwords_Goose.get(detected_language, None)

            if stopwords_class is not None:
                g = Goose({'stopwords_class': stopwords_class})
            else:
                g = Goose()  # Use the default stopwords for languages that don't have a configured StopWords class

            article = g.extract(url=url, raw_html=html_content)
            title = article.title
            text = article.cleaned_text
            return text, title
        else:
            title = ""
            text = ""
            logger.warning(f"The language with code {detected_language} is not supported by Goose")
            return text, title
    except Exception as e:
        title = ""
        text = ""
        logger.error(f"Error in Goose3 ({e}); that's okay Justext will fill in")
        return text, title

def get_article_content(html_content: str, url: str, detected_language: str, remove_code: bool = False) -> Tuple[str, str]:
    if remove_code:
        html_content = remove_code_from_html(html_content)

    text1, title1 = get_content_with_goose3(html_content, url, detected_language)
    text2, title2 = get_content_with_justext(html_content, detected_language)
    
    # both Goose and Justext do extraction without boilerplate; return the one that produces the longest text, trying to optimize for content
    if len(text1)>len(text2):
        return text1, title1
    else:
        return text2, title2
