import logging
from omegaconf import OmegaConf
from bs4 import BeautifulSoup

chunk_min_len = 50
chunk_max_len = 2500   # targeting roughly 500 words

#
# Utilities to ensure Vectara sections are within a certain size range
# We do this by calling process_chunks, and it will recursively split chunks that are too large or merges chunks that are too small
#

# Ensure all chunks are at least chunk_min_len characters
def ensure_min_len(self, chunks):
    result = []
    text = ""
    for chunk in chunks:
        if len(text)==0:
            text += chunk['text']
        else:
            text += ' ' + chunk['text']
        if len(text)>self.chunk_min_len:
            result.append({"text": text})
            text = ''
    if len(text)>0:
        result.append({"text": text})
    return result

# Ensure no chunk is higher than chunk_max_len characters
def ensure_max_len(chunks):
    result = []
    for chunk in chunks:
        text = chunk['text']
        while len(text) > chunk_max_len:
            # Calculate the midpoint of the remaining string
            mid_point = len(text) // 2
            # Find the nearest space to the midpoint
            left = text.rfind(" ", 0, mid_point)
            right = text.find(" ", mid_point)
            # Choose the closest space to the midpoint
            if mid_point - left < right - mid_point:
                split_index = left
            else:
                split_index = right
            # If a space was found, split the string there, otherwise split at max_len
            if split_index == -1:
                split_index = chunk_max_len
            # Add the chunk to the result and continue with the remainder
            result.append({"text": text[:split_index]})
            text = text[split_index:].lstrip()  # Remove leading space
        result.append({"text": text})
    return result

def process_chunks(chunks):
    while max([len(x['text']) for x in chunks]) > chunk_max_len or min([len(x['text']) for x in chunks]) < chunk_min_len:
        logging.info(f"normalizing chunk lengths: {[len(x['text']) for x in chunks]}")
        chunks = ensure_min_len(ensure_max_len(chunks))
    return chunks

def html_to_text(html):
    soup = BeautifulSoup(html, features='html.parser')
    return soup.get_text()
