import logging

from openai import OpenAI
from anthropic import Anthropic

from omegaconf import OmegaConf

from .utils import get_media_type_from_base64

def get_api_key(provider: str, cfg: OmegaConf) -> str:
    if provider == 'openai':
        return cfg.vectara.get("openai_api_key", None)
    elif provider == 'anthropic':
        return cfg.vectara.get("anthropic_api_key", None)
    elif provider == 'private':
        return cfg.vectara.get("private_api_key", None)
    else:
        logging.info(f"Unsupported LLM provider: {provider}")
        return None

def generate(
        cfg: OmegaConf,
        system_prompt: str, 
        user_prompt: str, 
        model_config: dict,
        max_tokens: int = 4096
    ) -> str:
    """
    Given a prompt, generate text using the specified model.
    """
    logging.debug(f"generate() - model_config: {model_config}")
    logging.debug(f"generate() - system_prompt: {system_prompt}")
    logging.debug(f"generate() - user_prompt: {user_prompt}")
    provider = model_config.get('provider', 'openai')
    model_api_key = get_api_key(provider, cfg)
    if provider == 'openai' or provider=='private':
        if provider=='private':
            client = OpenAI(api_key=model_api_key, base_url=model_config.get('base_url', None))
        else:
            client = OpenAI(api_key=model_api_key)
        response = client.chat.completions.create(
            model=model_config.get('model_name', 'gpt-4o'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        res = str(response.choices[0].message.content)
    elif provider == 'anthropic':
        client = Anthropic(api_key=model_api_key)
        response = client.messages.create(
            model=model_config.get('model_name', 'claude-3-7-sonnet-20250219'),
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
        cfg: OmegaConf,
        prompt: str, 
        image_content: str, 
        model_config: dict, 
        max_tokens: int = 4096
    ) -> str:
    """
    Given a prompt, generate text summarizing an image using the specified model.
    """
    provider = model_config.get('provider', 'openai')
    model_api_key = get_api_key(provider, cfg)
    if provider == 'openai' or provider=='private':
        if provider=='private':
            client = OpenAI(api_key=model_api_key, base_url=model_config.get('base_url', None))
        else:
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
            model=model_config.get('model_name', 'gpt-4o'),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0,
        )
        summary = response.choices[0].message.content
        return summary
    
    if provider == 'anthropic':
        client = Anthropic(api_key=model_api_key)
        media_type = get_media_type_from_base64(image_content)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
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
        ]
        response = client.messages.create(
            model=model_config.get("model_name", "claude-3-7-sonnet-20250219"),
            max_tokens=max_tokens,
            temperature=0,
            messages=messages,
        )
        summary = str(response.content[0].text)
        return summary
    
    logging.info(f"Unsupported vision LLM provider: {provider}")


