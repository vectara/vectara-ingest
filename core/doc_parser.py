import logging
from typing import List, Tuple, Iterator
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

from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

MAX_VERBOSE_LENGTH = 1000

class DocumentParser():
    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        parse_tables: bool = False,
        enable_gmft: bool = False,
        do_ocr: bool = False,
        summarize_images: bool = False,
    ):
        self.model_name = model_name
        self.model_api_key = model_api_key
        self.enable_gmft = enable_gmft
        self.do_ocr = do_ocr
        self.parse_tables = parse_tables and (model_api_key is not None)
        self.summarize_images = summarize_images and model_api_key is not None
        self.table_summarizer = TableSummarizer(model_name, model_api_key) if self.parse_tables else None
        self.image_summarizer = ImageSummarizer(model_name, model_api_key) if self.summarize_images else None
        self.logger = logging.getLogger()
        self.verbose = verbose

    def get_tables_with_gmft(self, filename: str) -> Iterator[Tuple[pd.DataFrame, str, str]]:
        if not filename.endswith('.pdf'):
            self.logger.warning(f"GMFT: only PDF files are supported, skipping {filename}")
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
                    print(f"GMFT: processing page {inx+1}")
                for table in detector.extract(page):
                    try:
                        ft = formatter.extract(table)
                        df = ft.df()
                        table_summary = self.table_summarizer.summarize_table_text(df.to_markdown())
                        yield (df, table_summary, " ".join(ft.captions()), {'parser_element_type': 'table', 'page': inx+1})
                    except Exception as e:
                        self.logger.error(f"Error processing table (with GMFT) on page {inx+1}: {e}")
                        continue
        finally:
            doc.close()
            if self.verbose:
                self.logger.info("GMFT: Finished processing PDF")


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
        super().__init__(
            verbose=verbose, 
            model_name=model_name, 
            model_api_key=model_api_key, 
            parse_tables=parse_tables, 
            enable_gmft=enable_gmft, 
            do_ocr=False,
            summarize_images=summarize_images
        )
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
        ) -> Tuple[str, List[Tuple], List[Tuple], list[Tuple]]:
        """
        Parse a local file and return the title and text content.
        Using LlamaPase
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
            Tuple with:
            * doc_title
            * list of Tuple[text,metadata]
            * list of Tuple[table, table description, table title, table metadata]
            * list of Tuple[image_summary, metadata]
        """
        st = time.time()
        doc_title = ''
        texts = []
        images = []
        tables = []
        img_folder = '/images'
        os.makedirs(img_folder, exist_ok=True)

        nest_asyncio.apply()
        for page in self.parser.get_json_result(filename)[0]['pages']:
            texts.append((page['text'], page['page']))

            if self.parse_tables:
                if self.enable_gmft and filename.endswith('.pdf'):
                    tables = self.get_tables_with_gmft(filename)
                else:
                    lm_tables = (item for item in page['items'] if item['type']=='table')
                    for table in lm_tables:
                        table_md = table['md']
                        table_summary = self.table_summarizer.summarize_table_text(table_md)
                        if table_summary:
                            if self.verbose:
                                self.logger.info(f"Table summary: {table_summary[:MAX_VERBOSE_LENGTH]}...")
                            tables.append([markdown_to_df(table_md), table_summary, ''], {'parser_element_type': 'table', 'page': page['page']})

            # process images
            if self.summarize_images:
                images = self.parser.get_images(page, download_path=img_folder)
                for image in images:
                    image_summary = self.image_summarizer.summarize_image(image['path'], source_url, None)
                    if image_summary:
                        images.append(image_summary, {'parser_element_type': 'image', 'page': page['page']})
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary[:MAX_VERBOSE_LENGTH]}...")

        self.logger.info(f"LlamaParse: {len(tables)} tables, and {len(images)} images")
        self.logger.info(f"parsing file {filename} with LlamaParse took {time.time()-st:.2f} seconds")

        return doc_title, texts, tables, images

class DoclingDocumentParser(DocumentParser):

    def __init__(
        self,
        verbose: bool = False,
        model_name: str = None,
        model_api_key: str = None,
        chunking_strategy: str = 'hierarchical',
        parse_tables: bool = False,
        enable_gmft: bool = False,
        do_ocr: bool = False,
        summarize_images: bool = False,
        image_scale: float = 1.0,
    ):
        super().__init__(
            verbose=verbose, 
            model_name=model_name, 
            model_api_key=model_api_key, 
            parse_tables=parse_tables, 
            enable_gmft=enable_gmft, 
            do_ocr=do_ocr,
            summarize_images=summarize_images
        )
        self.chunking_strategy = chunking_strategy
        self.image_scale = image_scale
        if self.verbose:
            self.logger.info(f"Using DoclingParser with chunking strategy {self.chunking_strategy}")

    @staticmethod
    def _lazy_load_docling():
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, EasyOcrOptions
        from docling.datamodel.base_models import InputFormat
        from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
        from docling_core.transforms.chunker import HierarchicalChunker

        return DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions, PdfFormatOption, InputFormat, EasyOcrOptions

    def _get_tables(self, tables):
        for table in tables:
            table_md = table.export_to_markdown()
            try:
                table_summary = self.table_summarizer.summarize_table_text(table_md)
                yield (table.export_to_dataframe(), table_summary, '', 
                       {'parser_element_type': 'table', 'page': table.prov[0].page_no})
            except ValueError as err:
                self.logger.error(f"Error parsing Markdown table: {err}. Skipping...")
                continue

    def parse(
            self,
            filename: str, 
            source_url: str = "No URL"
        ) -> Tuple[str, List[Tuple], List[Tuple], list[Tuple]]:
        """
        Parse a local file and return the title and text content.
        Using Docling
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
        Tuple with:
            * doc_title
            * list of Tuple[text,metadata]
            * list of Tuple[table, table description, table title, table metadata]
            * list of Tuple[image_summary, metadata]
        """
        # Process using Docling
        (
            DocumentConverter, HybridChunker, HierarchicalChunker, PdfPipelineOptions, 
            PdfFormatOption, InputFormat, EasyOcrOptions
        ) = self._lazy_load_docling()

        st = time.time()
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = self.image_scale
        pipeline_options.generate_picture_images = True
        pipeline_options.do_ocr = False
        if self.do_ocr:
            pipeline_options.do_ocr = True
            ocr_options = EasyOcrOptions(force_full_page_ocr=True)
            pipeline_options.ocr_options = ocr_options
        res = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        ).convert(filename)
        doc = res.document
        doc_title = doc.name

        if self.chunking_strategy == 'hybrid' or self.chunking_strategy == 'hierarchical':
            chunker = HybridChunker() if self.chunking_strategy == 'hybrid' else HierarchicalChunker()
            texts = [(chunker.serialize(chunk=chunk), {'parser_element_type': 'text', 'page': chunk.meta.doc_items[0].prov[0].page_no})
                     for chunk in chunker.chunk(doc)]
        else:
            texts = [(e.text, {'parser_element_type': 'text', 'page': e.prov[0].page_no}) for e in doc.texts]

        tables = []
        if self.parse_tables:
            if self.enable_gmft and filename.endswith('.pdf'):
                tables = self.get_tables_with_gmft(filename)
            else:
                tables = self._get_tables(doc.tables)

        images = []
        if self.summarize_images:
            image_path = 'image.png'
            self.logger.info(f"DoclingParser: {len(doc.pictures)} images")
            for pic in doc.pictures:
                image = pic.get_image(doc)
                if image:
                    with open(image_path, 'wb') as fp:
                        image.save(fp, 'PNG')
                    image_summary = self.image_summarizer.summarize_image(image_path, source_url, None)
                    if image_summary:
                        images.append((image_summary, 
                                      {'parser_element_type': 'image', 'page': pic.prov[0].page_no}))
                        if self.verbose:
                            self.logger.info(f"Image summary: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                else:
                    self.logger.info(f"Failed to retrieve image {pic}")
                    continue

        self.logger.info(f"parsing file {filename} with Docling took {time.time()-st:.2f} seconds")
        return doc_title, texts, tables, images


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
        super().__init__(
            verbose=verbose, 
            model_name=model_name, 
            model_api_key=model_api_key, 
            parse_tables=parse_tables, 
            enable_gmft=enable_gmft, 
            do_ocr=False,
            summarize_images=summarize_images
        )
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

    def _get_tables(self, elements):
        for e in elements:
            if isinstance(e, us.documents.elements.Table):
                try:
                    table_summary = self.table_summarizer.summarize_table_text(str(e))
                    html_table = e.metadata.text_as_html
                    df = pd.read_html(StringIO(html_table))[0]
                    yield [df, table_summary, '', {'parser_element_type': 'table', 'page': e.metadata.page_number}]
                except ValueError as err:
                    self.logger.error(f"Error parsing HTML table: {err}. Skipping...")
                    continue

    def parse(
            self,
            filename: str, 
            source_url: str = "No URL",
        ) -> Tuple[str, List[Tuple], List[Tuple], list[Tuple]]:
        """
        Parse a local file and return the title and text content.
        
        Args:
            filename (str): Name of the file to parse.

        Returns:
        Tuple with:
            * doc_title
            * list of Tuple[text,metadata]
            * list of Tuple[table, table description, table title, table metadata]
            * list of Tuple[image_summary, metadata]
        """
        # Process using unstructured partitioning functionality
        st = time.time()
        
        # Pass 1: process text
        if self.verbose:
            self.logger.info(f"Unstructured pass 1: extracting text from {filename}")
        elements = self._get_elements(filename, mode='text')
        texts = [
            (str(e), {'parser_element_type': 'text', 'page': e.metadata.page_number})
            for e in elements
        ]
        self.logger.info(f"UnstructuredParser: {len(texts)} text elements")

        # No chunking strategy may result in title elements; if so - use the first one as doc_title
        titles = [str(x) for x in elements if type(x)==us.documents.elements.Title and len(str(x))>10]
        doc_title = titles[0] if len(titles)>0 else ''

        # Pass 2: extract tables and images; here we never use unstructured chunking, and ignore any text
        if self.verbose:
            self.logger.info(f"Unstructured pass 2: extracting tables and images from {filename}")
        elements = self._get_elements(filename, mode='images')

        # get image summaries
        images = []
        if self.summarize_images:
            for inx,e in enumerate(elements):
                if isinstance(e, us.documents.elements.Image) and e.metadata.coordinates.system.width>100 and e.metadata.coordinates.system.height>100:
                    try:
                        if inx>0 and type(elements[inx-1]) in [us.documents.elements.Title, us.documents.elements.NarrativeText]:
                            image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, elements[inx-1].text)
                        else:
                            image_summary = self.image_summarizer.summarize_image(e.metadata.image_path, source_url, None)
                        if image_summary:
                            images.append((image_summary, {'parser_element_type': 'image', 'page': e.metadata.page_number}))
                            if self.verbose:
                                self.logger.info(f"Image summary: {image_summary[:MAX_VERBOSE_LENGTH]}...")
                    except Exception as exc:
                        self.logger.error(f"Error summarizing image ({e.metadata.image_path}): {exc}")
                        continue
        # get tables
        if self.parse_tables:
            if self.enable_gmft and filename.endswith('.pdf'):
                tables = self.get_tables_with_gmft(filename)
            else:
                tables = self._get_tables(elements)


        self.logger.info(f"parsing file {filename} with unstructured.io took {time.time()-st:.2f} seconds")
        return doc_title, texts, tables, images
