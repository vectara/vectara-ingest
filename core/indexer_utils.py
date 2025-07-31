import hashlib
import logging
import os
import re
import tempfile
import json
from typing import Dict, Any, Optional
from email.utils import parsedate_to_datetime
from datetime import datetime
from bs4 import BeautifulSoup
from omegaconf import OmegaConf

logger = logging.getLogger(__name__)


def get_chunking_config(cfg: OmegaConf) -> Optional[Dict]:
    """Helper function to get chunking configuration"""
    if cfg.vectara.get("chunking_strategy", "sentence") == "fixed":
        chunk_size = cfg.vectara.get("chunk_size", 512)
        return {
            "type": "max_chars_chunking_strategy",
            "max_chars_per_chunk": chunk_size
        }
    return None


def extract_last_modified(url: str, html: str) -> dict:
    """
    Extract last modified date from HTML content.
    Strategies: meta tags, time elements, regex search, fallback to hash
    """
    result = {'url': url, 'detection_method': None}
    soup = BeautifulSoup(html, 'html.parser')

    # 1) META tags
    for attr in ('http-equiv', 'name'):
        tag = soup.find('meta', attrs={attr: lambda v: v and v.lower() == 'last-modified'})
        if tag and tag.get('content'):
            try:
                dt = parsedate_to_datetime(tag['content'])
                result.update(last_modified=dt, detection_method='meta')
                return result
            except Exception:
                continue

    # 2) <time datetime="…">
    times = []
    for time_tag in soup.find_all('time', datetime=True):
        dt_str = time_tag['datetime'].strip()
        for parser in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                dt = parser(dt_str)
                times.append(dt)
                break
            except Exception:
                continue
    if times:
        result.update(last_modified=max(times), detection_method='time')
        return result

    # 3) Regex search
    text = soup.get_text(" ", strip=True)
    patterns = [
        r'\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?\b',
        r'\b(?:January|February|March|April|May|June|July|'
        r'August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b',
    ]
    candidates = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            dt_str = m.group(0)
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%B %d, %Y"):
                try:
                    dt = parsedate_to_datetime(dt_str) if 'T' in dt_str or '-' in dt_str else datetime.strptime(dt_str, fmt)
                    candidates.append(dt)
                    break
                except Exception:
                    continue

    if candidates:
        result.update(last_modified=max(candidates), detection_method='regex')
        return result

    # 4) Fallback to hash
    result.update(content_hash=hashlib.md5(html.encode('utf-8')).hexdigest(),
                  detection_method='hash')
    return result


def create_upload_files_dict(filename: str, metadata: Dict[str, Any], parse_tables: bool, cfg: OmegaConf) -> Dict[str, Any]:
    """Create files dictionary for upload API"""
    upload_filename = filename.split('/')[-1]
    content_type = 'application/pdf' if filename.lower().endswith('.pdf') else 'application/octet-stream'
    
    files = {
        'metadata': (None, json.dumps(metadata), 'application/json'),
    }
    
    if parse_tables and filename.lower().endswith('.pdf'):
        files['table_extraction_config'] = (None, json.dumps({'extract_tables': True}), 'application/json')
    
    chunking_config = get_chunking_config(cfg)
    if chunking_config:
        files['chunking_strategy'] = (None, json.dumps(chunking_config), 'application/json')
    
    return files, upload_filename, content_type


def handle_file_upload_response(response, uri: str, reindex: bool, delete_doc_func) -> bool:
    """Handle file upload response with reindexing logic"""
    if response.status_code == 409:
        if reindex:
            match = re.search(r"document id '([^']+)'", response.text)
            if match:
                doc_id = match.group(1)
                return delete_doc_func(doc_id)
            else:
                logger.error(f"Failed to extract document id from error: {response.text}")
                return False
        else:
            logger.info(f"Document {uri} already indexed, skipping")
            return False
    elif response.status_code == 201:
        logger.info(f"REST upload for {uri} successful")
        return True
    else:
        logger.error(f"REST upload for {uri} failed with code {response.status_code}, text = {response.text}")
        return False


def safe_file_cleanup(file_path: str):
    """Safely remove file if it exists"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"Failed to remove file {file_path}: {e}")


def validate_text_content(text: str, min_length: int = 3) -> bool:
    """Validate if text content is meaningful"""
    return text is not None and len(text) >= min_length


def prepare_file_metadata(metadata: Dict[str, Any], filename: str, static_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Prepare file metadata by adding filename and static metadata"""
    if static_metadata:
        metadata.update({k: v for k, v in static_metadata.items() if k not in metadata})
    
    metadata['file_name'] = filename.split('/')[-1]
    return metadata


def create_temp_pdf_file(pdf_writer) -> str:
    """Create temporary PDF file and return path"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", mode='wb', delete=False) as f:
        pdf_writer.write(f)
        f.flush()
        return f.name


def store_file(filename: str, orig_filename: str, store_docs: bool, store_docs_folder: str) -> None:
    """
    Store a file in the docs folder if configured to do so.
    
    Args:
        filename (str): Source file path
        orig_filename (str): Original filename to use for storage
        store_docs (bool): Whether to store documents
        store_docs_folder (str): Folder to store documents in
    """
    import shutil
    
    if store_docs:
        dest_path = f"{store_docs_folder}/{orig_filename}"
        shutil.copyfile(filename, dest_path)