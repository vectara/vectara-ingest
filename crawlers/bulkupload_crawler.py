import logging
from core.crawler import Crawler
import json
import os
from core.utils import get_docker_or_local_path

def is_valid(json_object):
    return 'id' in json_object and 'sections' in json_object

class BulkuploadCrawler(Crawler):

    def crawl(self) -> None:
        docker_path = '/home/vectara/data/file.json'
        config_path = self.cfg.bulkupload_crawler.json_path
        
        json_file = get_docker_or_local_path(
            docker_path=docker_path,
            config_path=config_path
        )
        
        with open(json_file, 'r') as file:
            data = file.read()
        json_array = json.loads(data)
        if not isinstance(json_array, list):
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
