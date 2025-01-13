import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.models import generate

class ContextualChunker():
    def __init__(self, model_name: str, model_api_key: str, whole_document: str):
        self.model_name = model_name
        self.model_api_key = model_api_key
        self.whole_document = whole_document

    def transform(self, chunk: str) -> str:
        prompt = f"""
            Here is the content of the whole document:
            <document>
            {self.whole_document}
            </document>
            Here is the chunk:
            <chunk>
            {chunk}
            </chunk>
            Please provide a short, succinct context to situate this chunk within the overall document to improve search retrieval. 
            Respond only with the context, don't include text of the originl chunk.
            """
        system_prompt = "You are a helpful assistant tasked with contextualizing text in a larger document."
        try:
            context = generate(system_prompt, prompt, self.model_name, self.model_api_key)
            return chunk + "\n" + context
        except Exception as e:
            logging.info(f"Failed to summarize table text: {e}")
            return ""

    def parallel_transform(self, texts, max_workers=None):
        """
        Transforms a list of text segments in parallel using the provided ContextualChunker instance.

        Args:
            texts (List[str]): List of text segments to process.
            max_workers (int, optional): The maximum number of threads to use. Defaults to None, which lets ThreadPoolExecutor decide.
        
        Returns:
            List[str]: The list of transformed text segments.
        """
        results = [None] * len(texts)  # Placeholder for transformed texts
        
        # Using ThreadPoolExecutor to parallelize cc.transform calls
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for all text segments along with their indices
            future_to_index = {executor.submit(self.transform, text): idx for idx, text in enumerate(texts)}
            
            # Collect results as they complete
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    # Handle exceptions if needed; for now, we just log them and leave that index as None
                    logging.error(f"Error transforming text at index {idx}: {e}")
        
        return results
