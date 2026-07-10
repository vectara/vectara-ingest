import logging
logger = logging.getLogger(__name__)
from core.crawler import Crawler
from omegaconf import OmegaConf
from notion_client import Client
from typing import Any
import os

from core.utils import get_docker_or_local_path
from core.incremental import build_manifest, plan_deletions

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
        try:
            children = notion.blocks.children.list(block["id"])
            for child in children["results"]:
                if block["type"] in ['child_page']:
                    continue
                text += get_block_text(notion, child) + " "
        except Exception as e:
            logger.warning(f"Failed to get children for block {block['id']}, likely due to permissions: {e}")

    return text

def list_all_pages(notion: Any):
    results = []
    start_cursor = None
    while True:
        # Build search parameters
        search_params = {
            "filter": {
                "property": "object",
                "value": "page"
            },
            "query": "",
            "sort": {
                "direction": "ascending",
                "timestamp": "last_edited_time",
            }
        }

        # Only include start_cursor if it has a value
        if start_cursor:
            search_params["start_cursor"] = start_cursor

        response = notion.search(**search_params)

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

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.notion_api_key = self.cfg.notion_crawler.notion_api_key
        # Incremental reindexing state (see core/incremental.py).
        self.incremental = self.cfg.notion_crawler.get("incremental", False)
        self.source = self.cfg.notion_crawler.get("source", "notion")

    def crawl(self) -> None:
        notion = Client(auth=self.notion_api_key)

        pages = list_all_pages(notion)
        indexed_ids = set()
        if self.tracker and not self.cfg.vectara.get("reindex", False):
            indexed_ids = self.tracker.get_indexed_ids()

        # Incremental reindexing: build the corpus manifest once (keyed by Notion page id,
        # source-scoped) so an unchanged page can be skipped before upload.
        manifest = {}
        if self.incremental or self.cfg.notion_crawler.get("remove_old_content", False):
            manifest_source = self.indexer.source_tag if self.incremental else None
            manifest = build_manifest(self.indexer, key="id", source=manifest_source)
            logger.info(f"Loaded corpus manifest: {len(manifest)} existing documents")
        present_keys = set()       # page ids present at the source (indexed or skipped)
        crawl_completed = False

        logger.info(f"Found {len(pages)} pages in Notion.")
        for page in pages:
            page_id = page["id"]
            # Every discovered page is "present at source" for the deletion diff — including
            # pages whose block fetch fails below. A transient API error is not evidence the
            # page was deleted, and must never turn into a deletion.
            present_keys.add(page_id)
            # Legacy blind crash-recovery pre-filter — suppressed under incremental, where the
            # fingerprint (not "was it indexed before") decides, so a changed page is re-fetched.
            if page_id in indexed_ids and not self.incremental:
                continue
            self.check_shutdown()
            try:
                blocks = notion.blocks.children.list(page_id)
                all_text = ""
                for block in blocks["results"]:
                    if block["type"] in ['child_page']:
                        continue
                    all_text += get_block_text(notion, block) + " "
                all_text = all_text.strip()

            except Exception as e:
                import traceback
                logger.error(f"Failed to get all text for page {page['url']}: {e}, traceback={traceback.format_exc()}")
                continue

            if len(all_text)==0:
                logger.info(f"Skipping notion page {page['url']}, since no text available")
                continue

            doc = {
                'id': page_id,
                'title': extract_title(page),
                'metadata': {
                    'source': self.source,
                    'url': page['url'],
                    'title': extract_title(page),
                },
                'sections': [{'text': all_text}]
            }
            # index_document computes the fingerprint from the page text + metadata + config and
            # skips the upload (returning True, last_skip_reason='unchanged') when nothing changed.
            prior_fingerprint = manifest[page_id].fingerprint if page_id in manifest else None
            succeeded = self.indexer.index_document(doc, prior_fingerprint=prior_fingerprint)
            if succeeded and self.indexer.was_skipped():
                logger.info(f"Notion page {page_id} unchanged (fingerprint match) — skipping")
                if self.tracker:
                    self.tracker.track_skipped(page_id, url=page['url'], title=doc['title'])
                continue
            if succeeded:
                logger.info(f"Indexed notion page {page_id}")
                if self.tracker:
                    self.tracker.track_indexed(page_id, url=page['url'], title=doc['title'])
            else:
                logger.info(f"Indexing failed for notion page {page_id}")
                if self.tracker:
                    self.tracker.track_failed(page_id, url=page['url'], title=doc['title'])

        # The loop ran to completion (check_shutdown raises on interruption), so the present
        # set is complete and safe to drive deletions.
        crawl_completed = True

        # report pages crawled if specified
        if self.cfg.notion_crawler.get("crawl_report", False):
            logger.info(f"Indexed {len(pages)} Pages. See pages_indexed.txt for a full report.")
            output_dir = self.cfg.notion_crawler.get("output_dir", "vectara_ingest_output")
            docker_path = f'/home/vectara/{output_dir}/pages_indexed.txt'
            filename = os.path.basename(docker_path)  # Extract just the filename
            file_path = get_docker_or_local_path(
                docker_path=docker_path,
                output_dir=output_dir
            )

            if not file_path.endswith(filename):
                file_path = os.path.join(file_path, filename)

            with open(file_path, 'w') as f:
                for page in sorted(pages, key=lambda x: x['id']):
                    f.write(f"{page['id']}: {page['url']}\n")


        # If remove_old_content is set to true:
        # remove from corpus any document previously indexed that is NOT in pages added,
        # guarded by plan_deletions against a partial/interrupted crawl mass-deleting live docs.
        if self.cfg.notion_crawler.get("remove_old_content", False):
            listing_complete = crawl_completed and len(present_keys) > 0
            ratio = self.cfg.notion_crawler.get("deletion_safety_ratio", 0.5)
            to_delete, refused = plan_deletions(manifest, present_keys, listing_complete, ratio)
            removed = []
            if not refused:
                to_delete_set = set(to_delete)
                for entry in manifest.values():
                    if entry.doc_id in to_delete_set and self.indexer.delete_doc(entry.doc_id):
                        removed.append(entry)
            logger.info(f"Removed {len(removed)} of {len(to_delete)} docs that are not "
                        f"included in the crawl but are in the corpus.")
            if self.cfg.notion_crawler.get("crawl_report", False):
                output_dir = self.cfg.vectara.get("output_dir", "vectara_ingest_output")
                docker_path = f'/home/vectara/{output_dir}/pages_removed.txt'
                filename = os.path.basename(docker_path)  # Extract just the filename
                file_path = get_docker_or_local_path(
                    docker_path=docker_path,
                    output_dir=output_dir
                )

                if not file_path.endswith(filename):
                    file_path = os.path.join(file_path, filename)

                with open(file_path, 'w') as f:
                    for entry in removed:
                        f.write(f"Page with ID {entry.doc_id}: {entry.url}\n")
