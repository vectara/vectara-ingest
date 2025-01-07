import logging
from openai import OpenAI

class ContextualChunker():
    def __init__(self, openai_api_key: str, whole_document: str):
        self.client = OpenAI(api_key=openai_api_key)
        self.whole_document = whole_document

    def transform(self, chunk: str) -> str:
        prompt = f"""
            <document>
            {self.whole_document}
            </document>
            Here is the chunk we want to situate within the whole document
            <chunk>
            {chunk}
            </chunk> 
            Please give a short succinct context to situate this chunk within the overall document for the purposes 
            of improving search retrieval of the chunk. Answer only with the succinct context and nothing else. 
            """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant tasked with contextualizing text in a larger document."},
                    {"role": "user", "content": prompt }
                ],
                temperature=0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.info(f"Failed to summarize table text: {e}")
            return ""
