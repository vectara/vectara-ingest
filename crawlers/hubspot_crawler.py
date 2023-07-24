import logging
from core.crawler import Crawler
from omegaconf import OmegaConf
import requests
import pandas as pd
from core.indexer import Indexer
class HubspotCrawler(Crawler):

    def __init__(self, cfg: OmegaConf, endpoint: str, customer_id: str, corpus_id: int, api_key: str) -> None:
        super().__init__(cfg, endpoint, customer_id, corpus_id, api_key)
        self.access_token = self.cfg.hubspot_crawler.access_token

    def retrieve_emails_from_hubspot(self):
        # Set up the API endpoint and headers
        api_endpoint = "https://api.hubapi.com/crm/v3/objects/emails"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Define the properties to retrieve, including email subject and text
        properties = ["hs_email_subject", "hs_email_text"]

        all_emails = []  # List to store all email data from all pages

        # Fetch data from all pages using after and next parameters for pagination
        after = 1
        limit = 100  # Set the number of results per page (adjust as needed)
        while after:
            # Set up the query parameters to include the desired properties and the current offset
            query_params = {
                "properties": properties,
                "limit": limit,
                "after": after  # Include the 'after' parameter to get the next page
            }

            # Send GET request to retrieve emails with the specified properties and the current offset
            response = requests.get(api_endpoint, headers=headers, params=query_params)

            # Process the API response
            if response.status_code == 200:
                emails_data = response.json()
                emails_on_page = emails_data["results"]

                if not emails_on_page:
                    # No more emails available, exit the loop
                    break

                # Append data from the current page to the overall list
                all_emails.extend(emails_on_page)

                # Check if there are more pages to fetch using the 'after' parameter
                paging_info = emails_data.get("paging", {})
                after = paging_info.get("next", {}).get("after")

            else:
                logging.error(f"Error: {response.status_code} - {response.text}")
                break

        # Extract email subject and text from all fetched emails
        email_subjects = []
        email_texts = []
        for email in all_emails:
            email_subject = email["properties"]["hs_email_subject"]
            email_text = email["properties"]["hs_email_text"]
            email_subjects.append(email_subject)
            email_texts.append(email_text)

        # Create a Pandas DataFrame to store the email data
        email_df = pd.DataFrame({
            "Subject": email_subjects,
            "Text": email_texts
        })

        # Additional processing can be performed based on your needs
        logging.info(f"Retrieved {len(email_df)} emails from HubSpot.")
        return all_emails

    def crawl(self):
        logging.info("Starting HubSpot Crawler.")
        # Retrieve emails from HubSpot
        all_emails = self.retrieve_emails_from_hubspot()


        # Index each email's content
        for email in all_emails:
            email_subject = email["properties"]["hs_email_subject"]
            email_text = email["properties"]["hs_email_text"]

            # Prepare metadata (if needed) for indexing
            metadata = {
                "email_subject": email_subject,
                "email_text": email_text
                # Add more metadata fields as needed
            }

            # Index the email content using the Indexer
            logging.info(f"Indexing email '{email_subject}'")
            succeeded = self.indexer.index_segments(doc_id=email_subject, 
                                               parts=[email_text], 
                                               metadatas=[metadata], 
                                               doc_metadata={'source': 'hubspot', 'title': email_subject})

            if succeeded:
                logging.info(f"Email '{email_subject}' indexed successfully.")
            else:
                # Log detailed error information if indexing fails
                logging.error(f"Failed to index email '{email_subject}'.")
        
        logging.info("HubSpot Crawler finished.")

