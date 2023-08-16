import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
import requests
from core.utils import clean_email_text
from slugify import slugify
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
import datetime

# Initialize Presidio Analyzer and Anonymizer
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()


class HubspotCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.hubspot_api_key = self.cfg.hubspot_crawler.hubspot_api_key


    def mask_pii(self, text):
        # Analyze and anonymize PII data
        results = analyzer.analyze(text=text,
                               entities=["PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "IBAN_CODE", "PERSON", "US_BANK_NUMBER", "US_PASSPORT", "US_SSN", "LOCATION"],
                               language='en')  # Other Entities can be added 
    
        anonymized_text = anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized_text.text


    def crawl(self):
        logging.info("Starting HubSpot Crawler.")
        
        # API endpoint for fetching contacts
        api_endpoint_contacts = "https://api.hubapi.com/crm/v3/objects/contacts"
        headers = {
            "Authorization": f"Bearer {self.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        query_params_contacts = {
            "limit": 100
        }

        after_contact = 1  # This is to use for pagination of contacts. The loop breaks when after_contact is None
        email_count = 0

        while after_contact:
            if after_contact:
                query_params_contacts["after"] = after_contact

            response_contacts = requests.get(api_endpoint_contacts, headers=headers, params=query_params_contacts)

            if response_contacts.status_code == 200:
                contacts_data = response_contacts.json()
                contacts = contacts_data["results"]

                if not contacts:
                    break

                for contact in contacts:
                    contact_id = contact["id"]
                    engagements, engagements_per_contact = self.get_contact_engagements(contact_id)
                    logging.info(f"NUMBER OF ENGAGEMENTS: {engagements_per_contact} FOR CONTACT ID: {contact_id}")
                    
            
                    for engagement in engagements:
                        engagement_type = engagement["engagement"].get("type", "UNKNOWN")
                        if engagement_type == "EMAIL" and "text" in engagement["metadata"] and "subject" in engagement["metadata"]:
                            email_subject = engagement["metadata"]["subject"]
                            email_text = engagement["metadata"]["text"]
                            email_url = self.get_email_url(contact_id, engagement["engagement"]["id"])
                        else:
                            continue
                        
                        # Skip indexing if email text is empty or None
                        if email_text is None or email_text.strip() == "":
                            logging.info(f"Email '{email_subject}' has no text. Skipping indexing.")
                            continue
                        
                        masked_email_text = self.mask_pii(email_text)
                        cleaned_email_text = clean_email_text(masked_email_text)
                        
                        metadata = {
                            "source": engagement['engagement']['source'],
                            "createdAt": datetime.datetime.utcfromtimestamp(int(engagement['engagement']['createdAt'])/1000).strftime("%Y-%m-%d"),
                        }
                        
                        
                        # Generate a unique doc_id for indexing
                        doc_id = str(contact_id) + "_" + str(engagement['engagement']['id'])
                        logging.info(f"Indexing email with doc_id '{doc_id}' and subject '{email_subject}'")
                        succeeded = self.indexer.index_segments(
                            doc_id=doc_id,
                            parts=[cleaned_email_text],
                            metadatas=[metadata],
                            doc_metadata={'source': 'hubspot', 'title': email_subject, 'url': email_url}
                        )

                        if succeeded:
                            logging.info(f"Email with doc_id '{doc_id}' and subject '{email_subject}' indexed successfully.")
                            email_count += 1
                        else:
                            logging.error(f"Failed to index email '{email_subject}'.")

                    
                            
                paging_info = contacts_data.get("paging", {})
                after_contact = paging_info.get("next", {}).get("after")

                logging.info(f"Crawled and indexed {email_count} emails successfully")

            else:
                logging.error(f"Error: {response_contacts.status_code} - {response_contacts.text}")


    def get_contact_engagements(self, contact_id):
        api_endpoint_engagements = f"https://api.hubapi.com/engagements/v1/engagements/associated/contact/{contact_id}/paged"
        headers = {
            "Authorization": f"Bearer {self.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        all_engagements = []

        while True:
            response_engagements = requests.get(api_endpoint_engagements, headers=headers)

            if response_engagements.status_code == 200:
                engagements_data = response_engagements.json()
                engagements = engagements_data.get("results", [])
                all_engagements.extend(engagements)

                # Check if there are more engagements to fetch
                if engagements_data.get("hasMore"):
                    offset = engagements_data.get("offset")
                    api_endpoint_engagements = f"https://api.hubapi.com/engagements/v1/engagements/associated/contact/{contact_id}/paged?offset={offset}"
                else:
                    break
            else:
                logging.error(f"Error: {response_engagements.status_code} - {response_engagements.text}")
                break

        return all_engagements, len(all_engagements)


    def get_email_url(self, contact_id, engagement_id):
        email_url = f"https://app.hubspot.com/contacts/{self.cfg.hubspot_crawler.hubspot_customer_id}/contact/{contact_id}/?engagement={engagement_id}"
        return email_url
