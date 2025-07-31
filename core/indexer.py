import logging
logger = logging.getLogger(__name__)
import json
import time
import warnings
from typing import Dict, Any, List, Optional, Sequence
import shutil

import uuid
import pandas as pd
import urllib.parse, tempfile, os

from slugify import slugify

from omegaconf import OmegaConf
from nbconvert import HTMLExporter  # type: ignore
import nbformat
import markdown
import whisper
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


from core.summary import TableSummarizer, get_attributes_from_text
from core.models import get_api_key
from core.utils import (
    html_to_text, detect_language, get_file_size_in_MB, create_session_with_retries,
    mask_pii, safe_remove_file, url_to_filename, df_cols_to_headers, html_table_to_header_and_rows,
    get_file_path_from_url, create_row_items, configure_session_for_ssl, get_docker_or_local_path,
    doc_extensions, get_headers, normalize_text, normalize_value
)
from core.extract import get_article_content
from core.doc_parser import UnstructuredDocumentParser, DoclingDocumentParser, LlamaParseDocumentParser, \
    DocupandaDocumentParser
from core.contextual import ContextualChunker
from core.indexer_utils import (
    get_chunking_config, extract_last_modified, create_upload_files_dict, 
    handle_file_upload_response, safe_file_cleanup, prepare_file_metadata, store_file
)
from core.web_content_extractor import WebContentExtractor
from core.file_processor import FileProcessor
from core.document_builder import DocumentBuilder
from core.table_extractor import TableExtractor
from core.image_processor import ImageProcessor
from pypdf import PdfReader, PdfWriter

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
                 corpus_key: str, api_key: str) -> None:
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
        self.whisper_model = None
        self.whisper_model_name = cfg.vectara.get("whisper_model", "base")
        self.static_metadata = cfg.get('metadata', None)

        if 'doc_processing' not in cfg:
            cfg.doc_processing = {}
        self.parse_tables = cfg.doc_processing.get("parse_tables", cfg.doc_processing.get("summarize_tables",
                                                                                          False))  # backward compatibility
        self.enable_gmft = cfg.doc_processing.get("enable_gmft", False)
        self.do_ocr = cfg.doc_processing.get("do_ocr", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.process_locally = cfg.doc_processing.get("process_locally", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.use_core_indexing = cfg.doc_processing.get("use_core_indexing", False)
        self.unstructured_config = cfg.doc_processing.get("unstructured_config",
                                                          {'chunking_strategy': 'by_title', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", {'chunking_strategy': 'none'})
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        self.contextual_chunking = cfg.doc_processing.get("contextual_chunking", False)

        self.model_config = self._setup_model_config()
        self._validate_model_dependencies()

        logger.info(f"Vectara API Url = '{self.api_url}'")

        # Initialize specialized processors (lazy loading)
        self.web_extractor = None
        self.file_processor = None
        self.document_builder = None
        self.table_extractor = None
        self.image_processor = None
        
        # Performance optimizations
        self._doc_exists_cache = {}  # Cache for document existence checks

        self.setup()

    def _init_processors(self):
        """Lazy initialization of specialized processors"""
        if self.web_extractor is None:
            self.web_extractor = WebContentExtractor(
                cfg=self.cfg,
                timeout=self.timeout,
                post_load_timeout=self.post_load_timeout
            )
        
        if self.file_processor is None:
            self.file_processor = FileProcessor(
                cfg=self.cfg,
                model_config=self.model_config
            )
        
        if self.document_builder is None:
            self.document_builder = DocumentBuilder(
                cfg=self.cfg,
                normalize_text_func=lambda text: normalize_text(text, self.cfg)
            )
        
        if self.table_extractor is None:
            self.table_extractor = TableExtractor(
                cfg=self.cfg,
                model_config=self.model_config,
                verbose=self.verbose
            )
        
        if self.image_processor is None:
            self.image_processor = ImageProcessor(
                cfg=self.cfg,
                model_config=self.model_config,
                verbose=self.verbose
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
            docker_env_path = '/home/vectara/env'

            self.store_docs_folder = get_docker_or_local_path(
                docker_path=os.path.join(docker_env_path, uuid_suffix),
                output_dir=os.path.join(self.output_dir, uuid_suffix),
                should_delete_existing=True
            )

    def store_file(self, filename: str, orig_filename) -> None:
        if self.store_docs:
            dest_path = f"{self.store_docs_folder}/{orig_filename}"
            shutil.copyfile(filename, dest_path)

    def url_triggers_download(self, url: str) -> bool:
        self._init_processors()
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
        return self.web_extractor.fetch_page_contents(
            url, extract_tables, extract_images, remove_code, html_processing, debug
        )


    def _does_doc_exist(self, doc_id: str) -> bool:
        """
        Check if a document exists in the Vectara corpus with caching.

        Args:
            doc_id (str): ID of the document to check.

        Returns:
            bool: True if the document exists, False otherwise.
        """
        # Check cache first
        if doc_id in self._doc_exists_cache:
            return self._doc_exists_cache[doc_id]
        
        post_headers = {
            'x-api-key': self.api_key,
            'X-Source': self.x_source
        }
        response = self.session.get(
            f"{self.api_url}/v2/corpora/{self.corpus_key}/documents/{doc_id}",
            headers=post_headers)
        
        exists = response.status_code == 200
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
        upload_filename = id if id is not None else filename.split('/')[-1]

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
            doc_title = url.split('/')[-1]  # no title in these files, so using file name
            text = html_to_text(html_content, self.remove_code)
            parts = [text]

        else:
            try:
                # Use Playwright to get the page content
                self._init_processors()
                context = self.web_extractor.browser.new_context()
                page = context.new_page()
                page.set_extra_http_headers(get_headers(self.cfg))
                file_path = None

                # 1) Try to catch an explicit download
                try:
                    with page.expect_download(timeout=self.timeout * 1000) as dl_info:
                        response = page.goto(url, wait_until="domcontentloaded")
                    download = dl_info.value
                    final_url = download.url
                    if 'url' in metadata:
                        metadata['url'] = final_url
                    suggested = download.suggested_filename or ""
                    ext = os.path.splitext(suggested)[1]
                    if not ext:
                        parsed = urllib.parse.urlparse(final_url)
                        ext = os.path.splitext(parsed.path)[1] or ".pdf"
                    filename = suggested or f"{uuid.uuid4()}{ext}"

                    file_path = os.path.join(tempfile.gettempdir(), filename)
                    download.save_as(file_path)
                    return self.index_file(file_path, final_url, metadata)
                except PlaywrightTimeoutError:
                    # no download event fired → maybe inline PDF or HTML
                    pass
                finally:
                    if page:
                        page.close()
                    if context:
                        context.close()

                # 2) Inspect the response headers for a PDF mime-type
                context = self.web_extractor.browser.new_context()
                page = context.new_page()
                page.set_extra_http_headers(get_headers(self.cfg))
                try:
                    response = page.goto(url, wait_until="domcontentloaded")
                    ctype = response.headers.get("content-type", "")
                    if "application/pdf" in ctype:
                        # figure out exactly where we ended up (Playwright follows redirects)
                        final_url = response.url
                        parsed    = urllib.parse.urlparse(final_url)
                        ext       = os.path.splitext(parsed.path)[1] or ".pdf"
                        filename  = os.path.basename(parsed.path) or f"{uuid.uuid4()}{ext}"
                        file_path = os.path.join(tempfile.gettempdir(), filename)
                        pdf_bytes = response.body()                # get the raw PDF bytes
                        if 'url' in metadata:
                            metadata['url'] = final_url
                        with open(file_path, "wb") as f:
                            f.write(pdf_bytes)
                        return self.index_file(file_path, final_url, metadata)
                finally:
                    if page:
                        page.close()
                    if context:
                        context.close()

                # 3) If not a PDF, then fetch the page content
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
                if text is None or len(text) < 3:
                    return False

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
                    self._init_processors()
                    vec_tables = self.table_extractor.process_tables(res['tables'], url)

                # index text and tables
                doc_id = slugify(url)
                succeeded = self.index_segments(doc_id=doc_id, texts=parts, metadatas=metadatas, tables=vec_tables,
                                                doc_metadata=metadata, doc_title=doc_title)

                # index images - each image as a separate "document" in Vectara
                if self.summarize_images:
                    self._init_processors()
                    if 'images' in res:
                        processed_images = self.image_processor.process_web_images(res['images'], url, ex_metadata)
                        for doc_id, image_summary, image_metadata in processed_images:
                            succeeded &= self.index_segments(
                                doc_id=doc_id,
                                texts=[image_summary],
                                metadatas=[image_metadata],
                                doc_metadata=image_metadata,
                                doc_title=doc_title,
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
                       use_core_indexing: bool = False) -> bool:
        """
        Index a document (by uploading it to the Vectara corpus) from the set of segments (parts) that make up the document.
        """
        self._init_processors()
        
        texts = list(texts) if texts else []
        tables = list(tables) if tables else []

        document = self.document_builder.build_document(
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
        filesize_mb = get_file_size_in_MB(filename)
        
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
                )
                title, texts, _, images = dp.parse(filename, uri)

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
                    metadata.update(ex_metadata)
            metadata.update(ex_metadata)
            metadata['file_name'] = filename.split('/')[-1]

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
                    metadata = image[1]
                    if ex_metadata:
                        metadata.update(ex_metadata)
                    doc_id = slugify(uri) + "_image_" + str(inx)
                    succeeded &= self.index_segments(doc_id=doc_id, texts=[image_summary], metadatas=[metadata],
                                                     doc_metadata=metadata, doc_title=title, use_core_indexing=True)
            return succeeded

        #
        # Case B: Process locally and upload to Vectara
        #
        logger.info(f"Parsing file {filename} locally")
        
        try:
            title, texts, tables, images = self.file_processor.process_file(filename, uri)
        except Exception as e:
            logger.info(f"Failed to parse {filename} with error {e}")
            return False

        # Get metadata attribute values from text content (if defined)
        max_chars = 128000  # all_text is limited to 128,000 characters
        all_text = "\n".join([t[0] for t in texts])[:max_chars]
        ex_metadata = self.file_processor.extract_metadata_from_text(all_text, metadata)

        # Apply contextual chunking if indicated
        processed_texts = self.file_processor.apply_contextual_chunking(texts, uri)
        
        # Process tables
        processed_tables = self.file_processor.generate_vec_tables(tables)

        # Index text portions
        succeeded = self.index_segments(
            doc_id=slugify(uri),
            texts=processed_texts,
            metadatas=[t[1] for t in texts],
            tables=processed_tables,
            doc_metadata=metadata,
            doc_title=title,
            use_core_indexing=self.use_core_indexing or self.file_processor.contextual_chunking
        )

        # index the images - one per document
        if images:
            processed_images = self.image_processor.process_document_images(images, uri, ex_metadata)
            image_success = []
            
            for doc_id, image_summary, image_metadata in processed_images:
                try:
                    img_okay = self.index_segments(
                        doc_id=doc_id,
                        texts=[image_summary],
                        metadatas=[image_metadata],
                        doc_metadata=image_metadata,
                        doc_title=title,
                        use_core_indexing=True
                    )
                    image_success.append(img_okay)
                except Exception as e:
                    logger.info(f"Failed to index image {image_metadata.get('src', 'no image name')} with error {e}")
                    image_success.append(False)
            
            self.image_processor.log_processing_summary(filename, len(images), sum(image_success))
            
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
            self.web_extractor.cleanup()
        # Clear caches
        self._doc_exists_cache.clear()
