import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
from notion_client import Client
from typing import Any, List, Dict

def get_text_from_block(block: Any) -> str:
    """
    Recursively extract all text from a block.
    """
    if block["type"] == "paragraph":
        text = " ".join([text["plain_text"] for text in block["paragraph"]["rich_text"]])
    else:
        text = ""
    if "children" in block:
        for child_block in block["children"]:
            text += "\n" + get_text_from_block(child_block)
    return text


def list_all_pages(notion: Any) -> List[Dict[str, Any]]:
    """
    List all pages in a Notion workspace.
    """
    pages = []
    has_more = True
    start_cursor = None
    while has_more:
        list_pages_response = notion.search(filter={"property": "object", "value": "page"}, start_cursor=start_cursor)
        for page in list_pages_response["results"]:
            pages.append(page)
        has_more = list_pages_response["has_more"]
        start_cursor = list_pages_response["next_cursor"]
    
    return pages

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
            title = extract_title(page)

            # Extract all text blocks from the page
            try:
                blocks = notion.blocks.children.list(page_id).get("results")        # type: ignore
            except Exception as e:
                logging.error(f"Failed to get blocks for page {page['url']}: {e}")
                continue
            segments = []
            metadatas = []
            for block in blocks:
                text = get_text_from_block(block)
                if len(text)>2:
                    segments.append(text)
                    metadatas.append({'block_id': block['id'], 'block_type': block['type']})
            doc_id = page['url']
            if len(segments)>0:
                logging.info(f"Indexing {len(segments)} segments in page {doc_id}")
                succeeded = self.indexer.index_segments(doc_id, texts=segments, titles=None, metadatas=metadatas, 
                                                        doc_metadata={'source': 'notion', 'title': title, 'url': page['url']},
                                                        doc_title=title)
                if succeeded:
                    logging.info(f"Indexed notion page {doc_id}")
                else:
                    logging.info(f"Indexing failed for notion page {doc_id}")
            else:
                logging.info(f"No text found in notion page {doc_id}")
            