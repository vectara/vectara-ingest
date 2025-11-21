import unittest
import os
import sys
import tempfile
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

# Mock cairosvg before it's imported by other modules
sys.modules['cairosvg'] = MagicMock()


class TestImageFileParser(unittest.TestCase):
    """Test cases for standalone image file parsing functionality"""

    def setUp(self):
        """Set up test fixtures"""
        # Create a temporary test image
        self.temp_image = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        img = Image.new('RGB', (100, 100), color='red')
        img.save(self.temp_image.name, 'PNG')
        self.temp_image.close()

    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_image.name):
            os.remove(self.temp_image.name)

    def test_image_file_parser_basic(self):
        """Test that ImageFileParser correctly processes a standalone image file"""
        from omegaconf import OmegaConf
        from core.doc_parser import ImageFileParser, ParsedDocument

        # Create mock configuration
        cfg = OmegaConf.create({
            'doc_processing': {
                'model_config': {
                    'vision': {
                        'provider': 'openai',
                        'model_name': 'gpt-4o',
                        'base_url': 'https://api.openai.com/v1'
                    }
                }
            }
        })

        model_config = {
            'vision': {
                'provider': 'openai',
                'model_name': 'gpt-4o',
                'base_url': 'https://api.openai.com/v1'
            }
        }

        # Mock the ImageSummarizer
        with patch('core.doc_parser.ImageSummarizer') as mock_summarizer_class:
            mock_summarizer = Mock()
            mock_summarizer.summarize_image.return_value = "A red colored square image"
            mock_summarizer_class.return_value = mock_summarizer

            # Create parser and parse the image
            parser = ImageFileParser(
                cfg=cfg,
                verbose=False,
                model_config=model_config,
                summarize_images=True
            )

            result = parser.parse(self.temp_image.name, "http://example.com/test.png")

            # Verify the result
            self.assertIsInstance(result, ParsedDocument)
            self.assertTrue(len(result.content_stream) == 1)

            # Check content
            content, metadata = result.content_stream[0]
            self.assertEqual(content, "A red colored square image")
            self.assertEqual(metadata['element_type'], 'image')
            self.assertEqual(metadata['page'], 1)
            self.assertIn('image_id', metadata)
            self.assertIn('filename', metadata)

            # Check title extraction from filename
            expected_title = os.path.splitext(os.path.basename(self.temp_image.name))[0].replace('_', ' ').replace('-', ' ').title()
            self.assertTrue(len(result.title) > 0)

            # Check image bytes stored
            self.assertEqual(len(result.image_bytes), 1)
            image_id, image_binary = result.image_bytes[0]
            self.assertTrue(len(image_binary) > 0)

            # Verify summarizer was called with correct parameters
            mock_summarizer.summarize_image.assert_called_once()
            call_args = mock_summarizer.summarize_image.call_args
            self.assertEqual(call_args[0][0], self.temp_image.name)  # filename
            self.assertEqual(call_args[0][1], "http://example.com/test.png")  # source_url
            self.assertIn("Filename:", call_args[1]['previous_text'])  # context includes filename

    def test_image_file_parser_nonexistent_file(self):
        """Test that ImageFileParser handles non-existent files gracefully"""
        from omegaconf import OmegaConf
        from core.doc_parser import ImageFileParser, ParsedDocument

        cfg = OmegaConf.create({'doc_processing': {'model_config': {'vision': {}}}})

        with patch('core.doc_parser.ImageSummarizer'):
            parser = ImageFileParser(
                cfg=cfg,
                verbose=False,
                model_config={'vision': {}},
                summarize_images=True
            )

            result = parser.parse("/nonexistent/image.png", "http://example.com/test.png")

            # Should return empty ParsedDocument
            self.assertIsInstance(result, ParsedDocument)
            self.assertEqual(len(result.content_stream), 0)
            self.assertEqual(len(result.tables), 0)
            self.assertEqual(len(result.image_bytes), 0)

    def test_image_file_parser_failed_summarization(self):
        """Test that ImageFileParser handles failed image summarization"""
        from omegaconf import OmegaConf
        from core.doc_parser import ImageFileParser, ParsedDocument

        cfg = OmegaConf.create({'doc_processing': {'model_config': {'vision': {}}}})

        with patch('core.doc_parser.ImageSummarizer') as mock_summarizer_class:
            mock_summarizer = Mock()
            mock_summarizer.summarize_image.return_value = None  # Failed summarization
            mock_summarizer_class.return_value = mock_summarizer

            parser = ImageFileParser(
                cfg=cfg,
                verbose=False,
                model_config={'vision': {}},
                summarize_images=True
            )

            result = parser.parse(self.temp_image.name, "http://example.com/test.png")

            # Should return empty content_stream but still have title
            self.assertIsInstance(result, ParsedDocument)
            self.assertEqual(len(result.content_stream), 0)
            self.assertTrue(len(result.title) > 0)

    def test_file_processor_detects_image_files(self):
        """Test that FileProcessor correctly detects and routes image files"""
        from omegaconf import OmegaConf
        from core.file_processor import FileProcessor

        cfg = OmegaConf.create({
            'vectara': {'verbose': False},
            'doc_processing': {
                'parse_tables': False,
                'enable_gmft': False,
                'do_ocr': False,
                'summarize_images': True,
                'doc_parser': 'docling',
                'contextual_chunking': False,
                'extract_metadata': [],
                'inline_images': True,
                'image_context': {'num_previous_chunks': 1, 'num_next_chunks': 1},
                'unstructured_config': {'chunking_strategy': 'by_title', 'chunk_size': 1024},
                'docling_config': {'chunking_strategy': 'none'},
                'model_config': {'vision': {}}
            }
        })

        processor = FileProcessor(cfg, model_config={'vision': {}})

        # Test that image files trigger local processing
        self.assertTrue(processor.should_process_locally("test.png", "test.png"))
        self.assertTrue(processor.should_process_locally("test.jpg", "test.jpg"))
        self.assertTrue(processor.should_process_locally("test.jpeg", "test.jpeg"))
        self.assertTrue(processor.should_process_locally("test.gif", "test.gif"))

        # Test that non-image files don't automatically trigger local processing
        # (unless other conditions are met)
        cfg.doc_processing.summarize_images = False
        processor = FileProcessor(cfg, model_config={'vision': {}})
        self.assertFalse(processor.should_process_locally("test.png", "test.png"))

    def test_file_processor_creates_image_parser(self):
        """Test that FileProcessor creates ImageFileParser for image files"""
        from omegaconf import OmegaConf
        from core.file_processor import FileProcessor
        from core.doc_parser import ImageFileParser

        cfg = OmegaConf.create({
            'vectara': {'verbose': False},
            'doc_processing': {
                'parse_tables': False,
                'enable_gmft': False,
                'do_ocr': False,
                'summarize_images': True,
                'doc_parser': 'docling',
                'contextual_chunking': False,
                'extract_metadata': [],
                'inline_images': True,
                'image_context': {'num_previous_chunks': 1, 'num_next_chunks': 1},
                'unstructured_config': {'chunking_strategy': 'by_title', 'chunk_size': 1024},
                'docling_config': {'chunking_strategy': 'none'},
                'model_config': {'vision': {}}
            }
        })

        with patch('core.doc_parser.ImageSummarizer'):
            processor = FileProcessor(cfg, model_config={'vision': {}})

            # Test that image files get routed to ImageFileParser
            parser = processor.create_document_parser(filename="test.png")
            self.assertIsInstance(parser, ImageFileParser)

            parser = processor.create_document_parser(filename="photo.jpg")
            self.assertIsInstance(parser, ImageFileParser)

            # Test that non-image files don't get ImageFileParser
            parser = processor.create_document_parser(filename="document.pdf")
            self.assertNotIsInstance(parser, ImageFileParser)

    def test_standalone_image_uses_core_indexing(self):
        """Test that standalone image files always use core indexing"""
        from omegaconf import OmegaConf
        from core.indexer import Indexer

        # Create config with use_core_indexing=False and no chunking
        cfg = OmegaConf.create({
            'vectara': {
                'verbose': False,
                'reindex': False,
                'create_corpus': False,
                'store_docs': False,
                'output_dir': 'test_output',
                'remove_code': True,
                'remove_boilerplate': False,
                'post_load_timeout': 5,
                'timeout': 90,
                'whisper_model': 'base'
            },
            'crawling': {'crawler_type': 'test'},
            'doc_processing': {
                'parse_tables': False,
                'enable_gmft': False,
                'do_ocr': False,
                'summarize_images': True,
                'add_image_bytes': False,
                'process_locally': True,
                'doc_parser': 'docling',
                'use_core_indexing': False,  # Explicitly disable
                'unstructured_config': {'chunking_strategy': 'none', 'chunk_size': 1024},
                'docling_config': {'chunking_strategy': 'none'},
                'extract_metadata': [],
                'contextual_chunking': False,  # No chunking
                'inline_images': True,
                'image_context': {'num_previous_chunks': 1, 'num_next_chunks': 1},
                'model_config': {'vision': {'provider': 'openai', 'model_name': 'gpt-4o'}}
            }
        })

        with patch('core.doc_parser.ImageSummarizer') as mock_summarizer_class:
            mock_summarizer = Mock()
            mock_summarizer.summarize_image.return_value = "A test image summary"
            mock_summarizer_class.return_value = mock_summarizer

            indexer = Indexer(cfg, "http://api.vectara.io", "test_corpus", "test_api_key")

            # Mock the index_segments method to capture its arguments
            indexer.index_segments = MagicMock(return_value=True)

            # Index a standalone image file
            result = indexer.index_file(self.temp_image.name, "http://example.com/test.png", {'source': 'test'})

            # Verify index_segments was called
            self.assertTrue(indexer.index_segments.called)

            # Get the call arguments
            call_args = indexer.index_segments.call_args

            # Verify use_core_indexing was set to True despite config having it False
            self.assertTrue(call_args.kwargs['use_core_indexing'],
                          "Standalone image files should force use_core_indexing=True")


if __name__ == '__main__':
    unittest.main()
