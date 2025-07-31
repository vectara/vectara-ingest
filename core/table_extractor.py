import logging
from typing import List, Dict, Any, Optional
from omegaconf import OmegaConf
from core.summary import TableSummarizer
from core.utils import html_table_to_header_and_rows

logger = logging.getLogger(__name__)


class TableExtractor:
    """Handles table extraction and summarization"""
    
    def __init__(self, cfg: OmegaConf, model_config: Dict[str, Any], verbose: bool = False):
        self.cfg = cfg
        self.model_config = model_config
        self.verbose = verbose
        self.table_summarizer = None
        
    def _get_table_summarizer(self):
        """Lazy initialization of table summarizer"""
        if self.table_summarizer is None:
            if 'text' not in self.model_config:
                logger.warning("Table summarization enabled but no text model configured")
                return None
            
            self.table_summarizer = TableSummarizer(
                cfg=self.cfg,
                table_model_config=self.model_config['text'],
            )
        return self.table_summarizer
    
    def process_tables(self, tables: List[str], url: str) -> List[Dict[str, Any]]:
        """
        Process HTML tables and return structured table data
        
        Args:
            tables: List of HTML table strings
            url: Source URL for logging
            
        Returns:
            List of processed table dictionaries
        """
        if not tables:
            return []
        
        table_summarizer = self._get_table_summarizer()
        if not table_summarizer:
            return []
        
        if self.verbose:
            logger.info(f"Found {len(tables)} tables in {url}")
        
        processed_tables = []
        
        for table_html in tables:
            try:
                table_summary = table_summarizer.summarize_table_text(table_html)
                if not table_summary:
                    continue
                
                if self.verbose:
                    logger.info(f"Table summary: {table_summary[:500]}...")
                
                cols, rows = html_table_to_header_and_rows(table_html)
                
                # Check if table has meaningful content
                cols_not_empty = any(col for col in cols)
                rows_not_empty = any(any(cell for cell in row) for row in rows)
                
                if cols_not_empty or rows_not_empty:
                    processed_tables.append({
                        'headers': cols,
                        'rows': rows,
                        'summary': table_summary
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to process table: {e}")
                continue
        
        return processed_tables
    
    def process_dataframe_tables(self, tables: List[tuple]) -> List[Dict[str, Any]]:
        """
        Process tables from document parser (DataFrame format)
        
        Args:
            tables: List of (dataframe, summary, title, metadata) tuples
            
        Returns:
            List of processed table dictionaries
        """
        from core.utils import df_cols_to_headers
        
        processed_tables = []
        
        for df, summary, table_title, table_metadata in tables:
            try:
                cols = df_cols_to_headers(df)
                rows = df.fillna('').values.tolist()
                
                if len(rows) > 0 and len(cols) > 0:
                    processed_tables.append({
                        'headers': cols,
                        'rows': rows,
                        'summary': summary,
                        'title': table_title,
                        'metadata': table_metadata
                    })
                    
            except Exception as e:
                logger.warning(f"Failed to process dataframe table: {e}")
                continue
            finally:
                # Clean up dataframe to free memory
                del df
        
        return processed_tables