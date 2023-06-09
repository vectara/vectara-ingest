import logging
from omegaconf import OmegaConf
import json
import requests
import re
from datetime import datetime

from core.crawler import Crawler

def is_date_in_range(datetime_str, start_year, end_year):
    dt = datetime.strptime(datetime_str.split(' ')[0], '%Y-%m-%d')
    return start_year <= dt.year <= end_year

def camelCase_to_words(s: str):
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', s).lower()

# Crawler for financial information using the financialmodelingprep.com service
# To use this crawler you have to have an fmp API_key in your secrets.toml profile
class FmpCrawler(Crawler):
    
    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.tickers = cfg.fmp_crawler.tickers
        self.start_year = int(cfg.fmp_crawler.start_year)
        self.end_year = int(cfg.fmp_crawler.end_year)
        self.api_key = cfg.fmp_crawler.fmp_api_key

    def index_doc(self, document):
        try:
            succeeded = self.indexer.index_document(document)
            if succeeded:
                logging.info(f"Indexed {document['documentId']}")
            else:
                logging.info(f"Error indexing issue {document['documentId']}")
            return succeeded
        except Exception as e:
            logging.info(f"Error during indexing of {document['documentId']}: {e}")
            return False

    def crawl(self):
        base_url = 'https://financialmodelingprep.com'
        keys_to_ignore = ['fillingDate', 'date', 'symbol', 'cik', 'acceptedDate', 'reportedCurrency', 'link', 'finalLink']
        for ticker in self.tickers:
            # get profile
            url = f'{base_url}/api/v3/profile/{ticker}?apikey={self.api_key}'
            try:
                response = requests.get(url)
            except Exception as e:
                logging.info(f"Error getting transcript for {ticker} quarter {quarter} of {year}: {e}")
                continue
            if response.status_code == 200:
                data = response.json()
                company_name = data[0]['companyName']
                logging.info(f"Processing {company_name}")
            else:
                logging.info(f"Can't get company profile for {ticker} - skipping")
                continue

            # index 10-K for ticker in date range
            url = f'{base_url}/api/v3/sec_filings/{ticker}?type=10-K&page=0&apikey={self.api_key}'
            filings = requests.get(url).json()
            for year in range(self.start_year, self.end_year+1):
                url = f'{base_url}/api/v4/financial-reports-json?symbol={ticker}&year={year}&period=FY&apikey={self.api_key}'
                try:
                    response = requests.get(url)
                except Exception as e:
                    logging.info(f"Error getting transcript for {ticker} quarter {quarter} of {year}: {e}")
                    continue
                if response.status_code == 200:
                    data = response.json()
                    doc_title = f"10-K for {company_name} from {year}"
                    rel_filings = [f for f in filings if f['acceptedDate'][:4] == str(year)]
                    url = rel_filings[0]['link'] if len(rel_filings)>0 else None
                    metadata = {'source': 'finsearch', 'title': doc_title, 'ticker': ticker, 'compnay name': company_name, 'year': year, 'type': '10-K', 'url': url}
                    document = {
                        "documentId": f"10-K-{company_name}-{year}",
                        "title": doc_title,
                        "metadataJson": json.dumps(metadata),
                        "section": []
                    }
                    for key in data.keys():
                        if type(data[key])==str:
                            continue
                        for item_dict in data[key]:
                            for title, values in item_dict.items():
                                values = [v for v in values if v and type(v)==str and len(v)>=10]
                                if len(values)>0 and len(' '.join(values))>100:
                                    document['section'].append({'title': f'{key} - {title}', 'text': '\n'.join(values)})
                    self.index_doc(document)


            # income statements
            logging.info(f"Ingesting income statements for {company_name}")
            url = f'{base_url}/api/v3/income-statement/{ticker}?limit=120&apikey={self.api_key}'
            statements = requests.get(url).json()
            for statement in statements:
                date = statement['fillingDate']
                if is_date_in_range(date, self.start_year, self.end_year):
                    text_pieces = [f'Income statement for {company_name} on date {date}.'] + \
                                  [f"{camelCase_to_words(key)}: {value}" for key, value in statement.items() if key not in keys_to_ignore]
                    title = f"Income statement for {company_name}, on {date}"
                    metadata = {'source': 'finsearch', 'title': title, 'ticker': ticker, 'compnay name': company_name, 'date': date, 'type': 'income-statement'}
                    document = {
                        "documentId": f"income-statment-{company_name}-{date}",
                        "title": title,
                        "metadataJson": json.dumps(metadata),
                        "section": [
                            {
                                'text': '\n'.join(text_pieces)
                            }
                        ]
                    }
                    self.index_doc(document)

            # balance sheet statenents
            logging.info(f"Ingesting balance sheet statements for {company_name}")
            url = f'{base_url}/api/v3/balance-sheet-statement/{ticker}?limit=120&apikey={self.api_key}'
            statements = requests.get(url).json()
            for statement in statements:
                date = statement['fillingDate']
                if is_date_in_range(date, self.start_year, self.end_year):
                    text_pieces = [f'Balance sheet statement for {company_name} on date {date}.'] + \
                                  [f"{camelCase_to_words(key)}: {value}" for key, value in statement.items() if key not in keys_to_ignore]
                    title = f"Balance sheet statement for {company_name}, on {date}"
                    metadata = {'source': 'finsearch', 'title': title, 'ticker': ticker, 'compnay name': company_name, 'date': date, 'type': 'balance-sheet'}
                    document = {
                        "documentId": f"balance-sheet-statment-{company_name}-{date}",
                        "title": title,
                        "metadataJson": json.dumps(metadata),
                        "section": [
                            {
                                'text': '\n'.join(text_pieces)
                            }
                        ]
                    }
                    self.index_doc(document)

            # Index earnings call transcript
            logging.info(f"Getting transcripts")
            for year in range(self.start_year, self.end_year+1):
                for quarter in range(1, 5):
                    url = f'{base_url}/api/v3/earning_call_transcript/{ticker}?quarter={quarter}&year={year}&apikey={self.api_key}'
                    try:
                        response = requests.get(url)
                    except Exception as e:
                        logging.info(f"Error getting transcript for {company_name} quarter {quarter} of {year}: {e}")
                        continue
                    if response.status_code == 200:
                        for transcript in response.json():
                            title = f"Earnings call transcript for {company_name}, quarter {quarter} of {year}"
                            metadata = {'source': 'finsearch', 'title': title, 'ticker': ticker, 'compnay name': company_name, 'year': year, 'quarter': quarter, 'type': 'transcript'}
                            document = {
                                "documentId": f"transcript-{company_name}-{year}-{quarter}",
                                "title": title,
                                "metadataJson": json.dumps(metadata),
                                "section": [
                                    {
                                        'text': transcript['content']
                                    }
                                ]
                            }
                            self.index_doc(document)
