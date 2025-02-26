import logging
import os
import json
from bs4 import BeautifulSoup
import xmltodict
from datetime import datetime, timedelta
from typing import Set, List, Any
from core.utils import html_to_text, create_session_with_retries, RateLimiter, configure_session_for_ssl
from core.crawler import Crawler

from omegaconf import OmegaConf
from Bio import Entrez

def get_top_n_papers(topic: str, n: int, email: str) -> Any:
    """
    Get the top n papers for a given topic from PMC
    """
    Entrez.email = email
    search_results = Entrez.read(
        Entrez.esearch(
            db="pmc",
            term=topic,
            sort="relevance",
            retmax=n,
            usehistory="y",
        )
    )
    id_list = search_results["IdList"]
    return id_list


class PmcCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.site_urls: Set[str] = set()
        self.crawled_pmc_ids: Set[str] = set()
        self.rate_limiter = RateLimiter(self.cfg.pmc_crawler.get("num_per_second", 3))
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.pmc_crawler)

    def index_papers_by_topic(self, topic: str, n_papers: int) -> None:
        """
        Index the top n papers for a given topic
        """
        email = "crawler@vectara.com"
        papers = list(set(get_top_n_papers(topic, n_papers, email)))
        if len(papers) > 0:
            logging.info(f"Found {len(papers)} papers for topic {topic}, now indexing...")
        else:
            logging.info(f"Found no papers for topic {topic}")
            return

        # index the papers
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        for i, pmc_id in enumerate(papers):
            if i%100 == 0:
                logging.info(f"Indexed {i} papers so far for topic {topic}")
            if pmc_id in self.crawled_pmc_ids:
                continue

            params = {"db": "pmc", "id": pmc_id, "retmode": "xml", "tool": "python_script", "email": email}
            try:
                with self.rate_limiter:
                    response = self.session.get(base_url, params=params)
            except Exception as e:
                logging.info(f"Failed to download paper {pmc_id} due to error {e}, skipping")
                continue
            if response.status_code != 200:
                logging.info(f"Failed to download paper {pmc_id}, skipping")
                continue

            soup = BeautifulSoup(response.text, "xml")

            # Extract the title
            title_element = soup.find("article-title")
            if title_element:
                title = title_element.get_text(strip=True)
            else:
                title = "Title not found"
    
            # Extract the publication date
            pub_date_soup = soup.find("pub-date")
            if pub_date_soup is not None:
                year = pub_date_soup.find("year")
                if year is None:
                    year_text = '1970'
                else:
                    year_text = str(year.text)
                month = pub_date_soup.find("month")
                if month is None:
                    month_text = '1'
                else:
                    month_text = str(month.text)
                day = pub_date_soup.find("day")
                if day is None:
                    day_text = '1'
                else:
                    day_text = str(day.text)

                try:
                    pub_date = f"{year_text}-{month_text}-{day_text}"
                except Exception as e:
                    pub_date = 'unknown'
            else:
                pub_date = "Publication date not found"
            
            self.crawled_pmc_ids.add(pmc_id)
            logging.info(f"Indexing paper {pmc_id} with publication date {pub_date} and title '{title}'")
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/pdf/"
            
            self.indexer.index_url(pdf_url, metadata={'url': pdf_url, 'source': 'pmc', 'title': title, "publicationDate": pub_date})

    def _get_xml_dict(self) -> Any:
        days_back = 1
        max_days = 30
        while (days_back <= max_days):
            xml_date = (datetime.now() - timedelta(days = days_back)).strftime("%Y-%m-%d")
            url = f'https://medlineplus.gov/xml/mplus_topics_{xml_date}.xml'
            response = self.session.get(url)
            if response.status_code == 200:
                break
            days_back += 1
        if days_back == max_days:
            logging.info(f"Could not find medline plus topics after checkint last {max_days} days")
            return {}

        logging.info(f"Using MedlinePlus topics from {xml_date}")        
        url = f'https://medlineplus.gov/xml/mplus_topics_{xml_date}.xml'
        response = self.session.get(url)
        response.raise_for_status()
        xml_dict = xmltodict.parse(response.text)
        return xml_dict

    def index_medline_plus(self, topics: List[str]) -> None:
        xml_dict = self._get_xml_dict()
        logging.info(f"Indexing {xml_dict['health-topics']['@total']} health topics from MedlinePlus")    

        for ht in xml_dict['health-topics']['health-topic']:
            title = ht['@title']
            all_names = [title.lower()]
            if 'also-called' in ht:
                synonyms = ht['also-called']
                if type(synonyms)==list:
                    all_names += [x.lower() for x in synonyms]
                else:
                    all_names += [synonyms.lower()]
            if not any([t.lower() in all_names for t in topics]):
                logging.info(f"Skipping {title} because it is not in our list of topics to crawl")
                continue

            medline_id = ht['@id']
            topic_url = ht['@url']
            date_created = ht['@date-created']
            summary = html_to_text(ht['full-summary'])
            meta_desc = ht['@meta-desc']
            document = {
                "id": f'medline-plus-{medline_id}',
                "title": title,
                "description": f'medline information for {title}',
                "metadata": {
                    "url": topic_url,
                    "publicationDate": date_created,
                    "source": "pmc",
                },
                "sections": [
                    {
                        'text': meta_desc
                    },
                    {
                        'text': summary
                    }
                ]
            }
            logging.info(f"Indexing data about {title}")
            succeeded = self.indexer.index_document(document)
            if not succeeded:
                logging.info(f"Failed to index document with title {title}")
                continue
            for site in ht['site']:
                site_title = site['@title']
                site_url = site['@url']
                if site_url in self.site_urls:
                    continue
                else:
                    self.site_urls.add(site_url)
                with self.rate_limiter:
                    succeeded = self.indexer.index_url(site_url, metadata={'url': site_url, 'source': 'medline_plus', 'title': site_title})

    def crawl(self) -> None:
        folder = 'papers'
        os.makedirs(folder, exist_ok=True)

        topics = self.cfg.pmc_crawler.topics
        n_papers = self.cfg.pmc_crawler.n_papers

        self.index_medline_plus(topics)
        for topic in topics:
            self.index_papers_by_topic(topic, n_papers)
