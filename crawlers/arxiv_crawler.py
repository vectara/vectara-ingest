import logging
from core.crawler import Crawler
import arxiv
from core.utils import create_session_with_retries

class ArxivCrawler(Crawler):

    def get_citations(self, arxiv_id):
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


    def crawl(self):
        n_papers = self.cfg.arxiv_crawler.n_papers
        query_terms = self.cfg.arxiv_crawler.query_terms
        year = self.cfg.arxiv_crawler.start_year

        # setup requests session and mount adapter to retry requests
        self.session = create_session_with_retries()

        # define query for arxiv: search for the query in the "computer science" (cs.*) category
        # We pull 100x papers so that we can get citations and enough highly cited paper.
        query = "cat:cs.* AND " + ' AND '.join([f'all:{q}' for q in query_terms])
        search = arxiv.Search(
            query = query,
            max_results = n_papers*100,
            sort_by = arxiv.SortCriterion.Relevance
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

        # sort by citation count and get top n papers
        sorted_papers = sorted(papers, key=lambda x: x['citation_count'], reverse=True) 
        top_n = sorted_papers[:n_papers]

        # Index top papers selected in Vectara
        for paper in top_n:
            url = paper['url'] + ".pdf"
            metadata = {'source': 'arxiv', 'title': paper['title'], 'abstract': paper['abstract'], 'url': paper['url'],
                        'published': str(paper['published']), 'citations': str(paper['citation_count'])}
            self.indexer.index_url(url, metadata=metadata)
