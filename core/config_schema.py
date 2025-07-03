from dataclasses import dataclass, field

from omegaconf import DictConfig, OmegaConf

from crawlers.csv_crawler import CsvCrawlerConfig
from crawlers.docs_crawler import DocsCrawlerConfig
from crawlers.edgar_crawler import EdgarCrawlerConfig
from crawlers.folder_crawler import FolderCrawlerConfig
from crawlers.rss_crawler import RssCrawlerConfig
from crawlers.website_crawler import WebsiteCrawlerConfig
from crawlers.arxiv_crawler import ArxivCrawlerConfig
from crawlers.database_crawler import DatabaseCrawlerConfig
from crawlers.confluencedatacenter_crawler import ConfluencedatacenterCrawlerConfig
from crawlers.confluence_crawler import ConfluenceCrawlerConfig
from crawlers.fmp_crawler import FmpCrawlerConfig
from crawlers.gdrive_crawler import GdriveCrawlerConfig
from crawlers.discourse_crawler import DiscourseCrawlerConfig
from crawlers.github_crawler import GithubCrawlerConfig
from crawlers.bulkupload_crawler import BulkuploadCrawlerConfig
from crawlers.hackernews_crawler import HackernewsCrawlerConfig
from crawlers.hfdataset_crawler import HfdatasetCrawlerConfig
from crawlers.hubspot_crawler import HubspotCrawlerConfig
from crawlers.jira_crawler import JiraCrawlerConfig
from crawlers.mediawiki_crawler import MediawikiCrawlerConfig
from crawlers.notion_crawler import NotionCrawlerConfig
from crawlers.pmc_crawler import PmcCrawlerConfig
from crawlers.s3_crawler import S3CrawlerConfig
from crawlers.sharepoint_crawler import SharepointCrawlerConfig
from crawlers.servicenow_crawler import ServicenowCrawlerConfig
from crawlers.slack_crawler import SlackCrawlerConfig
from crawlers.synapse_crawler import SynapseCrawlerConfig
from crawlers.twitter_crawler import TwitterCrawlerConfig
from crawlers.yt_crawler import YtCrawlerConfig

@dataclass
class VectaraConfig:
    """Defines the configuration for connecting to and interacting with the Vectara platform."""
    corpus_key: str
    """The corpus key for indexing data."""
    endpoint: str | None
    """The API endpoint for the Vectara platform."""
    api_key: str
    """The API key for authenticating with Vectara."""
    auth_url: str | None
    """The authentication URL for OAuth, used when `create_corpus` is enabled."""
    parallel_uploads: int
    """Number of parallel uploads to Vectara."""
    max_retries: int
    """Maximum number of retries for failed API requests."""
    initial_backoff: int
    """Initial backoff time in seconds for retries."""
    max_backoff: int
    """Maximum backoff time in seconds for retries."""
    timeout: int
    """Timeout in seconds for crawling web pages."""
    vectara_endpoint: str
    """The API endpoint for the Vectara platform."""
    disable_ssl_verify: bool
    """If True, SSL verification for the Vectara platform is disabled."""
    rpm: int
    """Requests Per Minute limit for API calls."""
    rps: int
    """Requests Per Second limit for API calls."""
    min_delay_between_requests: float
    """Minimum delay in seconds between API requests."""

    reindex: bool = True
    """If True, re-indexes documents that already exist in the corpus."""
    create_corpus: bool = True
    """If True, attempts to create the corpus if it doesn't exist."""
    mask_pii: bool = False
    """If True, attempts to mask Personally Identifiable Information (PII) in the text."""
    remove_boilerplate: bool = False
    """If True, removes boilerplate content (like ads, headers) from web pages."""
    remove_code: bool = True
    """If True, removes code blocks from HTML content."""
    verbose: bool = False
    """If True, enables extra debug messages."""
    store_docs: bool = False
    """If True, stores a local copy of all indexed documents."""
    private_api_key: str | None = None
    """API key for a privately-hosted LLM."""
    openai_api_key: str | None = None
    """API key for OpenAI services, used for features like table summarization."""
    whisper_model: str | None = "base"
    """The Whisper model to use for transcribing audio files (e.g., 'tiny', 'base', 'small')."""


@dataclass
class LLMConfig:
    """Configuration for a Large Language Model (LLM)."""
    provider: str = 'openai'
    """The LLM provider, e.g., 'openai', 'anthropic', or 'private'."""
    model_name: str = 'gpt-4o'
    """The specific model name to use, e.g., 'gpt-4o'."""
    base_url: str = 'https://api.openai.com/v1'
    """Optional base URL for a privately-hosted LLM."""


@dataclass
class EasyOCRConfig:
    """Configuration for EasyOCR."""
    force_full_page_ocr: bool = True
    """If True, forces OCR on the full page."""


@dataclass
class ModelConfig:
    """Configuration for text and vision models."""
    text: LLMConfig
    """Configuration for the text processing LLM."""
    vision: LLMConfig
    """Configuration for the vision (image processing) LLM."""


@dataclass
class DataFrameProcessingConfig:
    """Configuration for processing dataframes (e.g., from CSVs)."""
    mode: str = 'table'  # TODO: Set this to an enum
    """Processing mode for dataframes."""


@dataclass
class UnstructuredConfig:
    """Configuration for unstructured document parsing."""
    chunking_strategy: str = 'by_title'
    """Chunking strategy for unstructured documents, e.g., 'basic', 'by_title'."""
    chunk_size: int = 1024
    """The size of chunks for unstructured document chunking."""


@dataclass
class DocProcessingConfig:
    """Configuration for document processing and parsing."""
    model_config: ModelConfig
    """Configuration for text and vision models."""
    easy_ocr_config: EasyOCRConfig
    """Configuration for EasyOCR."""
    unstructured_config: UnstructuredConfig
    """Configuration for unstructured document parsing."""

    max_pages: int
    """Maximum number of pages to process in a document."""
    max_bytes: int
    """Maximum size in bytes of a document to process."""
    chunk_size: int
    """The size of chunks for document processing."""
    chunk_overlap: int
    """The number of characters to overlap between chunks."""
    parse_tables: bool = True
    """If True, parse tables from documents and ingest them with an LLM-generated summary."""
    enable_gmft: bool = False
    """If True, use GMFT to parse tables from PDF files."""
    model: str = "openai"
    """Backward-compatible setting for the LLM provider (e.g., 'openai', 'anthropic')."""
    doc_parser: str = "docling"
    """The document parser to use, e.g., 'docling', 'unstructured', 'llama_parse'."""
    do_ocr: bool = False
    """If True, use Optical Character Recognition (OCR) when parsing documents (Docling only)."""
    summarize_images: bool = False
    """If True, summarize image content using a vision model."""
    use_core_indexing: bool = False
    """If True, use chunks from the parser directly; otherwise, let Vectara perform chunking."""
    extract_metadata: dict[str, str] = field(default_factory=lambda: {})
    """A dictionary defining metadata to extract using an LLM, where keys are attribute names and values are extraction queries."""


@dataclass
class CrawlingConfig:
    """General crawling configuration."""
    crawler_type: str
    """The type of crawler to use, e.g., 'website', 'rss', 'jira'."""


@dataclass
class VectaraIngestConfig:
    """Top-level configuration for a vectara-ingest job."""
    vectara: VectaraConfig
    """Vectara platform connection and indexing configuration."""
    crawling: CrawlingConfig
    """General crawling configuration."""
    doc_processing: DocProcessingConfig
    """Document processing and parsing configuration."""
    dataframe_processing: DataFrameProcessingConfig
    """Configuration for processing dataframes (e.g., from CSVs)."""

    # Crawler-specific configurations
    folder_crawler: FolderCrawlerConfig | None
    website_crawler: WebsiteCrawlerConfig | None
    csv_crawler: CsvCrawlerConfig | None
    docs_crawler: DocsCrawlerConfig | None
    edgar_crawler: EdgarCrawlerConfig | None
    rss_crawler: RssCrawlerConfig | None
    arxiv_crawler: ArxivCrawlerConfig | None
    database_crawler: DatabaseCrawlerConfig | None
    confluencedatacenter: ConfluencedatacenterCrawlerConfig | None
    confluence_crawler: ConfluenceCrawlerConfig | None
    fmp_crawler: FmpCrawlerConfig | None
    gdrive_crawler: GdriveCrawlerConfig | None
    discourse_crawler: DiscourseCrawlerConfig | None
    github_crawler: GithubCrawlerConfig | None
    bulkupload_crawler: BulkuploadCrawlerConfig | None
    hackernews_crawler: HackernewsCrawlerConfig | None
    hfdataset_crawler: HfdatasetCrawlerConfig | None
    hubspot_crawler: HubspotCrawlerConfig | None
    jira_crawler: JiraCrawlerConfig | None
    mediawiki_crawler: MediawikiCrawlerConfig | None
    notion_crawler: NotionCrawlerConfig | None
    pmc_crawler: PmcCrawlerConfig | None
    s3_crawler: S3CrawlerConfig | None
    servicenow_crawler: ServicenowCrawlerConfig | None
    sharepoint_crawler: SharepointCrawlerConfig | None
    slack_crawler: SlackCrawlerConfig | None
    synapse_crawler: SynapseCrawlerConfig | None
    twitter_crawler: TwitterCrawlerConfig | None
    yt_crawler: YtCrawlerConfig | None


def check_config(cfg: DictConfig) -> DictConfig:
    """
    Validates the user-provided configuration against the structured schema.

    Args:
        cfg: The configuration loaded from a YAML file.

    Returns:
        The merged and validated configuration object.
    """
    structured_config = OmegaConf.structured(VectaraIngestConfig)
    OmegaConf.merge(structured_config, cfg)
    return structured_config