import logging
import os
import tempfile
from typing import Dict, List, Any, Optional, Tuple
from omegaconf import OmegaConf
from pypdf import PdfReader, PdfWriter
from core.utils import get_file_size_in_MB
from core.doc_parser import (
    UnstructuredDocumentParser, DoclingDocumentParser, 
    LlamaParseDocumentParser, DocupandaDocumentParser
)
from core.contextual import ContextualChunker
from core.summary import get_attributes_from_text

logger = logging.getLogger(__name__)


class FileProcessor:
    """Handles file processing and parsing operations"""
    
    def __init__(self, cfg: OmegaConf, model_config: Dict[str, Any]):
        self.cfg = cfg
        self.model_config = model_config
        self.verbose = cfg.vectara.get("verbose", False)
        
        # Document processing config
        self.parse_tables = cfg.doc_processing.get("parse_tables", False)
        self.enable_gmft = cfg.doc_processing.get("enable_gmft", False)
        self.do_ocr = cfg.doc_processing.get("do_ocr", False)
        self.summarize_images = cfg.doc_processing.get("summarize_images", False)
        self.doc_parser = cfg.doc_processing.get("doc_parser", "docling")
        self.contextual_chunking = cfg.doc_processing.get("contextual_chunking", False)
        self.extract_metadata = cfg.doc_processing.get("extract_metadata", [])
        
        # Parser configurations
        self.unstructured_config = cfg.doc_processing.get("unstructured_config", 
                                                          {'chunking_strategy': 'by_title', 'chunk_size': 1024})
        self.docling_config = cfg.doc_processing.get("docling_config", 
                                                     {'chunking_strategy': 'none'})
        
    def should_process_locally(self, filename: str, uri: str) -> bool:
        """Determine if file should be processed locally"""
        large_file_extensions = ['.pdf', '.html', '.htm', '.pptx', '.docx']
        
        return (
            any(uri.endswith(ext) for ext in large_file_extensions) and
            (self.contextual_chunking or self.summarize_images or self.enable_gmft)
        )
    
    def needs_pdf_splitting(self, filename: str) -> bool:
        """Check if PDF needs to be split due to size"""
        max_pdf_size = int(self.cfg.doc_processing.get('max_pdf_size', 50))
        filesize_mb = get_file_size_in_MB(filename)
        return filesize_mb > max_pdf_size
    
    def split_pdf(self, filename: str, metadata: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any], str]]:
        """Split large PDF into smaller chunks"""
        pages_per_pdf = int(self.cfg.doc_processing.get('pages_per_pdf', 100))
        pdf_reader = PdfReader(filename)
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"Splitting {filename} ({total_pages} pages) into {pages_per_pdf} page chunks")
        
        pdf_parts = []
        for i in range(0, total_pages, pages_per_pdf):
            pdf_writer = PdfWriter()
            pdf_part_metadata = metadata.copy()
            pdf_part_metadata.update({
                "start_page": i,
                "end_page": min(i + pages_per_pdf, total_pages)
            })
            
            # Add pages to writer
            for j in range(i, min(i + pages_per_pdf, total_pages)):
                pdf_writer.add_page(pdf_reader.pages[j])
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=".pdf", mode='wb', delete=False) as f:
                pdf_writer.write(f)
                f.flush()
                
                pdf_part_id = f"{metadata['file_name']}-{i}"
                pdf_parts.append((f.name, pdf_part_metadata, pdf_part_id))
        
        return pdf_parts
    
    def create_document_parser(self):
        """Create appropriate document parser based on configuration"""
        base_dict = {
            "cfg": self.cfg,
            "verbose": self.verbose,
            "model_config": self.model_config,
            "parse_tables": self.parse_tables,
            "enable_gmft": self.enable_gmft,
            "summarize_images": self.summarize_images
        }
        if self.contextual_chunking:
            return UnstructuredDocumentParser(
                **base_dict,
                chunking_strategy='by_title',
                chunk_size=1024,
            )
        elif self.doc_parser in ["llama_parse", "llama", "llama-parse"]:
            return LlamaParseDocumentParser(
                **base_dict,
                llama_parse_api_key=self.cfg.get("llama_cloud_api_key", None),
            )
        elif self.doc_parser == "docupanda":
            return DocupandaDocumentParser(
                **base_dict,
                docupanda_api_key=self.cfg.get("docupanda_api_key", None),
            )
        elif self.doc_parser == "docling":
            return DoclingDocumentParser(
                **base_dict,
                chunking_strategy=self.docling_config.get('chunking_strategy', 'none'),
                chunk_size=self.docling_config.get('chunk_size', 1024),
                do_ocr=self.do_ocr,
                image_scale=self.docling_config.get('image_scale', 2.0),
            )
        else:
            return UnstructuredDocumentParser(
                **base_dict,
                chunking_strategy=self.unstructured_config.get('chunking_strategy', 'by_title'),
                chunk_size=self.unstructured_config.get('chunk_size', 1024),
            )
    
    def extract_metadata_from_text(self, text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata attributes from text content"""
        if not self.extract_metadata:
            return {}
        
        if 'text' not in self.model_config:
            logger.warning("Metadata extraction enabled but no text model configured")
            return {}
        
        max_chars = 128000  # Limit text size
        truncated_text = text[:max_chars]
        
        ex_metadata = get_attributes_from_text(
            self.cfg,
            truncated_text,
            metadata_questions=self.extract_metadata,
            model_config=self.model_config['text']
        )
        
        metadata.update(ex_metadata)
        return ex_metadata
    
    def apply_contextual_chunking(self, texts: List[Tuple[str, Dict]], uri: str) -> List[str]:
        """Apply contextual chunking to text segments"""
        if not self.contextual_chunking:
            return [t[0] for t in texts]
        
        chunks = [t[0] for t in texts]
        all_text = "\n".join(chunks)
        
        cc = ContextualChunker(
            cfg=self.cfg,
            contextual_model_config=self.model_config['text'],
            whole_document=all_text
        )
        
        return cc.parallel_transform(chunks)
    
    def process_file(self, filename: str, uri: str) -> Tuple[str, List[Tuple[str, Dict]], List, List]:
        """
        Process file and return parsed content
        
        Returns:
            Tuple of (title, texts, tables, images)
        """
        if not os.path.exists(filename):
            raise FileNotFoundError(f"File {filename} does not exist")
        
        try:
            dp = self.create_document_parser()
            title, texts, tables, images = dp.parse(filename, uri)
            return title, texts, tables, images
        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")
            raise
    
    def generate_vec_tables(self, tables):
        """Generate vector-ready table format"""
        from core.utils import df_cols_to_headers
        
        for df, summary, table_title, table_metadata in tables:
            cols = df_cols_to_headers(df)
            rows = df.fillna('').values.tolist()
            del df
            
            if len(rows) > 0 and len(cols) > 0:
                yield {
                    'headers': cols,
                    'rows': rows,
                    'summary': summary,
                    'title': table_title,
                    'metadata': table_metadata
                }