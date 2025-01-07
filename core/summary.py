from typing import Set
import json
import base64
import logging

from PIL import Image
from io import BytesIO
from openai import OpenAI

def get_attributes_from_text(text: str, metadata_questions: list[dict], openai_api_key) -> Set[str]:
    """
    Given a text string, ask GPT-4o to answer a set of questions from the text
    Returns a dictionary of question/answer pairs.
    """
    prompt = f"""
        Here is text: {text}.
        Here is a list of attribute/question pairs:
    """
    for attr,question in metadata_questions.items():
        prompt += f"- {attr}: {question}\n"
    prompt += "Your task is retrieve the value of each attribute by answering the provided question, based on the text."
    prompt += "Your response should be as a dictionary of attribute/value pairs in JSON format."
    client = OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant tasked with answering questions from text."},
            {"role": "user", "content": prompt }
        ],
        temperature=0,
        max_tokens=4096,
    )
    res = str(response.choices[0].message.content)
    cleaned_res = res.strip().removeprefix("```json").removesuffix("```")
    return json.loads(cleaned_res)


def get_image_shape(content: str) -> tuple:
    """
    Given a base64-encoded image content string, return the image shape as (width, height).
    """
    img_data = base64.b64decode(content)
    img = Image.open(BytesIO(img_data))
    return img.size  # (width, height)

class ImageSummarizer():
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)

    def summarize_image(self, image_path: str, image_url: str, previous_text: str = None):
        content = None
        with open(image_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")
        
        width, height = get_image_shape(content)
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
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url":  f"data:image/jpeg;base64,{content}"
                        },
                    },
                ]
            }
        ]
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096
            )
            summary = response.choices[0].message.content
            if len(summary) < 100:      # If the summary is too short, it is likely not useful
                return ""
            return summary
        except Exception as e:
            logging.info(f"Failed to summarize image ({image_url}): {e}")
            return ""

class TableSummarizer():
    def __init__(self, openai_api_key: str):
        self.client = OpenAI(api_key=openai_api_key)

    def summarize_table_text(self, text: str):
        prompt = f"""
            Adopt the perspective of a professional data analyst, with expertise in generating insight from structured data. 
            Provide a detailed description of the results reported in this table, ensuring clarity, depth and relevance. Don't omit any data points.
            Start with a description for each each row in the table. Then follow by a broader analysis of trends and insights, and conclude with an interpretation of the data.
            Contextual Details:
            - Examine the table headings, footnotes, or accompanying text to identify key contextual details such as the time period, location, subject area, and units of measurement.
            - Always include the table title, time frame, and geographical or thematic scope in your description.
            - If context is missing, acknowledge this explicitly and provide plausible assumptions where appropriate.
            Data Analysis:
            - Describe each data point or category individually if values are listed for different categories or time periods.
            - Highlight key metrics, trends, and patterns evident in the data.
            - Provide numerical evidence for any insights (e.g., "Revenue grew from $X in 2019 to $Y in 2022, representing a Z% increase over three years").
            Trends and Insights:
            - Analyze relationships between variables or categories (e.g., correlations, contrasts).
            - Include comparisons across time periods, groups, or locations, as supported by the data.
            - Identify and discuss patterns, outliers, and significant changes or consistencies, specifying the relevant data points.
            Interpretation and Implications:
            - Discuss the broader implications of observed trends and patterns.
            - If the table represents a time series, emphasize changes over time and provide context for those changes (e.g., market trends, economic conditions).
            - If the table shows categorical comparisons, focus on key differences or similarities between groups.
            Clarity and Accuracy:
            - Use clear and professional language, ensuring all descriptions are tied explicitly to the data.
            - If uncertainties exist in the data or context, state them and clarify how they might impact the analysis.
            Your response should be without headings, and in text (not markdown). 
            Table chunk: {text} 
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant tasked with summarizing tables."},
                    {"role": "user", "content": prompt }
                ],
                temperature=0,
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.info(f"Failed to summarize table text: {e}")
            return None
