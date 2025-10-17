from omegaconf import OmegaConf, DictConfig
from core.indexer import Indexer
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
    
    def __del__(self):
        """Cleanup indexer resources when crawler is destroyed"""
        if hasattr(self, 'indexer'):
            try:
                logger.debug("Cleaning up indexer resources in Crawler destructor")
                self.indexer.cleanup()
            except Exception as e:
                # Ignore errors during cleanup to prevent issues during shutdown
                logger.debug(f"Error during indexer cleanup: {e}")
