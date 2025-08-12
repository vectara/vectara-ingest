import os
import logging

from datetime import datetime
import tempfile
import traceback

from io import StringIO
from typing import Dict, List

from dataclasses import asdict
from urllib.parse import urlparse

from sec_downloader import Downloader
from sec_downloader.types import RequestedFilings

from omegaconf import OmegaConf
from slugify import slugify
import pandas as pd

import ray
import psutil

from core.crawler import Crawler
from core.utils import (
    create_session_with_retries,
    configure_session_for_ssl,
    setup_logging,
)
from core.indexer import Indexer

logger = logging.getLogger(__name__)

COMPANY = "MyCompany"
EMAIL = "me@mycompany.com"


def get_headers() -> Dict[str, str]:
    """
    Get a set of headers to use for HTTP requests.
    """
    headers = {
        "User-Agent": f"{COMPANY} {EMAIL}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    return headers


class EdgarWorker():
    def __init__(self, indexer: Indexer, crawler: Crawler):
        self.crawler = crawler
        self.indexer = indexer

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, file_path: str, url: str, metadata: dict):
        try:
            succeeded = self.indexer.index_file(file_path, uri=url, metadata=metadata)
            if succeeded:
                ticker = metadata.get("ticker", "unknown ticker")
                year = metadata.get("year", "unknown year")
                filing_type = metadata.get("filing_type", "unknown filing type")
                logger.info(f"Indexing succeeded for url {url} ({ticker}, {year}, {filing_type})")
            else:
                logger.warning(f"Indexing failed for url {url}")
        except Exception as e:
            logger.error(
                f"Error while indexing {file_path}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        return 0


def get_filings(
    folder_name: str,
    ticker: str,
    start_date_str: str,
    end_date_str: str,
    filing_type: str = "10-K",
) -> List[Dict[str, str]]:
    dl = Downloader(COMPANY, EMAIL)

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    metadatas = dl.get_filing_metadatas(
        RequestedFilings(ticker_or_cik=ticker, form_type=filing_type, limit=None)
    )
    filings = [
        asdict(m)
        for m in metadatas
        if m.report_date and start_date <= datetime.strptime(m.report_date, "%Y-%m-%d") <= end_date
    ]

    for filing in filings:
        html = dl.download_filing(url=filing["primary_doc_url"]).decode()
        url = filing["primary_doc_url"]
        parsed_url = urlparse(url)
        extension = os.path.splitext(parsed_url.path)[1]
        fname = os.path.join(folder_name, slugify(url) + extension)
        with open(fname, "wt") as f:
            f.write(html)
        filing["file_path"] = fname

    return filings


class EdgarCrawler(Crawler):

    def __init__(
        self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str
    ) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.tickers = self.cfg.edgar_crawler.tickers
        self.start_date = self.cfg.edgar_crawler.start_date
        self.end_date = self.cfg.edgar_crawler.end_date
        self.filing_types = self.cfg.edgar_crawler.get(
            "filing_types", ["10-K", "10-Q", "8-K", "DEF 14A"]
        )

        # build mapping of ticker to cik
        url = "https://www.sec.gov/include/ticker.txt"
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.edgar_crawler)
        response = self.session.get(url, headers=get_headers())
        response.raise_for_status()
        data = StringIO(response.text)
        df = pd.read_csv(data, sep="\t", names=["ticker", "cik"], dtype=str)
        self.ticker_dict = dict(zip(df.ticker.map(lambda x: str(x).upper()), df.cik))

    def crawl(self) -> None:

        ray_workers = self.cfg.edgar_crawler.get(
            "ray_workers", 0
        )  # -1: use ray with ALL cores, 0: dont use ray
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)

        for ticker in self.tickers:
            logger.info(f"Processing ticker {ticker}")
            filings_to_process = []
            folder = tempfile.TemporaryDirectory(prefix="edgar-")
            for filing_type in self.filing_types:
                filings = get_filings(
                    folder.name, ticker, self.start_date, self.end_date, filing_type
                )
                logger.info(
                    f"downloaded {len(filings)} {filing_type}s for company with ticker {ticker}"
                )

                # no more filings in search universe
                if len(filings) == 0:
                    logger.info(
                        f"For {ticker}, no filings found in search universe ({filing_type})"
                    )
                    continue

                for filing in filings:
                    url = filing["primary_doc_url"]
                    title = ticker + "-" + filing["report_date"] + "-" + filing_type
                    metadata = {
                        "source": "edgar",
                        "url": url,
                        "title": title,
                        "ticker": ticker,
                        "company": filing["company_name"],
                        "filing_type": filing_type,
                        "date": filing["report_date"],
                        "year": int(
                            datetime.strptime(filing["report_date"], "%Y-%m-%d").year
                        ),
                    }
                    filings_to_process.append(
                        (filing["file_path"], url, title, metadata)
                    )

            logger.info(
                f"Processing {len(filings_to_process)} overall files "
                f"for company with ticker {ticker}"
            )
            if ray_workers > 0:
                self.indexer.p = self.indexer.browser = None
                actors = [
                    ray.remote(EdgarWorker).remote(self.indexer, self)
                    for _ in range(ray_workers)
                ]
                for a in actors:
                    a.setup.remote()
                pool = ray.util.ActorPool(actors)
                _ = list(
                    pool.map(
                        lambda a, u: a.process.remote(u[0], u[1], u[3]),
                        filings_to_process,
                    )
                )
            else:
                crawl_worker = EdgarWorker(self.indexer, self)
                for inx, tup in enumerate(filings_to_process):
                    if inx % 100 == 0:
                        logger.info(
                            f"Crawling URL number {inx+1} out of {len(filings_to_process)}"
                        )
                    file_path, url, title, file_metadata = tup
                    crawl_worker.process(file_path, url, file_metadata)

            folder.cleanup()
