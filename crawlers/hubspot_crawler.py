import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
import requests
import pandas as pd
from core.indexer import Indexer
from core.utils import clean_email_text, clean_urls
from FastDataMask import clsCircularList as ccl
import re
from slugify import slugify
charList = ccl.clsCircularList()

class HubspotCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.hubspot_api_key = self.cfg.hubspot_crawler.hubspot_api_key

    def mask_pii(self, text):
        
        def mask_email(match):
            return charList.maskEmail(match.group())

        def mask_phone(match):
            return charList.maskPhone(match.group())

        def mask_ssn(match):
            return charList.maskSSN(match.group())

        masked_text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", mask_email, text)
        masked_text = re.sub(r"\b1-\d{3}-\d{3}-\d{4}\b", mask_phone, masked_text)
        masked_text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", mask_ssn, masked_text)

        return masked_text


    def crawl(self):
        logging.info("Starting HubSpot Crawler.")

        api_endpoint = "https://api.hubapi.com/crm/v3/objects/emails"
        headers = {
            "Authorization": f"Bearer {self.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        properties = ["hs_email_subject", "hs_email_text"]

        after = 1
        limit = 100
        email_count = 0

        while after:
            query_params = {
                "properties": properties,
                "limit": limit,
                "after": after
            }

            response = requests.get(api_endpoint, headers=headers, params=query_params)

            if response.status_code == 200:
                emails_data = response.json()
                emails_on_page = emails_data["results"]

                if not emails_on_page:
                    break
                
                for email in emails_on_page:
                    email_subject = email["properties"]["hs_email_subject"]
                    email_text = email["properties"]["hs_email_text"]
                    email_id = email["id"]
                    email_url = self.get_email_url(email_id)

                    # Skip indexing if email text is empty or None
                    if email_text is None or email_text.strip() == "":
                        logging.info(f"Email '{email_subject}' has no text. Skipping indexing.")
                        continue

                    masked_email_text = self.mask_pii(email_text)
                    cleaned_email_text = clean_email_text(masked_email_text)

                    metadata = {
                        "email_subject": email_subject,
                        "email_text": cleaned_email_text,
                    }

                    logging.info(f"Indexing email '{email_subject}'")
                    succeeded = self.indexer.index_segments(doc_id=slugify(email_url), 
                                                             parts=[cleaned_email_text], 
                                                             metadatas=[metadata], 
                                                             doc_metadata={'source': 'hubspot', 'title': email_subject, 'url': email_url})

                    if succeeded:
                        logging.info(f"Email '{email_subject}' indexed successfully.")
                        email_count += 1
                    else:
                        logging.error(f"Failed to index email '{email_subject}'.")

                paging_info = emails_data.get("paging", {})
                after = paging_info.get("next", {}).get("after")

            else:
                logging.error(f"Error: {response.status_code} - {response.text}")
                break
            
        logging.info(f"Crawled and indexed {email_count} emails successfully")

    def get_email_url(self, email_id):
        email_url = f"https://app.hubspot.com/live-messages/{self.cfg.hubspot_crawler.hubspot_customer_id}/inbox/{email_id}#email"
        return email_url

