import hashlib
import logging
from typing import Dict, List, Any, Optional, Sequence
from core.utils import create_row_items

logger = logging.getLogger(__name__)


class DocumentBuilder:
    """Handles document structure creation for Vectara indexing"""
    
    def __init__(self, cfg, normalize_text_func=None):
        self.cfg = cfg
        if normalize_text_func:
            self.normalize_text = normalize_text_func
        else:
            from core.utils import normalize_text
            self.normalize_text = lambda text: normalize_text(text, cfg)
        
    def build_document(
        self,
        doc_id: str,
        texts: List[str],
        titles: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        doc_metadata: Optional[Dict[str, Any]] = None,
        doc_title: str = "",
        tables: Optional[Sequence[Dict[str, Any]]] = None,
        use_core_indexing: bool = False
    ) -> Dict[str, Any]:
        """
        Build document structure for Vectara indexing
        
        Args:
            doc_id: Document ID
            texts: List of text segments
            titles: List of titles for each segment
            metadatas: List of metadata for each segment
            doc_metadata: Document-level metadata
            doc_title: Document title
            tables: List of tables
            use_core_indexing: Whether to use core indexing format
            
        Returns:
            Document dictionary ready for indexing
        """
        if ''.join(texts).strip() == '':
            logger.info(f"Document {doc_id} has no content")
            return None
        
        # Normalize inputs
        if titles is None:
            titles = ["" for _ in range(len(texts))]
        if doc_metadata is None:
            doc_metadata = {}
        if metadatas is None:
            metadatas = [{} for _ in range(len(texts))]
        else:
            metadatas = [{k: self._normalize_value(v) for k, v in md.items()} for md in metadatas]
        
        # Build document structure
        document = {}
        document["id"] = self._generate_doc_id(doc_id)
        document["metadata"] = {}
        
        # Build tables structure
        tables_array = self._build_tables_array(tables) if tables else []
        
        if use_core_indexing:
            document = self._build_core_document(document, texts, metadatas, doc_title, tables_array)
        else:
            document = self._build_structured_document(document, texts, titles, metadatas, doc_title, tables_array)
        
        if doc_metadata:
            document["metadata"].update(doc_metadata)

        return document
    
    def _normalize_value(self, value):
        """Normalize value using the provided normalize function"""
        if isinstance(value, str):
            return self.normalize_text(value)
        return value
    
    def _generate_doc_id(self, doc_id: str) -> str:
        """Generate a valid document ID, truncating if necessary"""
        max_doc_id_length = 128
        if len(doc_id) < max_doc_id_length:
            return doc_id
        return doc_id[:max_doc_id_length] + "-" + hashlib.sha256(doc_id.encode('utf-8')).hexdigest()[:16]

    def _build_tables_array(self, tables: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build tables array for document structure"""
        tables_array = []
        
        for inx, table in enumerate(tables):
            # Validate table summary - skip table if empty or None
            table_summary = table.get('summary', '')
            if not table_summary or table_summary.strip() == '':
                logger.warning(f"Skipping table {inx} due to empty or missing summary")
                continue
                
            table_dict = {
                'id': 'table_' + str(inx),
                'title': table.get('title', ''),
                'data': {
                    'headers': [
                        [{'text_value': str(col)} for col in header]
                        for header in table['headers']
                    ],
                    'rows': [
                        create_row_items(row) for row in table['rows']
                    ]
                },
                'description': table_summary
            }
            tables_array.append(table_dict)
            
        return tables_array
    
    def _build_core_document(
        self,
        document: Dict[str, Any],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        doc_title: str,
        tables_array: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build document for core indexing"""
        # Check text size limits for core indexing
        if any(len(text) > 16384 for text in texts):
            logger.warning(f"Document {document['id']} has segments too large for core indexing")
            return None
            
        document["document_parts"] = [
            {"text": self.normalize_text(text), "metadata": md}
            for text, md in zip(texts, metadatas)
        ]
        
        if tables_array:
            document["tables"] = tables_array
            
        if doc_title:
            document["metadata"] = {"title": doc_title}

        return document
    
    def _build_structured_document(
        self,
        document: Dict[str, Any],
        texts: List[str],
        titles: List[str],
        metadatas: List[Dict[str, Any]],
        doc_title: str,
        tables_array: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build document for structured indexing"""
        if doc_title and len(doc_title) > 0:
            document["title"] = self.normalize_text(doc_title)
            
        document["sections"] = [
            {
                "text": self.normalize_text(text),
                "title": self.normalize_text(title),
                "metadata": md
            }
            for text, title, md in zip(texts, titles, metadatas)
        ]
        
        if tables_array:
            document["sections"].append({
                "text": '',
                "title": '',
                "metadata": {},
                "tables": tables_array
            })
            
        return document
    
    def create_image_document(
        self,
        doc_id: str,
        image_summary: str,
        image_metadata: Dict[str, Any],
        doc_title: str = ""
    ) -> Dict[str, Any]:
        """Create a document structure for image content"""
        return self.build_document(
            doc_id=doc_id,
            texts=[image_summary],
            metadatas=[image_metadata],
            doc_metadata=image_metadata,
            doc_title=doc_title,
            use_core_indexing=True
        )