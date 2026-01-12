import logging
logger = logging.getLogger(__name__)

from openai import OpenAI
from anthropic import Anthropic

from omegaconf import OmegaConf

from .utils import get_media_type_from_base64

# Try to import Vertex AI SDK
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Part
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False
    logger.warning("Vertex AI SDK not available. Install with: pip install google-cloud-aiplatform")

def get_api_key(provider: str, cfg: OmegaConf, model_type: str = None) -> str:
    """
    Get the API key for the specified provider.

    Args:
        provider: The LLM provider ('openai', 'anthropic', 'private')
        cfg: The OmegaConf configuration object
        model_type: Optional model type ('text' or 'vision') for provider-specific keys.
                    For 'private' provider, allows using separate keys:
                    - 'text': uses private_text_api_key if available, else private_api_key
                    - 'vision': uses private_vision_api_key if available, else private_api_key
    """
    if provider == 'openai':
        return cfg.vectara.get("openai_api_key", None)
    elif provider == 'anthropic':
        return cfg.vectara.get("anthropic_api_key", None)
    elif provider == 'private':
        # Check for model-type-specific keys first, fallback to generic private_api_key
        if model_type == 'text':
            key = cfg.vectara.get("private_text_api_key", None)
            if key:
                return key
        elif model_type == 'vision':
            key = cfg.vectara.get("private_vision_api_key", None)
            if key:
                return key
        return cfg.vectara.get("private_api_key", None)
    elif provider == 'vertex':
        # Vertex AI uses project_id and location instead of API key
        return None
    else:
        logger.warning(f"Unsupported LLM provider: {provider}")
        return None

def _init_vertex_ai(cfg: OmegaConf, model_config: dict):
    """Initialize Vertex AI with project and location from config"""
    if not VERTEX_AVAILABLE:
        raise ImportError("Vertex AI SDK not available. Install with: pip install google-cloud-aiplatform")

    project_id = model_config.get('project_id') or cfg.vectara.get('vertex_project_id')
    location = model_config.get('location', 'us-central1')
    credentials_file = model_config.get('credentials_file')

    if not project_id:
        raise ValueError("Vertex AI requires 'project_id' in model_config or 'vertex_project_id' in vectara config")

    # Initialize with explicit credentials if provided
    if credentials_file:
        import os
        from google.oauth2 import service_account

        # Check if credentials file exists (it may be in /home/vectara/env/ in Docker)
        if not os.path.exists(credentials_file):
            docker_path = f"/home/vectara/env/{os.path.basename(credentials_file)}"
            if os.path.exists(docker_path):
                credentials_file = docker_path

        if os.path.exists(credentials_file):
            credentials = service_account.Credentials.from_service_account_file(credentials_file)
            vertexai.init(project=project_id, location=location, credentials=credentials)
            logger.info(f"Initialized Vertex AI with project={project_id}, location={location}, credentials={credentials_file}")
        else:
            logger.warning(f"Credentials file not found: {credentials_file}. Falling back to default credentials.")
            vertexai.init(project=project_id, location=location)
    else:
        vertexai.init(project=project_id, location=location)
        logger.info(f"Initialized Vertex AI with project={project_id}, location={location}")

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
    logger.debug(f"generate() - model_config: {model_config}")
    logger.debug(f"generate() - system_prompt: {system_prompt}")
    logger.debug(f"generate() - user_prompt: {user_prompt}")
    provider = model_config.get('provider', 'openai')
    model_api_key = get_api_key(provider, cfg, model_type='text')
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
    elif provider == 'vertex':
        _init_vertex_ai(cfg, model_config)
        model_name = model_config.get('model_name', 'gemini-2.0-flash-exp')
        model = GenerativeModel(model_name)

        # Combine system and user prompts for Vertex AI
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        response = model.generate_content(
            combined_prompt,
            generation_config={
                'temperature': 0,
                'max_output_tokens': max_tokens,
            }
        )
        res = str(response.text)
    else:
        raise ValueError(f"Unsupported provider for text generation: {provider}")

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
    model_api_key = get_api_key(provider, cfg, model_type='vision')
    if provider == 'openai' or provider=='private':
        if provider=='private':
            client = OpenAI(api_key=model_api_key, base_url=model_config.get('base_url', None))
        else:
            client = OpenAI(api_key=model_api_key)
        messages = [
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": [
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

    elif provider == 'anthropic':
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
    elif provider == 'vertex':
        import base64
        _init_vertex_ai(cfg, model_config)
        model_name = model_config.get('model_name', 'gemini-2.0-flash-exp')
        model = GenerativeModel(model_name)

        # Convert base64 image to Part
        image_bytes = base64.b64decode(image_content)
        media_type = get_media_type_from_base64(image_content)
        image_part = Part.from_data(data=image_bytes, mime_type=media_type)

        response = model.generate_content(
            [image_part, prompt],
            generation_config={
                'temperature': 0,
                'max_output_tokens': max_tokens,
            }
        )
        summary = str(response.text)
        return summary
    else:
        logger.warning(f"Unsupported vision LLM provider: {provider}")
        return None


