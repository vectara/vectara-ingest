import logging
from core.crawler import Crawler
import json

def is_valid(json_object):
    return 'documentId' in json_object and 'section' in json_object

class JACrawler(Crawler):

    def crawl(self) -> None:
        json_file = '/home/vectara/data/file.json'
        with open(json_file, 'r') as file:
            data = file.read()
        json_array = json.loads(data)
        if type(json_array) != list:
            raise Exception("JSON file must contain an array of JSON objects")

        logging.info(f"indexing {len(json_array)} JSON documents from JSON file")
        count = 0
        for json_object in json_array:
            if count % 100 == 0:
                logging.info(f"finished {count} documents so far")
            if is_valid(json_object):
                self.indexer.index_document(json_object)
                count += 1
            else:
                logging.info(f"invalid JSON object: {json_object}")
