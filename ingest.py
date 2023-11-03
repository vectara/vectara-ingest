import logging
import json
import requests
import time
from omegaconf import OmegaConf, DictConfig
import toml     # type: ignore
import sys
import os
from typing import Any

import importlib
from core.crawler import Crawler
from authlib.integrations.requests_client import OAuth2Session

def instantiate_crawler(base_class, folder_name: str, class_name: str, *args, **kwargs) -> Any:   # type: ignore
    sys.path.insert(0, os.path.abspath(folder_name))

    crawler_name = class_name.split('Crawler')[0]
    module_name = f"{folder_name}.{crawler_name.lower()}_crawler"  # Construct the full module path
    module = importlib.import_module(module_name)
    
    class_ = getattr(module, class_name)

    # Ensure the class is a subclass of the base class
    if not issubclass(class_, base_class):
        raise TypeError(f"{class_name} is not a subclass of {base_class.__name__}")

    # Instantiate the class and return the instance
    return class_(*args, **kwargs)

def get_jwt_token(auth_url: str, auth_id: str, auth_secret: str, customer_id: str) -> Any:
    """Connect to the server and get a JWT token."""
    token_endpoint = f'{auth_url}/oauth2/token'
    session = OAuth2Session(auth_id, auth_secret, scope="")
    token = session.fetch_token(token_endpoint, grant_type="client_credentials")
    return token["access_token"]

def reset_corpus(endpoint: str, customer_id: str, corpus_id: int, auth_url: str, auth_id: str, auth_secret: str) -> None:
    """
    Reset the corpus by deleting all documents and metadata.

    Args:
        endpoint (str): Endpoint for the Vectara API.
        customer_id (str): ID of the Vectara customer.
        appclient_id (str): ID of the Vectara app client.
        appclient_secret (str): Secret key for the Vectara app client.
        corpus_id (int): ID of the Vectara corpus to index to.
    """
    url = f"https://{endpoint}/v1/reset-corpus"
    payload = json.dumps({
        "customerId": customer_id,
        "corpusId": corpus_id
    })
    token = get_jwt_token(auth_url, auth_id, auth_secret, customer_id)
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'customer-id': str(customer_id),
        'Authorization': f'Bearer {token}'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code == 200:
        logging.info(f"Reset corpus {corpus_id}")
    else:
        logging.error(f"Error resetting corpus: {response.status_code} {response.text}")
                      

def main() -> None:
    """
    Main function that runs the web crawler based on environment variables.
    
    Reads the necessary environment variables and sets up the web crawler
    accordingly. Starts the crawl loop and logs the progress and errors.
    """

    if len(sys.argv) != 3:
        logging.info("Usage: python ingest.py <config_file> <secrets-profile>")
        return
    config_name = sys.argv[1]
    profile_name = sys.argv[2]

    # process arguments 
    cfg: DictConfig = DictConfig(OmegaConf.load(config_name))
    
    # add .env params, by profile
    volume = '/home/vectara/env'
    with open(f"{volume}/secrets.toml", 'r') as f:
        env_dict = toml.load(f)
    if profile_name not in env_dict:
        logging.info(f'Profile "{profile_name}" not found in secrets.toml')
        return
    env_dict = env_dict[profile_name]

    for k,v in env_dict.items():
        if k=='HUBSPOT_API_KEY':
            OmegaConf.update(cfg, f'hubspot_crawler.{k.lower()}', v)
            continue
        if k=='NOTION_API_KEY':
            OmegaConf.update(cfg, f'notion_crawler.{k.lower()}', v)
            continue
        if k=='DISCOURSE_API_KEY':
            OmegaConf.update(cfg, f'discourse_crawler.{k.lower()}', v)
            continue
        if k=='FMP_API_KEY':
            OmegaConf.update(cfg, f'fmp_crawler.{k.lower()}', v)
            continue
        if k=='JIRA_PASSWORD':
            OmegaConf.update(cfg, f'jira_crawler.{k.lower()}', v)
            continue
        if k=='GITHUB_TOKEN':
            OmegaConf.update(cfg, f'github_crawler.{k.lower()}', v)
            continue
        if k=='SYNAPSE_TOKEN':
            OmegaConf.update(cfg, f'synapse_crawler.{k.lower()}', v)
            continue
        if k.startswith('aws_'):
            OmegaConf.update(cfg, f's3_crawler.{k.lower()}', v)
            continue

        # default (otherwise) - add to vectara and arguflow configs
        OmegaConf.update(cfg['vectara'], k, v)
        OmegaConf.update(cfg['arguflow'], k, v)

    if cfg.use_arguflow:
        endpoint = cfg.arguflow.endpoint
        customer_id = "0"
        corpus_id = 0
        api_key = cfg.arguflow.api_key
    else:
        endpoint = 'api.vectara.io'
        customer_id = cfg.vectara.customer_id
        corpus_id = cfg.vectara.corpus_id
        api_key = cfg.vectara.api_key

    crawler_type = cfg.crawling.crawler_type

    # instantiate the crawler
    crawler = instantiate_crawler(Crawler, 'crawlers', f'{crawler_type.capitalize()}Crawler', cfg, endpoint, customer_id, corpus_id, api_key)

    # When debugging a crawler, it is sometimes useful to reset the corpus (remove all documents)
    # To do that you would have to set this to True and also include <auth_url> and <auth_id> in the secrets.toml file
    # NOTE: use with caution; this will delete all documents in the corpus and is irreversible
    reset_corpus_flag = False
    if reset_corpus_flag and not cfg.use_arguflow:
        logging.info("Resetting corpus")
        reset_corpus(endpoint, customer_id, corpus_id, cfg.vectara.auth_url, cfg.vectara.auth_id, cfg.vectara.auth_secret)
        time.sleep(5)   # wait 5 seconds to allow reset_corpus enough time to complete on the backend
    logging.info(f"Starting crawl of type {crawler_type}...")
    crawler.crawl()
    logging.info(f"Finished crawl of type {crawler_type}...")

if __name__ == '__main__':
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    main()
