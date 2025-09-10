import logging
logger = logging.getLogger(__name__)
import json
import time
import warnings
import base64
from typing import Dict, Any, List, Optional, Sequence, Tuple
from collections import OrderedDict
import shutil
import mimetypes

import uuid
import urllib.parse
import tempfile
import os

from slugify import slugify

from omegaconf import OmegaConf
from nbconvert import HTMLExporter  # type: ignore
import nbformat
import markdown
import whisper
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


from core.summary import get_attributes_from_text
from core.models import get_api_key
from core.utils import (
    html_to_text, detect_language, create_session_with_retries,
    safe_remove_file, url_to_filename, 
    get_file_path_from_url, configure_session_for_ssl, get_docker_or_local_path,
    get_headers, normalize_text, normalize_value
)
from core.extract import get_article_content
from core.doc_parser import UnstructuredDocumentParser
from core.image_processor import ImageProcessor


from core.indexer_utils import (
    get_chunking_config, extract_last_modified, create_upload_files_dict, 
    handle_file_upload_response, safe_file_cleanup, prepare_file_metadata, store_file,
    normalize_url_for_metadata
)
from core.web_extractor_base import create_web_extractor
from core.file_processor import FileProcessor

# Suppress FutureWarning related to torch.load
warnings.filterwarnings("ignore", category=FutureWarning, module="whisper")
warnings.filterwarnings("ignore", category=UserWarning, message="FP16 is not supported on CPU; using FP32 instead")


class Indexer:
    """
    Vectara API class.
    Args:
        api_url (str): Url for the Vectara API.
        corpus_key (str): Key of the Vectara corpus to index to.
        api_key (str): API key for the Vectara API.
    """

    def __init__(self, cfg: OmegaConf, api_url: str,
                 corpus_key: str, api_key: str, scrape_method: str = None) -> None:
        self.cfg = cfg
        self.api_url = api_url
        self.corpus_key = corpus_key
        self.api_key = api_key
        self.reindex = cfg.vectara.get("reindex", False)
        self.create_corpus = cfg.vectara.get("create_corpus", False)
        self.verbose = cfg.vectara.get("verbose", False)
        self.store_docs = cfg.vectara.get("store_docs", False)
        self.output_dir = cfg.vectara.get("output_dir", "vectara_ingest_output")
        self.remove_code = cfg.vectara.get("remove_code", True)
        self.remove_boilerplate = cfg.vectara.get("remove_boilerplate", False)
        self.post_load_timeout = cfg.vectara.get("post_load_timeout", 5)
        self.timeout = cfg.vectara.get("timeout", 90)
        self.detected_language: Optional[str] = None
        self.x_source = f'vectara-ingest-{self.cfg.crawling.crawler_type}'
        self.scrape_method = scrape_method  # Store scrape_method for web extractor
        self.whisper_model = None
        self.whisper_model_name = cfg.vectara.get("whisper_model", "base")
        self.static_metadata = cfg.get('metadata', None)

        if 'doc_processing' not in cfg:
            cfg.doc_processing = {}
        self.parse_tables = cfg.doc_processing.get("parse_tables", False)
        self.enable_gmft = cfg.doc_processing.get("enable_gmft", False)
        self.do_ocr = cfg.doc_processing.get("do_ocr", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.add_image_bytes = cfg.doc_processing.get("add_image_bytes", False)
        self.process_locally = cfg.doc_processing.get("process_locally", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.use_core_indexing = cfg.doc_processing.get("use_core_indexing", False)
        self.unstructured_config = cfg.doc_processing.get("unstructured_config",
                                                          {'chunking_strategy': 'by_title', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", {'chunking_strategy': 'none'})
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        self.contextual_chunking = cfg.doc_processing.get("contextual_chunking", False)
        self.image_context = cfg.doc_processing.get("image_context", {'num_previous_chunks': 1, 'num_next_chunks': 1})
        
        # Auto-enable core indexing when chunking is detected
        if self._is_chunking_enabled():
            if not self.use_core_indexing:
                logger.info("Chunking detected - automatically enabling use_core_indexing")
                self.use_core_indexing = True

        self.model_config = self._setup_model_config()
        self._validate_model_dependencies()

        logger.info(f"Vectara API Url = '{self.api_url}'")

        # Initialize specialized processors (lazy loading)
        self.web_extractor = None
        self.file_processor = None
        
        # Performance optimizations
        self._doc_exists_cache = OrderedDict()  # LRU cache for document existence checks
        self._max_cache_size = 1000  # Prevent memory leaks on large corpora

        self.setup()
    
    def _is_chunking_enabled(self) -> bool:
        """Check if chunking is enabled in any parser configuration"""
        # Check unstructured chunking
        is_unstructured_chunking = (
            self.doc_parser in ["unstructured", None] and 
            self.unstructured_config.get('chunking_strategy', 'by_title') != 'none'
        )
        
        # Check docling chunking
        is_docling_chunking = (
            self.doc_parser == "docling" and 
            self.docling_config.get('chunking_strategy', 'none') != 'none'
        )
        
        # Contextual chunking is also a form of chunking
        return is_unstructured_chunking or is_docling_chunking or self.contextual_chunking

    def _init_processors(self):
        """Lazy initialization of specialized processors"""
        if self.web_extractor is None:
            self.web_extractor = create_web_extractor(
                cfg=self.cfg,
                scrape_method=self.scrape_method,
                timeout=self.timeout,
                post_load_timeout=self.post_load_timeout
            )
        
        if self.file_processor is None:
            self.file_processor = FileProcessor(
                cfg=self.cfg,
                model_config=self.model_config
            )
        

    def _setup_model_config(self):
        """Setup model configuration with backward compatibility"""
        if ('model' in self.cfg.doc_processing or
            ('model_config' not in self.cfg.doc_processing and 'model' not in self.cfg.doc_processing)):
            logger.warning(
                "doc_processing.model will no longer be supported in a future release. Use doc_processing.model_config instead.")

            provider = self.cfg.doc_processing.get("model", "openai")
            pcfg = {
                'provider': provider,
                'model_name': self.cfg.doc_processing.get("model_name", "gpt-4o"),
                'base_url': self.cfg.doc_processing.get("base_url",
                                                        "https://api.openai.com/v1") if provider == 'openai' else \
                    self.cfg.doc_processing.get("base_url", "https://api.anthropic.com/"),
            }
            mcfg = {
                'text': pcfg,
                'vision': pcfg,
            }  # By default use the same model for text and image processing
            OmegaConf.update(self.cfg, "doc_processing.model_config", mcfg, merge=False)

        return self.cfg.doc_processing.get("model_config", {})
    
    def _validate_model_dependencies(self):
        """Validate model dependencies and disable features if needed"""
        text_api_key = get_api_key(self.model_config.get('text', {}).get('provider', None), self.cfg)
        vision_api_key = get_api_key(self.model_config.get('vision', {}).get('provider', None), self.cfg)

        if self.parse_tables and text_api_key is None and self.process_locally:
            self.parse_tables = False
            logger.warning("Table summarization enabled but model API key not found, disabling table summarization")

        if self.summarize_images and vision_api_key is None:
            self.summarize_images = False
            logger.warning(
                "Image summarization (doc_processing.summarize_images) enabled but model API key not found, disabling image summarization")

        if self.contextual_chunking and text_api_key is None:
            self.contextual_chunking = False
            logger.warning("Contextual chunking enabled but model API key not found, disabling contextual chunking")

        if self.extract_metadata and text_api_key is None:
            self.extract_metadata = []
            logger.warning(
                "Metadata extraction (doc_processing.extract_metadata) enabled but model API key not found, disabling metadata extraction")

    def normalize_text(self, text: str) -> str:
        return normalize_text(text, self.cfg)

    def normalize_value(self, v):
        return normalize_value(v, self.cfg)

    def setup(self, use_playwright: bool = True) -> None:
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.vectara)

        # Browser handling is now done by WebContentExtractor
        if self.store_docs:
            uuid_suffix = f"indexed_docs_{str(uuid.uuid4())}"
            docker_output_path = f'/home/vectara/{self.output_dir}'

            self.store_docs_folder = get_docker_or_local_path(
                docker_path=os.path.join(docker_output_path, uuid_suffix),
                output_dir=os.path.join(self.output_dir, uuid_suffix),
                should_delete_existing=True
            )

    def store_file(self, filename: str, orig_filename) -> None:
        if self.store_docs:
            dest_path = f"{self.store_docs_folder}/{orig_filename}"
            shutil.copyfile(filename, dest_path)

    def url_triggers_download(self, url: str) -> bool:
        self._init_processors()
        # Direct sync call since WebContentExtractor is now sync
        return self.web_extractor.url_triggers_download(url)

    def fetch_page_contents(
            self,
            url: str,
            extract_tables: bool = False,
            extract_images: bool = False,
            remove_code: bool = False,
            html_processing: dict = None,
            debug: bool = False
    ) -> dict:
        '''
        Fetch content from a URL with a timeout, including content from the Shadow DOM.
        '''
        self._init_processors()
        # Direct sync call since WebContentExtractor is now sync
        return self.web_extractor.fetch_page_contents(
            url, extract_tables, extract_images, remove_code, html_processing, debug
        )
    
    def check_download_or_pdf(self, url: str, timeout: int = 5000):
        """Check if URL triggers download or serves PDF content directly"""
        self._init_processors()
        # Direct sync call since WebContentExtractor is now sync
        return self.web_extractor.check_download_or_pdf(url, get_headers(self.cfg), timeout)


    def _does_doc_exist(self, doc_id: str) -> bool:
        """
        Check if a document exists in the Vectara corpus with caching.

        Args:
            doc_id (str): ID of the document to check.

        Returns:
            bool: True if the document exists, False otherwise.
        """
        # Check cache first - this moves item to end (most recently used)
        if doc_id in self._doc_exists_cache:
            self._doc_exists_cache.move_to_end(doc_id)
            return self._doc_exists_cache[doc_id]
        
        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }
        response = self.session.get(
            f"{self.api_url}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            headers=post_headers)
        
        exists = response.status_code == 200
        
        # LRU eviction: remove least recently used item when cache is full
        if len(self._doc_exists_cache) >= self._max_cache_size:
            self._doc_exists_cache.popitem(last=False)
        
        self._doc_exists_cache[doc_id] = exists
        return exists

    # delete document; returns True if successful, False otherwise
    def delete_doc(self, doc_id: str) -> bool:
        """
        Delete a document from the Vectara corpus.

        Args:
            url (str): URL of the page to delete.
            doc_id (str): ID of the document to delete.

        Returns:
            bool: True if the delete was successful, False otherwise.
        """
        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }

        response = self.session.delete(
            f"{self.api_url}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            headers=post_headers)

        if response.status_code != 204:
            logger.error(
                f"Delete request failed for doc_id = {doc_id} with status code {response.status_code}, reason {response.reason}, text {response.text}")
            return False
        
        # Clear from cache since it's now deleted
        self._doc_exists_cache.pop(doc_id, None)
        return True

    def _list_docs(self) -> List[Dict[str, str]]:
        """
        List documents in the corpus.
        Returns:
            list of [docId, URL] for each document in the corpus
            URL taken from metadata if exists, otherwise it'd be None
        """
        page_key = None  # Initialize page_key as None
        docs = []

        # Loop until there's no next page
        while True:
            params = {"limit": 100}
            if page_key:  # Add page_key to the request if it's not None
                params["page_key"] = page_key

            post_headers = {
                'x-api-key': self.api_key,
                'X-Source': self.x_source
            }
            response = self.session.get(
                f"{self.api_url}/v2/corpora/{self.corpus_key}/documents",
                headers=post_headers, params=params)
            if response.status_code != 200:
                logger.error(f"Error listing documents with status code {response.status_code}")
                return []
            res = response.json()

            # Extract URLs from documents
            for doc in res.get('documents', []):
                url = doc['metadata']['url'] if 'url' in doc['metadata'] else None
                docs.append({'id': doc['id'], 'url': url})

            response_metadata = res.get('metadata', None)
            # Check if we need to go further
            if not response_metadata or not response_metadata['page_key']:  # Break the loop if there's no next page
                break
            else:
                page_key = response_metadata['page_key']

        return docs


    def _index_file(self, filename: str, uri: str, metadata: Dict[str, Any], id: str = None) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus, using APIv2
        """
        if not os.path.exists(filename):
            logger.error(f"File {filename} does not exist")
            return False

        metadata = prepare_file_metadata(metadata, filename, self.static_metadata)
        
        post_headers = {
            'Accept': 'application/json',
            'x-api-key': self.api_key,
        }
        url = f"{self.api_url}/v2/corpora/{self.corpus_key}/upload_file"
        upload_filename = id if id is not None else os.path.basename(filename)

        def upload_file():
            with open(filename, 'rb') as file_handle:
                files, _, content_type = create_upload_files_dict(filename, metadata, self.parse_tables, self.cfg)
                files['file'] = (upload_filename, file_handle, content_type)
                return self.session.request("POST", url, headers=post_headers, files=files)

        response = upload_file()
        success = handle_file_upload_response(response, uri, self.reindex, self.delete_doc)
        
        if success and response.status_code == 409 and self.reindex:
            # Retry after deletion
            response = upload_file()
            success = response.status_code == 201
            if success:
                logger.info(f"REST upload for {uri} successful (reindex)")
            else:
                logger.error(f"REST upload for {uri} (reindex) failed with code = {response.status_code}")
        
        if success and self.store_docs:
            store_file(filename, url_to_filename(uri), self.store_docs, self.store_docs_folder)
            
        return success

    def index_document(self, document: Dict[str, Any], use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the document dictionary

        Args:
            document (dict): Document to index.
            use_core_indexing (bool): Whether to use the core indexing API.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        api_endpoint = f"{self.api_url}/v2/corpora/{self.corpus_key}/documents"
        doc_exists = self._does_doc_exist(document['id'])
        if doc_exists:
            if self.reindex:
                logger.info(f"Document {document['id']} already exists, deleting then reindexing")
                self.delete_doc(document['id'])
            else:
                logger.info(f"Document {document['id']} already exists, skipping")
                return False


        if self.static_metadata:
            metadata = None
            if 'metadata' in document:
                metadata = document['metadata']
            else:
                metadata = {}
                document['metadata'] = metadata
            metadata.update({k: v for k, v in self.static_metadata.items() if k not in metadata})

        # Normalize URLs in document metadata
        if 'metadata' in document and 'url' in document['metadata']:
            document['metadata']['url'] = normalize_url_for_metadata(document['metadata']['url'])
        
        # Normalize URLs in section metadata
        if 'sections' in document:
            for section in document['sections']:
                if 'metadata' in section and 'url' in section['metadata']:
                    section['metadata']['url'] = normalize_url_for_metadata(section['metadata']['url'])

        if use_core_indexing:
            document['type'] = 'core'
        else:
            document['type'] = 'structured'

        if not self.use_core_indexing:
            chunking_config = get_chunking_config(self.cfg)
            if chunking_config:
                document['chunking_strategy'] = chunking_config

        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }
        try:
            data = json.dumps(document)
        except Exception as e:
            logger.info(f"Can't serialize document {document} (error {e}), skipping")
            return False

        try:
            response = self.session.post(api_endpoint, data=data, headers=post_headers)
        except Exception as e:
            logger.info(f"Exception {e} while indexing document {document['id']}")
            return False

        if response.status_code != 201:
            logger.error("REST upload failed with code %d, reason %s, text %s",
                              response.status_code,
                              response.reason,
                              response.text)
            return False

        if self.store_docs:
            with open(f"{self.store_docs_folder}/{document['id']}.json", "w") as f:
                json.dump(document, f)
        return True



    def index_url(self, url: str, metadata: Dict[str, Any], html_processing: dict = None) -> bool:
        """
        Index a url by rendering it with scrapy-playwright, extracting paragraphs, then uploading to the Vectara corpus.

        Args:
            url (str): URL for where the document originated.
            metadata (dict): Metadata for the document.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        succeeded = False
        if html_processing is None:
            html_processing = {}
        st = time.time()
        url = url.split("#")[0]  # remove fragment, if exists

        # if file is going to download, then handle it as local file
        if self.url_triggers_download(url):
            os.makedirs("/tmp", exist_ok=True)
            url_file_path = get_file_path_from_url(url)
            if not url_file_path:
                logger.error(f"Failed to extract file path from URL {url}, skipping...")
                return False
            file_path = os.path.join("/tmp/" + url_file_path)

            response = self.session.get(url, headers=get_headers(self.cfg), stream=True)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"File downloaded successfully and saved as {file_path}")
                res = self.index_file(file_path, url, metadata)
                safe_remove_file(file_path)
                return res
            else:
                logger.error(f"Failed to download file. Status code: {response.status_code}")
                return False

        # If MD or IPYNB file, then we don't need playwright - can just download content directly and convert to text
        if url.lower().endswith(".md") or url.lower().endswith(".ipynb"):
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            dl_content = response.content.decode('utf-8')
            if url.lower().endswith('md'):
                html_content = markdown.markdown(dl_content)
            elif url.lower().endswith('ipynb'):
                nb = nbformat.reads(dl_content, as_version=4)
                exporter = HTMLExporter()
                html_content, _ = exporter.from_notebook_node(nb)
            doc_title = os.path.basename(url)  # no title in these files, so using file name
            text = html_to_text(html_content, self.remove_code)
            parts = [text]

        else:
            try:
                # Check if URL triggers download or serves PDF content
                result = self.check_download_or_pdf(url)
                
                if result["type"] == "download":
                    # Handle explicit download
                    download = result["download"]
                    final_url = result["url"]
                    if 'url' in metadata:
                        metadata['url'] = normalize_url_for_metadata(final_url)
                    suggested = result["filename"] or ""
                    ext = os.path.splitext(suggested)[1]
                    if not ext:
                        parsed = urllib.parse.urlparse(final_url)
                        ext = os.path.splitext(parsed.path)[1] or ".pdf"
                    filename = suggested or f"{uuid.uuid4()}{ext}"
                    
                    file_path = os.path.join(tempfile.gettempdir(), filename)
                    download.save_as(file_path)
                    result = self.index_file(file_path, final_url, metadata)
                    safe_remove_file(file_path)
                    return result
                    
                elif result["type"] == "pdf":
                    # Handle inline PDF
                    final_url = result["url"]
                    parsed = urllib.parse.urlparse(final_url)
                    ext = os.path.splitext(parsed.path)[1] or ".pdf"
                    filename = os.path.basename(parsed.path) or f"{uuid.uuid4()}{ext}"
                    file_path = os.path.join(tempfile.gettempdir(), filename)
                    
                    if 'url' in metadata:
                        metadata['url'] = normalize_url_for_metadata(final_url)
                    with open(file_path, "wb") as f:
                        f.write(result["content"])
                    res = self.index_file(file_path, final_url, metadata)
                    safe_remove_file(file_path)
                    return res

                # If not download or PDF, fetch the page content
                res = self.fetch_page_contents(
                    url=url,
                    extract_tables=self.parse_tables,
                    extract_images=self.summarize_images,
                    remove_code=self.remove_code,
                    html_processing=html_processing,
                )
                html = res['html']
                text = res['text']
                doc_title = res['title']
                metadata['url'] = normalize_url_for_metadata(res['url'])
                if text is None or len(text) < 3:
                    return False

                # If process_locally is enabled, route web content through document parser
                if self.process_locally:
                    try:
                        # Save HTML to temporary file and process through doc parser
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp_file:
                            tmp_file.write(html)
                            tmp_file.flush()
                            temp_html_path = tmp_file.name
                        
                        if self.verbose:
                            logger.info(f"Processing web content from {url} locally using doc parser: {self.doc_parser}")
                        
                        # Process through index_file which uses the configured document parser
                        result = self.index_file(temp_html_path, url, metadata)
                        safe_remove_file(temp_html_path)
                        return result
                    except Exception as e:
                        logger.warning(f"Failed to process {url} locally with doc parser: {e}. Falling back to web extraction.")
                        safe_remove_file(temp_html_path)
                        # Continue with normal web processing below

                # Extract the last modified date from the HTML content.
                ext_res = extract_last_modified(url, html)
                last_modified = ext_res.get('last_modified', None)
                if last_modified:
                    metadata['last_updated'] = last_modified.strftime("%Y-%m-%d")

                # Detect language if needed
                if self.detected_language is None:
                    self.detected_language = detect_language(text)
                    logger.info(f"The detected language is {self.detected_language}")

                if len(self.extract_metadata) > 0:
                    ex_metadata = get_attributes_from_text(
                        self.cfg,
                        text,
                        metadata_questions=self.extract_metadata,
                        model_config=self.model_config.text
                    )
                    metadata.update(ex_metadata)
                else:
                    ex_metadata = {}

                #
                # By default, 'text' is extracted above.
                # If remove_boilerplate is True, then use it directly
                # If no boilerplate remove but need to remove code, then we need to use html_to_text
                #
                if self.remove_boilerplate:
                    url = res['url']
                    if self.verbose:
                        logger.info(
                            f"Removing boilerplate from content of {url}, and extracting important text only")
                    text, doc_title = get_article_content(html, url, self.detected_language, self.remove_code)
                else:
                    text = html_to_text(html, self.remove_code, html_processing)

                parts = [text]
                metadatas = [{'element_type': 'text'}]

                # Process tables
                vec_tables = []
                if self.parse_tables and 'tables' in res:
                    from core.table_extractor import TableExtractor
                    table_extractor = TableExtractor(
                        cfg=self.cfg,
                        model_config=self.model_config,
                        verbose=self.verbose
                    )
                    vec_tables = table_extractor.process_tables(res['tables'], url)

                # Check if images should be indexed inline or separately
                if self.file_processor.inline_images:
                    # Inline mode: Process images and create unified content stream
                    all_texts = []
                    all_metadatas = []
                    
                    # Add text elements
                    for text, segment_metadata in zip(parts, metadatas):
                        all_texts.append(text)
                        all_metadatas.append(segment_metadata)
                    
                    # Add image elements inline if images exist and summarization is enabled
                    if self.summarize_images and 'images' in res:
                        image_processor = ImageProcessor(
                            cfg=self.cfg,
                            model_config=self.model_config,
                            verbose=self.verbose
                        )
                        processed_images, web_image_bytes = image_processor.process_web_images(res['images'], url, ex_metadata)
                        if web_image_bytes and self.verbose:
                            logger.info(f"URL {url} contains {len(web_image_bytes)} images with binary data available")
                        
                        for _, image_summary, image_metadata in processed_images:
                            all_texts.append(image_summary)
                            all_metadatas.append(image_metadata)
                    
                    # Index unified content in single document
                    doc_id = slugify(url)
                    succeeded = self.index_segments(
                        doc_id=doc_id, 
                        texts=all_texts, 
                        metadatas=all_metadatas, 
                        tables=vec_tables,
                        doc_metadata=metadata, 
                        doc_title=doc_title,
                        image_bytes=web_image_bytes if 'web_image_bytes' in locals() else []
                    )
                else:
                    # Legacy mode: Index text and images separately
                    # Index text and tables first
                    doc_id = slugify(url)
                    succeeded = self.index_segments(
                        doc_id=doc_id, 
                        texts=parts, 
                        metadatas=metadatas, 
                        tables=vec_tables,
                        doc_metadata=metadata, 
                        doc_title=doc_title
                    )
                    
                    # Index images as separate documents
                    if self.summarize_images and 'images' in res:
                        image_processor = ImageProcessor(
                            cfg=self.cfg,
                            model_config=self.model_config,
                            verbose=self.verbose
                        )
                        processed_images, web_image_bytes = image_processor.process_web_images(res['images'], url, ex_metadata)
                        if web_image_bytes and self.verbose:
                            logger.info(f"URL {url} contains {len(web_image_bytes)} images with binary data available")
                        
                        for doc_id, image_summary, image_metadata in processed_images:
                            # Pass web image bits if available and enabled
                            image_bytes_param = web_image_bytes if self.add_image_bytes else []
                            
                            succeeded &= self.index_segments(
                                doc_id=doc_id,
                                texts=[image_summary],
                                metadatas=[image_metadata],
                                doc_metadata=image_metadata,
                                doc_title=doc_title,
                                image_bytes=image_bytes_param,
                                use_core_indexing=True
                            )

                logger.info(f"retrieving content took {time.time() - st:.2f} seconds")
            except Exception as e:
                import traceback
                logger.error(
                    f"Failed to crawl {url}, skipping due to error {e}, traceback={traceback.format_exc()}")
                return False

        return succeeded

    def index_segments(self, doc_id: str, texts: List[str], titles: Optional[List[str]] = None,
                       metadatas: Optional[List[Dict[str, Any]]] = None,
                       doc_metadata: Dict[str, Any] = None, doc_title: str = "",
                       tables: Optional[Sequence[Dict[str, Any]]] = None,
                       image_bytes: Optional[List[Tuple[str, bytes]]] = None,
                       use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        
        Args:
            image_bytes: Optional list of (image_id, binary_data) tuples containing image binary data
        """
        self._init_processors()
        
        texts = list(texts) if texts else []
        tables = list(tables) if tables else []
        image_bytes = list(image_bytes) if image_bytes else []
        
        # Log image bits availability
        if image_bytes and self.verbose:
            logger.info(f"Document {doc_id} has {len(image_bytes)} images with binary data available for later upload")

        from core.document_builder import DocumentBuilder
        # Normalize URLs in doc_metadata
        if doc_metadata and 'url' in doc_metadata:
            doc_metadata['url'] = normalize_url_for_metadata(doc_metadata['url'])
        
        document_builder = DocumentBuilder(
            cfg=self.cfg,
            normalize_text_func=lambda text: normalize_text(text, self.cfg)
        )
        document = document_builder.build_document(
            doc_id=doc_id,
            texts=texts,
            titles=titles,
            metadatas=metadatas,
            doc_metadata=doc_metadata,
            doc_title=doc_title,
            tables=tables,
            use_core_indexing=use_core_indexing
        )
        
        if document is None:
            return False
            
        # Add image binary data if available and enabled
        if self.add_image_bytes and image_bytes and metadatas:
            images_array = []
            updated_document_parts = []
            
            # Process each text/metadata pair to find images
            for i, (text, metadata) in enumerate(zip(texts, metadatas)):
                image_id = metadata.get('image_id') if metadata else None
                
                if image_id:
                    # Find binary data for this image
                    binary_data = self._find_image_binary_data(image_id, image_bytes)
                    if binary_data:
                        mime_type = self._detect_image_mime_type(image_id, binary_data)
                        
                        # Add to images array - encode binary data as base64 for JSON serialization
                        images_array.append({
                            "id": image_id,
                            "caption": "",
                            "description": text,
                            "image_data": {
                                "data": base64.b64encode(binary_data).decode('utf-8'),
                                "mime_type": mime_type
                            }
                        })
                        
                        # Update document part to reference the image
                        updated_document_parts.append({
                            "text": text,
                            "image_id": image_id,
                            "metadata": metadata
                        })
                        
                        if self.verbose:
                            logger.info(f"Added binary data for image {image_id} with MIME type {mime_type}")
                    else:
                        # No binary data found, add as regular text
                        updated_document_parts.append({
                            "text": text,
                            "metadata": metadata
                        })
                        if self.verbose:
                            logger.warning(f"Binary data not found for image {image_id}")
                else:
                    # Regular text element
                    updated_document_parts.append({
                        "text": text,
                        "metadata": metadata
                    })
            
            # Update document structure if we found any images with binary data
            if images_array:
                document["images"] = images_array
                document["document_parts"] = updated_document_parts
                if self.verbose:
                    logger.info(f"Document {doc_id} now includes {len(images_array)} images with binary data")
            
        if self.verbose:
            logger.info(f"Indexing document {doc_id} with json {str(document)[:500]}...")

        return self.index_document(document, use_core_indexing)

    def index_file(self, filename: str, uri: str, metadata: Dict[str, Any], id: str = None) -> bool:
        """
        Index a file on local file system by uploading it to the Vectara corpus.

        Args:
            filename (str): Name of the PDF file to create.
            uri (str): URI for where the document originated. In some cases the local file name is not the same, and we want to include this in the index.
            metadata (dict): Metadata for the document.
            id (str, optional): Document id for the uploaded document.

        Returns:
            bool: True if the upload was successful, False otherwise.
        """
        if not os.path.exists(filename):
            logger.error(f"File {filename} does not exist")
            return False

        # Determine processing strategy
        self._init_processors()
        
        if self.file_processor.should_process_locally(filename, uri):
            self.process_locally = True

        #
        # Case A: using the file-upload API
        # Used when we don't need to process the file locally, and we don't need to parse tables from non-PDF files
        #
        if not self.process_locally and (
                (self.parse_tables and filename.lower().endswith('.pdf')) or not self.parse_tables):
            logger.info(f"For {uri} - Uploading via Vectara file upload API")
            if len(self.extract_metadata) > 0 or self.summarize_images:
                logger.info(f"Reading contents of {filename} (url={uri})")
                dp = UnstructuredDocumentParser(
                    cfg=self.cfg,
                    verbose=self.verbose,
                    model_config=self.cfg.doc_processing.model_config,
                    parse_tables=False, enable_gmft=False,
                    summarize_images=self.summarize_images,
                    image_context=self.image_context,
                )
                parsed_doc = dp.parse(filename, uri)
                title, texts, _, images = parsed_doc.to_legacy_format()

            # Get metadata attribute values from text content (if defined)
            ex_metadata = {}
            if len(self.extract_metadata) > 0:
                if 'text' not in self.model_config:
                    logger.warning("Metadata field extraction is enabled but no text model is configured, skipping")
                else:
                    max_chars = 128000  # all_text is limited to 128,000 characters
                    all_text = "\n".join([t[0] for t in texts])[:max_chars]
                    ex_metadata = get_attributes_from_text(
                        self.cfg,
                        all_text,
                        metadata_questions=self.extract_metadata,
                        model_config=self.model_config.text
                    )
            metadata['file_name'] = os.path.basename(filename)
            metadata.update(ex_metadata)

            if self.file_processor.needs_pdf_splitting(filename):
                # Split large PDF into smaller chunks
                pdf_parts = self.file_processor.split_pdf(filename, metadata)
                error_count = 0
                
                for pdf_path, pdf_metadata, pdf_id in pdf_parts:
                    try:
                        part_success = self._index_file(pdf_path, uri, pdf_metadata, pdf_id)
                        if not part_success:
                            error_count += 1
                    finally:
                        safe_file_cleanup(pdf_path)
                        
                succeeded = error_count == 0
            else:
                # index the file within Vectara (use FILE UPLOAD API)
                succeeded = self._index_file(filename, uri, metadata, id)

            # If indicated, summarize images - and upload each image summary as a single doc
            if self.summarize_images and images:
                logger.info(f"Extracted {len(images)} images from {uri}")
                for inx, image in enumerate(images):
                    image_summary = image[0]
                    img_metadata = image[1]
                    if ex_metadata:
                        img_metadata.update(ex_metadata)
                    doc_id = slugify(uri) + "_image_" + str(inx)
                    
                    # Pass image bits if available and enabled
                    image_bytes_param = parsed_doc.image_bytes if self.add_image_bytes and hasattr(parsed_doc, 'image_bytes') else []
                    
                    succeeded &= self.index_segments(
                        doc_id=doc_id, 
                        texts=[image_summary], 
                        metadatas=[img_metadata],
                        doc_metadata=metadata, 
                        doc_title=title, 
                        image_bytes=image_bytes_param,
                        use_core_indexing=True
                    )
            return succeeded

        #
        # Case B: Process locally and upload to Vectara
        #
        logger.info(f"Parsing file {filename} locally")
        
        try:
            parsed_doc = self.file_processor.process_file(filename, uri)
        except Exception as e:
            import traceback
            logger.info(f"Failed to parse {filename} with error {e}, traceback={traceback.format_exc()}")
            return False

        # Extract metadata from all text content
        max_chars = 128000
        all_text = "\n".join([content for content, metadata in parsed_doc.content_stream 
                            if metadata.get('element_type') == 'text'])[:max_chars]
        ex_metadata = self.file_processor.extract_metadata_from_text(all_text, metadata)

        # Apply contextual chunking to text elements if needed
        content_stream = parsed_doc.content_stream
        if self.file_processor.contextual_chunking:
            text_elements = [(content, metadata) for content, metadata in content_stream 
                           if metadata.get('element_type') == 'text']
            processed_text_contents = self.file_processor.apply_contextual_chunking(text_elements, uri)
            
            # Rebuild content stream with processed text
            processed_content_stream = []
            text_index = 0
            for content, metadata in content_stream:
                if metadata.get('element_type') == 'text':
                    processed_content_stream.append((processed_text_contents[text_index], metadata))
                    text_index += 1
                else:
                    processed_content_stream.append((content, metadata))
            content_stream = processed_content_stream

        # Process tables
        processed_tables = self.file_processor.generate_vec_tables(parsed_doc.tables)
        
        # Store image binary bits for later use (available in parsed_doc.image_bytes)
        if parsed_doc.image_bytes and self.verbose:
            logger.info(f"Document {filename} contains {len(parsed_doc.image_bytes)} images with binary data available")

        # Check if images should be indexed inline or separately
        if self.file_processor.inline_images:
            # Index all content (text and images) in a single document
            texts = [content for content, metadata in content_stream]
            metadatas = [metadata for content, metadata in content_stream]
            
            succeeded = self.index_segments(
                doc_id=slugify(uri),
                texts=texts,
                metadatas=metadatas,
                tables=processed_tables,
                doc_metadata=metadata,
                doc_title=parsed_doc.title,
                image_bytes=parsed_doc.image_bytes,
                use_core_indexing=self.use_core_indexing or self._is_chunking_enabled()
            )
        else:
            # Legacy mode: Index text in main document, images as separate documents
            text_content = []
            image_content = []
            elements_without_type = []
            
            for content, meta in content_stream:
                element_type = meta.get('element_type')
                if element_type == 'text':
                    text_content.append((content, meta))
                elif element_type == 'image':
                    image_content.append((content, meta))
                elif element_type is None:
                    # Default to text if element_type is missing
                    text_content.append((content, meta))
                    elements_without_type.append(content[:50] + "..." if len(content) > 50 else content)
                else:
                    # Unknown element_type, default to text
                    text_content.append((content, meta))
                    logger.warning(f"Unknown element_type '{element_type}' found, treating as text")
            
            if elements_without_type:
                logger.warning(f"Found {len(elements_without_type)} content elements without element_type metadata, treating as text")
            
            # Index text portions
            texts = [content for content, meta in text_content]
            metadatas = [meta for content, meta in text_content]
            
            succeeded = self.index_segments(
                doc_id=slugify(uri),
                texts=texts,
                metadatas=metadatas,
                tables=processed_tables,
                doc_metadata=metadata,
                doc_title=parsed_doc.title,
                image_bytes=parsed_doc.image_bytes,
                use_core_indexing=self.use_core_indexing or self._is_chunking_enabled()
            )
            
            # Index images as separate documents
            if image_content:
                for idx, (image_summary, image_metadata) in enumerate(image_content):
                    doc_id = f"{slugify(uri)}_image_{idx}"
                    image_metadata.update(ex_metadata)  # Add extracted metadata
                    try:
                        # Pass image bits if available and enabled
                        image_bytes_param = parsed_doc.image_bytes if self.add_image_bytes else []
                        
                        img_okay = self.index_segments(
                            doc_id=doc_id,
                            texts=[image_summary],
                            metadatas=[image_metadata],
                            doc_metadata=image_metadata,
                            doc_title=parsed_doc.title,
                            image_bytes=image_bytes_param,
                            use_core_indexing=True
                        )
                        succeeded &= img_okay
                    except Exception as e:
                        logger.info(f"Failed to index image {idx} with error {e}")
                        succeeded = False
            
        return succeeded

    def index_media_file(self, file_path, metadata=None):
        """
        Index a media file (audio or video) by transcribing it with Whisper and uploading it to the Vectara corpus.

        Args:
            file_path (str): Path to the media file.
            metadata (dict): Metadata for the document.

        Returns:
            bool: True if the upload was successful, False
        """
        logger.info(
            f"Transcribing file {file_path} with Whisper model of size {self.whisper_model_name} (this may take a while)")
        if self.whisper_model is None:
            self.whisper_model = whisper.load_model(self.whisper_model_name, device="cpu")
        result = self.whisper_model.transcribe(file_path, temperature=0, verbose=False)
        text = result['segments']
        doc = {
            'id': slugify(file_path),
            'title': file_path,
            'sections': [
                {
                    'text': t['text'],
                } for t in text
            ]
        }
        if metadata:
            doc['metadata'] = metadata
        self.index_document(doc)
        
    def cleanup(self):
        """Clean up resources used by the indexer"""
        if self.web_extractor:
            # Direct sync call since WebContentExtractor is now sync
            self.web_extractor.cleanup()
        # Clear caches
        self._doc_exists_cache.clear()
        
    def _detect_image_mime_type(self, image_id: str = "", image_data: bytes = None) -> str:
        """Detect MIME type for image data"""
        if image_data:
            # Check for common image headers
            if image_data.startswith(b'\xff\xd8\xff'):
                return "image/jpeg"
            elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                return "image/png"
            elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
                return "image/gif"
            elif image_data.startswith(b'\x00\x00\x01\x00') or image_data.startswith(b'\x00\x00\x02\x00'):
                return "image/x-icon"
        
        # Fallback to guessing from image_id/filename
        if image_id:
            mime_type, _ = mimetypes.guess_type(image_id)
            if mime_type and mime_type.startswith('image/'):
                return mime_type
        
        # Default fallback
        return "image/png"
    
    def _find_image_binary_data(self, image_id: str, image_bytes: List[Tuple[str, bytes]]) -> Optional[bytes]:
        """Find binary data for a given image ID"""
        if not image_bytes or not image_id:
            return None
            
        for stored_id, binary_data in image_bytes:
            if stored_id == image_id:
                return binary_data
        
        # If exact match not found, try partial match (useful for web images)
        for stored_id, binary_data in image_bytes:
            if image_id in stored_id or stored_id in image_id:
                return binary_data
                
        return None
