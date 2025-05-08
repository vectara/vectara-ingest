from typing import Set
import os
import json
import base64
import logging
from omegaconf import OmegaConf

from PIL import Image
from io import BytesIO
import cairosvg

from core.models import generate, generate_image_summary

def _get_image_shape(content: str) -> tuple:
    """
    Given a base64-encoded image content string, return the image shape as (width, height).
    """
    try:
        img_data = base64.b64decode(content)
        img = Image.open(BytesIO(img_data))
        return img.size  # (width, height)
    except (IOError, OSError, ValueError) as e:
        logging.info(f"Skipping summarization: not a valid image ({e})")
        return None

def get_attributes_from_text(cfg: OmegaConf, text: str, metadata_questions: list[dict], model_config: dict) -> Set[str]:
    """
    Given a text string, ask GPT-4o to answer a set of questions from the text
    Returns a dictionary of question/answer pairs.
    """
    system_prompt = "You are a helpful assistant tasked with answering questions from text."
    prompt = f"""
        Here is text: {text}.
        Here is a list of attribute/question pairs:
    """
    for attr,question in metadata_questions.items():
        prompt += f"- {attr}: {question}\n"
    prompt += "Your task is retrieve the value of each attribute by answering the provided question, based on the text."
    prompt += "Your response should be as concise and accurate as possible. Prioritize 1-2 word responses."
    prompt += "Your response should be as a dictionary of attribute/value pairs in JSON format, and include only the JSON output without any additional text."
    logging.info(f"get_attributes_from_text() - Calling generate")
    res = generate(cfg, system_prompt, prompt, model_config)
    if res.strip().startswith("```json"):
        res = res.strip().removeprefix("```json").removesuffix("```")
    return json.loads(res)

class ImageSummarizer():
    def __init__(self, cfg: OmegaConf, image_model_config: dict):
        self.image_model_config = image_model_config
        self.cfg = cfg

    def get_image_content_for_summarization(self, image_path: str):
        
        orig_image_path = image_path
        if orig_image_path.lower().endswith(".svg"):
            logging.info(f"Converting svg image ({image_path}) to png for summarization")
            new_image_path = image_path.replace(".svg", ".png")
            cairosvg.svg2png(url=image_path, write_to=new_image_path, dpi=300)
            image_path = new_image_path

        content = None
        with open(image_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        if orig_image_path.lower().endswith(".svg"):
            try:
                os.remove(orig_image_path)
            except FileNotFoundError:
                logging.warning(f"File '{orig_image_path}' not found.")
            except Exception as e:
                logging.warning(f"An error occurred: {e}")

        return content

    def summarize_image(self, image_path: str, image_url: str, previous_text: str = None):
        content = self.get_image_content_for_summarization(image_path)        
        shape = _get_image_shape(content)
        if not shape:
             logging.info(f"Image too small to summarize ({image_url})")
             return None
        width, height = shape
        if width<10 or height<10:
            logging.info(f"Image too small to summarize ({image_url})")
            return None

        prompt = """
            Analyze all the details in this image, including any diagrams, graphs, or visual data representations. 
            Your task is to provide a comprehensive description of the image with as much detail as possible.
            Your response should be a paragraph without headings and include:
            - A detailed description of the main focus or subject of the image.
            - For any diagrams or graphs: what information they convey, a detailed description of the data, and any observed trends or conclusions that can be drawn.
            - Any other detail or information that a human observer would find useful or relevant.
            - Respond in complete sentences, and aim to provide a comprehensive and informative response.
            - Any specific text that is shown in the image (with context).
            - For any schemas, or flowcharts describe them in a way that a human reading your description could recreate the diagram.
            If you are unable to summarize it, respond with an empty string. Do not respond with "I can't do that" or similar.
        """
        if previous_text:
            prompt += f"The image came immediately following this text: '{previous_text}'"
        try:
            summary = generate_image_summary(self.cfg, prompt, content, self.image_model_config)
            return summary
        except Exception as e:
            logging.info(f"Failed to summarize image ({image_url}): {e}")
            return ""

class TableSummarizer():
    def __init__(self, cfg: OmegaConf, table_model_config: dict):
        self.table_model_config = table_model_config
        self.cfg = cfg

    def summarize_table_text(self, text: str):
        prompt = f"""
            Adopt the perspective of a data analyst.
            Summarize the key results reported in this table (in markdown format) without omitting critical details.
            Make sure your summary is concise, informative and comprehensive.
            Use clear and professional language, ensuring all descriptions are tied explicitly to the data.
            Your response should be without headings, and in text (not markdown).
            Your response should include contextual information, so that it is identified as relevant in search results.
            Review your response for accuracy, coherence, and no hallucinations.
            Here is the table: {text}
        """
        try:
            system_prompt = "You are a helpful assistant tasked with summarizing data tables. Each table is represented in markdown format."
            summary = generate(self.cfg, system_prompt, prompt, self.table_model_config)
            return summary
        except Exception as e:
            import traceback
            logging.info(f"Failed to summarize table text: {e}, traceback: {traceback.format_exc()}")
            return None
