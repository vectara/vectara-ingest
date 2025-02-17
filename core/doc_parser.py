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

from gmft.pdf_bindings import PyPDFium2Document
from gmft.auto import TableDetector, AutoTableFormatter, AutoFormatConfig

import nltk
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)


class DocumentParser():
    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False,
    ):
        self.model_name = model_name
        self.model_api_key = model_api_key
        self.enable_gmft = enable_gmft
        self.parse_tables = parse_tables and (model_api_key is not None)
        self.summarize_images = summarize_images and model_api_key is not None
        self.table_summarizer = TableSummarizer(model_name, model_api_key) if self.parse_tables else None
        self.image_summarizer = ImageSummarizer(model_name, model_api_key) if self.summarize_images else None
        self.logger = logging.getLogger()
        self.verbose = verbose

    def get_tables_with_gmft(self, filename: str) -> List[pd.DataFrame]:
        if not filename.endswith('.pdf'):
            self.logger.warning(f"GMFT: only PDF files are supported, skipping {filename}")
            return None
        
        detector = TableDetector()
        config = AutoFormatConfig()
        config.semantic_spanning_cells = True   # [Experimental] better spanning cells
        config.enable_multi_header = True       # multi-indices
        formatter = AutoTableFormatter(config)

        doc = PyPDFium2Document(filename)
        dfs = []
        for page in doc:
            for table in detector.extract(page):
                ft = formatter.extract(table)
                dfs.append([ft.df(), " ".join(ft.captions())])
        tables = []
        for df, title in dfs:
            table_summary = self.table_summarizer.summarize_table_text(df.to_markdown())
            tables.append((df, table_summary, title))

        doc.close()
        if self.verbose:
            self.logger.info(f"GMFT: extracted {len(tables)} tables")

        return tables


class LlamaParseDocumentParser(DocumentParser):

    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        llama_parse_api_key: str = None,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, parse_tables, enable_gmft, summarize_images)
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
 
            if self.parse_tables and not (self.enable_gmft and filename.endswith('.pdf')):
                lm_tables = [item for item in page['items'] if item['type']=='table']
                for table in lm_tables:
                    table_md = table['md']
                    table_summary = self.table_summarizer.summarize_table_text(table_md)
                    if table_summary:
                        texts.append(table_summary)
                        metadatas.append({'parser_element_type': 'table', 'page': page['page']})
                        if self.verbose:
                            self.logger.info(f"Table summary: {table_summary}")
                    tables.append([markdown_to_df(table_md), table_summary, ''])

            # process images
            if self.summarize_images:
                images = self.parser.get_images(page, download_path=img_folder)
                for image in images:
                    image_summary = self.image_summarizer.summarize_image(image['path'], source_url, None)
                    if image_summary:
                        image_summaries.append(image_summary)
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary}")

        if self.enable_gmft and self.parse_tables and filename.endswith('.pdf'):
            tables = self.get_tables_with_gmft(filename)

        self.logger.info(f"LlamaParse: {len(tables)} tables, and {len(image_summaries)} images")
        self.logger.info(f"parsing file {filename} with LlamaParse took {time.time()-st:.2f} seconds")

        return doc_title, texts, metadatas, tables, image_summaries

class DoclingDocumentParser(DocumentParser):

    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        chunking_strategy: str = 'hierarchical',
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, parse_tables, enable_gmft, summarize_images)
        self.chunking_strategy = chunking_strategy
        if self.verbose:
            self.logger.info(f"Using DoclingParser with chunking strategy {self.chunking_strategy}")

    @staticmethod
    def _lazy_load_docling():
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
        from docling_core.transforms.chunker import HierarchicalChunker

        return DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions, PdfFormatOption, InputFormat

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
        DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions, PdfFormatOption, InputFormat = self._lazy_load_docling()

        st = time.time()
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = 2.0
        pipeline_options.generate_picture_images = True
        res = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        ).convert(filename)
        doc = res.document
        doc_title = doc.name

        if self.chunking_strategy == 'hybrid':
            chunker = HybridChunker()
            texts = [chunker.serialize(chunk=chunk) for chunk in chunker.chunk(doc)]
        elif self.chunking_strategy == 'hierarchical':
            chunker = HierarchicalChunker()
            texts = [chunk.text for chunk in chunker.chunk(doc)]
        else:
            texts = [e.text for e in doc.texts]     # no chunking
        metadatas = [{'parser_element_type': 'text'} for _ in texts]
        self.logger.info(f"DoclingParser: {len(texts)} text elements")

        tables = []
        if self.parse_tables and not (self.enable_gmft and filename.endswith('.pdf')):
            self.logger.info(f"DoclingParser: {len(doc.tables)} tables")
            for table in doc.tables:
                table_md = table.export_to_markdown()
                table_summary = self.table_summarizer.summarize_table_text(table_md)
                if table_summary:
                    metadatas.append({'parser_element_type': 'table'})
                    if self.verbose:
                        self.logger.info(f"Table summary: {table_summary}")
                tables.append([table.export_to_dataframe(), table_summary, ''])

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

        if self.enable_gmft and self.parse_tables and filename.endswith('.pdf'):
            tables = self.get_tables_with_gmft(filename)

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
        parse_tables: bool = False,
        enable_gmft: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, model_name, model_api_key, parse_tables, enable_gmft, summarize_images)
        self.chunking_strategy = chunking_strategy     # none, by_title or basic
        self.chunk_size = chunk_size
        if self.verbose:
            self.logger.info(f"Using UnstructuredDocumentParser with chunking strategy '{self.chunking_strategy}' and chunk size {self.chunk_size}")

    def _get_elements(
        self,
        filename: str, 
        mode: str = "text",
    ) -> List[us.documents.elements.Element]:
        '''
        Get elements from document using Unstructured partition_XXX functions
        Args:
            filename (str): Name of the file to parse.
            mode (str): Mode to use for parsing: text, images (images and tables)
        Returns:
            List of elements from the document
        '''

        mime_type = detect_file_type(filename)
        partition_kwargs = {}
        if mode == 'text':
            partition_kwargs = {} if self.chunking_strategy == 'none' else {
                "chunking_strategy": self.chunking_strategy,
                "max_characters": self.chunk_size
            }
        else:
            partition_kwargs = {'infer_table_structure': True }
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
        
        # Pass 1: process text
        elements = self._get_elements(filename, mode='text')
        texts = [str(e) for e in elements]
        metadatas = [{'parser_element_type': 'text'} for _ in texts]
        self.logger.info(f"UnstructuredParser: {len(texts)} text elements")

        # No chunking strategy may result in title elements; if so - use the first one as doc_title
        titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>10]
        doc_title = titles[0] if len(titles)>0 else ''

        # Pass 2: extract tables and images; here we never use unstructured chunking, and ignore any text
        elements = self._get_elements(filename, mode='images')

        tables = []
        if self.parse_tables and not (self.enable_gmft and filename.endswith('.pdf')):
            for inx,e in enumerate(elements):
                if isinstance(e, us.documents.elements.Table):
                    try:
                        table_summary = self.table_summarizer.summarize_table_text(str(e))
                        html_table = e.metadata.text_as_html
                        df = pd.read_html(StringIO(html_table))[0]
                        tables.append([df, table_summary, ''])
                        if self.verbose:
                            self.logger.info(f"Table summary: {table_summary}")
                    except ValueError as e:
                        self.logger.error(f"Error parsing HTML table: {e}. Skipping...")
                        continue

        image_summaries = []
        if self.summarize_images:
            for inx,e in enumerate(elements):
                if isinstance(e, us.documents.elements.Image) and e.metadata.coordinates.system.width>100 and e.metadata.coordinates.system.height>100:
                    if inx>0 and type(elements[inx-1]) in [us.documents.elements.Title, us.documents.elements.NarrativeText]:
                        image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, elements[inx-1].text)
                    else:
                        image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, None)
                    if image_summary:
                        image_summaries.append(image_summary)
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary}")

        if self.enable_gmft and self.parse_tables and filename.endswith('.pdf'):
            tables = self.get_tables_with_gmft(filename)

        self.logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")
        return doc_title, texts, metadatas, tables, image_summaries
