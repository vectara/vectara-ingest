import json

from openai import OpenAI
from anthropic import Anthropic

def generate(
        system_prompt: str, 
        user_prompt: str, 
        model_name: str, model_api_key: str, 
        max_tokens: int = 4096
    ) -> str:
    """
    Given a prompt, generate text using the specified model.
    """
    if model_name == 'openai':
        client = OpenAI(api_key=model_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        res = str(response.choices[0].message.content)
    elif model_name == 'anthropic':
        client = Anthropic(api_key=model_api_key)
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            system=system_prompt,
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": user_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                }
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        res = str(response.content[0].text)

    return res


def generate_image_summary(
        prompt: str, image_content: str, 
        model_name: str, model_api_key: str, 
        max_tokens: int = 4096
    ) -> str:
    """
    Given a prompt, generate text summarizing an image using the specified model.
    """
    if model_name == 'openai':
        client = OpenAI(api_key=model_api_key)
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
                            "url":  f"data:image/jpeg;base64,{image_content}"
                        },
                    },
                ]
            }
        ]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=max_tokens
        )
        summary = response.choices[0].message.content
        return summary
    elif model_name == 'anthropic':
        client = Anthropic(api_key=model_api_key)
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=max_tokens,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_content,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ],
                }
            ],
        )
        summary = str(response.content[0].text)
        return summary

