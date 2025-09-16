import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from omegaconf import OmegaConf
from typing import Any, Dict, List, Optional, Tuple

from core.crawler import Crawler
from core.utils import clean_email_text, mask_pii

logger = logging.getLogger(__name__)

class HubspotcrmCrawler(Crawler):
    """
    Simplified HubSpot CRM crawler optimized for Vectara RAG systems.
    Focuses on core data extraction with hierarchical references.
    """

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        """Initialize the crawler with configuration and API credentials."""
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.hubspot_api_key = self.cfg.hubspot_crawler.hubspot_api_key
        self.hubspot_customer_id = self.cfg.hubspot_crawler.hubspot_customer_id
        self.api_base_url = "https://api.hubapi.com/crm/v3/objects"
        self.headers = {
            "Authorization": f"Bearer {self.hubspot_api_key}",
            "Content-Type": "application/json"
        }
        
        # Cache for denormalized data
        self.companies_cache = {}
        self.contacts_cache = {}
        
        # Track indexing statistics
        self.stats = {
            'deals_indexed': 0,
            'companies_indexed': 0,
            'contacts_indexed': 0,
            'tickets_indexed': 0,
            'engagements_indexed': 0,
            'total_errors': 0
        }

    def crawl(self) -> None:
        """Main crawl orchestration method."""
        logger.info("Starting Simplified HubSpot CRM Crawler.")
        
        try:
            # First, cache and index companies (needed for denormalization)
            logger.info("Step 1: Caching and indexing companies...")
            self._cache_companies()
            logger.info(f"✓ Companies indexed: {self.stats['companies_indexed']}")
            
            # TODO: Re-enable contacts later
            # logger.info("Step 2: Caching and indexing contacts...")
            # self._cache_contacts()
            # logger.info(f"✓ Contacts indexed: {self.stats['contacts_indexed']}")
            
            # Now crawl and index objects that depend on the cache
            logger.info("Step 2: Crawling and indexing deals...")
            self._crawl_deals()
            logger.info(f"✓ Deals indexed: {self.stats['deals_indexed']}")
            
            logger.info("Step 3: Crawling and indexing tickets...")
            self._crawl_tickets()
            logger.info(f"✓ Tickets indexed: {self.stats['tickets_indexed']}")
            
            logger.info("Step 4: Crawling and indexing engagements...")
            self._crawl_engagements()
            logger.info(f"✓ Engagements indexed: {self.stats['engagements_indexed']}")
            
            # Log final statistics
            logger.info("=" * 50)
            logger.info("FINAL CRAWL STATISTICS:")
            logger.info(f"  Deals indexed: {self.stats['deals_indexed']}")
            logger.info(f"  Companies indexed: {self.stats['companies_indexed']}")
            logger.info(f"  Contacts indexed: {self.stats['contacts_indexed']} (DISABLED)")
            logger.info(f"  Tickets indexed: {self.stats['tickets_indexed']}")
            logger.info(f"  Engagements indexed: {self.stats['engagements_indexed']}")
            logger.info(f"  Total errors: {self.stats['total_errors']}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Critical error during crawl: {str(e)}")
            self.stats['total_errors'] += 1
            raise

    def _cache_companies(self) -> None:
        """Cache company data for denormalization and index companies."""
        company_properties = [
            "name", "domain", "industry", "annualrevenue", "numberofemployees",
            "city", "state", "country", "phone", "website", "lifecyclestage",
            "hubspot_owner_id", "createdate", "hs_lastmodifieddate",
            "description"
        ]
        
        companies = self._fetch_all_objects("companies", company_properties)
        logger.info(f"Found {len(companies)} companies to cache and index.")
        
        for company in companies:
            company_id = company["id"]
            
            # Cache for denormalization
            self.companies_cache[company_id] = company.get("properties", {})
        
            # Also build and index the company document
            try:
                # Get associations
                associations = self._get_associations(company["id"], "company")
                
                # Build and index document
                doc = self._build_company_document(company, associations)
                
                if self._index_document(doc):
                    self.stats['companies_indexed'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing company {company['id']}: {str(e)}")
                self.stats['total_errors'] += 1
                continue
        
        logger.info(f"Cached and indexed {len(self.companies_cache)} companies.")

        # TODO: Re-enable contacts later
    # def _cache_contacts(self) -> None:
    #     """Cache contact data for denormalization and index contacts."""
    #     contact_properties = [
    #         "firstname", "lastname", "email", "phone", "jobtitle", "company",
    #         "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
    #         "createdate", "hs_lastmodifieddate", "lastactivitydate"
    #     ]
    #     
    #     contacts = self._fetch_all_objects("contacts", contact_properties)
    #     logger.info(f"Found {len(contacts)} contacts to cache and index.")
    #     
    #     for contact in contacts:
    #         contact_id = contact["id"]
    #         
    #         # Cache for denormalization
    #         self.contacts_cache[contact_id] = contact.get("properties", {})
    #         
    #         # Also build and index the contact document
    #         try:
    #             # Get associations
    #             associations = self._get_associations(contact["id"], "contact")
    #             
    #             # Build and index document
    #             doc = self._build_contact_document(contact, associations)
    #             
    #             if self._index_document(doc):
    #                 self.stats['contacts_indexed'] += 1
    #                 
    #         except Exception as e:
    #             logger.error(f"Error processing contact {contact['id']}: {str(e)}")
    #             self.stats['total_errors'] += 1
    #             continue
    #     
    #     logger.info(f"Cached and indexed {len(self.contacts_cache)} contacts.")

    def _crawl_deals(self) -> None:
        """Crawl and index all deals."""
        deal_properties = [
            "dealname", "amount", "dealstage", "pipeline", "closedate",
            "dealtype", "hs_forecast_probability", 
            "createdate", "hs_lastmodifieddate", "hubspot_owner_id",
            "description", "hs_next_step"
        ]
        
        deals = self._fetch_all_objects("deals", deal_properties)
        logger.info(f"Found {len(deals)} deals to process.")
        
        for deal in deals:
            try:
                # Get associations
                associations = self._get_associations(deal["id"], "deal")
                
                # Build and index document
                doc = self._build_deal_document(deal, associations)
                
                if self._index_document(doc):
                    self.stats['deals_indexed'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing deal {deal['id']}: {str(e)}")
                self.stats['total_errors'] += 1
                continue



    def _crawl_engagements(self) -> None:
        """Crawl and index all engagements (emails, calls, meetings, notes, tasks)."""
        logger.info("Starting to fetch all engagements.")
        
        # HubSpot Engagements API v3 endpoint
        api_endpoint = "https://api.hubapi.com/crm/v3/objects"
        
        # Define engagement types to crawl
        engagement_types = ["emails", "calls", "meetings", "notes", "tasks"]
        
        for engagement_type in engagement_types:
            logger.info(f"Crawling {engagement_type}...")
            
            # Properties vary by engagement type
            properties = self._get_engagement_properties(engagement_type)
            
            # Fetch all engagements of this type
            engagements = self._fetch_all_objects(engagement_type, properties)
            logger.info(f"Found {len(engagements)} {engagement_type} to process.")
            
            for engagement in engagements:
                try:
                    # Get associations
                    associations = self._get_engagement_associations(engagement["id"], engagement_type)
                    
                    # Build and index document
                    doc = self._build_engagement_document(engagement, engagement_type, associations)
                    
                    if self._index_document(doc):
                            self.stats['engagements_indexed'] += 1
                except Exception as e:
                    logger.error(f"Error processing {engagement_type} {engagement['id']}: {str(e)}")
                    self.stats['total_errors'] += 1
                    continue

    def _get_engagement_properties(self, engagement_type: str) -> List[str]:
        """Get the relevant properties for each engagement type."""
        # Common properties for all engagements
        common = ["hs_timestamp", "hubspot_owner_id", "hs_lastmodifieddate", "hs_createdate"]
        
        # Type-specific properties
        type_specific = {
            "emails": ["hs_email_subject", "hs_email_status", "hs_email_text", 
                      "hs_email_direction", "hs_email_from", "hs_email_to"],
            "calls": ["hs_call_title", "hs_call_body", "hs_call_duration", 
                     "hs_call_status", "hs_call_direction", "hs_call_recording_url"],
            "meetings": ["hs_meeting_title", "hs_meeting_body", "hs_meeting_start_time",
                        "hs_meeting_end_time", "hs_meeting_location", "hs_meeting_outcome"],
            "notes": ["hs_note_body"],
            "tasks": ["hs_task_subject", "hs_task_body", "hs_task_status", 
                     "hs_task_priority", "hs_task_type", "hs_due_date"]
        }
        
        return common + type_specific.get(engagement_type, [])

    def _get_engagement_associations(self, engagement_id: str, engagement_type: str) -> Dict[str, List[str]]:
        """Get associations for an engagement."""
        associations = {
            "companies": [],
            "contacts": [],
            "deals": [],
            "tickets": []
        }
        
        # Engagements can be associated with multiple object types
        for target_type in ["companies", "contacts", "deals", "tickets"]:
            try:
                url = f"{self.api_base_url}/{engagement_type}/{engagement_id}/associations/{target_type}"
                response = requests.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    for result in data.get("results", []):
                        associations[target_type].append(result.get("id"))
            except Exception as e:
                logger.debug(f"Error getting associations for {engagement_type} {engagement_id}: {e}")
        
        return associations

    def _build_engagement_document(self, engagement: Dict, engagement_type: str, associations: Dict) -> Dict:
        """Build an engagement document."""
        properties = engagement.get("properties", {})
        engagement_id = engagement["id"]
        
        # Get associated entities for context
        company_names = []
        contact_names = []
        deal_names = []
        company_ids = []
        contact_ids = []
        deal_ids = []
        ticket_ids = []
        
        # Get company names
        if "companies" in associations and associations["companies"]:
            company_ids = [f"company_{cid}" for cid in associations["companies"][:5]]
            for comp_id in associations["companies"][:5]:
                if comp_id in self.companies_cache:
                    company_names.append(self.companies_cache[comp_id].get("name", ""))
        
        # TODO: Re-enable contacts later
        # # Get contact names
        # if "contacts" in associations and associations["contacts"]:
        #     contact_ids = [f"contact_{cid}" for cid in associations["contacts"][:10]]
        #     for cont_id in associations["contacts"][:10]:
        #         if cont_id in self.contacts_cache:
        #             cont_data = self.contacts_cache[cont_id]
        #             full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
        #             if full_name:
        #                 contact_names.append(full_name)
        
        # Set defaults for disabled contacts
        contact_ids = []
        
        # Get deal IDs (we don't cache deals, so just store IDs)
        if "deals" in associations:
            deal_ids = [f"deal_{did}" for did in associations["deals"][:10]]
        
        # Get ticket IDs
        if "tickets" in associations:
            ticket_ids = [f"ticket_{tid}" for tid in associations["tickets"][:10]]
        
        # Build the title based on engagement type
        title = self._get_engagement_title(engagement_type, properties, company_names, contact_names)
        
        # Build document structure
        doc = {
            "type": "structured",
            "id": f"{engagement_type.rstrip('s')}_{engagement_id}",  # e.g., "email_123", "call_456"
            "title": title,
            "metadata": {
                "object_type": engagement_type.rstrip('s'),  # singular form
                "engagement_id": engagement_id,
                "engagement_type": engagement_type,
                "timestamp": properties.get("hs_timestamp", ""),
                
                # Associated entities
                "company_names": company_names,
                "contact_names": contact_names,
                
                # Hierarchical Reference Structure
                "linked_company_ids": company_ids,
                "linked_contact_ids": contact_ids,
                "linked_deal_ids": deal_ids,
                "linked_ticket_ids": ticket_ids,
                
                # Type-specific metadata
                **self._get_type_specific_metadata(engagement_type, properties),
                
                "owner_id": properties.get("hubspot_owner_id", ""),
                "created_date": properties.get("hs_createdate", ""),
                "modified_date": properties.get("hs_lastmodifieddate", ""),
                "hubspot_url": f"https://app.hubspot.com/contacts/{self.hubspot_customer_id}/record/{engagement_type}/{engagement_id}"
            },
            "sections": [
                {
                    "title": "Engagement Details",
                    "text": self._generate_engagement_content(engagement_type, properties)
                },
                {
                    "title": "Context",
                    "text": self._generate_engagement_context(engagement_type, properties, company_names, contact_names)
                }
            ]
        }
        
        return doc

    def _get_engagement_title(self, engagement_type: str, properties: Dict, companies: List[str], contacts: List[str]) -> str:
        """Generate a title for the engagement document."""
        primary_company = companies[0] if companies else "Unknown Company"
        primary_contact = contacts[0] if contacts else "Unknown Contact"
        
        if engagement_type == "emails":
            subject = properties.get("hs_email_subject", "No Subject")
            return f"Email: {subject} - {primary_contact}"
        elif engagement_type == "calls":
            title = properties.get("hs_call_title", "Call")
            return f"Call: {title} - {primary_contact}"
        elif engagement_type == "meetings":
            title = properties.get("hs_meeting_title", "Meeting")
            return f"Meeting: {title} - {primary_company}"
        elif engagement_type == "notes":
            return f"Note about {primary_contact} at {primary_company}"
        elif engagement_type == "tasks":
            subject = properties.get("hs_task_subject", "Task")
            return f"Task: {subject} - {primary_company}"
        else:
            return f"{engagement_type.rstrip('s').capitalize()} - {primary_company}"

    def _get_type_specific_metadata(self, engagement_type: str, properties: Dict) -> Dict:
        """Get engagement-type specific metadata."""
        metadata = {}
        
        if engagement_type == "emails":
            metadata.update({
                "email_subject": properties.get("hs_email_subject", ""),
                "email_status": properties.get("hs_email_status", ""),
                "email_direction": properties.get("hs_email_direction", ""),
                "email_from": properties.get("hs_email_from", ""),
                "email_to": properties.get("hs_email_to", "")
            })
        elif engagement_type == "calls":
            metadata.update({
                "call_title": properties.get("hs_call_title", ""),
                "call_duration": properties.get("hs_call_duration", ""),
                "call_status": properties.get("hs_call_status", ""),
                "call_direction": properties.get("hs_call_direction", "")
            })
        elif engagement_type == "meetings":
            metadata.update({
                "meeting_title": properties.get("hs_meeting_title", ""),
                "meeting_start": properties.get("hs_meeting_start_time", ""),
                "meeting_end": properties.get("hs_meeting_end_time", ""),
                "meeting_location": properties.get("hs_meeting_location", ""),
                "meeting_outcome": properties.get("hs_meeting_outcome", "")
            })
        elif engagement_type == "tasks":
            metadata.update({
                "task_subject": properties.get("hs_task_subject", ""),
                "task_status": properties.get("hs_task_status", ""),
                "task_priority": properties.get("hs_task_priority", ""),
                "task_type": properties.get("hs_task_type", ""),
                "due_date": properties.get("hs_due_date", "")
            })
        
        return metadata

    def _generate_engagement_content(self, engagement_type: str, properties: Dict) -> str:
        """Generate the main content for an engagement."""
        if engagement_type == "emails":
            subject = properties.get("hs_email_subject", "No subject")
            text = properties.get("hs_email_text", "")
            direction = properties.get("hs_email_direction", "")
            status = properties.get("hs_email_status", "")
            
            # Clean and truncate email text if needed
            if text:
                text = clean_email_text(text)[:1000]  # Limit to 1000 chars
            
            content = f"Email {direction}: {subject}. Status: {status}. "
            if text:
                content += f"Content: {text}"
            return content
            
        elif engagement_type == "calls":
            title = properties.get("hs_call_title", "")
            body = properties.get("hs_call_body", "")
            duration = properties.get("hs_call_duration", "")
            direction = properties.get("hs_call_direction", "")
            
            content = f"Call {direction}"
            if title:
                content += f": {title}"
            if duration:
                content += f". Duration: {duration} seconds"
            if body:
                content += f". Notes: {body}"
            return content
            
        elif engagement_type == "meetings":
            title = properties.get("hs_meeting_title", "")
            body = properties.get("hs_meeting_body", "")
            start = properties.get("hs_meeting_start_time", "")
            location = properties.get("hs_meeting_location", "")
            outcome = properties.get("hs_meeting_outcome", "")
            
            content = f"Meeting: {title}. "
            if start:
                content += f"Scheduled for {start}. "
            if location:
                content += f"Location: {location}. "
            if outcome:
                content += f"Outcome: {outcome}. "
            if body:
                content += f"Notes: {body}"
            return content
            
        elif engagement_type == "notes":
            body = properties.get("hs_note_body", "No content")
            return f"Note: {body}"
            
        elif engagement_type == "tasks":
            subject = properties.get("hs_task_subject", "")
            body = properties.get("hs_task_body", "")
            status = properties.get("hs_task_status", "")
            priority = properties.get("hs_task_priority", "")
            due_date = properties.get("hs_due_date", "")
            
            content = f"Task: {subject}. "
            if priority:
                content += f"Priority: {priority}. "
            if status:
                content += f"Status: {status}. "
            if due_date:
                content += f"Due: {due_date}. "
            if body:
                content += f"Details: {body}"
            return content
        
        return "No content available."

    def _generate_engagement_context(self, engagement_type: str, properties: Dict, 
                                    companies: List[str], contacts: List[str]) -> str:
        """Generate context information for the engagement."""
        timestamp = properties.get("hs_timestamp", "")
        owner = properties.get("hubspot_owner_id", "")
        
        context = f"This {engagement_type.rstrip('s')} "
        
        if timestamp:
            context += f"occurred on {timestamp}. "
        
        if companies:
            context += f"Related to companies: {', '.join(companies[:3])}. "
        
        if contacts:
            context += f"Involves contacts: {', '.join(contacts[:5])}. "
        
        if owner:
            context += f"Assigned to: {owner}."
        
        return context if context else "No additional context available."

    def _crawl_tickets(self) -> None:
        """Crawl and index support tickets."""
        ticket_properties = [
            "subject", "hs_ticket_priority", "hs_pipeline_stage",
            "createdate", "hs_lastmodifieddate", "closed_date",
            "hs_resolution", "hubspot_owner_id", "content"
        ]
        
        tickets = self._fetch_all_objects("tickets", ticket_properties)
        logger.info(f"Found {len(tickets)} tickets to process.")
        
        for ticket in tickets:
            try:
                # Get associations
                associations = self._get_associations(ticket["id"], "ticket")
                
                # Build and index document
                doc = self._build_ticket_document(ticket, associations)
                
                if self._index_document(doc):
                    self.stats['tickets_indexed'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing ticket {ticket['id']}: {str(e)}")
                self.stats['total_errors'] += 1
                continue

    def _build_deal_document(self, deal: Dict, associations: Dict) -> Dict:
        """Build a simplified deal document with denormalized data."""
        properties = deal.get("properties", {})
        deal_id = deal["id"]
        
        # Get associated company and contact details
        company_names = []
        company_ids = []
        primary_company_name = None
        primary_company_industry = None
        
        if "companies" in associations:
            for comp_id in associations["companies"][:5]:  # Limit to 5 companies
                company_ids.append(f"company_{comp_id}")
                if comp_id in self.companies_cache:
                    comp_data = self.companies_cache[comp_id]
                    company_names.append(comp_data.get("name", ""))
                    if not primary_company_name:
                        primary_company_name = comp_data.get("name", "")
                        primary_company_industry = comp_data.get("industry", "")
        
        # TODO: Re-enable contacts later
        # contact_names = []
        # contact_ids = []
        # primary_contact_name = None
        # primary_contact_title = None
        # 
        # if "contacts" in associations:
        #     for cont_id in associations["contacts"][:10]:  # Limit to 10 contacts
        #         contact_ids.append(f"contact_{cont_id}")
        #         if cont_id in self.contacts_cache:
        #             cont_data = self.contacts_cache[cont_id]
        #             full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
        #             if full_name:
        #                 contact_names.append(full_name)
        #                 if not primary_contact_name:
        #                     primary_contact_name = full_name
        #                     primary_contact_title = cont_data.get("jobtitle", "")
        
        # Set defaults for disabled contacts
        contact_names = []
        contact_ids = []
        primary_contact_name = None
        primary_contact_title = None
        
        # Get associated ticket IDs
        ticket_ids = []
        if "tickets" in associations:
            ticket_ids = [f"ticket_{tid}" for tid in associations["tickets"][:10]]  # Limit to 10 tickets
        
        # Basic deal metrics
        amount = float(properties.get("amount", 0) or 0)
        probability = float(properties.get("hs_forecast_probability", 0) or 0)
        
        # Build document structure
        doc = {
            "type": "structured",
            "id": f"deal_{deal_id}",
            "title": f"{properties.get('dealname', 'Unnamed Deal')} - {primary_company_name or 'No Company'} ({properties.get('dealstage', 'Unknown Stage')})",
            "metadata": {
                # Core deal properties
                "object_type": "deal",
                "deal_id": deal_id,
                "dealname": properties.get("dealname", ""),
                "amount": amount,
                "dealstage": properties.get("dealstage", ""),
                "pipeline": properties.get("pipeline", ""),
                "closedate": properties.get("closedate", ""),
                "dealtype": properties.get("dealtype", ""),
                "probability": probability,
                
                # Denormalized associations (for search/display)
                "company_names": company_names,
                "primary_company_name": primary_company_name,
                "primary_company_industry": primary_company_industry,
                # TODO: Re-enable contacts later
                # "contact_names": contact_names,
                # "primary_contact_name": primary_contact_name,
                # "primary_contact_title": primary_contact_title,
                
                # Hierarchical Reference Structure (for navigation)
                "linked_company_ids": company_ids,
                # TODO: Re-enable contacts later
                # "linked_contact_ids": contact_ids,
                "linked_ticket_ids": ticket_ids,
                
                # Administrative
                "owner_id": properties.get("hubspot_owner_id", ""),
                "created_date": properties.get("createdate", ""),
                "modified_date": properties.get("hs_lastmodifieddate", ""),
                
                # HubSpot URL
                "hubspot_url": f"https://app.hubspot.com/contacts/{self.hubspot_customer_id}/deal/{deal_id}"
            },
            "sections": [
                {
                    "title": "Deal Summary",
                    "text": self._generate_deal_summary(properties, primary_company_name, None, None)  # Contacts disabled
                },
                {
                    "title": "Key Information",
                    "text": self._generate_deal_key_info(properties, company_names, [])  # Contacts disabled
                }
            ]
        }
        
        return doc

    def _build_company_document(self, company: Dict, associations: Dict) -> Dict:
        """Build a simplified company document."""
        properties = company.get("properties", {})
        company_id = company["id"]
        
        # Get associated IDs
        deal_ids = [f"deal_{did}" for did in associations.get("deals", [])][:20]  # Limit to 20 deals
        contact_ids = [f"contact_{cid}" for cid in associations.get("contacts", [])][:20]  # Limit to 20 contacts
        ticket_ids = [f"ticket_{tid}" for tid in associations.get("tickets", [])][:10]  # Limit to 10 tickets
        
        deal_count = len(associations.get("deals", []))
        contact_count = len(associations.get("contacts", []))
        
        # Basic company metrics
        annual_revenue = float(properties.get("annualrevenue", 0) or 0)
        employee_count = int(properties.get("numberofemployees", 0) or 0)
        
        doc = {
            "type": "structured",
            "id": f"company_{company_id}",
            "title": f"{properties.get('name', 'Unnamed Company')} - {properties.get('industry', 'Unknown Industry')}",
            "metadata": {
                "object_type": "company",
                "company_id": company_id,
                "name": properties.get("name", ""),
                "domain": properties.get("domain", ""),
                "industry": properties.get("industry", ""),
                "annual_revenue": annual_revenue,
                "number_of_employees": employee_count,
                "city": properties.get("city", ""),
                "state": properties.get("state", ""),
                "country": properties.get("country", ""),
                "lifecyclestage": properties.get("lifecyclestage", ""),
                "associated_deals_count": deal_count,
                "associated_contacts_count": contact_count,
                
                # Hierarchical Reference Structure
                "linked_deal_ids": deal_ids,
                "linked_contact_ids": contact_ids,
                "linked_ticket_ids": ticket_ids,
                
                "owner_id": properties.get("hubspot_owner_id", ""),
                "created_date": properties.get("createdate", ""),
                "modified_date": properties.get("hs_lastmodifieddate", ""),
                "hubspot_url": f"https://app.hubspot.com/contacts/{self.hubspot_customer_id}/company/{company_id}"
            },
            "sections": [
                {
                    "title": "Company Overview",
                    "text": self._generate_company_overview(properties)
                },
                {
                    "title": "Key Information",
                    "text": self._generate_company_key_info(properties, deal_count, contact_count)
                }
            ]
        }
        
        return doc

    def _build_contact_document(self, contact: Dict, associations: Dict) -> Dict:
        """Build a simplified contact document."""
        properties = contact.get("properties", {})
        contact_id = contact["id"]
        
        # Get associated company
        company_name = None
        company_ids = []
        if "companies" in associations and associations["companies"]:
            company_ids = [f"company_{cid}" for cid in associations["companies"][:5]]  # Limit to 5 companies
            comp_id = associations["companies"][0]
            if comp_id in self.companies_cache:
                company_name = self.companies_cache[comp_id].get("name", "")
        
        # Get associated deals and tickets
        deal_ids = [f"deal_{did}" for did in associations.get("deals", [])][:10]  # Limit to 10 deals
        ticket_ids = [f"ticket_{tid}" for tid in associations.get("tickets", [])][:10]  # Limit to 10 tickets
        
        doc = {
            "type": "structured",
            "id": f"contact_{contact_id}",
            "title": f"{properties.get('firstname', '')} {properties.get('lastname', '')} - {properties.get('jobtitle', 'Unknown Role')}",
            "metadata": {
                "object_type": "contact",
                "contact_id": contact_id,
                "firstname": properties.get("firstname", ""),
                "lastname": properties.get("lastname", ""),
                "email": properties.get("email", ""),
                "phone": properties.get("phone", ""),
                "jobtitle": properties.get("jobtitle", ""),
                "company_name": company_name or properties.get("company", ""),
                "lifecyclestage": properties.get("lifecyclestage", ""),
                "lead_status": properties.get("hs_lead_status", ""),
                
                # Hierarchical Reference Structure
                "linked_company_ids": company_ids,
                "linked_deal_ids": deal_ids,
                "linked_ticket_ids": ticket_ids,
                
                "associated_deals_count": len(associations.get("deals", [])),
                "owner_id": properties.get("hubspot_owner_id", ""),
                "created_date": properties.get("createdate", ""),
                "modified_date": properties.get("hs_lastmodifieddate", ""),
                "last_activity_date": properties.get("lastactivitydate", ""),
                "hubspot_url": f"https://app.hubspot.com/contacts/{self.hubspot_customer_id}/contact/{contact_id}"
            },
            "sections": [
                {
                    "title": "Contact Profile",
                    "text": self._generate_contact_profile(properties, company_name)
                },
                {
                    "title": "Contact Information",
                    "text": self._generate_contact_info(properties, associations)
                }
            ]
        }
        
        return doc

    def _build_ticket_document(self, ticket: Dict, associations: Dict) -> Dict:
        """Build a simplified ticket document."""
        properties = ticket.get("properties", {})
        ticket_id = ticket["id"]
        
        # Get associated company and contact
        company_name = None
        contact_name = None
        company_ids = []
        contact_ids = []
        deal_ids = []
        
        if "companies" in associations and associations["companies"]:
            company_ids = [f"company_{cid}" for cid in associations["companies"][:5]]
            comp_id = associations["companies"][0]
            if comp_id in self.companies_cache:
                company_name = self.companies_cache[comp_id].get("name", "")
        
        # TODO: Re-enable contacts later
        # if "contacts" in associations and associations["contacts"]:
        #     contact_ids = [f"contact_{cid}" for cid in associations["contacts"][:10]]
        #     cont_id = associations["contacts"][0]
        #     if cont_id in self.contacts_cache:
        #         cont_data = self.contacts_cache[cont_id]
        #         contact_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
        
        # Set defaults for disabled contacts
        contact_ids = []
        contact_name = None
        
        if "deals" in associations:
            deal_ids = [f"deal_{did}" for did in associations["deals"][:10]]
        
        doc = {
            "type": "structured",
            "id": f"ticket_{ticket_id}",
            "title": f"Ticket: {properties.get('subject', 'No Subject')} - {company_name or 'Unknown Company'}",
            "metadata": {
                "object_type": "ticket",
                "ticket_id": ticket_id,
                "subject": properties.get("subject", ""),
                "priority": properties.get("hs_ticket_priority", ""),
                "stage": properties.get("hs_pipeline_stage", ""),
                "company_name": company_name,
                "contact_name": contact_name,
                
                # Hierarchical Reference Structure
                "linked_company_ids": company_ids,
                "linked_contact_ids": contact_ids,
                "linked_deal_ids": deal_ids,
                
                "resolution": properties.get("hs_resolution", ""),
                "owner_id": properties.get("hubspot_owner_id", ""),
                "created_date": properties.get("createdate", ""),
                "closed_date": properties.get("closed_date", ""),
                "hubspot_url": f"https://app.hubspot.com/contacts/{self.hubspot_customer_id}/ticket/{ticket_id}"
            },
            "sections": [
                {
                    "title": "Issue Description",
                    "text": properties.get("content", "No description provided.")
                },
                {
                    "title": "Ticket Information",
                    "text": self._generate_ticket_info(properties, company_name, contact_name)
                }
            ]
        }
        
        return doc

    # Simplified text generation methods
    def _generate_deal_summary(self, properties: Dict, company: str, contact: str, title: str) -> str:
        """Generate natural language deal summary."""
        amount = float(properties.get("amount", 0) or 0)
        stage = properties.get("dealstage", "unknown stage")
        close_date = properties.get("closedate", "no close date set")
        deal_type = properties.get("dealtype", "")
        description = properties.get("description", "")
        
        summary = f"This is a {deal_type} deal with {company or 'an unnamed company'} valued at ${amount:,.2f}. "
        summary += f"The deal is currently in {stage} stage with an expected close date of {close_date}. "
        
        if contact:
            summary += f"Primary contact is {contact}"
            if title:
                summary += f" ({title})"
            summary += ". "
        
        if description:
            summary += f"Deal description: {description[:500]}... "
        
        return summary

    def _generate_deal_key_info(self, properties: Dict, companies: List[str], contacts: List[str]) -> str:
        """Generate key deal information."""
        next_step = properties.get("hs_next_step", "")
        probability = properties.get("hs_forecast_probability", "")
        
        info = ""
        
        if next_step:
            info += f"Next step: {next_step}. "
        
        if probability:
            info += f"Forecast probability: {probability}%. "
        
        if companies:
            info += f"Associated companies: {', '.join(companies[:3])}. "
        
        if contacts:
            info += f"Key contacts: {', '.join(contacts[:5])}. "
        
        return info if info else "No additional information available."

    def _generate_company_overview(self, properties: Dict) -> str:
        """Generate natural language company overview."""
        name = properties.get("name", "Unknown Company")
        industry = properties.get("industry", "unknown industry")
        revenue = float(properties.get("annualrevenue", 0) or 0)
        employees = properties.get("numberofemployees", 0)
        location = ", ".join(filter(None, [
            properties.get("city"),
            properties.get("state"),
            properties.get("country")
        ]))
        
        overview = f"{name} is a company in the {industry} industry"
        
        if location:
            overview += f" located in {location}"
        
        if revenue > 0:
            overview += f" with annual revenue of ${revenue:,.0f}"
        
        if employees:
            overview += f" and {employees} employees"
        
        overview += ". "
        
        description = properties.get("description", "")
        if description:
            overview += f"Company description: {description[:500]}..."
        
        return overview

    def _generate_company_key_info(self, properties: Dict, deals: int, contacts: int) -> str:
        """Generate company key information."""
        lifecycle = properties.get("lifecyclestage", "")
        website = properties.get("website", "")
        phone = properties.get("phone", "")
        
        info = f"This company has {contacts} contacts and {deals} deals in our system. "
        
        if lifecycle:
            info += f"Currently classified as {lifecycle}. "
        
        if website:
            info += f"Website: {website}. "
        
        if phone:
            info += f"Phone: {phone}. "
        
        return info

    def _generate_contact_profile(self, properties: Dict, company: str) -> str:
        """Generate natural language contact profile."""
        firstname = properties.get("firstname", "")
        lastname = properties.get("lastname", "")
        title = properties.get("jobtitle", "")
        email = properties.get("email", "")
        phone = properties.get("phone", "")
        
        profile = f"{firstname} {lastname} "
        
        if title:
            profile += f"is a {title} "
        
        if company:
            profile += f"at {company} "
        
        if email:
            profile += f"(Email: {email}) "
        
        if phone:
            profile += f"(Phone: {phone}) "
        
        return profile.strip()

    def _generate_contact_info(self, properties: Dict, associations: Dict) -> str:
        """Generate contact information."""
        lifecycle = properties.get("lifecyclestage", "")
        lead_status = properties.get("hs_lead_status", "")
        deal_count = len(associations.get("deals", []))
        
        info = ""
        
        if lifecycle:
            info += f"Lifecycle stage: {lifecycle}. "
        
        if lead_status:
            info += f"Lead status: {lead_status}. "
        
        info += f"Associated with {deal_count} deals. "
        
        return info

    def _generate_ticket_info(self, properties: Dict, company: str, contact: str) -> str:
        """Generate ticket information."""
        priority = properties.get("hs_ticket_priority", "Not set")
        stage = properties.get("hs_pipeline_stage", "Unknown")
        resolution = properties.get("hs_resolution", "Pending")
        
        info = f"Ticket from {contact or 'unknown contact'} at {company or 'unknown company'}. "
        info += f"Priority: {priority}. Current stage: {stage}. "
        info += f"Resolution status: {resolution}."
        
        return info

    # Utility methods
    def _fetch_all_objects(self, object_type: str, properties: List[str]) -> List[Dict[str, Any]]:
        """Fetch all records for a given HubSpot CRM object type with pagination."""
        all_objects = []
        after_token = None
        api_endpoint = f"{self.api_base_url}/{object_type}"
        
        logger.info(f"Starting to fetch all '{object_type}' objects.")

        while True:
            query_params = {
                "limit": 100,
                "properties": ",".join(properties),
                "associations": "companies,contacts,deals,tickets"  # Request associations
            }
            if after_token:
                query_params["after"] = after_token

            try:
                response = requests.get(api_endpoint, headers=self.headers, params=query_params)
                response.raise_for_status()

                data = response.json()
                results = data.get("results", [])
                all_objects.extend(results)
                logger.info(f"Fetched {len(results)} '{object_type}'. Total so far: {len(all_objects)}.")

                after_token = data.get("paging", {}).get("next", {}).get("after")
                if not after_token:
                    break

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning("Rate limit hit. Waiting for 60 seconds before retrying...")
                    time.sleep(60)
                    continue
                else:
                    logger.error(f"HTTP Error fetching '{object_type}': {e.response.status_code} - {e.response.text}")
                    break
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for '{object_type}': {e}")
                break

        logger.info(f"Finished fetching. Found a total of {len(all_objects)} '{object_type}' objects.")
        return all_objects

    def _get_associations(self, object_id: str, object_type: str) -> Dict[str, List[str]]:
        """Get all associations for a specific object."""
        associations = {
            "companies": [],
            "contacts": [],
            "deals": [],
            "tickets": []
        }
        
        # Define association types based on object type
        association_mappings = {
            "deal": {"companies": 5, "contacts": 3},
            "company": {"contacts": 2, "deals": 6},
            "contact": {"companies": 1, "deals": 4},
            "ticket": {"companies": 339, "contacts": 16}
        }
        
        if object_type not in association_mappings:
            return associations
        
        for target_type, type_id in association_mappings[object_type].items():
            try:
                url = f"{self.api_base_url}/{object_type}s/{object_id}/associations/{target_type}"
                response = requests.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    for result in data.get("results", []):
                        associations[target_type].append(result.get("id"))
            except Exception as e:
                logger.debug(f"Error getting associations for {object_type} {object_id}: {e}")
        
        return associations

    def _index_document(self, document: Dict) -> bool:
        """Index a document in Vectara."""
        try:
            doc_id = document["id"]
            doc_metadata = document["metadata"]
            
            # Log what we're about to index for debugging
            logger.info(f"Indexing {doc_metadata.get('object_type', 'unknown')} document: {doc_id}")
            
            # Call the indexer with the document structure that matches other crawlers
            succeeded = self.indexer.index_document(document)
            
            if succeeded:
                logger.info(f"Successfully indexed {doc_metadata.get('object_type', 'unknown')} document '{doc_id}'")
            else:
                logger.error(f"Failed to index {doc_metadata.get('object_type', 'unknown')} document '{doc_id}'")
            
            return succeeded
            
        except Exception as e:
            logger.error(f"Error indexing document {document.get('id', 'unknown')}: {str(e)}")
            return False