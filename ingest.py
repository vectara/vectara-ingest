import logging
import time
import sys

from typing import Any
import importlib
from urllib.parse import urlparse
import requests
import toml     # type: ignore

from omegaconf import OmegaConf, DictConfig
from authlib.integrations.requests_client import OAuth2Session

from core.crawler import Crawler
from core.utils import setup_logging

import re
import os

def instantiate_crawler(base_class, folder_name: str, class_name: str, *args, **kwargs) -> Any:   # type: ignore
    """
    Dynamically import a module and instantiate a crawler class.
    """
    logging.info('inside instantiate crawler')
    sys.path.insert(0, os.path.abspath(folder_name))

    crawler_name = class_name.split('Crawler')[0]
    module_name = f"{folder_name}.{crawler_name.lower()}_crawler"  # Construct the full module path
    module = importlib.import_module(module_name)

    class_ = getattr(module, class_name)

    # Ensure the class is a subclass of the base class
    if not issubclass(class_, base_class):
        raise TypeError(f"{class_name} is not a subclass of {base_class.__name__}")

    # Instantiate the class and return the instance
    logging.info('end of instantiate crawler')
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
        logging.info(f"Reset corpus {corpus_key}")
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
        logging.info(f"Reset corpus {corpus_key}")
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
        logging.info(f"Reset corpus {corpus_key}")
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
        logging.info(f"Reset corpus {corpus_key}")
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


def main() -> None:
    """
    Main function that runs the web crawler based on environment variables.
    
    Reads the necessary environment variables and sets up the web crawler
    accordingly. Starts the crawl loop and logs the progress and errors.
    """
    if len(sys.argv) != 3:
        logging.info("Usage: python ingest.py <config_file> <secrets-profile>")
        return
    
    logging.info("Starting the Crawler...")
    config_name = sys.argv[1]
    profile_name = sys.argv[2]

    # process arguments
    logging.info(f"Loading config {config_name}")
    try:
        cfg: DictConfig = DictConfig(OmegaConf.load(config_name))
    except Exception as e:
        logging.error(f"Error loading config file ({config_name}): {e}")
        exit(1)

    if not cfg.get('vectara', None):
        vectara_defaults = {
            "endpoint": "https://api.vectara.io",
            "auth_url": "https://auth.vectara.io"
        }
        OmegaConf.update(cfg, 'vectara', vectara_defaults)

    secrets_path = os.environ.get('VECTARA_SECRETS_PATH', '/home/vectara/env/secrets.toml')
    # add .env params, by profile
    logging.info(f"Loading {secrets_path}")
    with open(secrets_path, "r") as f:
        env_dict = toml.load(f)
    if profile_name not in env_dict:
        logging.error(f'Profile "{profile_name}" not found in secrets.toml')
        exit(1)
    logging.info(f'Using profile "{profile_name}" from secrets.toml')
    
    # Add all keys from "general" section to the vectara config
    general_dict = env_dict.get('general', {})
    update_environment(cfg, f"{secrets_path}:general", general_dict)

    # Add all supported special secrets from the specified profile to the specific crawler config
    env_dict = env_dict[profile_name]
    update_environment(cfg, secrets_path, env_dict)
    update_environment(cfg, 'os.environ', dict(os.environ))

    logging.info("Configuration loaded...")
    api_url = cfg.vectara.get("endpoint", "https://api.vectara.io")

    if not api_url.startswith(("http://", "https://")):
        logging.warning(f"Correcting endpoint {api_url} to https://{api_url}. This will error in a future release.")
        api_url = f"https://{api_url}"
    if not is_valid_url(api_url):
        raise Exception(f"endpoint '{api_url}' could not be parsed to a valid URL.")

    auth_url = cfg.vectara.get("auth_url", "https://auth.vectara.io")
    if not auth_url.startswith(("http://", "https://")):
        logging.warning(f"Correcting auth_url {auth_url} to https://{auth_url}. This will error in a future release.")
        auth_url = f"https://{auth_url}"
    if not is_valid_url(auth_url):
        raise Exception(f"endpoint '{auth_url}' could not be parsed to a valid URL.")

    create_corpus_flag = cfg.vectara.get("create_corpus", False)
    corpus_key = cfg.vectara.corpus_key
    api_key = cfg.vectara.api_key
    crawler_type = cfg.crawling.crawler_type

    # instantiate the crawler
    crawler = instantiate_crawler(
        Crawler, 'crawlers', f'{crawler_type.capitalize()}Crawler',
        cfg, api_url, corpus_key, api_key
    )

    logging.info("Crawling instantiated...")
    # It is sometimes useful to create a new corpus.
    # To do that you would have to set this to True and also include <auth_id> in the secrets.toml file
    if create_corpus_flag:
        logging.info("Creating corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            create_corpus_oauth(api_url, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            create_corpus_apikey(api_url, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow create_corpus enough time to complete on the backend

    # When debugging a crawler, it is sometimes useful to reset the corpus (remove all documents)
    # To do that you would have to set this to True and also include <auth_id> in the secrets.toml file
    # NOTE: use with caution; this will delete all documents in the corpus and is irreversible
    reset_corpus_flag = False
    if reset_corpus_flag:
        logging.info("Resetting corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            reset_corpus_oauth(api_url, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            reset_corpus_apikey(api_url, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow reset_corpus enough time to complete on the backend

    logging.info(f"Starting crawl of type {crawler_type}...")
    crawler.crawl()
    logging.info(f"Finished crawl of type {crawler_type}...")

if __name__ == '__main__':
    setup_logging()
    main()
