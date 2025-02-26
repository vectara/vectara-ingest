import logging
from core.crawler import Crawler
import arxiv
from core.utils import create_session_with_retries, configure_session_for_ssl


def validate_category(category: str) -> bool:
    valid_categories = [
        "cs", "econ", "q-fin","stat",
        "math", "math-ph", "q-bio", "stat-mech",
        "physics", "astro-ph", "cond-mat", "gr-qc", "hep-ex", "hep-lat", "hep-ph", 
        "hep-th", "nucl-ex", "nucl-th", "physics-ao-ph", "physics-ao-pl", "physics-ao-po",
        "physics-ao-ps", "physics-app-ph",
        "quant-ph"
    ]
    return category in valid_categories

class ArxivCrawler(Crawler):

    def get_citations(self, arxiv_id: str) -> int:
        """
        Retrieves the number of citations for a given paper from Semantic Scholar API based on its arXiv ID.

        Parameters:
        arxiv_id (str): The arXiv ID of the paper.

        Returns:
        int: Number of citations if the paper exists and the request was successful, otherwise -1.
        If an exception occurs during the request, it also returns -1 and logs the exception.
        """
        base_url = "https://api.semanticscholar.org/v1/paper/arXiv:"
        arxiv_id = arxiv_id.split('v')[0]   # remove any 'v1' or 'v2', etc from the ending, if it exists

        try:
            response = self.session.get(base_url + arxiv_id)
            if response.status_code != 200:
                return -1
            paper_info = response.json()
        
            paper_id = paper_info.get('paperId')
            base_url = "https://api.semanticscholar.org/v1/paper/"
            response = self.session.get(base_url + paper_id)

            if response.status_code == 200:
                paper_info = response.json()
                n_citations = len(paper_info.get("citations"))
                return n_citations
            else:
                return -1

        except Exception as e:
            logging.info(f"Error parsing response from arxiv API: {e}, response={response.text}")
            return -1


    def crawl(self) -> None:
        n_papers = self.cfg.arxiv_crawler.n_papers
        query_terms = self.cfg.arxiv_crawler.query_terms
        year = self.cfg.arxiv_crawler.start_year
        category = self.cfg.arxiv_crawler.arxiv_category
        if not validate_category(category):
            logging.info(f"Invalid arxiv category: {category}, please check the config file")
            exit(1)

        # setup requests session and mount adapter to retry requests
        self.session = create_session_with_retries()
        configure_session_for_ssl(self.session, self.cfg.arxiv_crawler)

        # define query for arxiv: search for the query in the "computer science" (cs.*) category
        query = f"cat:{category}.* AND " + ' AND '.join([f'all:{q}' for q in query_terms])
        if self.cfg.arxiv_crawler.sort_by == 'citations':
            # for sort by n_citations We pull 100x papers so that we can get citations and enough highly cited paper.
            search = arxiv.Search(
                query = query,
                max_results = n_papers*100,
                sort_by = arxiv.SortCriterion.Relevance,
                sort_order = arxiv.SortOrder.Descending
            )
        else:
            search = arxiv.Search(
                query = query,
                max_results = n_papers,
                sort_by = arxiv.SortCriterion.submittedDate,
                sort_order = arxiv.SortOrder.Descending
            )

        # filter by publication year
        papers = []
        try:
            for result in search.results():
                date = result.published.date()
                if date.year < year:
                    continue
                id = result.entry_id.split('/')[-1]
                papers.append({
                    'id': result.entry_id,
                    'citation_count': self.get_citations(id),
                    'url': result.pdf_url,
                    'title': result.title,
                    'authors': result.authors,
                    'abstract': result.summary,
                    'published': str(date)
                })
        except Exception as e:
            logging.info(f"Exception {e}, we have {len(papers)} papers already, so will continue with indexing")

        if len(papers) == 0:
            logging.info(f"Found 0 papers for query: {query}, ignore crawl")
            return

        # sort by citation count and get top n papers
        if self.cfg.arxiv_crawler.sort_by == 'citations':
            sorted_papers = sorted(papers, key=lambda x: x['citation_count'], reverse=True) 
            top_n = sorted_papers[:n_papers]
        else:
            top_n = papers

        # Index top papers selected in Vectara
        for paper in top_n:
            url = paper['url'] + ".pdf"
            metadata = {'source': 'arxiv', 'title': paper['title'], 'abstract': paper['abstract'], 'url': paper['url'],
                        'published': str(paper['published']), 'citations': str(paper['citation_count'])}
            self.indexer.index_url(url, metadata=metadata)
