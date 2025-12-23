import logging
logger = logging.getLogger(__name__)
from typing import List, Tuple, Iterator, Dict, Any
import time
import pandas as pd
import os
from io import StringIO
import base64
import requests
from dataclasses import dataclass

import pathlib
from pdf2image import convert_from_bytes
from slugify import slugify

from core.summary import TableSummarizer, ImageSummarizer
from core.utils import detect_file_type, markdown_to_df
from core.context_utils import extract_image_context

import unstructured as us
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.html import partition_html
from unstructured.partition.pptx import partition_pptx
from unstructured.partition.docx import partition_docx

from omegaconf import OmegaConf

import nest_asyncio
from llama_parse import LlamaParse

from gmft.pdf_bindings import PyPDFium2Document
from gmft.auto import TableDetector, AutoTableFormatter, AutoFormatConfig

import nltk
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)

from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_VERBOSE_LENGTH = 1000

import warnings
warnings.filterwarnings(
    "ignore",
    message=".*pin_memory.*no accelerator is found.*"
)


def extract_document_title(filename: str) -> str:
    """
    Extract title from document metadata using appropriate libraries.
    
    Supports:
    - PDF files: Uses pypdf to extract title from PDF metadata
    - DOCX files: Uses python-docx to extract title from document properties  
    - PPTX files: Uses python-pptx to extract title from presentation properties
    - HTML files: Returns empty (will fallback to filename)
    - Other files: Returns empty (will fallback to filename or Title elements)
    
    Args:
        filename (str): Path to the document file
        
    Returns:
        str: Document title from metadata, or empty string if not found or on error
    """
    if filename.endswith('.pdf'):
        return _extract_pdf_title(filename)
    elif filename.endswith('.docx'):
        return _extract_docx_title(filename)
    elif filename.endswith('.pptx'):
        return _extract_pptx_title(filename)
    elif filename.endswith(('.html', '.htm')):
        # HTML files should use filename fallback per user requirement
        return ''
    else:
        # Other files return empty for fallback to Title elements or filename
        return ''


def _extract_pdf_title(filename: str) -> str:
    """Extract title from PDF metadata using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(filename)
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title.strip()
            if title:  # Only return non-empty titles
                logger.info(f"Extracted PDF metadata title: '{title}' from file {filename}")
                return title
    except Exception as e:
        logger.warning(f"Failed to extract PDF metadata title from {filename}: {e}")
    return ''


def _extract_docx_title(filename: str) -> str:
    """Extract title from DOCX document properties using python-docx."""
    try:
        from docx import Document
        doc = Document(filename)
        if doc.core_properties.title:
            title = doc.core_properties.title.strip()
            if title:  # Only return non-empty titles
                logger.info(f"Extracted DOCX document title: '{title}' from file {filename}")
                return title
    except ImportError:
        logger.debug(f"python-docx not available, skipping DOCX title extraction for {filename}")
    except Exception as e:
        logger.warning(f"Failed to extract DOCX document title from {filename}: {e}")
    return ''


def _extract_pptx_title(filename: str) -> str:
    """Extract title from PPTX presentation properties using python-pptx."""
    try:
        from pptx import Presentation
        prs = Presentation(filename)
        if prs.core_properties.title:
            title = prs.core_properties.title.strip()
            if title:  # Only return non-empty titles
                logger.info(f"Extracted PPTX presentation title: '{title}' from file {filename}")
                return title
    except ImportError:
        logger.debug(f"python-pptx not available, skipping PPTX title extraction for {filename}")
    except Exception as e:
        logger.warning(f"Failed to extract PPTX presentation title from {filename}: {e}")
    return ''


@dataclass
class ParsedDocument:
    """
    Unified document representation with content in document order
    """
    title: str
    content_stream: List[Tuple[Any, Dict[str, Any]]]  # All content elements in document order
    tables: List[Tuple]  # Detailed table data for structured indexing
    image_bytes: List[Tuple[str, bytes]]  # Image binary data as (image_id, binary_data)
    
    def get_texts(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Get only text elements from content stream"""
        return [(content, metadata) for content, metadata in self.content_stream 
                if metadata.get('element_type') == 'text']
    
    def get_images(self) -> List[Tuple[str, Dict[str, Any]]]:
        """Get only image elements from content stream"""
        return [(content, metadata) for content, metadata in self.content_stream 
                if metadata.get('element_type') == 'image']
    
    def get_all_content(self) -> List[Tuple[Any, Dict[str, Any]]]:
        """Get all content elements in document order"""
        return self.content_stream.copy()
    
    def to_legacy_format(self) -> Tuple[str, List[Tuple], List[Tuple], List[Tuple]]:
        """Convert to legacy (title, texts, tables, images) format for backward compatibility"""
        return (self.title, self.get_texts(), self.tables, self.get_images())
    
    def __iter__(self):
        """Allow direct unpacking: title, texts, tables, images = parsed_doc"""
        return iter(self.to_legacy_format())


class DocumentParser():
    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = {},
        parse_tables: bool = False,
        enable_gmft: bool = False,
        do_ocr: bool = False,
        summarize_images: bool = False,
    ):
        self.cfg = cfg
        self.model_config = model_config
        self.enable_gmft = enable_gmft
        self.do_ocr = do_ocr
        self.parse_tables = parse_tables
        self.summarize_images = summarize_images
        # Support both dict and OmegaConf access patterns
        text_config = model_config.get('text') if isinstance(model_config, dict) else getattr(model_config, 'text', None)
        vision_config = model_config.get('vision') if isinstance(model_config, dict) else getattr(model_config, 'vision', None)
        self.table_summarizer = TableSummarizer(self.cfg, text_config) if self.parse_tables and text_config else None
        self.image_summarizer = ImageSummarizer(self.cfg, vision_config) if self.summarize_images and vision_config else None
        self.verbose = verbose

    def parse(self, filename: str, source_url: str = "No URL") -> ParsedDocument:
        """
        Parse a document and return unified content stream with proper element ordering.
        Subclasses must override this method.
        
        Args:
            filename: Path to the file to parse
            source_url: Source URL for context
            
        Returns:
            ParsedDocument with unified content stream
        """
        raise NotImplementedError("Subclasses must implement parse() method")

    def get_tables_with_gmft(self, filename: str) -> Iterator[Tuple[pd.DataFrame, str, str]]:
        if not filename.endswith('.pdf'):
            logger.warning(f"GMFT: only PDF files are supported, skipping {filename}")
            return None

        detector = TableDetector()
        config = AutoFormatConfig()
        config.semantic_spanning_cells = True   # [Experimental] better spanning cells
        config.enable_multi_header = True       # multi-indices
        formatter = AutoTableFormatter(config)

        doc = PyPDFium2Document(filename)
        try:
            for inx,page in enumerate(doc):
                if inx % 100 == 0:
                    logger.info(f"GMFT: processing page {inx+1}")
                for table in detector.extract(page):
                    try:
                        ft = formatter.extract(table)
                        df = ft.df()
                        table_summary = self.table_summarizer.summarize_table_text(df.to_markdown())
                        yield (df, table_summary, " ".join(ft.captions()), {'page': inx+1})
                    except Exception as e:
                        logger.error(f"Error processing table (with GMFT) on page {inx+1}: {e}")
                        continue
        finally:
            doc.close()
            if self.verbose:
                logger.info("GMFT: Finished processing PDF")


class DocupandaDocumentParser(DocumentParser):

    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = {},
        docupanda_api_key: str = None,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False,
        image_context: dict = None
    ):
        super().__init__(
            verbose=verbose,
            cfg=cfg,
            model_config=model_config,
            parse_tables=parse_tables,
            enable_gmft=enable_gmft,
            do_ocr=False,
            summarize_images=summarize_images
        )
        self._api_key = docupanda_api_key
        self.image_context = image_context or {'num_previous_chunks': 1, 'num_next_chunks': 1}
        if not self._api_key:
            raise ValueError("No Docupanda API key found, skipping Docupanda")

    def parse(
            self,
            filename: str,
            source_url: str = "No URL"
        ) -> ParsedDocument:
        """
        Parse a document and return unified content stream with images interleaved in proper order.
        Tables are extracted separately for structured indexing.
        Using DocuPanda

        Args:
            filename (str): Name of the file to parse.
            source_url (str): Source URL for context.

        Returns:
            ParsedDocument with unified content stream
        """
        st = time.time()
        doc_title = extract_document_title(filename)
        
        all_elements = []  # For building unified content stream
        tables = []
        image_bytes = []  # Store image binary data
        img_folder = '/images'
        base_url = 'https://app.docupanda.io/document'
        os.makedirs(img_folder, exist_ok=True)

        # Phase 1: post document
        payload = {"document": {"file": {
            "contents": base64.b64encode(open(filename, 'rb').read()).decode(),
                "filename": filename
            }}}
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-API-Key": self._api_key
        }
        response = requests.post(base_url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(f"Docupanda: failed to post document, response code {response.status_code}, msg={response.json()}")
            return ParsedDocument(title='', content_stream=[], tables=[], image_bytes=[])

        # Phase 2: get document; poll until ready, but no longer than timeout
        document_id = response.json()['documentId']
        timeout = 60
        start_time = time.time()
        completed = False
        while time.time() - start_time < timeout:
            response = requests.get(f"{base_url}/{document_id}", headers=headers)
            if response.json()['status'] == 'completed':
                completed = True
                break
            time.sleep(1)

        if not completed:
            logger.error(f"Docupanda: document processing timed out after {timeout} seconds")
            return ParsedDocument(title='', content_stream=[], tables=[], image_bytes=[])

        # Phase 3: get results
        pdf_bytes = pathlib.Path(filename).read_bytes()
        extracted_images = convert_from_bytes(pdf_bytes, dpi=300)
        img_num = 0

        # First pass: collect all sections for context extraction
        all_sections = []
        element_index = 0
        for page in response.json()['result']['pages']:
            page_num = page['pageNum']
            base_position = page_num * 1000
            
            for section in page['sections']:
                position = base_position + element_index
                all_sections.append({
                    'section': section,
                    'page_num': page_num,
                    'position': position,
                    'element_index': element_index
                })
                element_index += 1

        # Second pass: process sections with context
        for idx, section_info in enumerate(all_sections):
            section = section_info['section']
            page_num = section_info['page_num']
            position = section_info['position']
            
            if section['type'] == 'text':
                metadata = {
                    'element_type': 'text',
                    'page': page_num
                }
                all_elements.append((position, section['text'], metadata))
                
            elif section['type'] == 'table':
                # Tables are processed separately for structured indexing, not added inline
                tableList = section['tableList']
                header = tableList[0]
                rows = tableList[1:]
                df = pd.DataFrame(rows, columns=header)
                table_summary = self.table_summarizer.summarize_table_text(df.to_markdown()) if self.table_summarizer else df.to_markdown()
                tables.append([df, table_summary, '', {'page': page_num}])
                if self.verbose:
                    logger.info(f"Table found on page {page_num} - will be processed for structured indexing")
                
            elif section['type'] == 'image' and self.summarize_images:
                # Extract context from surrounding sections
                previous_text, next_text = extract_image_context(
                    [s['section'] for s in all_sections],
                    idx,
                    num_previous=self.image_context['num_previous_chunks'],
                    num_next=self.image_context['num_next_chunks'],
                    text_extractor=lambda x: x.get('text') if x.get('type') == 'text' else None
                )
                
                bbox = [round(x,2) for x in section['bbox']]
                img = extracted_images[img_num]
                image_dims = img.size
                bbox_pixels = (int(bbox[0] * image_dims[0]), int(bbox[1] * image_dims[1]),
                               int(bbox[2] * image_dims[0]), int(bbox[3] * image_dims[1]))
                img_cropped = img.crop(box=bbox_pixels)
                image_path = 'image.png'
                with open(image_path, 'wb') as fp:
                    img_cropped.save(fp, 'PNG')
                
                # Store image binary data
                with open(image_path, 'rb') as fp:
                    image_binary = fp.read()
                image_id = f"docupanda_page_{page_num}_image_{img_num}"
                image_bytes.append((image_id, image_binary))
                
                image_summary = self.image_summarizer.summarize_image(
                    image_path, source_url, previous_text, next_text
                )
                if image_summary and len(image_summary) > 10:
                    metadata = {
                        'element_type': 'image',
                        'page': page_num,
                        'image_id': image_id
                    }
                    # Use position + 0.5 for images to place them right after text
                    all_elements.append((position + 0.5, image_summary, metadata))
                    if self.verbose:
                        logger.info(f"Image summary: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                logger.info(f"Docupanda: processed image with bounding box {bbox} on page {page_num}")
                img_num += 1
                
            else:
                logger.info(f"Docupanda: unknown section type {section['type']} on page {page_num} ignored...")

        # Sort all elements by position to maintain document order
        all_elements.sort(key=lambda x: x[0])
        content_stream = [(content, metadata) for _, content, metadata in all_elements]

        # Fallback to filename if no title found
        if not doc_title:
            basename = os.path.basename(filename)
            doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            logger.info(f"No title found in document, using filename fallback: '{doc_title}' for file {filename}")

        logger.info(f"DocupandaParser unified: {len(content_stream)} content elements, {len(tables)} tables")
        logger.info(f"parsing file {filename} with Docupanda took {time.time()-st:.2f} seconds")

        return ParsedDocument(
            title=doc_title,
            content_stream=content_stream,
            tables=tables,
            image_bytes=image_bytes
        )

class LlamaParseDocumentParser(DocumentParser):

    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = {},
        llama_parse_api_key: str = None,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False,
        image_context: dict = None
    ):
        super().__init__(
            cfg=cfg,
            verbose=verbose,
            model_config=model_config,
            parse_tables=parse_tables,
            enable_gmft=enable_gmft,
            do_ocr=False,
            summarize_images=summarize_images
        )
        self.image_context = image_context or {'num_previous_chunks': 1, 'num_next_chunks': 1}
        if llama_parse_api_key:
            self.parser = LlamaParse(verbose=True, premium_mode=True, api_key=llama_parse_api_key)
            if self.verbose:
                logger.info("Using LlamaParse, premium mode")
        else:
            raise ValueError("No LlamaParse API key found, skipping LlamaParse")

    def parse(self, filename: str, source_url: str = "No URL") -> ParsedDocument:
        """
        Parse a document and return unified content stream with images interleaved in proper order.
        Tables are extracted separately for structured indexing.
        """
        st = time.time()
        doc_title = extract_document_title(filename)
        
        image_bytes = []  # Store image binary data
        img_folder = '/images'
        os.makedirs(img_folder, exist_ok=True)

        nest_asyncio.apply()
        json_objs = self.parser.get_json_result(filename)
        
        # Collect all elements with their positions for proper ordering
        all_elements = []
        
        # First pass: collect all text elements per page
        page_elements = {}  # page_num -> list of (element_type, content, metadata)
        
        for page_data in json_objs[0]['pages']:
            page_num = page_data['page']
            if page_num not in page_elements:
                page_elements[page_num] = []
            
            # Add page text
            page_text = page_data['text']
            if page_text and page_text.strip():
                metadata = {
                    'element_type': 'text', 
                    'page': page_num
                }
                page_elements[page_num].append(('text', page_text, metadata))
            
            # Tables are not added inline - they are processed separately for structured indexing
        
        # Second pass: process images with context
        if self.summarize_images:
            parsed_images = self.parser.get_images(json_objs, download_path=img_folder)
            
            # Build flat list of all elements for context extraction
            flat_elements = []
            image_positions = {}  # Track where images should be inserted
            
            for page_num in sorted(page_elements.keys()):
                for elem in page_elements[page_num]:
                    flat_elements.append(elem)
            
            # Process each image with context
            for image_dict in parsed_images:
                page_num = image_dict['page_number']
                
                # Find position of this image in the document flow
                # Images typically come after text on the same page
                image_idx = len(flat_elements)  # Default to end
                for idx, (elem_type, content, meta) in enumerate(flat_elements):
                    if meta['page'] == page_num:
                        image_idx = idx + 1  # Place after the text on same page
                        break
                
                # Extract context
                previous_text, next_text = extract_image_context(
                    flat_elements,
                    image_idx,
                    num_previous=self.image_context['num_previous_chunks'],
                    num_next=self.image_context['num_next_chunks'],
                    text_extractor=lambda x: x[1] if x[0] == 'text' else None
                )
                
                # Store image binary data
                with open(image_dict['path'], 'rb') as fp:
                    image_binary = fp.read()
                image_id = f"llamaparse_page_{page_num}_image_{len(image_bytes)}"
                image_bytes.append((image_id, image_binary))
                
                image_summary = self.image_summarizer.summarize_image(
                    image_dict['path'], source_url, previous_text, next_text
                )
                if image_summary:
                    if page_num not in page_elements:
                        page_elements[page_num] = []
                    metadata = {
                        'element_type': 'image', 
                        'page': page_num,
                        'image_id': image_id
                    }
                    page_elements[page_num].append(('image', image_summary, metadata))
        
        # Now build the final positioned elements using standard formula
        for page_num in sorted(page_elements.keys()):
            base_position = page_num * 1000
            for element_index, (element_type, content, metadata) in enumerate(page_elements[page_num]):
                if element_type == 'image':
                    position = base_position + element_index + 0.5
                else:
                    position = base_position + element_index
                all_elements.append((position, content, metadata))
                
                if self.verbose:
                    if element_type == 'image':
                        logger.info(f"Image summary: {content[:MAX_VERBOSE_LENGTH]}...")

        # Sort all elements by position to maintain document order
        all_elements.sort(key=lambda x: x[0])
        content_stream = [(content, metadata) for _, content, metadata in all_elements]

        # Process tables separately for structured indexing
        tables = []
        if self.parse_tables:
            if self.enable_gmft and filename.endswith('.pdf'):
                tables = list(self.get_tables_with_gmft(filename))
            else:
                # Extract tables from LlamaParse JSON structure for tables list
                for page_data in json_objs[0]['pages']:
                    page_num = page_data['page']
                    if 'items' in page_data:
                        lm_tables = (item for item in page_data['items'] if item['type'] == 'table')
                        for table in lm_tables:
                            table_md = table['md']
                            table_summary = self.table_summarizer.summarize_table_text(table_md) if self.table_summarizer else table_md
                            tables.append([markdown_to_df(table_md), table_summary, '', 
                                         {'page': page_num}])

        # Fallback to filename if no title found
        if not doc_title:
            basename = os.path.basename(filename)
            doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            logger.info(f"No title found in document, using filename fallback: '{doc_title}' for file {filename}")

        logger.info(f"LlamaParseParser: {len(content_stream)} content elements, {len(tables)} tables")
        logger.info(f"parsing file {filename} with LlamaParse took {time.time()-st:.2f} seconds")

        return ParsedDocument(
            title=doc_title,
            content_stream=content_stream,
            tables=tables,
            image_bytes=image_bytes
        )

class DoclingDocumentParser(DocumentParser):

    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = {},
        chunking_strategy: str = 'hierarchical',
        chunk_size: int = 1024,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        do_ocr: bool = False,
        summarize_images: bool = False,
        image_scale: float = 1.0,
        image_context: dict = None
    ):
        super().__init__(
            cfg=cfg,
            verbose=verbose,
            model_config=model_config,
            parse_tables=parse_tables,
            enable_gmft=enable_gmft,
            do_ocr=do_ocr,
            summarize_images=summarize_images
        )
        self.chunking_strategy = chunking_strategy
        self.chunk_size = chunk_size
        self.image_scale = image_scale
        self.image_context = image_context or {'num_previous_chunks': 1, 'num_next_chunks': 1}
        if self.verbose:
            logger.info(f"Using DoclingParser with chunking strategy {self.chunking_strategy} and chunk size {self.chunk_size}")

    @staticmethod
    def _lazy_load_docling():
        import warnings

        warnings.filterwarnings(
            "ignore",
            message="Token indices sequence length",
            category=UserWarning
        )

        from docling.document_converter import DocumentConverter, PdfFormatOption, HTMLFormatOption, PowerpointFormatOption, WordFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions, PaginatedPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
        from docling_core.transforms.chunker import HierarchicalChunker

        return (
            DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions,
            PdfFormatOption, HTMLFormatOption, PowerpointFormatOption, WordFormatOption, InputFormat, EasyOcrOptions, PaginatedPipelineOptions
        )

    def _get_tables(self, tables):
        def _get_metadata(table):
            md = {}
            if table.prov:
                md['page'] = table.prov[0].page_no
            return md
        for table in tables:
            try:
                table_df = table.export_to_dataframe()
                table_md = table_df.to_markdown()
                table_summary = self.table_summarizer.summarize_table_text(table_md)
                yield (table_df, table_summary, '', _get_metadata(table))
            except ValueError as err:
                logger.error(f"Error parsing Markdown table: {err}. Skipping...")
                continue

    def parse(self, filename: str, source_url: str = "No URL") -> ParsedDocument:
        """
        Parse a local file and return unified content stream with images interleaved in proper order.
        Tables are extracted separately for structured indexing.
        Uses position-based ordering to maintain document structure.
        """
        # Process using Docling
        (
            DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions,
            PdfFormatOption, HTMLFormatOption, PowerpointFormatOption, WordFormatOption, InputFormat, EasyOcrOptions,
            PaginatedPipelineOptions
        ) = self._lazy_load_docling()

        st = time.time()

        html_opts = PaginatedPipelineOptions()
        html_opts.generate_page_images = True
        html_opts.images_scale = self.image_scale

        pdf_opts = PdfPipelineOptions()
        pdf_opts.images_scale = self.image_scale
        pdf_opts.generate_picture_images = True
        pdf_opts.do_ocr = False
        pdf_opts.do_formula_enrichment = True
        
        # Pipeline options for Office documents
        office_opts = PaginatedPipelineOptions()
        office_opts.generate_page_images = True
        office_opts.images_scale = self.image_scale

        if self.do_ocr:
            pdf_opts.do_ocr = True
            easy_ocr_config = self.cfg.doc_processing.easy_ocr_config
            ocr_options = EasyOcrOptions()
            mapping = {
                "bitmap_area_threshold": lambda val: setattr(ocr_options, "bitmap_area_threshold", val),
                "confidence_threshold": lambda val: setattr(ocr_options, "confidence_threshold", val),
                "download_enabled": lambda val: setattr(ocr_options, "download_enabled", val),
                "force_full_page_ocr": lambda val: setattr(ocr_options, "force_full_page_ocr", val),
                "kind": lambda val: setattr(ocr_options, "kind", val),
                "lang": lambda val: setattr(ocr_options, "lang", val),
                "model_config": lambda val: setattr(ocr_options, "model_config", val),
                "model_storage_directory": lambda val: setattr(ocr_options, "model_storage_directory", val),
                "recog_network": lambda val: setattr(ocr_options, "recog_network", val),
                "use_gpu": lambda val: setattr(ocr_options, "use_gpu", val),
            }

            for key, func in mapping.items():
                value = getattr(easy_ocr_config, key, None)
                if value is not None:
                    func(value)
            pdf_opts.ocr_options = ocr_options
            
        res = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF, InputFormat.HTML, InputFormat.PPTX, InputFormat.DOCX,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_opts),
                InputFormat.HTML: HTMLFormatOption(pipeline_options=html_opts),
                InputFormat.PPTX: PowerpointFormatOption(pipeline_options=office_opts),
                InputFormat.DOCX: WordFormatOption(pipeline_options=office_opts),
            }
        ).convert(filename)
        doc = res.document
        doc_title = extract_document_title(filename)
        
        # Fallback to Docling document name if no document metadata title found
        if not doc_title and doc.name:
            doc_title = doc.name
            logger.info(f"Using Docling document name: '{doc_title}' from file {filename}")

        # Build content stream with position-based ordering
        positioned_elements = []  # List of (position, content, metadata) tuples
        all_items = []  # Collect all items for context extraction
        image_bytes = []  # Store image binary data
        
        # First pass: collect all items for context extraction
        element_index = 0
        for item, _ in doc.iterate_items():
            # Get page number for position calculation
            page_no = 0
            if hasattr(item, 'prov') and item.prov:
                page_no = item.prov[0].page_no
            
            base_position = page_no * 1000
            position = base_position + element_index
            
            # Store item with its position and page info
            all_items.append({
                'item': item,
                'position': position,
                'page_no': page_no,
                'index': element_index
            })
            element_index += 1
        
        # Second pass: process items with context
        for idx, item_info in enumerate(all_items):
            item = item_info['item']
            page_no = item_info['page_no']
            position = item_info['position']
            
            # Check what type of item this is
            if hasattr(item, 'export_to_dataframe'):
                # Table element - skip inline, will be processed separately for structured indexing
                if self.verbose and self.parse_tables:
                    logger.info(f"Table found on page {page_no} - will be processed for structured indexing")
                
            elif hasattr(item, 'text'):
                # Text element
                metadata = {
                    'element_type': 'text',
                    'page': page_no
                }
                positioned_elements.append((position, item.text, metadata))
                
            elif hasattr(item, 'get_image') and self.summarize_images:
                # Picture element - extract context from surrounding items
                previous_text, next_text = extract_image_context(
                    [i['item'] for i in all_items],
                    idx,
                    num_previous=self.image_context['num_previous_chunks'],
                    num_next=self.image_context['num_next_chunks'],
                    text_extractor=lambda x: x.text if hasattr(x, 'text') else None
                )
                
                image = item.get_image(doc)
                if image:
                    image_path = 'image.png'
                    with open(image_path, 'wb') as fp:
                        image.save(fp, 'PNG')
                    
                    # Store image binary data
                    with open(image_path, 'rb') as fp:
                        image_binary = fp.read()
                    image_id = f"docling_page_{page_no}_image_{len(image_bytes)}"
                    image_bytes.append((image_id, image_binary))
                    
                    image_summary = self.image_summarizer.summarize_image(
                        image_path, source_url, previous_text, next_text
                    )
                    if image_summary:
                        metadata = {
                            'element_type': 'image',
                            'page': page_no,
                            'image_id': image_id
                        }
                        # Images get +0.5 offset to appear right after preceding element
                        positioned_elements.append((position + 0.5, image_summary, metadata))
                        
                        if self.verbose:
                            logger.info(f"Image summary at position {position + 0.5}: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                else:
                    logger.info("Failed to retrieve image")
        
        # Apply chunking if needed
        if self.chunking_strategy in ['hybrid', 'hierarchical']:
            # Need to apply chunking to text elements only
            chunker = (
                HybridChunker(max_tokens=self.chunk_size) 
                if self.chunking_strategy == 'hybrid' else HierarchicalChunker()
            )
            
            # Extract text elements, chunk them, then re-insert
            non_text_elements = [(pos, content, meta) for pos, content, meta in positioned_elements 
                               if meta['element_type'] != 'text']
            
            # Build a document-like structure for chunking
            # Note: This is a simplified approach - may need refinement based on Docling's chunking API
            chunked_text_elements = []
            for chunk in chunker.chunk(doc):
                metadata = {'element_type': 'text'}
                if chunk.meta.doc_items and chunk.meta.doc_items[0].prov:
                    page_no = chunk.meta.doc_items[0].prov[0].page_no
                    metadata['page'] = page_no
                else:
                    metadata['page'] = 0
                    
                # Assign positions based on page
                base_position = metadata['page'] * 1000
                position = base_position + len([e for e in chunked_text_elements if e[2]['page'] == metadata['page']])
                chunked_text_elements.append((position, chunker.serialize(chunk=chunk), metadata))
            
            # Combine chunked text with non-text elements
            positioned_elements = chunked_text_elements + non_text_elements
        
        # Sort all elements by position to maintain document order
        positioned_elements.sort(key=lambda x: x[0])
        content_stream = [(content, metadata) for _, content, metadata in positioned_elements]

        # Process tables
        tables = []
        if self.parse_tables:
            if self.enable_gmft and filename.endswith('.pdf'):
                tables = list(self.get_tables_with_gmft(filename))
            else:
                tables = list(self._get_tables(doc.tables))

        # Fallback to filename if no title found
        if not doc_title:
            basename = os.path.basename(filename)
            doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            logger.info(f"No title found in document, using filename fallback: '{doc_title}' for file {filename}")

        logger.info(f"DoclingParser: {len(content_stream)} content elements, {len(tables)} tables")
        logger.info(f"parsing file {filename} with Docling took {time.time()-st:.2f} seconds")

        return ParsedDocument(
            title=doc_title,
            content_stream=content_stream,
            tables=tables,
            image_bytes=image_bytes
        )



class ImageFileParser(DocumentParser):
    """
    Parser for standalone image files (PNG, JPG, GIF, etc.)
    Returns a single-element ParsedDocument with the image summary

    Note: This parser always requires summarize_images=True and vision model config.
    """
    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = None,
    ):
        model_config = model_config or {}

        # Validate that vision config key exists (value can be empty dict for testing)
        if 'vision' not in model_config:
            raise ValueError("ImageFileParser requires 'vision' key in model_config")

        super().__init__(
            cfg=cfg,
            verbose=verbose,
            model_config=model_config,
            parse_tables=False,
            enable_gmft=False,
            do_ocr=False,
            summarize_images=True  # Always True for image files
        )

    def parse(self, filename: str, source_url: str = "No URL") -> ParsedDocument:
        """
        Parse a standalone image file and return single-element ParsedDocument

        Args:
            filename: Path to the image file
            source_url: Source URL for context

        Returns:
            ParsedDocument with single image element
        """
        st = time.time()

        if not os.path.exists(filename):
            logger.error(f"Image file {filename} does not exist")
            return ParsedDocument(title='', content_stream=[], tables=[], image_bytes=[])

        # Use filename (without extension) as title
        basename = os.path.basename(filename)
        doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()

        # Use filename and path as context for standalone images
        file_context = f"Filename: {basename}\nPath: {filename}"
        if source_url != "No URL":
            file_context += f"\nSource: {source_url}"

        # Generate image summary with filename/path as context
        try:
            # Read image binary data
            with open(filename, 'rb') as fp:
                image_binary = fp.read()
            image_id = f"standalone_image_{slugify(basename)}"
            image_bytes = [(image_id, image_binary)]

            image_summary = self.image_summarizer.summarize_image(
                filename, source_url, previous_text=file_context, next_text=None
            )

            if not image_summary:
                logger.warning(f"Failed to generate summary for image {filename}")
                return ParsedDocument(title=doc_title, content_stream=[], tables=[], image_bytes=[])

            # Create single element with position 0
            metadata = {
                'element_type': 'image',
                'page': 1,
                'image_id': image_id,
                'filename': basename
            }
            content_stream = [(image_summary, metadata)]

            if self.verbose:
                logger.info(f"Image summary: {image_summary[:MAX_VERBOSE_LENGTH]}...")

            logger.info(f"ImageFileParser: parsed standalone image {filename} in {time.time()-st:.2f} seconds")

            return ParsedDocument(
                title=doc_title,
                content_stream=content_stream,
                tables=[],
                image_bytes=image_bytes
            )

        except Exception as e:
            logger.error(f"Failed to parse image file {filename}: {e}")
            return ParsedDocument(title=doc_title, content_stream=[], tables=[], image_bytes=[])


class UnstructuredDocumentParser(DocumentParser):
    def __init__(
        self,
        cfg: OmegaConf,
        verbose: bool = False,
        model_config: dict = {},
        chunking_strategy: str = "by_title",
        chunk_size: int = 1024,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False,
        image_context: dict = None
    ):
        super().__init__(
            cfg=cfg,
            verbose=verbose,
            model_config=model_config,
            parse_tables=parse_tables,
            enable_gmft=enable_gmft,
            do_ocr=False,
            summarize_images=summarize_images
        )
        self.chunking_strategy = chunking_strategy     # none, by_title or basic
        self.chunk_size = chunk_size
        self.image_context = image_context or {'num_previous_chunks': 1, 'num_next_chunks': 1}
        if self.verbose:
            logger.info(f"Using UnstructuredDocumentParser with chunking strategy '{self.chunking_strategy}' and chunk size {self.chunk_size}")

    def _get_elements(
        self,
        filename: str,
        override_chunking: bool = False,
    ) -> List[us.documents.elements.Element]:
        '''
        Get elements from document using Unstructured partition_XXX functions
        Args:
            filename (str): Name of the file to parse.
            override_chunking (bool): If True, disable chunking regardless of config
        Returns:
            List of elements from the document
        '''

        mime_type = detect_file_type(filename)
        partition_kwargs = {'infer_table_structure': True}
        
        # Apply chunking strategy if configured and not overridden
        if self.chunking_strategy != 'none' and not override_chunking:
            partition_kwargs.update({
                "chunking_strategy": self.chunking_strategy,
                "max_characters": self.chunk_size,
            })
        
        # Configure image and table extraction for PDFs
        if mime_type == 'application/pdf':
            partition_kwargs.update({
                'extract_images_in_pdf': True,
                'extract_image_block_types': ["Image", "Table"],
                'strategy': "hi_res",
                'hi_res_model_name': "yolox",
            })

        if mime_type == 'application/pdf':
            partition_func = partition_pdf
        elif mime_type == 'text/html' or mime_type == 'application/xml':
            partition_func = partition_html
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            partition_func = partition_docx
        elif mime_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
            partition_func = partition_pptx
        else:
            logger.info(f"data from {filename} is not HTML, PPTX, DOCX or PDF (mime type = {mime_type}), skipping")
            return []

        try:
            elements = partition_func(
                filename=filename,
                **partition_kwargs
            )
            return elements
        except Exception as e:
            logger.error(f"Error occurred while partitioning document {filename}: {e}")
            return []

    def _get_tables(self, elements):
        for e in elements:
            if isinstance(e, us.documents.elements.Table):
                try:
                    table_summary = self.table_summarizer.summarize_table_text(str(e))
                    html_table = e.metadata.text_as_html
                    df = pd.read_html(StringIO(html_table))[0]
                    yield [df, table_summary, '', {'page': e.metadata.page_number}]
                except Exception as err:
                    logger.error(f"Error parsing HTML table: {err}. Skipping...")
                    continue

    def parse(self, filename: str, source_url: str = "No URL") -> ParsedDocument:
        """
        Parse a document and return unified content stream with images inline.
        Tables are extracted separately for structured indexing.
        When chunking is enabled, make two passes:
        1. Extract chunked text
        2. Extract raw images without chunking
        Then map everything together using position-based ordering.
        """
        st = time.time()

        if self.verbose:
            logger.info(f"Unstructured: extracting all content from {filename}")
        
        # Determine if we're using chunking
        is_chunking = self.chunking_strategy != 'none'
        
        if is_chunking:
            # Two-pass extraction for chunked content
            if self.verbose:
                logger.info("Using dual extraction with position tracking: chunked text + raw tables/images")
            
            # Pass 1: Get raw elements without chunking to establish positions
            raw_elements = self._get_elements(filename, override_chunking=True)
            
            # Create position map for raw elements
            raw_positions = {}
            for idx, element in enumerate(raw_elements):
                page_num = getattr(element.metadata, 'page_number', 1) or 1
                # Position formula: page_num * 1000 + element_index
                position = page_num * 1000 + idx
                raw_positions[id(element)] = (position, page_num, idx)
            
            # Pass 2: Get chunked text elements
            chunked_elements = self._get_elements(filename, override_chunking=False)
            
            # Log what we found
            chunked_types = {}
            for e in chunked_elements:
                etype = type(e).__name__
                chunked_types[etype] = chunked_types.get(etype, 0) + 1
            logger.info(f"Chunked element types: {chunked_types}")
            
            raw_types = {}
            for e in raw_elements:
                etype = type(e).__name__
                raw_types[etype] = raw_types.get(etype, 0) + 1
            logger.info(f"Raw element types: {raw_types}")
            
            elements = chunked_elements  # Use chunked for text processing
            raw_tables_images = raw_elements  # Keep raw for table/image extraction
        else:
            # Single pass when not chunking
            elements = self._get_elements(filename)
            raw_tables_images = elements  # Same elements for everything
            raw_positions = None  # Not needed when not chunking
            
            # Log element types
            element_types = {}
            for e in elements:
                etype = type(e).__name__
                element_types[etype] = element_types.get(etype, 0) + 1
            logger.info(f"Element types found: {element_types}")
        
        # Build list of positioned elements
        positioned_elements = []  # List of (position, content, metadata) tuples
        image_bytes = []  # Store image binary data
        
        if not is_chunking:
            # When not chunking, process everything inline with simple positioning
            for idx, element in enumerate(elements):
                page_num = getattr(element.metadata, 'page_number', 1) or 1
                base_position = page_num * 1000
                
                if isinstance(element, us.documents.elements.Image):
                    # Process image inline when not chunking
                    if self.summarize_images:
                        has_valid_coords = (
                            element.metadata.coordinates and 
                            element.metadata.coordinates.system.width > 50 and 
                            element.metadata.coordinates.system.height > 50
                        )
                        has_image_path = hasattr(element.metadata, 'image_path') and element.metadata.image_path
                        
                        if has_image_path or has_valid_coords:
                            try:
                                # Extract context using the utility function
                                previous_text, next_text = extract_image_context(
                                    elements,
                                    idx,
                                    num_previous=self.image_context['num_previous_chunks'],
                                    num_next=self.image_context['num_next_chunks']
                                )
                                
                                # Try to get image path
                                image_path = getattr(element.metadata, 'image_path', None)
                                if not image_path and hasattr(element, 'image'):
                                    image_path = element.image
                                
                                if image_path:
                                    # Store image binary data
                                    if os.path.exists(image_path):
                                        with open(image_path, 'rb') as fp:
                                            image_binary = fp.read()
                                        image_id = f"unstructured_page_{page_num}_image_{len(image_bytes)}"
                                        image_bytes.append((image_id, image_binary))
                                    else:
                                        image_id = None
                                        
                                    image_summary = self.image_summarizer.summarize_image(
                                        image_path, source_url, previous_text, next_text
                                    )
                                    if image_summary:
                                        position = base_position + idx + 0.5  # Images get +0.5 offset
                                        metadata = {
                                            'element_type': 'image', 
                                            'page': page_num,
                                            'image_id': image_id
                                        }
                                        positioned_elements.append((position, image_summary, metadata))
                                        if self.verbose:
                                            logger.info(f"Image summary at position {position}: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                                else:
                                    logger.warning("Image element found but no valid image path available")
                            except Exception as exc:
                                logger.error(f"Error summarizing image: {exc}")
                            
                elif isinstance(element, us.documents.elements.Table):
                    # Tables are processed separately for structured indexing, not added inline
                    pass
                else:
                    # Regular text element
                    position = base_position + idx
                    metadata = {'element_type': 'text', 'page': page_num}
                    positioned_elements.append((position, str(element), metadata))
        else:
            # When chunking, process chunked text with position mapping
            chunk_position_counter = {}
            for element in elements:
                page_num = getattr(element.metadata, 'page_number', 1) or 1
                
                # Skip tables and images in chunked elements (will process from raw)
                if isinstance(element, (us.documents.elements.Table, us.documents.elements.Image)):
                    continue
                
                # Process text/composite elements
                # Assign positions based on page and order within page
                if page_num not in chunk_position_counter:
                    chunk_position_counter[page_num] = 0
                
                base_position = page_num * 1000
                position = base_position + chunk_position_counter[page_num]
                chunk_position_counter[page_num] += 10  # Leave gaps for inserting images/tables
                
                metadata = {'element_type': 'text', 'page': page_num}
                positioned_elements.append((position, str(element), metadata))
        
            # Now process tables and images from raw extraction with proper positioning
            for idx, element in enumerate(raw_tables_images):
                page_num = getattr(element.metadata, 'page_number', 1) or 1
                base_position = page_num * 1000
                
                if isinstance(element, us.documents.elements.Image):
                    # Process image element - ALWAYS log for debugging
                    logger.info(f"Found Image element on page {page_num}")
                    logger.info(f"  Has coordinates: {hasattr(element.metadata, 'coordinates')}")
                    if hasattr(element.metadata, 'coordinates') and element.metadata.coordinates:
                        logger.info(f"  Coords dimensions: {element.metadata.coordinates.system.width}x{element.metadata.coordinates.system.height}")
                    logger.info(f"  Has image_path: {hasattr(element.metadata, 'image_path')}")
                    if hasattr(element.metadata, 'image_path'):
                        logger.info(f"  Image path: {element.metadata.image_path}")
                    
                    if self.summarize_images:
                        # More lenient image detection
                        has_valid_coords = (
                            element.metadata.coordinates and 
                            element.metadata.coordinates.system.width > 50 and 
                            element.metadata.coordinates.system.height > 50
                        )
                        has_image_path = hasattr(element.metadata, 'image_path') and element.metadata.image_path
                        
                        if has_image_path or has_valid_coords:
                            try:
                                # Calculate image position using same formula as text elements
                                image_position = base_position + idx + 0.5
                                
                                # Find the chunked element with closest position for context extraction
                                best_context_idx = 0
                                for chunk_idx, chunk_elem in enumerate(elements):
                                    chunk_page = getattr(chunk_elem.metadata, 'page_number', 1) or 1
                                    chunk_position = chunk_page * 1000 + chunk_idx
                                    
                                    if chunk_position > image_position:
                                        best_context_idx = chunk_idx
                                        break
                                    best_context_idx = chunk_idx
                                
                                # Extract context using chunked elements instead of raw elements
                                previous_text, next_text = extract_image_context(
                                    elements,
                                    best_context_idx,
                                    num_previous=self.image_context['num_previous_chunks'],
                                    num_next=self.image_context['num_next_chunks']
                                )
                                
                                # Try to get image path
                                image_path = getattr(element.metadata, 'image_path', None)
                                if not image_path and hasattr(element, 'image'):
                                    image_path = element.image
                                
                                if image_path:
                                    # Store image binary data
                                    if os.path.exists(image_path):
                                        with open(image_path, 'rb') as fp:
                                            image_binary = fp.read()
                                        image_id = f"unstructured_chunked_page_{page_num}_image_{len(image_bytes)}"
                                        image_bytes.append((image_id, image_binary))
                                    else:
                                        image_id = None
                                        
                                    image_summary = self.image_summarizer.summarize_image(
                                        image_path, source_url, previous_text, next_text
                                    )
                                    if image_summary:
                                        # Use position from raw element + 0.5 for images
                                        position = base_position + idx + 0.5
                                        metadata = {
                                            'element_type': 'image', 
                                            'page': page_num,
                                            'image_id': image_id
                                        }
                                        positioned_elements.append((position, image_summary, metadata))
                                        
                                        if self.verbose:
                                            logger.info(f"Image summary at position {position}: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                                
                                else:
                                    logger.warning("Image element found but no valid image path available")
                            except Exception as exc:
                                logger.error(f"Error summarizing image: {exc}")
                                continue
                            
                elif isinstance(element, us.documents.elements.Table):
                    # Tables are processed separately for structured indexing, not added inline
                    if self.verbose:
                        logger.info(f"Table found on page {page_num} - will be processed for structured indexing")

        # Sort all positioned elements by position to create final document order
        positioned_elements.sort(key=lambda x: x[0])
        
        # Convert to content_stream format (without positions)
        content_stream = [(content, metadata) for _, content, metadata in positioned_elements]
        
        if self.verbose:
            logger.info(f"Final content stream has {len(content_stream)} elements")
            # Log the element type distribution in final stream
            type_counts = {}
            for _, metadata in content_stream:
                etype = metadata.get('element_type', 'unknown')
                type_counts[etype] = type_counts.get(etype, 0) + 1
            logger.info(f"Final element distribution: {type_counts}")
        
        # Find document title with priority: Document metadata > Title elements > filename
        doc_title = extract_document_title(filename)
        
        # For files without metadata title, look for Title elements (except PDF/DOCX/PPTX which skip Title elements)
        if not doc_title and not filename.endswith(('.pdf', '.docx', '.pptx')):
            title_elements = raw_tables_images if is_chunking else elements
            titles = [str(x) for x in title_elements if type(x) == us.documents.elements.Title and len(str(x).strip()) > 3]
            if titles:
                doc_title = titles[0]
                logger.info(f"Extracted document title from Title element: '{doc_title}' from file {filename}")
        
        # Fallback: use filename if no title found
        if not doc_title:
            basename = os.path.basename(filename)
            doc_title = os.path.splitext(basename)[0].replace('_', ' ').replace('-', ' ').title()
            logger.info(f"No title found in document, using filename fallback: '{doc_title}' for file {filename}")

        # Process tables separately for structured indexing
        tables = []
        if self.parse_tables:
            if self.enable_gmft and filename.endswith('.pdf'):
                tables = list(self.get_tables_with_gmft(filename))
            else:
                # Use raw elements for table extraction when chunking
                table_elements = raw_tables_images if is_chunking else elements
                tables = list(self._get_tables(table_elements))

        logger.info(f"UnstructuredParser: {len(content_stream)} content elements, {len(tables)} tables")
        logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")

        return ParsedDocument(
            title=doc_title,
            content_stream=content_stream,
            tables=tables,
            image_bytes=image_bytes
        )

