# Configuration Schema Documentation

This document is auto-generated from `core/config_schema.py` and describes all available configuration options.

### `CrawlingConfig`
> General crawling configuration.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `crawler_type` | `str` | _Required_ | The type of crawler to use, e.g., 'website', 'rss', 'jira'. |

### `DataFrameProcessingConfig`
> Configuration for processing dataframes (e.g., from CSVs).

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `str` | `table` | Processing mode for dataframes. |

### `DocProcessingConfig`
> Configuration for document processing and parsing.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_config` | `core.config_schema.ModelConfig` | _Required_ | Configuration for text and vision models. |
| `easy_ocr_config` | `core.config_schema.EasyOCRConfig` | _Required_ | Configuration for EasyOCR. |
| `unstructured_config` | `core.config_schema.UnstructuredConfig` | _Required_ | Configuration for unstructured document parsing. |
| `max_pages` | `int` | _Required_ | Maximum number of pages to process in a document. |
| `max_bytes` | `int` | _Required_ | Maximum size in bytes of a document to process. |
| `chunk_size` | `int` | _Required_ | The size of chunks for document processing. |
| `chunk_overlap` | `int` | _Required_ | The number of characters to overlap between chunks. |
| `parse_tables` | `bool` | `True` | If True, parse tables from documents and ingest them with an LLM-generated summary. |
| `enable_gmft` | `bool` | `False` | If True, use GMFT to parse tables from PDF files. |
| `model` | `str` | `openai` | Backward-compatible setting for the LLM provider (e.g., 'openai', 'anthropic'). |
| `doc_parser` | `str` | `docling` | The document parser to use, e.g., 'docling', 'unstructured', 'llama_parse'. |
| `do_ocr` | `bool` | `False` | If True, use Optical Character Recognition (OCR) when parsing documents (Docling only). |
| `summarize_images` | `bool` | `False` | If True, summarize image content using a vision model. |
| `use_core_indexing` | `bool` | `False` | If True, use chunks from the parser directly; otherwise, let Vectara perform chunking. |
| `extract_metadata` | dict[str, str | _(generated)_ | A dictionary defining metadata to extract using an LLM, where keys are attribute names and values are extraction queries. |

### `EasyOCRConfig`
> Configuration for EasyOCR.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `force_full_page_ocr` | `bool` | `True` | If True, forces OCR on the full page. |

### `LLMConfig`
> Configuration for a Large Language Model (LLM).

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | `str` | `openai` | The LLM provider, e.g., 'openai', 'anthropic', or 'private'. |
| `model_name` | `str` | `gpt-4o` | The specific model name to use, e.g., 'gpt-4o'. |
| `base_url` | `str` | `https://api.openai.com/v1` | Optional base URL for a privately-hosted LLM. |

### `ModelConfig`
> Configuration for text and vision models.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `core.config_schema.LLMConfig` | _Required_ | Configuration for the text processing LLM. |
| `vision` | `core.config_schema.LLMConfig` | _Required_ | Configuration for the vision (image processing) LLM. |

### `UnstructuredConfig`
> Configuration for unstructured document parsing.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `chunking_strategy` | `str` | `by_title` | Chunking strategy for unstructured documents, e.g., 'basic', 'by_title'. |
| `chunk_size` | `int` | `1024` | The size of chunks for unstructured document chunking. |

### `VectaraConfig`
> Defines the configuration for connecting to and interacting with the Vectara platform.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `corpus_key` | `str` | _Required_ | The corpus key for indexing data. |
| `endpoint` | str (optional) | _Required_ | The API endpoint for the Vectara platform. |
| `api_key` | `str` | _Required_ | The API key for authenticating with Vectara. |
| `auth_url` | str (optional) | _Required_ | The authentication URL for OAuth, used when `create_corpus` is enabled. |
| `parallel_uploads` | `int` | _Required_ | Number of parallel uploads to Vectara. |
| `max_retries` | `int` | _Required_ | Maximum number of retries for failed API requests. |
| `initial_backoff` | `int` | _Required_ | Initial backoff time in seconds for retries. |
| `max_backoff` | `int` | _Required_ | Maximum backoff time in seconds for retries. |
| `timeout` | `int` | _Required_ | Timeout in seconds for crawling web pages. |
| `vectara_endpoint` | `str` | _Required_ | The API endpoint for the Vectara platform. |
| `disable_ssl_verify` | `bool` | _Required_ | If True, SSL verification for the Vectara platform is disabled. |
| `rpm` | `int` | _Required_ | Requests Per Minute limit for API calls. |
| `rps` | `int` | _Required_ | Requests Per Second limit for API calls. |
| `min_delay_between_requests` | `float` | _Required_ | Minimum delay in seconds between API requests. |
| `reindex` | `bool` | `True` | If True, re-indexes documents that already exist in the corpus. |
| `create_corpus` | `bool` | `True` | If True, attempts to create the corpus if it doesn't exist. |
| `mask_pii` | `bool` | `False` | If True, attempts to mask Personally Identifiable Information (PII) in the text. |
| `remove_boilerplate` | `bool` | `False` | If True, removes boilerplate content (like ads, headers) from web pages. |
| `remove_code` | `bool` | `True` | If True, removes code blocks from HTML content. |
| `verbose` | `bool` | `False` | If True, enables extra debug messages. |
| `store_docs` | `bool` | `False` | If True, stores a local copy of all indexed documents. |
| `private_api_key` | str (optional) | `None` | API key for a privately-hosted LLM. |
| `openai_api_key` | str (optional) | `None` | API key for OpenAI services, used for features like table summarization. |
| `whisper_model` | str (optional) | `base` | The Whisper model to use for transcribing audio files (e.g., 'tiny', 'base', 'small'). |

### `VectaraIngestConfig`
> Top-level configuration for a vectara-ingest job.

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `vectara` | `core.config_schema.VectaraConfig` | _Required_ | Vectara platform connection and indexing configuration. |
| `crawling` | `core.config_schema.CrawlingConfig` | _Required_ | General crawling configuration. |
| `doc_processing` | `core.config_schema.DocProcessingConfig` | _Required_ | Document processing and parsing configuration. |
| `dataframe_processing` | `core.config_schema.DataFrameProcessingConfig` | _Required_ | Configuration for processing dataframes (e.g., from CSVs). |
| `folder_crawler` | crawlers.folder_crawler.FolderCrawlerConfig (optional) | _Required_ | No description available. |
| `website_crawler` | crawlers.website_crawler.WebsiteCrawlerConfig (optional) | _Required_ | No description available. |
| `csv_crawler` | crawlers.csv_crawler.CsvCrawlerConfig (optional) | _Required_ | No description available. |
| `docs_crawler` | crawlers.docs_crawler.DocsCrawlerConfig (optional) | _Required_ | No description available. |
| `edgar_crawler` | crawlers.edgar_crawler.EdgarCrawlerConfig (optional) | _Required_ | No description available. |
| `rss_crawler` | crawlers.rss_crawler.RssCrawlerConfig (optional) | _Required_ | No description available. |
| `arxiv_crawler` | crawlers.arxiv_crawler.ArxivCrawlerConfig (optional) | _Required_ | No description available. |
| `database_crawler` | crawlers.database_crawler.DatabaseCrawlerConfig (optional) | _Required_ | No description available. |
| `confluencedatacenter` | crawlers.confluencedatacenter_crawler.ConfluencedatacenterCrawlerConfig (optional) | _Required_ | No description available. |
| `confluence_crawler` | crawlers.confluence_crawler.ConfluenceCrawlerConfig (optional) | _Required_ | No description available. |
| `fmp_crawler` | crawlers.fmp_crawler.FmpCrawlerConfig (optional) | _Required_ | No description available. |
| `gdrive_crawler` | crawlers.gdrive_crawler.GdriveCrawlerConfig (optional) | _Required_ | No description available. |
| `discourse_crawler` | crawlers.discourse_crawler.DiscourseCrawlerConfig (optional) | _Required_ | No description available. |
| `github_crawler` | crawlers.github_crawler.GithubCrawlerConfig (optional) | _Required_ | No description available. |
| `bulkupload_crawler` | crawlers.bulkupload_crawler.BulkuploadCrawlerConfig (optional) | _Required_ | No description available. |
| `hackernews_crawler` | crawlers.hackernews_crawler.HackernewsCrawlerConfig (optional) | _Required_ | No description available. |
| `hfdataset_crawler` | crawlers.hfdataset_crawler.HfdatasetCrawlerConfig (optional) | _Required_ | No description available. |
| `hubspot_crawler` | crawlers.hubspot_crawler.HubspotCrawlerConfig (optional) | _Required_ | No description available. |
| `jira_crawler` | crawlers.jira_crawler.JiraCrawlerConfig (optional) | _Required_ | No description available. |
| `mediawiki_crawler` | crawlers.mediawiki_crawler.MediawikiCrawlerConfig (optional) | _Required_ | No description available. |
| `notion_crawler` | crawlers.notion_crawler.NotionCrawlerConfig (optional) | _Required_ | No description available. |
| `pmc_crawler` | crawlers.pmc_crawler.PmcCrawlerConfig (optional) | _Required_ | No description available. |
| `s3_crawler` | crawlers.s3_crawler.S3CrawlerConfig (optional) | _Required_ | No description available. |
| `servicenow_crawler` | crawlers.servicenow_crawler.ServicenowCrawlerConfig (optional) | _Required_ | No description available. |
| `sharepoint_crawler` | crawlers.sharepoint_crawler.SharepointCrawlerConfig (optional) | _Required_ | No description available. |
| `slack_crawler` | crawlers.slack_crawler.SlackCrawlerConfig (optional) | _Required_ | No description available. |
| `synapse_crawler` | crawlers.synapse_crawler.SynapseCrawlerConfig (optional) | _Required_ | No description available. |
| `twitter_crawler` | crawlers.twitter_crawler.TwitterCrawlerConfig (optional) | _Required_ | No description available. |
| `yt_crawler` | crawlers.yt_crawler.YtCrawlerConfig (optional) | _Required_ | No description available. |

