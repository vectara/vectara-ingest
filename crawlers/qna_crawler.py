import pandas as pd
from core.crawler import Crawler
from typing import List
import logging

class QnaCrawler(Crawler):

    def index_qna(self, doc_id: str, questions: List[str], answers: List[str]) -> None:
        texts = []
        titles = []
        for question, answer in zip(questions, answers):
            titles.append(f"Answer to '{question}'")
            texts.append(answer)
            
        self.indexer.index_segments(doc_id, texts=texts, titles=titles, metadatas=None, 
                                    doc_metadata = {'source': 'qna'})

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

        for inx, row in df.iterrows():
            self.index_qna(doc_id = f"question-answer pair {inx+1}", questions = [row[question_column]], answers = [row[answer_column]])
