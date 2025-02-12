import logging
import time
import sys
import os
from typing import Any
import importlib

import requests
import toml     # type: ignore

from omegaconf import OmegaConf, DictConfig
from authlib.integrations.requests_client import OAuth2Session

from core.crawler import Crawler
from core.utils import setup_logging

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
    url = f"https://{endpoint}/v2/corpora/{corpus_key}/reset"
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
    url = f"https://{endpoint}/v2/corpora/{corpus_key}/reset"
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
    url = f"https://{endpoint}/v2/corpora"
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
    url = f"https://{endpoint}/v2/corpora"
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

def load_environment_variables(source:dict, cfg:DictConfig) -> None:
    prefix_mappings = {
        'JIRA_': 'jira_crawler',
        'CONFLUENCE_': 'confluence_crawler',
        'HUBSPOT_': 'hubspot_crawler',
        'NOTION_': 'notion_crawler',
        'SLACK_': 'slack_crawler',
        'DISCOURSE_': 'discourse_crawler',
        'FMP_': 'fmp_crawler',
        'SERVICENOW_': 'servicenow_crawler',
        'GITHUB_': 'github_crawler',
        'SYNAPSE_': 'synapse_crawler',
        'TWITTER_': 'twitter_crawler',
        'AWS_': 's3_crawler',
        'aws_': 's3_crawler',
    }
    for k,v in source.items():
        config_set = False
        for prefix, crawler_name in prefix_mappings.items():
            if k.startswith(prefix):
                OmegaConf.update(cfg, f'{crawler_name}.{k.lower()}', v)
                config_set = True
                break
            if k.startswith('VECTARA_'):
                k_trimmed = k.removeprefix("VECTARA_")
                OmegaConf.update(cfg, f'vectara.{k_trimmed.lower()}', v)
                config_set = True
                break
        if config_set:
            continue
        OmegaConf.update(cfg['vectara'], k, v)


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
    config_file = sys.argv[1]
    profile_name = sys.argv[2]

    # process arguments 
    try:
        cfg: DictConfig = DictConfig(OmegaConf.load(config_file))
    except Exception as e:
        logging.error(f"Error loading config file ({config_file}): {e}")
        return

    if not os.getenv('DISABLE_SECRETS_TOML'):
        secrets_path = os.environ.get('VECTARA_SECRETS_PATH', '/home/vectara/env/secrets.toml')
        # add .env params, by profile
        logging.info(f"Loading {secrets_path}")
        with open(secrets_path, "r") as f:
            env_dict = toml.load(f)
        if profile_name not in env_dict:
            logging.info(f'Profile "{profile_name}" not found in secrets.toml')
            return
        logging.info(f'Using profile "{profile_name}" from secrets.toml')
        # Add all keys from "general" section to the vectara config
        general_dict = env_dict.get('general', {})
        for k,v in general_dict.items():
            OmegaConf.update(cfg, f'vectara.{k.lower()}', v)
        env_dict = env_dict[profile_name]
        load_environment_variables(env_dict, cfg)

    env_vars = dict(os.environ)
    load_environment_variables(env_vars, cfg)

    logging.info("Configuration loaded...")
    endpoint = cfg.vectara.get("endpoint", "api.vectara.io")
    auth_url = cfg.vectara.get("auth_url", "auth.vectara.io")
    create_corpus_flag = cfg.vectara.get("create_corpus", False)
    corpus_key = cfg.vectara.corpus_key
    api_key = cfg.vectara.api_key
    crawler_type = cfg.crawling.crawler_type

    # instantiate the crawler
    crawler = instantiate_crawler(
        Crawler, 'crawlers', f'{crawler_type.capitalize()}Crawler',
        cfg, endpoint, corpus_key, api_key
    )

    logging.info("Crawling instantiated...")
    # It is sometimes useful to create a new corpus.
    # To do that you would have to set this to True and also include <auth_id> in the secrets.toml file
    if create_corpus_flag:
        logging.info("Creating corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            create_corpus_oauth(endpoint, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            create_corpus_apikey(endpoint, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow create_corpus enough time to complete on the backend

    # When debugging a crawler, it is sometimes useful to reset the corpus (remove all documents)
    # To do that you would have to set this to True and also include <auth_id> in the secrets.toml file
    # NOTE: use with caution; this will delete all documents in the corpus and is irreversible
    reset_corpus_flag = False
    if reset_corpus_flag:
        logging.info("Resetting corpus")
        if 'auth_id' in cfg.vectara and 'auth_secret' in cfg.vectara:
            reset_corpus_oauth(endpoint, corpus_key, auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        else:
            reset_corpus_apikey(endpoint, corpus_key, api_key)
        time.sleep(5)   # wait 5 seconds to allow reset_corpus enough time to complete on the backend

    logging.info(f"Starting crawl of type {crawler_type}...")
    crawler.crawl()
    logging.info(f"Finished crawl of type {crawler_type}...")

if __name__ == '__main__':
    setup_logging()
    main()
