import unittest
import tempfile
import os
import time
import threading
from unittest.mock import Mock, MagicMock, patch, mock_open
from io import StringIO
import pandas as pd
from omegaconf import OmegaConf

from core.utils import (
    get_file_size_in_MB,
    normalize_url,
    clean_urls,
    url_to_filename,
    get_file_extension,
    get_file_path_from_url,
    detect_language,
    clean_email_text,
    html_to_text,
    remove_code_from_html,
    safe_remove_file,
    get_docker_or_local_path,
    markdown_to_df,
    html_table_to_header_and_rows,
    create_row_items,
    df_cols_to_headers,
    setup_logging,
    load_config,
    RateLimiter,
    create_session_with_retries,
    configure_session_for_ssl,
    get_headers,
    url_matches_patterns,
    normalize_text,
    normalize_value,
    get_media_type_from_base64,
    detect_file_type
)


class TestUtils(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up after each test method."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    # =============================================================================
    # FILE UTILITIES TESTS
    # =============================================================================
    
    def test_get_file_size_in_MB(self):
        file_size = 2 * 1024 * 1024
        with tempfile.TemporaryFile() as fp:
            buffer = bytearray(file_size)
            fp.write(buffer)
            fp.flush()
            actual = get_file_size_in_MB(fp.name)
            self.assertEqual(2.0, actual)

    def test_get_file_size_in_MB_zero_byte_file(self):
        with tempfile.TemporaryFile() as fp:
            fp.flush()
            actual = get_file_size_in_MB(fp.name)
            self.assertEqual(0, actual)
    
    @patch('os.remove')
    def test_safe_remove_file_success(self, mock_remove):
        """Test successful file removal."""
        safe_remove_file('/path/to/file.txt')
        mock_remove.assert_called_once_with('/path/to/file.txt')
    
    @patch('os.remove')
    @patch('core.utils.logger')
    def test_safe_remove_file_failure(self, mock_logger, mock_remove):
        """Test file removal failure is logged."""
        mock_remove.side_effect = OSError("Permission denied")
        safe_remove_file('/path/to/file.txt')
        mock_logger.warning.assert_called_once()
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    @patch('core.utils.logger')
    def test_get_docker_or_local_path_docker_exists(self, mock_logger, mock_makedirs, mock_exists):
        """Test Docker path is used when it exists."""
        mock_exists.return_value = True
        result = get_docker_or_local_path('/docker/path')
        self.assertEqual(result, '/docker/path')
        mock_logger.info.assert_called_with('Using Docker path: /docker/path')
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    @patch('os.getcwd')
    @patch('core.utils.logger')
    def test_get_docker_or_local_path_local_fallback(self, mock_logger, mock_getcwd, mock_makedirs, mock_exists):
        """Test local path fallback when Docker path doesn't exist."""
        mock_exists.return_value = False
        mock_getcwd.return_value = '/current/dir'
        result = get_docker_or_local_path('/docker/path')
        expected = '/current/dir/vectara_ingest_output'
        self.assertEqual(result, expected)
        mock_makedirs.assert_called_once_with(expected, exist_ok=True)
    
    @patch('os.path.exists')
    @patch('core.utils.logger')
    def test_get_docker_or_local_path_config_path_exists(self, mock_logger, mock_exists):
        """Test config path is used when provided and exists."""
        mock_exists.side_effect = lambda path: path == '/config/path'
        result = get_docker_or_local_path('/docker/path', config_path='/config/path')
        self.assertEqual(result, '/config/path')
        mock_logger.info.assert_called_with('Using config path: /config/path')
    
    @patch('os.path.exists')
    def test_get_docker_or_local_path_config_path_missing(self, mock_exists):
        """Test FileNotFoundError when config path doesn't exist."""
        mock_exists.return_value = False
        with self.assertRaises(FileNotFoundError):
            get_docker_or_local_path('/docker/path', config_path='/missing/path')

    @patch('magic.Magic')
    def test_detect_file_type_basic(self, mock_magic):
        """Test basic file type detection."""
        mock_magic_instance = Mock()
        mock_magic_instance.from_file.return_value = 'text/plain'
        mock_magic.return_value = mock_magic_instance
        
        result = detect_file_type('/path/to/file.txt')
        self.assertEqual(result, 'text/plain')
    
    @patch('magic.Magic')
    @patch('builtins.open', new_callable=mock_open, read_data='<?xml version="1.0"?><root></root>')
    def test_detect_file_type_xml(self, mock_file, mock_magic):
        """Test XML file type detection."""
        mock_magic_instance = Mock()
        mock_magic_instance.from_file.return_value = 'text/html'
        mock_magic.return_value = mock_magic_instance
        
        result = detect_file_type('/path/to/file.xml')
        self.assertEqual(result, 'application/xml')
    
    @patch('magic.Magic')
    @patch('builtins.open', new_callable=mock_open, read_data='<html><body>test</body></html>')
    def test_detect_file_type_html(self, mock_file, mock_magic):
        """Test HTML file type detection."""
        mock_magic_instance = Mock()
        mock_magic_instance.from_file.return_value = 'text/html'
        mock_magic.return_value = mock_magic_instance
        
        result = detect_file_type('/path/to/file.html')
        self.assertEqual(result, 'text/html')

    # =============================================================================
    # URL UTILITIES TESTS
    # =============================================================================
    
    def test_normalize_url_basic(self):
        """Test basic URL normalization."""
        result = normalize_url('https://www.example.com/path?param=value')
        self.assertEqual(result, 'https://example.com/path')
    
    def test_normalize_url_keep_query_params(self):
        """Test URL normalization keeping query parameters."""
        result = normalize_url('https://www.example.com/path?param=value', keep_query_params=True)
        self.assertEqual(result, 'https://example.com/path?param=value')
    
    def test_normalize_url_no_scheme(self):
        """Test URL normalization with no scheme."""
        result = normalize_url('example.com/path')
        self.assertEqual(result, 'http://example.com/path')
    
    def test_normalize_url_root_path(self):
        """Test URL normalization with root path."""
        result = normalize_url('https://example.com/')
        self.assertEqual(result, 'https://example.com/')
    
    def test_clean_urls(self):
        """Test URL cleaning and deduplication."""
        urls = {
            'https://www.example.com/path?param=1',
            'https://example.com/path?param=2',
            'http://www.example.com/path'
        }
        result = clean_urls(urls)
        self.assertEqual(len(result), 2)  # Should deduplicate
        self.assertIn('https://example.com/path', result)
        self.assertIn('http://example.com/path', result)
    
    def test_url_to_filename(self):
        """Test URL to filename conversion."""
        result = url_to_filename('https://example.com/path/My File Name.pdf')
        self.assertEqual(result, 'my-file-name.pdf')
    
    def test_url_to_filename_no_extension(self):
        """Test URL to filename conversion without extension."""
        result = url_to_filename('https://example.com/path/filename')
        self.assertEqual(result, 'filename')
    
    def test_get_file_extension(self):
        """Test file extension extraction from URL."""
        result = get_file_extension('https://example.com/path/file.PDF')
        self.assertEqual(result, '.pdf')
    
    def test_get_file_extension_no_extension(self):
        """Test file extension extraction with no extension."""
        result = get_file_extension('https://example.com/path/file')
        self.assertEqual(result, '')
    
    def test_get_file_path_from_url(self):
        """Test file path extraction from URL."""
        result = get_file_path_from_url('https://example.com/path/My File Name.pdf?param=1')
        self.assertEqual(result, 'my-file-name.pdf')
    
    def test_get_file_path_from_url_no_extension(self):
        """Test file path extraction without extension."""
        result = get_file_path_from_url('https://example.com/path/filename')
        self.assertEqual(result, 'filename')

    # =============================================================================
    # TEXT PROCESSING UTILITIES TESTS
    # =============================================================================
    
    def test_clean_email_text(self):
        """Test email text cleaning."""
        email_text = "  <Subject: Important>  \n<From: sender@example.com>  \nBody content  "
        result = clean_email_text(email_text)
        self.assertEqual(result, "Subject: Important  \nFrom: sender@example.com  \nBody content")
    
    @patch('core.utils.detect')
    def test_detect_language_success(self, mock_detect):
        """Test successful language detection."""
        mock_detect.return_value = 'en'
        result = detect_language('Hello world')
        self.assertEqual(result, 'en')
    
    @patch('core.utils.detect')
    @patch('core.utils.logger')
    def test_detect_language_failure(self, mock_logger, mock_detect):
        """Test language detection failure fallback."""
        mock_detect.side_effect = Exception("Detection failed")
        result = detect_language('Hello world')
        self.assertEqual(result, 'en')
        mock_logger.warning.assert_called_once()
    
    def test_html_to_text_basic(self):
        """Test basic HTML to text conversion."""
        html = '<html><body><h1>Title</h1><p>Paragraph</p></body></html>'
        result = html_to_text(html)
        self.assertIn('Title', result)
        self.assertIn('Paragraph', result)
    
    def test_html_to_text_remove_script(self):
        """Test HTML to text with script removal."""
        html = '<html><body><script>alert("test")</script><p>Content</p></body></html>'
        result = html_to_text(html)
        self.assertNotIn('alert', result)
        self.assertIn('Content', result)
    
    def test_html_to_text_remove_ids(self):
        """Test HTML to text with ID removal."""
        html = '<html><body><div id="remove-me">Remove this</div><p>Keep this</p></body></html>'
        result = html_to_text(html, html_processing={'ids_to_remove': ['remove-me']})
        self.assertNotIn('Remove this', result)
        self.assertIn('Keep this', result)
    
    def test_html_to_text_remove_tags(self):
        """Test HTML to text with tag removal."""
        html = '<html><body><nav>Navigation</nav><p>Content</p></body></html>'
        result = html_to_text(html, html_processing={'tags_to_remove': ['nav']})
        self.assertNotIn('Navigation', result)
        self.assertIn('Content', result)
    
    def test_html_to_text_remove_classes(self):
        """Test HTML to text with class removal."""
        html = '<html><body><div class="ad">Advertisement</div><p>Content</p></body></html>'
        result = html_to_text(html, html_processing={'classes_to_remove': ['ad']})
        self.assertNotIn('Advertisement', result)
        self.assertIn('Content', result)
    
    def test_remove_code_from_html(self):
        """Test code removal from HTML."""
        html = '<html><body><code>code content</code><p>regular content</p></body></html>'
        result = remove_code_from_html(html)
        self.assertNotIn('code content', result)
        self.assertIn('regular content', result)
    
    def test_normalize_text_basic(self):
        """Test basic text normalization."""
        cfg = OmegaConf.create({'vectara': {'mask_pii': False}})
        result = normalize_text('Hello world', cfg)
        self.assertEqual(result, 'Hello world')
    
    def test_normalize_text_empty(self):
        """Test text normalization with empty input."""
        cfg = OmegaConf.create({'vectara': {'mask_pii': False}})
        result = normalize_text('', cfg)
        self.assertEqual(result, '')
    
    def test_normalize_text_null(self):
        """Test text normalization with null input."""
        cfg = OmegaConf.create({'vectara': {'mask_pii': False}})
        result = normalize_text(None, cfg)
        self.assertIsNone(result)
    
    def test_normalize_value_string(self):
        """Test value normalization with string input."""
        cfg = OmegaConf.create({'vectara': {'mask_pii': False}})
        result = normalize_value('test string', cfg)
        self.assertEqual(result, 'test string')
    
    def test_normalize_value_non_string(self):
        """Test value normalization with non-string input."""
        cfg = OmegaConf.create({'vectara': {'mask_pii': False}})
        result = normalize_value(123, cfg)
        self.assertEqual(result, 123)

    # =============================================================================
    # DATA PROCESSING UTILITIES TESTS
    # =============================================================================
    
    def test_markdown_to_df_basic(self):
        """Test basic markdown table to DataFrame conversion."""
        markdown = """| Name | Age | City |
|------|-----|------|
| John | 30  | NYC  |
| Jane | 25  | LA   |"""
        df = markdown_to_df(markdown)
        self.assertEqual(df.shape, (2, 3))
        self.assertEqual(df.columns.tolist(), ['Name', 'Age', 'City'])
        self.assertEqual(df.iloc[0, 0], 'John')
    
    def test_markdown_to_df_empty(self):
        """Test empty markdown table."""
        df = markdown_to_df('')
        self.assertTrue(df.empty)
    
    def test_markdown_to_df_no_separator(self):
        """Test markdown table without separator row."""
        markdown = """| Name | Age |
| John | 30  |
| Jane | 25  |"""
        df = markdown_to_df(markdown)
        self.assertEqual(df.shape, (2, 2))
    
    def test_html_table_to_header_and_rows(self):
        """Test HTML table parsing."""
        html = """<table>
            <tr><th>Name</th><th>Age</th></tr>
            <tr><td>John</td><td>30</td></tr>
            <tr><td>Jane</td><td>25</td></tr>
        </table>"""
        header, rows = html_table_to_header_and_rows(html)
        self.assertEqual(header, ['Name', 'Age'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ['John', '30'])
        self.assertEqual(rows[1], ['Jane', '25'])
    
    def test_html_table_to_header_and_rows_no_table(self):
        """Test HTML table parsing with no table."""
        html = '<div>No table here</div>'
        header, rows = html_table_to_header_and_rows(html)
        self.assertEqual(header, [])
        self.assertEqual(rows, [])
    
    def test_html_table_to_header_and_rows_colspan(self):
        """Test HTML table parsing with colspan."""
        html = """<table>
            <tr><th colspan="2">Name</th></tr>
            <tr><td>John</td><td>30</td></tr>
        </table>"""
        header, rows = html_table_to_header_and_rows(html)
        self.assertEqual(header, ['Name', 'Name'])
        self.assertEqual(rows[0], ['John', '30'])
    
    def test_create_row_items_basic(self):
        """Test creating row items from basic data."""
        items = ['cell1', 'cell2', 123, True]
        result = create_row_items(items)
        expected = [
            {'text_value': 'cell1'},
            {'text_value': 'cell2'},
            {'text_value': '123'},
            {'text_value': 'True'}
        ]
        self.assertEqual(result, expected)
    
    def test_create_row_items_with_colspan(self):
        """Test creating row items with colspan tuples."""
        items = [('header', 2), 'normal_cell']
        result = create_row_items(items)
        expected = [
            {'text_value': 'header'},
            {'text_value': ''},
            {'text_value': 'normal_cell'}
        ]
        self.assertEqual(result, expected)
    
    def test_df_cols_to_headers_simple(self):
        """Test DataFrame columns to headers conversion."""
        df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
        result = df_cols_to_headers(df)
        self.assertEqual(result, [['A', 'B']])
    
    def test_df_cols_to_headers_multiindex(self):
        """Test DataFrame MultiIndex columns to headers conversion."""
        arrays = [['A', 'A', 'B'], ['X', 'Y', 'Z']]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples)
        df = pd.DataFrame([[1, 2, 3]], columns=index)
        result = df_cols_to_headers(df)
        self.assertEqual(len(result), 2)  # Two levels
        self.assertEqual(result[0], [('A', 2), ('B', 1)])
        self.assertEqual(result[1], [('X', 1), ('Y', 1), ('Z', 1)])
    
    @patch('base64.b64decode')
    @patch('magic.Magic')
    def test_get_media_type_from_base64(self, mock_magic, mock_b64decode):
        """Test media type detection from base64 data."""
        mock_b64decode.return_value = b'fake_data'
        mock_magic_instance = Mock()
        mock_magic_instance.from_buffer.return_value = 'image/png'
        mock_magic.return_value = mock_magic_instance
        
        result = get_media_type_from_base64('fake_base64_data')
        self.assertEqual(result, 'image/png')

    # =============================================================================
    # HTTP/SESSION UTILITIES TESTS
    # =============================================================================
    
    def test_create_session_with_retries(self):
        """Test creating session with retry configuration."""
        session = create_session_with_retries(retries=3)
        self.assertIsNotNone(session)
        # Check that adapters are mounted
        self.assertIn('http://', session.adapters)
        self.assertIn('https://', session.adapters)
    
    @patch('core.utils.logger')
    def test_configure_session_for_ssl_disable(self, mock_logger):
        """Test SSL configuration with verification disabled."""
        session = Mock()
        config = OmegaConf.create({'ssl_verify': False})
        configure_session_for_ssl(session, config)
        self.assertFalse(session.verify)
        mock_logger.warning.assert_called_once()
    
    @patch('core.utils.logger')
    def test_configure_session_for_ssl_string_false(self, mock_logger):
        """Test SSL configuration with string 'false'."""
        session = Mock()
        config = OmegaConf.create({'ssl_verify': 'false'})
        configure_session_for_ssl(session, config)
        self.assertFalse(session.verify)
        mock_logger.warning.assert_called_once()
    
    @patch('core.utils.logger')
    def test_configure_session_for_ssl_default(self, mock_logger):
        """Test SSL configuration with default settings."""
        session = Mock()
        config = OmegaConf.create({'ssl_verify': True})
        configure_session_for_ssl(session, config)
        mock_logger.debug.assert_called_once()
    
    @patch('os.path.exists')
    @patch('core.utils.logger')
    def test_configure_session_for_ssl_custom_cert(self, mock_logger, mock_exists):
        """Test SSL configuration with custom certificate."""
        mock_exists.return_value = True
        session = Mock()
        config = OmegaConf.create({'ssl_verify': '/path/to/cert.pem'})
        configure_session_for_ssl(session, config)
        self.assertEqual(session.verify, '/path/to/cert.pem')
        mock_logger.info.assert_called_once()
    
    @patch('os.path.exists')
    @patch('os.path.expanduser')
    def test_configure_session_for_ssl_cert_not_found(self, mock_expanduser, mock_exists):
        """Test SSL configuration with certificate not found."""
        mock_exists.return_value = False
        mock_expanduser.return_value = '/expanded/path/cert.pem'
        session = Mock()
        config = OmegaConf.create({'ssl_verify': '/path/to/cert.pem'})
        with self.assertRaises(FileNotFoundError):
            configure_session_for_ssl(session, config)
    
    def test_get_headers_default(self):
        """Test getting HTTP headers with default user agent."""
        cfg = OmegaConf.create({'vectara': {}})
        headers = get_headers(cfg)
        self.assertIn('User-Agent', headers)
        self.assertIn('Accept', headers)
        self.assertIn('Accept-Language', headers)
    
    def test_get_headers_custom_user_agent(self):
        """Test getting HTTP headers with custom user agent."""
        cfg = OmegaConf.create({'vectara': {'user_agent': 'CustomBot/1.0'}})
        headers = get_headers(cfg)
        self.assertEqual(headers['User-Agent'], 'CustomBot/1.0')

    # =============================================================================
    # CONFIGURATION UTILITIES TESTS
    # =============================================================================
    
    @patch('core.utils.OmegaConf.load')
    @patch('core.utils.logger')
    def test_load_config_single_file(self, mock_logger, mock_load):
        """Test loading single configuration file."""
        mock_config = OmegaConf.create({'test': 'value'})
        mock_load.return_value = mock_config
        
        result = load_config('config.yaml')
        self.assertIsNotNone(result)
        mock_logger.info.assert_called_once()
    
    @patch('core.utils.OmegaConf.load')
    @patch('core.utils.logger')
    def test_load_config_multiple_files(self, mock_logger, mock_load):
        """Test loading multiple configuration files."""
        mock_config1 = OmegaConf.create({'key1': 'value1'})
        mock_config2 = OmegaConf.create({'key2': 'value2'})
        mock_load.side_effect = [mock_config1, mock_config2]
        
        result = load_config('config1.yaml', 'config2.yaml')
        self.assertIsNotNone(result)
        self.assertEqual(mock_logger.info.call_count, 2)
    
    @patch('logging.getLogger')
    @patch('logging.StreamHandler')
    @patch('sys.stdout')
    def test_setup_logging_default(self, mock_stdout, mock_handler, mock_get_logger):
        """Test logging setup with default level."""
        mock_root_logger = Mock()
        mock_get_logger.return_value = mock_root_logger
        mock_handler_instance = Mock()
        mock_handler.return_value = mock_handler_instance
        
        setup_logging()
        
        mock_root_logger.setLevel.assert_called_once()
        mock_handler_instance.setLevel.assert_called_once()
        mock_root_logger.addHandler.assert_called_once()
    
    @patch('logging.getLogger')
    @patch('os.environ', {'LOGGING_LEVEL': 'DEBUG'})
    def test_setup_logging_env_level(self, mock_get_logger):
        """Test logging setup with environment variable."""
        mock_root_logger = Mock()
        mock_get_logger.return_value = mock_root_logger
        
        with patch('logging.StreamHandler'):
            setup_logging()
        
        # Should use DEBUG level from environment
        mock_root_logger.setLevel.assert_called_once()

    # =============================================================================
    # PATTERN MATCHING UTILITIES TESTS
    # =============================================================================
    
    def test_url_matches_patterns_positive_match(self):
        """Test URL pattern matching with positive patterns."""
        import re
        pos_patterns = [re.compile(r'.*example\.com.*')]
        neg_patterns = []
        
        result = url_matches_patterns('https://example.com/page', pos_patterns, neg_patterns)
        self.assertTrue(result)
    
    def test_url_matches_patterns_negative_match(self):
        """Test URL pattern matching with negative patterns."""
        import re
        pos_patterns = []
        neg_patterns = [re.compile(r'.*admin.*')]
        
        result = url_matches_patterns('https://example.com/admin', pos_patterns, neg_patterns)
        self.assertFalse(result)
    
    def test_url_matches_patterns_both_patterns(self):
        """Test URL pattern matching with both positive and negative patterns."""
        import re
        pos_patterns = [re.compile(r'.*example\.com.*')]
        neg_patterns = [re.compile(r'.*admin.*')]
        
        result = url_matches_patterns('https://example.com/page', pos_patterns, neg_patterns)
        self.assertTrue(result)
        
        result = url_matches_patterns('https://example.com/admin', pos_patterns, neg_patterns)
        self.assertFalse(result)

    # =============================================================================
    # RATE LIMITER TESTS
    # =============================================================================
    
    def test_rate_limiter_basic(self):
        """Test basic rate limiter functionality."""
        limiter = RateLimiter(max_rate=2, window_size=1.0)
        
        start_time = time.time()
        with limiter:
            pass
        with limiter:
            pass
        
        # Third call should be delayed
        with limiter:
            pass
        
        elapsed = time.time() - start_time
        # Should take at least 1 second due to rate limiting
        self.assertGreaterEqual(elapsed, 0.8)  # Allow some tolerance
    
    def test_rate_limiter_threaded(self):
        """Test rate limiter with multiple threads."""
        limiter = RateLimiter(max_rate=2, window_size=1.0)
        results = []
        
        def worker():
            start = time.time()
            with limiter:
                pass
            results.append(time.time() - start)
        
        threads = []
        start_time = time.time()
        
        for _ in range(4):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Should have some delays due to rate limiting
        total_time = time.time() - start_time
        self.assertGreaterEqual(total_time, 0.8)  # Allow some tolerance