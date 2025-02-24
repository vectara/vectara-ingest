import logging
import json

from typing import Dict, Any
from omegaconf import OmegaConf, DictConfig

from core.crawler import Crawler
from core.utils import create_session_with_retries, configure_session_for_ssl


# Crawler for financial information using the financialmodelingprep.com service
# To use this crawler you have to have an fmp API_key in your secrets.toml profile
class FmpCrawler(Crawler):
    
    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        '''
        Initialize the FmpCrawler
        '''
        super().__init__(cfg, endpoint, corpus_key, api_key)
        cfg_dict: DictConfig = DictConfig(cfg)
        self.tickers = cfg_dict.fmp_crawler.tickers
        self.start_year = int(cfg_dict.fmp_crawler.start_year)
        self.end_year = int(cfg_dict.fmp_crawler.end_year)
        self.api_key = cfg_dict.fmp_crawler.fmp_api_key
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.fmp_crawler)
        self.base_url = 'https://financialmodelingprep.com'

    def index_doc(self, document: Dict[str, Any]) -> bool:
        '''
        Index a document into the Vectara index
        '''
        try:
            succeeded = self.indexer.index_document(document)
            if succeeded:
                logging.info(f"Indexed {document['id']}")
            else:
                logging.info(f"Error indexing issue {document['id']}")
            return succeeded
        except Exception as e:
            logging.info(f"Error during indexing of {document['id']}: {e}")
            return False

    def index_10k(self, ticker: str, company_name: str, year: int) -> None:
        '''
        Index 10-Ks for a ticker in a given year range
        Args:
            ticker: The ticker symbol of the company
            company_name: The name of the company
            year: The year to get transcripts for
        '''
        url = f'{self.base_url}/api/v3/sec_filings/{ticker}?type=10-K&page=0&apikey={self.api_key}'
        filings = self.session.get(url).json()
        for year in range(self.start_year, self.end_year+1):
            url = f'{self.base_url}/api/v4/financial-reports-json?symbol={ticker}&year={year}&period=FY&apikey={self.api_key}'
            try:
                response = self.session.get(url)
            except Exception as e:
                logging.info(f"Error getting transcript for {ticker}: {e}")
                continue
            if response.status_code == 200:
                data = response.json()
                doc_title = f"10-K for {company_name} from {year}"
                rel_filings = [f for f in filings if f['acceptedDate'][:4] == str(year)]
                url = rel_filings[0]['finalLink'] if len(rel_filings)>0 else None
                metadata = {
                    'source': ticker.lower(), 'title': doc_title, 'ticker': ticker, 'company name': company_name, 'year': year, 
                    'type': 'filing', 'filing_type': '10-K', 'url': url
                }
                document: Dict[str, Any] = {
                    "id": f"10-K-{company_name}-{year}",
                    "title": doc_title,
                    "metadata": metadata,
                    "sections": []
                }
                for key in data.keys():
                    if isinstance(data[key], str):
                        continue
                    # data[key] is a list of dicts
                    for item_dict in data[key]:
                        for title, values in item_dict.items():
                            values = [v for v in values if v and isinstance(v, str) and len(v)>=50]
                            text = '\n'.join(values)
                            if len(values)>0 and len(text)>100:
                                document['sections'].append({'title': title, 'text': text})
                if len(document['sections'])>0:
                    self.index_doc(document)

    def index_call_transcripts(self, ticker: str, company_name: str, year: int) -> None:
        '''
        Index earnings call transcripts for a ticker in a given year range
        Args:
            ticker: The ticker symbol of the company
            company_name: The name of the company
            year: The year to get transcripts for
        '''
        for year in range(self.start_year, self.end_year+1):
            for quarter in range(1, 5):
                url = f'{self.base_url}/api/v3/earning_call_transcript/{ticker}?quarter={quarter}&year={year}&apikey={self.api_key}'
                try:
                    response = self.session.get(url)
                except Exception as e:
                    logging.info(f"Error getting transcript for {company_name} quarter {quarter} of {year}: {e}")
                    continue
                if response.status_code == 200:
                    for transcript in response.json():
                        title = f"Earnings call transcript for {company_name}, quarter {quarter} of {year}"
                        metadata = {
                            'source': ticker.lower(), 'title': title, 'ticker': ticker, 'company name': company_name, 
                            'year': year, 'quarter': quarter, 'type': 'transcript'
                        }
                        document = {
                            "id": f"transcript-{company_name}-{year}-{quarter}",
                            "title": title,
                            "metadata": metadata,
                            "sections": [
                                {
                                    'text': transcript['content']
                                }
                            ]
                        }
                        self.index_doc(document)
    
    def crawl(self) -> None:

        for ticker in self.tickers:
            # get profile
            url = f'{self.base_url}/api/v3/profile/{ticker}?apikey={self.api_key}'
            try:
                response = self.session.get(url)
            except Exception as e:
                logging.info(f"Error getting transcript for {ticker}: {e}")
                continue
            if response.status_code == 200:
                data = response.json()
                company_name = data[0]['companyName']
                logging.info(f"Processing {company_name}")
            else:
                logging.info(f"Can't get company profile for {ticker} - skipping")
                continue

            # index 10-K for ticker in date range
            if self.cfg.fmp_crawler.get("index_10k", True):
                logging.info("Getting 10-Ks and indexing content into Vectara")
                self.index_10k(ticker, company_name, self.start_year)

            # Index earnings call transcript
            if self.cfg.fmp_crawler.get("index_call_transcripts", True):
                logging.info("Getting call transcripts and indexing into Vectara")
                self.index_call_transcripts(ticker, company_name, self.start_year)

