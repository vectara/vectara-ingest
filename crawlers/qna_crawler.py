import pandas as pd
from core.crawler import Crawler
import os

class QnaCrawler(Crawler):

    def crawl(self) -> None:
        file_path = '/home/vectara/data/file'
        question_column = self.cfg.qna_crawler.get("question_column", None)
        answer_column = self.cfg.qna_crawler.get("answer_column", None)
        if question_column is None or answer_column is None:
            raise Exception("Question or Answer column not found in config file")

        sep = self.cfg.qna_crawler.get("separator", ",")
        all_columns = [question_column, answer_column]
        df = pd.read_csv(file_path, usecols=all_columns, sep=sep)

        if question_column not in df.columns:
            raise Exception("Question column not found in file")
        if answer_column not in df.columns:
            raise Exception("Answer column not found in file")

        for question, answer in zip(df[question_column], df[answer_column]):
            self.indexer.index_segments(
                doc_id = os.urandom(8).hex(),
                texts = [f"Question: {question}\nAnswer: {answer}"],
                doc_metadata = {'source': 'qna'}
            )
