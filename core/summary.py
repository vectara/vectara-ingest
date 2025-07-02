import base64, logging

from PIL import Image

from typing import Set, Optional, Tuple
import base64
import logging
from omegaconf import OmegaConf

from PIL import Image, UnidentifiedImageError
from io import BytesIO
import cairosvg

from core.models import generate, generate_image_summary

def _get_image_shape(data_b64: str) -> Optional[Tuple[int, int]]:
    """
    Decode a base64 image and return its (width, height).
    Supports raster formats (via Pillow) and SVG (via CairoSVG).
    """
    try:
        data = base64.b64decode(data_b64)
    except Exception as e:
        logging.warning(f"Base64 decode failed: {e}")
        return None

    # First, try to open as a standard raster image (PNG, JPEG, etc.)
    try:
        with Image.open(BytesIO(data)) as img:
            return img.size
    except (UnidentifiedImageError, OSError):
        # If it's not a standard raster image, it might be an SVG.
        pass

    # Next, try to process as an SVG
    try:
        # Render SVG to PNG in memory and get dimensions from the result
        png_data = cairosvg.svg2png(bytestring=data)
        with Image.open(BytesIO(png_data)) as img:
            return img.size
    except Exception:
        # If cairosvg fails, it's not a valid SVG or raster image we can handle.
        logging.info("Data is not a valid raster image or SVG.")
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

    def _load_image_b64(self, image_path: str, image_url: str) -> Optional[str]:
        """
        Load image from path and return a base64-encoded PNG payload.
        SVGs are rasterized; others are read directly.
        """
        ext = image_url.lower().rsplit('.', 1)[-1]
        try:
            if ext == 'svg':
                # Convert SVG to PNG using cairosvg
                logging.info(f"Converting SVG {image_path} to PNG using cairosvg")
                png_bytes = cairosvg.svg2png(url=image_path)
                return base64.b64encode(png_bytes).decode('utf-8')
            else:
                # Read raster formats
                with open(image_path, 'rb') as f:
                    return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logging.error(f"Failed to load image {image_path}: {e}")
            return None
            
    def summarize_image(
            self, 
            image_path: str, 
            image_url: str, 
            previous_text: Optional[str] = None
    ) -> Optional[str]:
        """
        Summarize the image at the given path.
        Returns a descriptive paragraph or None if summarization fails.
        """
        content_b64 = self._load_image_b64(image_path, image_url)
        if not content_b64:
            return None

        shape = _get_image_shape(content_b64)
        if not shape or min(shape) < 10:
            logging.info(f"Image too small or invalid to summarize: {image_url}")
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
            return generate_image_summary(
                self.cfg,
                prompt,
                content_b64,
                self.image_model_config
            )
        except Exception as e:
            logging.error(f"Image summary generation failed for {image_url}: {e}")
            return None

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
