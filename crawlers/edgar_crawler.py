import os
import logging

from omegaconf import OmegaConf
from slugify import slugify

import pandas as pd
from datetime import datetime

from sec_downloader import Downloader
from sec_downloader.types import RequestedFilings

from core.crawler import Crawler
from core.utils import create_session_with_retries, RateLimiter, ensure_empty_folder, configure_session_for_ssl

from io import StringIO
from typing import Dict, List

from dataclasses import asdict
from urllib.parse import urlparse

company = "MyCompany"
email = "me@mycompany.com"
    
def get_headers() -> Dict[str, str]:
    """
    Get a set of headers to use for HTTP requests.
    """
    headers = {
        "User-Agent": f"{company} {email}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8" 
    }
    return headers


def get_filings(ticker: str, start_date_str: str, end_date_str: str, filing_type: str = "10-K") -> List[Dict[str, str]]:
    folder = 'edgar_dl'
    ensure_empty_folder(folder)
    dl = Downloader(company, email)

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')    

    metadatas = dl.get_filing_metadatas(
        RequestedFilings(ticker_or_cik=ticker, form_type=filing_type, limit=20)
    )
    filings = [asdict(m) for m in metadatas 
               if start_date <= datetime.strptime(m.report_date, '%Y-%m-%d') <= end_date]

    for filing in filings:
        html = dl.download_filing(url=filing['primary_doc_url']).decode()
        url = filing['primary_doc_url']
        parsed_url = urlparse(url)
        extension = os.path.splitext(parsed_url.path)[1]
        fname = os.path.join(folder, slugify(url) + extension)
        with open(fname, 'wt') as f:
            f.write(html)
        filing['file_path'] = fname

    return filings

class EdgarCrawler(Crawler):
    
    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.tickers = self.cfg.edgar_crawler.tickers
        self.start_date = self.cfg.edgar_crawler.start_date
        self.end_date = self.cfg.edgar_crawler.end_date
        self.num_per_second = self.cfg.edgar_crawler.get("num_per_second", 1)
        self.filing_types = self.cfg.edgar_crawler.get("filing_types", ['10-K'])
        self.rate_limiter = RateLimiter(self.num_per_second)

        # build mapping of ticker to cik
        url = 'https://www.sec.gov/include/ticker.txt'
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.edgar_crawler)
        response = self.session.get(url, headers=get_headers())
        response.raise_for_status()
        data = StringIO(response.text)
        df = pd.read_csv(data, sep='\t', names=['ticker', 'cik'], dtype=str)
        self.ticker_dict = dict(zip(df.ticker.map(lambda x: str(x).upper()), df.cik))


    def crawl(self) -> None:
        for ticker in self.tickers:

            for filing_type in self.filing_types:
                logging.info(f"downloading {filing_type}s for company with ticker {ticker}")
                filings = get_filings(ticker, self.start_date, self.end_date, filing_type)

                # no more filings in search universe
                if len(filings) == 0:
                    logging.info(f"For {ticker}, no filings found in search universe")
                    continue
                for filing in filings:
                    url = filing['primary_doc_url']
                    title = ticker + '-' + filing['report_date'] + '-' + filing_type
                    logging.info(f"indexing document {url}")
                    metadata = {
                        'source': 'edgar', 'url': url, 'title': title, 'ticker': ticker, 
                        'company': filing['company_name'], 'filing_type': filing_type,
                        'date': filing['report_date'], 
                        'year': int(datetime.strptime(filing['report_date'], '%Y-%m-%d').year)
                    }

                    succeeded = self.indexer.index_file(filing['file_path'], uri=url, metadata=metadata)
                    if not succeeded:
                        logging.info(f"Indexing failed for url {url}")


