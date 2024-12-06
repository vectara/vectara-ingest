import logging
from typing import List, Tuple
import time

from core.utils import TableSummarizer, ImageSummarizer, detect_file_type

import unstructured as us
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.html import partition_html
from unstructured.partition.pptx import partition_pptx
from unstructured.partition.docx import partition_docx

import nltk
nltk.download('punkt_tab', quiet=True)
nltk.download('averaged_perceptron_tagger_eng', quiet=True)


class DocumentParser():
    def __init__(
        self,
        verbose: bool = False,
        openai_api_key: str = None,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        self.openai_api_key = openai_api_key
        self.summarize_tables = summarize_tables and openai_api_key
        self.summarize_images = summarize_images and openai_api_key
        self.table_summarizer = TableSummarizer(openai_api_key) if self.summarize_tables else None
        self.image_summarizer = ImageSummarizer(openai_api_key) if self.summarize_images else None
        self.logger = logging.getLogger()
        self.verbose = verbose

class DoclingDocumentParser(DocumentParser):
    def __init__(
        self,
        verbose: bool = False,
        openai_api_key: str = None,
        chunk: bool = False,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, openai_api_key, summarize_tables, summarize_images)
        self.chunk = chunk
        self.logger.info(f"Using DoclingParser with chunking {'enabled' if self.chunk else 'disabled'}")

    @staticmethod
    def _lazy_load_docling():
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling_core.transforms.chunker import HierarchicalChunker
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat

        return DocumentConverter, HierarchicalChunker, PdfPipelineOptions, PdfFormatOption, InputFormat

    def parse(
            self,
            filename: str, 
        ) -> Tuple[str, List[str]]:
        """
        Parse a local file and return the title and text content.
        Using Docling
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with title and list of text content.
        """
        # Process using Docling
        DocumentConverter, HierarchicalChunker, PdfPipelineOptions, PdfFormatOption, InputFormat = self._lazy_load_docling()


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
            chunks = list(HierarchicalChunker().chunk(doc))
            texts = [chunk.text for chunk in chunks]
        else:
            texts = [e.text for e in doc.texts]
        self.logger.info(f"DoclingParser: {len(texts)} text elements")

        if self.summarize_tables:
            self.logger.info(f"DoclingParser: {len(doc.tables)} tables")
            for table in doc.tables:
                table_md = table.export_to_markdown()
                table_summary = self.table_summarizer.summarize_table_text(table_md)
                if table_summary:
                    texts.append(table_summary)
                    if self.verbose:
                        self.logger.info(f"Table summary: {table_summary}")

        if self.summarize_images:
            image_path = 'image.png'
            self.logger.info(f"DoclingParser: {len(doc.pictures)} images")
            for pic in doc.pictures:
                image = pic.get_image(res.document)
                if image:
                    with open(image_path, 'wb') as fp:
                        image.save(fp, 'PNG')
                    image_summary = self.image_summarizer.summarize_image(image_path, None)
                    if image_summary:
                        texts.append(image_summary)
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary}")
                else:
                    self.logger.info(f"Failed to retrieve image {pic}")
                    continue

        self.logger.info(f"parsing file {filename} with Docling took {time.time()-st:.2f} seconds")
        return doc_title, texts


class UnstructuredDocumentParser(DocumentParser):
    def __init__(
        self,
        verbose: bool = False,
        openai_api_key: str = None,
        chunking_strategy: str = "none",
        chunk_size: int = 1024,
        summarize_tables: bool = False,
        summarize_images: bool = False
    ):
        super().__init__(verbose, openai_api_key, summarize_tables, summarize_images)
        self.chunking_strategy = chunking_strategy     # none, by_title or basic
        self.chunk_size = chunk_size
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
        ) -> Tuple[str, List[str]]:
        """
        Parse a local file and return the title and text content.
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with title and list of text content.
        """
        # Process using unstructured partitioning functionality
        st = time.time()
        
        # Pass 1: process text and tables (if summarize_tables is True)
        elements = self._get_elements(
            filename,
            mode='tables' if self.summarize_tables else 'default',
        )
        texts = []
        num_tables = len([x for x in elements if type(x)==us.documents.elements.Table])
        self.logger.info(f"UnstructuredDocumentParser: {len(elements)} elements in pass 1, {num_tables} are tables")
        for inx,e in enumerate(elements):
            if (type(e)==us.documents.elements.Table and self.summarize_tables):
                table_summary = self.table_summarizer.summarize_table_text(str(e))
                if table_summary:
                    texts.append(table_summary)
                    if self.verbose:
                        self.logger.info(f"Table summary: {table_summary}")
            else:
                texts.append(str(e))

        # Pass 2: process any images; here we never use unstructured chunking, and ignore any text
        elements = self._get_elements(
            filename,
            mode = 'images' if self.summarize_images else 'default',
        )
        num_images = len([x for x in elements if type(x)==us.documents.elements.Image])
        self.logger.info(f"UnstructuredDocumentParser: {len(elements)} elements in pass 2, {num_images} are images")
        for inx,e in enumerate(elements):
            if (type(e)==us.documents.elements.Image and  self.summarize_images):
                if inx>0 and type(elements[inx-1]) in [us.documents.elements.Title, us.documents.elements.NarrativeText]:
                    image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, elements[inx-1].text)
                else:
                    image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, None)
                if image_summary:
                    texts.append(image_summary)
                    if self.verbose:
                        self.logger.info(f"Image summary: {image_summary}")

        # No chunking strategy may result in title elements; if so - use the first one as doc_title
        titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>10]
        doc_title = titles[0] if len(titles)>0 else ''

        self.logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")
        return doc_title, texts
