import logging
import time
import sys
import os
import re
import importlib
import requests
import toml     # type: ignore
import typer
from pathlib import Path

from typing import Any, Optional
from urllib.parse import urlparse
from omegaconf import OmegaConf, DictConfig
from authlib.integrations.requests_client import OAuth2Session

from core.crawler import Crawler
from core.utils import setup_logging

app = typer.Typer()
setup_logging()

logger = logging.getLogger()

def instantiate_crawler(base_class, folder_name: str, class_name: str, *args, **kwargs) -> Any:   # type: ignore
    """
    Dynamically import a module and instantiate a crawler class.
    """
    logger.info('inside instantiate crawler')
    sys.path.insert(0, os.path.abspath(folder_name))

    crawler_name = class_name.split('Crawler')[0]
    module_name = f"{folder_name}.{crawler_name.lower()}_crawler"  # Construct the full module path
    module = importlib.import_module(module_name)

    class_ = getattr(module, class_name)

    # Ensure the class is a subclass of the base class
    if not issubclass(class_, base_class):
        raise TypeError(f"{class_name} is not a subclass of {base_class.__name__}")

    # Instantiate the class and return the instance
    logger.info('end of instantiate crawler')
    return class_(*args, **kwargs)

def get_jwt_token(auth_url: str, auth_id: str, auth_secret: str) -> Any:
    """Connect to the server and get a JWT token."""
    token_endpoint = f'{auth_url}/oauth2/token'
    session = OAuth2Session(auth_id, auth_secret, scope="")
    token = session.fetch_token(token_endpoint, grant_type="client_credentials")
    return token["access_token"]

def reset_corpus_oauth(endpoint: str, corpus_key: str, auth_url: str, auth_id: str, auth_secret: str) -> None:
    """
    Reset the corpus by deleting all documents and metadata.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        appclient_id (str): ID of the Vectara app client.
        appclient_secret (str): Secret key for the Vectara app client.
        corpus_key (str): Corpus key of the Vectara corpus to index to.
    """
    url = f"{endpoint}/v2/corpora/{corpus_key}/reset"
    token = get_jwt_token(auth_url, auth_id, auth_secret)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    response = requests.request("POST", url, headers=headers)
    if response.status_code == 200:
        logger.info(f"Reset corpus {corpus_key}")
    else:
        logging.error(f"Error resetting corpus: {response.status_code} {response.text}")

def reset_corpus_apikey(endpoint: str, corpus_key: str, api_key: str) -> None:
    """
    Reset the corpus by deleting all documents and metadata.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        appclient_id (str): ID of the Vectara app client.
        appclient_secret (str): Secret key for the Vectara app client.
        corpus_key (str): Corpus key of the Vectara corpus to index to.
    """
    url = f"{endpoint}/v2/corpora/{corpus_key}/reset"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'x-api-key': api_key
    }
    response = requests.request("POST", url, headers=headers)
    if response.status_code == 200:
        logger.info(f"Reset corpus {corpus_key}")
    else:
        logging.error(f"Error resetting corpus: {response.status_code} {response.text}")

def create_corpus_oauth(endpoint: str, corpus_key: str, auth_url: str, auth_id: str, auth_secret: str) -> None:
    """
    Create the corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        appclient_id (str): ID of the Vectara app client.
        appclient_secret (str): Secret key for the Vectara app client.
        corpus_key (str): Corpus key of the Vectara corpus to create
    """
    url = f"{endpoint}/v2/corpora"
    token = get_jwt_token(auth_url, auth_id, auth_secret)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    payload = {
        'key': corpus_key
    }

    response = requests.request("POST", url, headers=headers, json=payload)
    if response.status_code == 201:
        logger.info(f"Reset corpus {corpus_key}")
    else:
        logging.error(f"Error creating corpus: {response.status_code} {response.text}")

def create_corpus_apikey(endpoint: str, corpus_key: str, api_key: str) -> None:
    """
    Create the corpus.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        corpus_key (str): Corpus key of the Vectara corpus to index to.
        api_key (str): personal API key to create the corpus
    """
    url = f"{endpoint}/v2/corpora"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'x-api-key': api_key
    }

    payload = {
        'key': corpus_key
    }

    response = requests.request("POST", url, headers=headers, json=payload)
    if response.status_code == 201:
        logger.info(f"Reset corpus {corpus_key}")
    else:
        logging.error(f"Error creating corpus: {response.status_code} {response.text}")

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except ValueError:
        return False



def update_omega_conf(cfg: DictConfig, source: str, key: str, new_value)-> None:
    """
    Method is used for troubleshooting. When config settings are change, they are logging with the source of the change.
    :param cfg: Config to update
    :param source: Source of the change
    :param key: key that was changed
    :param new_value: value
    :return:
    """
    old_value = cfg.get(key, None)
    logging.debug(f"Updating Config: source='{source}' key='{key}' old_value='{old_value}' new_value='{new_value}'")
    OmegaConf.update(cfg, key, new_value)


def update_environment(cfg: DictConfig, source: str, env_dict) -> None:
    """Method is used to loop through the items and update the underlying OmegaConf. All changes are logged with the source """
    for k, v in env_dict.items():
        reason = f"{source}:{k}"
        if k == 'HUBSPOT_API_KEY':
            update_omega_conf(cfg, reason, f'hubspot_crawler.{k.lower()}', v)
            continue
        if k == 'NOTION_API_KEY':
            update_omega_conf(cfg, reason, f'notion_crawler.{k.lower()}', v)
            continue
        if k == 'SLACK_USER_TOKEN':
            update_omega_conf(cfg, reason, f'slack_crawler.{k.lower()}', v)
            continue
        if k == 'DISCOURSE_API_KEY':
            update_omega_conf(cfg, reason, f'discourse_crawler.{k.lower()}', v)
            continue
        if k == 'FMP_API_KEY':
            update_omega_conf(cfg, reason, f'fmp_crawler.{k.lower()}', v)
            continue
        if k == 'JIRA_PASSWORD':
            update_omega_conf(cfg, reason, f'jira_crawler.{k.lower()}', v)
            continue
        if k == 'GITHUB_TOKEN':
            update_omega_conf(cfg, reason, f'github_crawler.{k.lower()}', v)
            continue
        if k == 'SYNAPSE_TOKEN':
            update_omega_conf(cfg, reason, f'synapse_crawler.{k.lower()}', v)
            continue
        if k == 'TWITTER_BEARER_TOKEN':
            update_omega_conf(cfg, reason, f'twitter_crawler.{k.lower()}', v)
            continue
        if k == 'LLAMA_CLOUD_API_KEY':
            update_omega_conf(cfg, reason, 'llama_cloud_api_key', v)
            continue
        if k == 'DOCUPANDA_API_KEY':
            update_omega_conf(cfg, reason, 'docupanda_api_key', v)
            continue
        if k == 'MEDIAWIKI_API_KEY':
            update_omega_conf(cfg, reason, 'mediawiki_api_key', v)
            continue
        if k.startswith('aws_'):
            update_omega_conf(cfg, reason, f's3_crawler.{k.lower()}', v)
            continue

        patterns = {
            'VECTARA_(.+)': 'vectara',
            'SHAREPOINT_(.+)': 'sharepoint_crawler',
            '(CONFLUENCE_DATACENTER_.+)': 'confluencedatacenter_crawler',
            '(CONFLUENCE_.+)': 'confluence_crawler',
            '(SERVICENOW_.+)': 'servicenow_crawler'
        }

        for pattern, section in patterns.items():
            match = re.match(pattern, k)
            if match:
                logging.debug(f"Matched '{k}' with '{pattern}'")
                key = match.group(1)
                update_omega_conf(cfg, reason, f'{section}.{key.lower()}', v)
                break

        update_omega_conf(cfg.vectara, reason, k.lower(), v)


def run_ingest(config_file: str, profile: str, secrets_path: Optional[str] = None, reset_corpus: bool = False) -> None:
    """
    Core ingest functionality that can be called from both Docker and CLI.
    """
    logger = logging.getLogger()

    # process arguments
    logger.info(f"Loading config {config_file}")
    try:
        cfg: DictConfig = DictConfig(OmegaConf.load(config_file))
    except Exception as e:
        logging.error(f"Error loading config file ({config_file}): {e}")
        exit(1)

    if not cfg.get('vectara', None):
        vectara_defaults = {
            "endpoint": "https://api.vectara.io",
            "auth_url": "https://auth.vectara.io"
        }
        OmegaConf.update(cfg, 'vectara', vectara_defaults)

    # If ssl_verify is not set, check for ca.pem
    if not cfg.vectara.get("ssl_verify", None):
        if os.path.exists("ca.pem"):
            logger.info("Found ca.pem in current directory, using it for SSL verification")
            OmegaConf.update(cfg, 'vectara.ssl_verify', os.path.abspath("ca.pem"))

    # Determine secrets.toml path with more robust prioritization
    if secrets_path is None:
        # Check environment variable first
        env_secrets_path = os.environ.get('VECTARA_SECRETS_PATH')
        if env_secrets_path and os.path.exists(env_secrets_path):
            secrets_path = env_secrets_path
            logger.info(f"Using secrets from environment variable: {secrets_path}")
        elif os.path.exists('/home/vectara/env/secrets.toml'):
            secrets_path = '/home/vectara/env/secrets.toml'
            logger.info(f"Using Docker secrets path: {secrets_path}")
        else:
            # Fallback to directory for CLI mode
            local_path = 'secrets.toml'
            if os.path.exists(local_path):
                secrets_path = local_path
                logger.info(f"Using local secrets path: {secrets_path}")
            else:
                logger.error('secrets.toml not found in repository root')
                raise typer.Exit(1)
    else:
        # If explicitly provided, verify it exists
        if not os.path.exists(secrets_path):
            logger.error(f"Provided secrets path '{secrets_path}' does not exist")
            raise typer.Exit(1)
        logger.info(f"Using provided secrets path: {secrets_path}")
    
    # add .env params, by profile
    logger.info(f"Loading {secrets_path}")
    with open(secrets_path, "r") as f:
        env_dict = toml.load(f)
    if profile not in env_dict:
        logging.error(f'Profile "{profile}" not found in secrets.toml')
        exit(1)
    logger.info(f'Using profile "{profile}" from secrets.toml')
    
    # Add all keys from "general" section to the vectara config
    general_dict = env_dict.get('general', {})
    update_environment(cfg, f"{secrets_path}:general", general_dict)

    # Add all supported special secrets from the specified profile to the specific crawler config
    env_dict = env_dict[profile]
    update_environment(cfg, secrets_path, env_dict)
    update_environment(cfg, 'os.environ', dict(os.environ))

    logger.info("Configuration loaded...")
    api_url = cfg.vectara.get("endpoint", "https://api.vectara.io")

    if not api_url.startswith(("http://", "https://")):
        logger.warning(f"Correcting endpoint {api_url} to https://{api_url}. This will error in a future release.")
        api_url = f"https://{api_url}"
    if not is_valid_url(api_url):
        raise Exception(f"endpoint '{api_url}' could not be parsed to a valid URL.")

    auth_url = cfg.vectara.get("auth_url", "https://auth.vectara.io")
    if not auth_url.startswith(("http://", "https://")):
        logger.warning(f"Correcting auth_url {auth_url} to https://{auth_url}. This will error in a future release.")
        auth_url = f"https://{auth_url}"
    if not is_valid_url(auth_url):
        raise Exception(f"endpoint '{auth_url}' could not be parsed to a valid URL.")

    create_corpus_flag = cfg.vectara.get("create_corpus", False)  # Default to False
    corpus_key = cfg.vectara.corpus_key
    api_key = cfg.vectara.api_key
    crawler_type = cfg.crawling.crawler_type

    # instantiate the crawler
    crawler = instantiate_crawler(
        Crawler, 'crawlers', f'{crawler_type.capitalize()}Crawler',
        cfg, api_url, corpus_key, api_key
    )

    logger.info("Crawler instantiated...")
    
    # Create corpus if needed
    if create_corpus_flag:
        logger.info("Creating corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            create_corpus_oauth(api_url, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            create_corpus_apikey(api_url, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow create_corpus enough time to complete on the backend

    # Reset corpus if requested
    if reset_corpus:
        logger.info("Resetting corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            reset_corpus_oauth(api_url, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            reset_corpus_apikey(api_url, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow reset_corpus enough time to complete on the backend

    logger.info(f"Starting crawl of type {crawler_type}...")
    crawler.crawl()
    logger.info(f"Finished crawl of type {crawler_type}...")
    

@app.command()
def main(
    config_file: str = typer.Option(..., help="Path to the configuration file"),
    profile: str = typer.Option(..., help="Profile name in secrets.toml"),
    secrets_path: Optional[str] = typer.Option(None, help="Path to secrets.toml file (defaults to secrets.toml in current directory)"),
    reset_corpus: bool = typer.Option(False, help="Reset the corpus before indexing")
) -> None:
    """
    Main entry point for the vectara-ingest tool.
    
    This tool can be run in two ways:
    
    1. Docker style: vectara-ingest CONFIG_FILE PROFILE
    2. CLI style: vectara-ingest --config-file CONFIG_FILE --profile PROFILE [OPTIONS]
    
    The tool automatically detects if it's running in a Docker container and adjusts behavior accordingly.
    """

    logger.info(f"Starting vectara-ingest")
    run_ingest(config_file, profile, secrets_path, reset_corpus)

if __name__ == '__main__':
    # Check if we're running with named arguments (CLI style)
    has_named_args = any(arg.startswith('--') for arg in sys.argv[1:])
    
    if has_named_args:
        app()
    else:
        if len(sys.argv) != 3:
            logger.info("Usage: python ingest.py <config_file> <secrets-profile>")
            exit(1)
        
        config_file = sys.argv[1]
        profile = sys.argv[2]
        logger.info(f"Running with config={config_file}, profile={profile}")
        run_ingest(config_file, profile)

