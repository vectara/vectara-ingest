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

# langdetect code -> justext stoplist name. Languages not listed use justext's
# language-independent mode (see get_content_with_justext).
language_stopwords_JusText = {
    'en': 'English',
    'fr': 'French',
    'ar': 'Arabic',  # Use Arabic stopwords
    'ko': 'Korean' , # Use Korean stopwords
    'ur': 'Urdu' ,  # Use urdu stopwords
    'hi': 'Hindi' ,  # Use Hindi stopwords
    'fa': 'Persian',  # Use Persian stopwords
    'bg': 'Bulgarian',  # Use Bulgarian stopwords
    'sv': 'Swedish',  # Use Swedish stopwords
    'lv': 'Latvian',  # Use Latvian stopwords
    'sq': 'Albanian',  # Use Albanian stopwords
    'es': 'Spanish',  # Use Spanish stopwords
    'de': 'German',  # Use German stopwords
    'el': 'Greek',  # Use Greek stopwords
    'vi': 'Vietnamese',  # Use Vietnamese stopwords
    'hu': 'Hungarian',  # Use Hungarian stopwords
    'pt': 'Portuguese',  # Use Portuguese stopwords
    'pl': 'Polish',  # Use Polish stopwords
    'it': 'Italian',  # Use Italian stopwords
    'tr': 'Turkish',  # Use Turkish stopwords
    'id': 'Indonesian',  # Use Indonesian stopwords
    'hr': 'Croatian',  # Use Croatian stopwords
    'ru': 'Russian',  # Use Russian stopwords
    'et': 'Estonian',  # Use Estonian stopwords
    'uk': 'Ukrainian',  # Use Ukrainian stopwords
    'ro': 'Romanian',  # Use Romanian stowords
    'cs': 'Czech',  # Use Czech stopwords
    'ml': 'Malayalam',  # Use Malayalam stopwords
    'sk': 'Slovak',  # Use Slovak stopwords
    'fi': 'Finnish',  # Use Finnish stopwords
    'da': 'Danish',  # Use Danish stopwords
    'ca': 'Catalan',  # Use Catalan stopwords
    'he': "Hebrew",
    'nl': 'Dutch',
    'no': 'Norwegian_Bokmal',
    'lt': 'Lithuanian',
    'sl': 'Slovenian',
    'mk': 'Macedonian',
    'af': 'Afrikaans',
    'cy': 'Welsh',
    'sw': 'Swahili',
    'tl': 'Tagalog',
    'bn': 'Bengali',
    'ta': 'Tamil',
    'te': 'Telugu',
    'kn': 'Kannada',
    'mr': 'Marathi',
    'gu': 'Gujarati',
    'ne': 'Nepali',
    # Add more languages and their stopwords keywords here
}



def get_content_with_justext(html_content: str, detected_language: str) -> Tuple[str, str]:
    stoplist_name = language_stopwords_JusText.get(detected_language)
    if stoplist_name:
        paragraphs = justext.justext(html_content, justext.get_stoplist(stoplist_name))
    else:
        # No stoplist for this language (e.g. Japanese): justext's language-independent
        # mode. Another language's stoplist would mark every paragraph as boilerplate.
        paragraphs = justext.justext(html_content, frozenset(), stopwords_low=0, stopwords_high=0)

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
