import hashlib
import logging
import re
from typing import Dict, List, Any, Optional, Sequence
from core.utils import create_row_items

logger = logging.getLogger(__name__)

MAX_SECTION_CHARS = 16000


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
        use_core_indexing: bool = False,
        split_oversized: bool = False
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
            split_oversized: When True, split oversized text sections and
                tables to stay under the API size limit. Used on retry.

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
            document = self._build_structured_document(
                document, texts, titles, metadatas, doc_title, tables_array,
                split_oversized=split_oversized
            )
        
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
                
            headers = table['headers']
            if headers and isinstance(headers[0], str):
                headers = [headers]

            table_dict = {
                'id': 'table_' + str(inx),
                'title': table.get('title', ''),
                'data': {
                    'headers': [
                        [{'text_value': str(col)} for col in header]
                        for header in headers
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
        if any(len(text) > MAX_SECTION_CHARS for text in texts):
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
        tables_array: List[Dict[str, Any]],
        split_oversized: bool = False
    ) -> Dict[str, Any]:
        """Build document for structured indexing.

        Args:
            split_oversized: When True, split text sections exceeding
                MAX_SECTION_CHARS and large tables by row count. Used on
                retry after a 400 "document part too large" error.
        """
        if doc_title and len(doc_title) > 0:
            document["title"] = self.normalize_text(doc_title)

        sections = []
        for text, title, md in zip(texts, titles, metadatas):
            normalized = self.normalize_text(text)
            normalized_title = self.normalize_text(title)
            if not split_oversized or len(normalized) <= MAX_SECTION_CHARS:
                sections.append({"text": normalized, "title": normalized_title, "metadata": md})
            else:
                chunks = self._split_text(normalized, MAX_SECTION_CHARS)
                logger.info(
                    f"Section text ({len(normalized)} chars) exceeds {MAX_SECTION_CHARS}, "
                    f"split into {len(chunks)} sections for document {document.get('id', '?')}"
                )
                for chunk in chunks:
                    sections.append({"text": chunk, "title": normalized_title, "metadata": md})

        if tables_array:
            if split_oversized:
                for table in tables_array:
                    table_sections = self._split_table_if_needed(table)
                    for table_section in table_sections:
                        sections.append({
                            "text": '',
                            "title": '',
                            "metadata": {},
                            "tables": [table_section]
                        })
            else:
                sections.append({
                    "text": '',
                    "title": '',
                    "metadata": {},
                    "tables": tables_array
                })

        document["sections"] = sections

        return document

    @staticmethod
    def _split_table_if_needed(table: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split a table into multiple tables if its data exceeds MAX_SECTION_CHARS.

        Uses greedy row-by-row accumulation to handle tables with unevenly
        sized rows. Each row's actual JSON size is measured individually.

        The first chunk keeps the original description (summary). Subsequent
        chunks get an empty description to avoid repetition.
        """
        import json
        estimated = len(json.dumps(table.get('data', {})))
        if estimated <= MAX_SECTION_CHARS:
            return [table]

        rows = table.get('data', {}).get('rows', [])
        headers = table.get('data', {}).get('headers', [])
        if not rows:
            return [table]

        headers_size = len(json.dumps(headers))
        budget = int(MAX_SECTION_CHARS * 0.8)

        description = table.get('description', '')
        if len(description) > MAX_SECTION_CHARS:
            description = description[:MAX_SECTION_CHARS]

        row_budget = budget - headers_size
        split_rows = []
        for row in rows:
            row_size = len(json.dumps(row))
            if row_size > row_budget:
                split_rows.extend(DocumentBuilder._split_oversized_row(row, row_budget))
            else:
                split_rows.append(row)

        chunks = []
        current_rows = []
        current_size = headers_size

        for row in split_rows:
            row_size = len(json.dumps(row))
            if current_rows and current_size + row_size > budget:
                is_first = (len(chunks) == 0)
                chunks.append({
                    'id': table['id'] + ('' if is_first else f'_part{len(chunks)}'),
                    'title': table.get('title', ''),
                    'data': {'headers': headers, 'rows': current_rows},
                    'description': description
                })
                current_rows = []
                current_size = headers_size

            current_rows.append(row)
            current_size += row_size

        if current_rows:
            is_first = (len(chunks) == 0)
            chunks.append({
                'id': table['id'] + ('' if is_first else f'_part{len(chunks)}'),
                'title': table.get('title', ''),
                'data': {'headers': headers, 'rows': current_rows},
                'description': description
            })

        logger.info(
            f"Table {table['id']} ({len(rows)} rows, ~{estimated} chars) "
            f"split into {len(chunks)} chunks"
        )
        return chunks

    @staticmethod
    def _split_oversized_row(row: List[Dict[str, Any]], max_row_chars: int) -> List[List[Dict[str, Any]]]:
        """Split a single oversized row into multiple rows.

        Finds the largest cell and splits its text_value across multiple rows,
        keeping the other cells' values only in the first resulting row (empty
        in subsequent rows).
        """
        import json
        largest_idx = 0
        largest_size = 0
        for i, cell in enumerate(row):
            cell_size = len(json.dumps(cell))
            if cell_size > largest_size:
                largest_size = cell_size
                largest_idx = i

        large_text = row[largest_idx].get('text_value', '')
        overhead = len(json.dumps(row)) - len(json.dumps(large_text))
        chunk_size = max(100, max_row_chars - overhead)

        text_chunks = []
        for i in range(0, len(large_text), chunk_size):
            text_chunks.append(large_text[i:i + chunk_size])

        result_rows = []
        for ci, chunk in enumerate(text_chunks):
            new_row = []
            for i, cell in enumerate(row):
                if i == largest_idx:
                    new_row.append({'text_value': chunk})
                elif ci == 0:
                    new_row.append(dict(cell))
                else:
                    new_row.append({'text_value': ''})
            result_rows.append(new_row)

        logger.info(
            f"Split oversized row ({largest_size} chars in cell {largest_idx}) "
            f"into {len(result_rows)} rows"
        )
        return result_rows

    @staticmethod
    def _split_text(text: str, max_chars: int) -> List[str]:
        """Split *text* into chunks of at most *max_chars* characters.

        Tries to break on paragraph boundaries (blank lines) first, then
        falls back to sentence boundaries, and finally to a hard character
        cut so that every returned chunk is within the limit.
        """
        if len(text) <= max_chars:
            return [text]

        paragraph_joiner = "\n\n"
        paragraphs = re.split(r'\n\s*\n', text)
        if len(paragraphs) == 1 and '\n' in text:
            paragraphs = re.split(r'\n+', text)
            paragraph_joiner = "\n"

        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            candidate = (current + paragraph_joiner + para).strip() if current else para
            if len(candidate) <= max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(para) <= max_chars:
                current = para
            else:
                for sub in DocumentBuilder._split_by_sentences(para, max_chars):
                    chunks.append(sub)

        if current:
            chunks.append(current)

        return chunks

    @staticmethod
    def _split_by_sentences(text: str, max_chars: int) -> List[str]:
        """Split text on sentence boundaries, with a hard-cut fallback."""
        sentences = re.split(r'(?<=[.!?])\s+', text)

        chunks: List[str] = []
        current = ""

        for sentence in sentences:
            candidate = (current + " " + sentence).strip() if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(sentence) <= max_chars:
                current = sentence
            else:
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i:i + max_chars])

        if current:
            chunks.append(current)

        return chunks
    
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