import logging
import os
from Bio import Entrez
import json
from lxml import etree
from ratelimiter import RateLimiter
import requests

from crawler import Crawler

def get_top_n_papers(topic: str, n: int, email: str):
    """
    Get the top n papers for a given topic from PMC
    """
    Entrez.email = email
    search_results = Entrez.read(
        Entrez.esearch(
            db="pmc",
            term=topic,
            retmax=n,
            usehistory="y",
        )
    )
    id_list = search_results["IdList"]    
    return id_list



class PmcCrawler(Crawler):

    def index_papers_by_topic(self, topic: str, n_papers: int):
        """
        Index the top n papers for a given topic
        """
        email = "crawler@vectara.com"
        papers = list(set(get_top_n_papers(topic, n_papers, email)))
        logging.info(f"Found {len(papers)} papers for topic {topic}, now indexing...")

        # index the papers
        rate_limiter = RateLimiter(max_calls=3, period=1)
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        for i, pmc_id in enumerate(papers):
            if i%100 == 0:
                logging.info(f"Indexed {i} papers so far for topic {topic}")
            params = {"db": "pmc", "id": pmc_id, "retmode": "xml", "tool": "python_script", "email": email}
            try:
                with rate_limiter:
                    response = requests.get(base_url, params=params)
            except Exception as e:
                logging.info(f"Failed to download paper {pmc_id} due to error {e}, skipping")
                continue
            if response.status_code != 200:
                logging.info(f"Failed to download paper {pmc_id}, skipping")
                continue

            xml_data = response.text
            root = etree.fromstring(xml_data)

            # Extract the title
            title = root.find(".//article-title")
            if title is not None:
                title = title.text
            else:
                title = "Title not found"

            # Extract the publication date
            pub_date = root.find(".//pub-date")
            if pub_date is not None:
                year = pub_date.find("year")
                month = pub_date.find("month")
                day = pub_date.find("day")
                try:
                    pub_date = f"{year.text}-{month.text}-{day.text}"
                except Exception as e:
                    if year is not None:
                        pub_date = year.text
                    else:
                        pub_date = 'unknown'
            else:
                pub_date = "Publication date not found"

            logging.info(f"Indexing paper {pmc_id} with publication date {pub_date} and title '{title}'")

            # Index the page into Vectara
            document = {
                "documentId": pmc_id,
                "title": title,
                "description": "",
                "metadataJson": json.dumps({
                    "url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/",
                    "publicationDate": pub_date,
                    "source": "pmc",
                }),
                "section": []
            }
            for paragraph in root.findall(".//body//p"):
                document['section'].append({
                    "text": paragraph.text,
                })

            _, succeeded = self.indexer.index_document(document)
            if not succeeded:
                logging.info(f"Failed to index document {pmc_id}")

    def crawl(self):
        folder = 'papers'
        os.makedirs(folder, exist_ok=True)

        topics = self.cfg.pmc_crawler.topics
        n_papers = self.cfg.pmc_crawler.n_papers
        for topic in topics:
            self.index_papers_by_topic(topic, n_papers)
