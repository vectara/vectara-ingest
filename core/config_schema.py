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
    corpus_key: str
    endpoint: str | None
    api_key: str
    auth_url: str | None
    parallel_uploads: int
    max_retries: int
    initial_backoff: int
    max_backoff: int
    timeout: int
    vectara_endpoint: str
    disable_ssl_verify: bool
    rpm: int
    rps: int
    min_delay_between_requests: float

    reindex: bool = True
    create_corpus: bool = True
    mask_pii: bool = False
    remove_boilerplate: bool = False
    remove_code: bool = True
    verbose: bool = False
    store_docs: bool = False
    private_api_key: str | None = None
    openai_api_key: str | None = None
    whisper_model: str | None = "base"


@dataclass
class LLMConfig:
    provider: str = 'openai'
    model_name: str = 'gpt-4o'
    base_url: str = 'https://api.openai.com/v1'


@dataclass
class EasyOCRConfig:
    force_full_page_ocr: bool = True


@dataclass
class ModelConfig:
    text: LLMConfig
    vision: LLMConfig


@dataclass
class DataFrameProcessingConfig:
    mode: str = 'table'  # TODO: Set this to an enum


@dataclass
class UnstructuredConfig:
    chunking_strategy: str = 'by_title'
    chunk_size: int = 1024


@dataclass
class DocProcessingConfig:
    model_config: ModelConfig
    easy_ocr_config: EasyOCRConfig
    unstructured_config: UnstructuredConfig

    max_pages: int
    max_bytes: int
    chunk_size: int
    chunk_overlap: int
    parse_tables: bool = True
    enable_gmft: bool = False
    model: str = "openai"
    doc_parser: str = "docling"
    do_ocr: bool = False
    summarize_images: bool = False
    use_core_indexing: bool = False
    extract_metadata: dict[str, str] = field(default_factory=lambda: {})


@dataclass
class CrawlingConfig:
    crawler_type: str


@dataclass
class VectaraIngestConfig:
    vectara: VectaraConfig
    crawling: CrawlingConfig
    doc_processing: DocProcessingConfig
    dataframe_processing: DataFrameProcessingConfig

    # crawler specific config
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







def check_config(cfg: DictConfig):
    structured_config = OmegaConf.structured(VectaraIngestConfig)
    OmegaConf.merge(structured_config, cfg)
    return structured_config
