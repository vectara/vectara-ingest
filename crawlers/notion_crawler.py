import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
from notion_client import Client
from typing import Any, List, Dict
import json

logging.getLogger("httpx").setLevel(logging.WARNING)

def format_notion_id(page_id):
    '''
    Formats a Notion page ID into a human-readable format.
    '''
    return f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"

def get_block_text(notion, block):
    text = ""
    block_type = block["type"]
    
    if block_type in block:
        content = block[block_type]
        if "rich_text" in content:
            for text_item in content["rich_text"]:
                text += text_item.get("plain_text", "") + " "
        elif "title" in content:  # For page blocks
            if isinstance(content["title"], str):
                text += content["title"] + " "
            else:
                text += content["title"][0].get("plain_text","") + " "
    
    # Check for child blocks
    if block.get("has_children", False):
        children = notion.blocks.children.list(block["id"])
        for child in children["results"]:
            text += get_block_text(notion, child) + " "
    
    return text

def list_all_pages(notion: Any):
    results = []
    start_cursor = None
    while True:
        response = notion.search(
            filter={
                "property": "object",
                "value": "page"
            },
            query="",
            sort={
                "direction": "ascending",
                "timestamp": "last_edited_time",
            },
            start_cursor=start_cursor
        )

        results.extend(response.get("results"))
        start_cursor = response.get("next_cursor")
        if not start_cursor:
            break

    return results


def extract_title(page):
    properties = page['properties']
    
    # Case 1: Title property exists
    if 'title' in properties and properties['title']['type'] == 'title':
        return properties['title']['title'][0]['plain_text'] if properties['title']['title'] else ''
    
    # Case 2: Name property exists (common for databases)
    if 'Name' in properties and properties['Name']['type'] == 'title':
        return properties['Name']['title'][0]['plain_text'] if properties['Name']['title'] else ''
    
    # Case 3: Search for any property of type 'title'
    for prop in properties.values():
        if prop['type'] == 'title':
            return prop['title'][0]['plain_text'] if prop['title'] else ''

    # No title found
    return ''

class NotionCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.notion_api_key = self.cfg.notion_crawler.notion_api_key

    def crawl(self) -> None:
        notion = Client(auth=self.notion_api_key)

        pages = list_all_pages(notion)

        logging.info(f"Found {len(pages)} pages in Notion.")
        for page in pages:
            page_id = page["id"]
            try:
                blocks = notion.blocks.children.list(page_id)
                all_text = ""
                for block in blocks["results"]:
                    all_text += get_block_text(notion, block) + " "
                all_text = all_text.strip()

            except Exception as e:
                import traceback
                logging.error(f"Failed to get all text for page {page['url']}: {e}, traceback={traceback.format_exc()}")
                continue

            if len(all_text)==0:
                logging.info(f"Skipping notion page {page['url']}, since no text available")
                continue

            doc = {
                'documentId': page_id,
                'title': extract_title(page),
                'metadataJson': json.dumps({
                    'source': 'notion',
                    'url': page['url'],
                    'title': extract_title(page),
                }),
                'section': [{'text': all_text}]
            }
            succeeded = self.indexer.index_document(doc)
            if succeeded:
                logging.info(f"Indexed notion page {page_id}")
            else:
                logging.info(f"Indexing failed for notion page {page_id}")
            