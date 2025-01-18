import logging
from typing import List, Tuple
import time
import pandas as pd
import os
from io import StringIO

from core.summary import TableSummarizer, ImageSummarizer
from core.utils import detect_file_type, markdown_to_df

import unstructured as us
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.html import partition_html
from unstructured.partition.pptx import partition_pptx
from unstructured.partition.docx import partition_docx

import nest_asyncio
from llama_parse import LlamaParse

import nltk
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)


class DocumentParser():
    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        self.model_name = model_name
        self.model_api_key = model_api_key
        self.summarize_tables = summarize_tables and model_api_key
        self.summarize_images = summarize_images and model_api_key
        self.table_summarizer = TableSummarizer(model_name, model_api_key) if self.summarize_tables else None
        self.image_summarizer = ImageSummarizer(model_name, model_api_key) if self.summarize_images else None
        self.logger = logging.getLogger()
        self.verbose = verbose

class LlamaParseDocumentParser(DocumentParser):

    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        llama_parse_api_key: str = None,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, summarize_tables, summarize_images)
        if llama_parse_api_key:
            self.parser = LlamaParse(verbose=True, premium_mode=True, api_key=llama_parse_api_key)
            if self.verbose:
                self.logger.info("Using LlamaParse, premium mode")
        else:
            raise ValueError("No LlamaParse API key found, skipping LlamaParse")

    def parse(
            self,
            filename: str, 
            source_url: str = "No URL"
        ) -> Tuple[str, List[str], List[dict], list[str]]:
        """
        Parse a local file and return the title and text content.
        Using LlamaPase
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with doc_title, list of texts, list of metdatas
        """
        st = time.time()
        doc_title = ''
        texts = []
        image_summaries = []
        tables = []
        metadatas = []
        img_folder = '/images'
        os.makedirs(img_folder, exist_ok=True)

        nest_asyncio.apply()
        json_objs = self.parser.get_json_result(filename)
        pages = json_objs[0]['pages']
        for page in pages:
            texts.append(page['text'])
 
            # process tables
            if self.summarize_tables:
                lm_tables = [item for item in page['items'] if item['type']=='table']
                for table in lm_tables:
                    table_md = table['md']
                    table_summary = self.table_summarizer.summarize_table_text(table_md)
                    if table_summary:
                        texts.append(table_summary)
                        metadatas.append({'parser_element_type': 'table', 'page': page['page']})
                        if self.verbose:
                            self.logger.info(f"Table summary: {table_summary}")
                    tables.append([markdown_to_df(table_md), table_summary])

            # process images
            if self.summarize_images:
                images = self.parser.get_images(page, download_path=img_folder)
                for image in images:
                    image_summary = self.image_summarizer.summarize_image(image['path'], source_url, None)
                    if image_summary:
                        image_summaries.append(image_summary)
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary}")

        self.logger.info(f"LlamaParse: {len(tables)} tables, and {len(image_summaries)} images")
        self.logger.info(f"parsing file {filename} with LlamaParse took {time.time()-st:.2f} seconds")

        return doc_title, texts, metadatas, tables, image_summaries

class DoclingDocumentParser(DocumentParser):

    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        chunk: bool = False,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, summarize_tables, summarize_images)
        self.chunk = chunk
        if self.verbose:
            self.logger.info(f"Using DoclingParser with chunking {'enabled' if self.chunk else 'disabled'}")

    @staticmethod
    def _lazy_load_docling():
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker

        return DocumentConverter, HybridChunker, PdfPipelineOptions, PdfFormatOption, InputFormat

    def parse(
            self,
            filename: str, 
            source_url: str = "No URL"
        ) -> Tuple[str, List[str], List[dict], list[str]]:
        """
        Parse a local file and return the title and text content.
        Using Docling
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with doc_title, list of texts, list of metdatas
        """
        # Process using Docling
        DocumentConverter, HybridChunker, PdfPipelineOptions, PdfFormatOption, InputFormat = self._lazy_load_docling()

        st = time.time()
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = 2.0
        pipeline_options.generate_picture_images = True
        res = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        ).convert(filename)
        doc = res.document
        doc_title = doc.name

        if self.chunk:
            chunks = list(HybridChunker().chunk(doc))
            texts = [chunk.text for chunk in chunks]
        else:
            texts = [e.text for e in doc.texts]
        metadatas = [{'parser_element_type': 'text'} for _ in texts]
        self.logger.info(f"DoclingParser: {len(texts)} text elements")

        tables = []
        if self.summarize_tables:
            self.logger.info(f"DoclingParser: {len(doc.tables)} tables")
            for table in doc.tables:
                table_md = table.export_to_markdown()
                table_summary = self.table_summarizer.summarize_table_text(table_md)
                if table_summary:
                    texts.append(table_summary)
                    metadatas.append({'parser_element_type': 'table'})
                    if self.verbose:
                        self.logger.info(f"Table summary: {table_summary}")
                tables.append([table.export_to_dataframe(), table_summary])

        image_summaries = []
        if self.summarize_images:
            image_path = 'image.png'
            self.logger.info(f"DoclingParser: {len(doc.pictures)} images")
            for pic in doc.pictures:
                image = pic.get_image(res.document)
                if image:
                    with open(image_path, 'wb') as fp:
                        image.save(fp, 'PNG')
                    image_summary = self.image_summarizer.summarize_image(image_path, source_url, None)
                    if image_summary:
                        image_summaries.append(image_summary)
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary}")
                else:
                    self.logger.info(f"Failed to retrieve image {pic}")
                    continue

        self.logger.info(f"parsing file {filename} with Docling took {time.time()-st:.2f} seconds")
        return doc_title, texts, metadatas, tables, image_summaries


class UnstructuredDocumentParser(DocumentParser):
    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        chunking_strategy: str = "by_title",
        chunk_size: int = 1024,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, summarize_tables, summarize_images)
        self.chunking_strategy = chunking_strategy     # none, by_title or basic
        self.chunk_size = chunk_size
        if self.verbose:
            self.logger.info(f"Using UnstructuredDocumentParser with chunking strategy '{self.chunking_strategy}' and chunk size {self.chunk_size}")

    def _get_elements(
        self,
        filename: str, 
        mode: str = "default",
    ) -> List[us.documents.elements.Element]:
        '''
        Get elements from document using Unstructured partition_XXX functions
        Args:
            filename (str): Name of the file to parse.
            mode (str): Mode to use for parsing: none, tables or images
        Returns:
            List of elements from the document
        '''

        partition_kwargs = {} if self.chunking_strategy == 'none' or mode == "images" else {
            "chunking_strategy": self.chunking_strategy,
            "max_characters": self.chunk_size
        }
        if mode == 'tables':
            partition_kwargs['infer_table_structure'] = True

        mime_type = detect_file_type(filename)
        if mime_type in [
            'application/pdf', 
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        ]:
            partition_kwargs.update({
                "extract_images_in_pdf": True,
                "extract_image_block_types": ["Image", "Table"],
                "strategy": "hi_res", 
                "hi_res_model_name": "yolox",
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
            self.logger.info(f"data from {filename} is not HTML, PPTX, DOCX or PDF (mime type = {mime_type}), skipping")
            return []

        elements = partition_func(
            filename=filename,
            **partition_kwargs
        )    
        return elements

    def parse(
            self,
            filename: str, 
            source_url: str = "No URL",
        ) -> Tuple[str, List[str], List[dict], list[str]]:
        """
        Parse a local file and return the title and text content.
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with doc_title, list of texts, list of metdatas
        """
        # Process using unstructured partitioning functionality
        st = time.time()
        
        # Pass 1: process text and tables (if summarize_tables is True)
        elements = self._get_elements(
            filename,
            mode='tables' if self.summarize_tables else 'default',
        )
        texts = []
        metadatas = []
        tables = []
        num_tables = len([x for x in elements if type(x)==us.documents.elements.Table])
        if self.verbose:
            self.logger.info(f"UnstructuredDocumentParser: {len(elements)} elements in pass 1, {num_tables} are tables")
        for inx,e in enumerate(elements):
            if (type(e)==us.documents.elements.Table and self.summarize_tables):
                table_summary = self.table_summarizer.summarize_table_text(str(e))
                if table_summary:
                    texts.append(table_summary)
                    metadatas.append({'parser_element_type': 'table'})
                    if self.verbose:
                        self.logger.info(f"Table summary: {table_summary}")
                html_table = e.metadata.text_as_html
                df = pd.read_html(StringIO(html_table))[0]
                tables.append([df, table_summary])
            else:
                texts.append(str(e))
                metadatas.append({'parser_element_type': 'text'})

        # Pass 2: process any images; here we never use unstructured chunking, and ignore any text
        elements = self._get_elements(
            filename,
            mode = 'images' if self.summarize_images else 'default',
        )
        num_images = len([x for x in elements if type(x)==us.documents.elements.Image])
        self.logger.info(f"UnstructuredDocumentParser: {len(elements)} elements in pass 2, {num_images} are images")
        image_summaries = []
        for inx,e in enumerate(elements):
            if (type(e)==us.documents.elements.Image and  self.summarize_images):
                if inx>0 and type(elements[inx-1]) in [us.documents.elements.Title, us.documents.elements.NarrativeText]:
                    image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, elements[inx-1].text)
                else:
                    image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, None)
                if image_summary:
                    image_summaries.append(image_summary)
                    if self.verbose:
                        self.logger.info(f"Image summary: {image_summary}")

        # No chunking strategy may result in title elements; if so - use the first one as doc_title
        titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>10]
        doc_title = titles[0] if len(titles)>0 else ''

        self.logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")
        return doc_title, texts, metadatas, tables, image_summaries
