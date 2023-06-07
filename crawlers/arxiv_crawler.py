import requests
import logging
from core.crawler import Crawler
import arxiv

class ArxivCrawler(Crawler):

    def get_citations(self, arxiv_id):
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

        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=5)
        self.session.mount('http://', adapter)

        query = "cat:cs.* AND " + ' AND '.join([f'all:{q}' for q in query_terms])
        search = arxiv.Search(
            query = query,
            max_results = n_papers*100,
            sort_by = arxiv.SortCriterion.Relevance
        )

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
    
        sorted_papers = sorted(papers, key=lambda x: x['citation_count'], reverse=True) 
        top_n = sorted_papers[:n_papers]

        # Index top papers
        for paper in top_n:
            url = paper['url'] + ".pdf"
            metadata = {'source': 'arxiv', 'title': paper['title'], 'abstract': paper['abstract'], 'url': paper['url'],
                        'published': str(paper['published']), 'citations': str(paper['citation_count'])}
            self.indexer.index_url(url, metadata=metadata)
