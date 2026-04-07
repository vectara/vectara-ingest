from omegaconf import OmegaConf, DictConfig
from core.indexer import Indexer
from core.crawl_tracker import CrawlShutdownException
import logging

logger = logging.getLogger(__name__)

class Crawler(object):
    """
    Base class for a crawler that indexes documents into a Vectara corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        corpus_key (str): Key of the Vectara corpus to index to.
        api_key (str): API key to use for indexing into Vectara
    """

    def __init__(
        self,
        cfg: OmegaConf,
        endpoint: str,
        corpus_key: str,
        api_key: str,
    ) -> None:
        self.cfg: DictConfig = DictConfig(cfg)
        self.indexer = Indexer(cfg, endpoint, corpus_key, api_key)
        self.verbose = cfg.vectara.get("verbose", False)
        self.tracker = None  # Set by ingest.py after instantiation
        self.shutdown_requested = False  # Set by signal handler

    def check_shutdown(self):
        """Raise CrawlShutdownException if shutdown was requested."""
        if self.shutdown_requested:
            raise CrawlShutdownException("Graceful shutdown requested")
        if self.tracker:
            self.tracker.check_shutdown()

    def __del__(self):
        """Cleanup indexer and tracker resources when crawler is destroyed"""
        if hasattr(self, 'tracker') and self.tracker:
            try:
                self.tracker.close()
            except Exception as e:
                logger.debug(f"Error during tracker cleanup: {e}")
        if hasattr(self, 'indexer'):
            try:
                logger.debug("Cleaning up indexer resources in Crawler destructor")
                self.indexer.cleanup()
            except Exception as e:
                logger.debug(f"Error during indexer cleanup: {e}")
