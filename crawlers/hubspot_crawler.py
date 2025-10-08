import time
import logging
import requests
import ray
import psutil
import datetime
from datetime import datetime as dt
from omegaconf import OmegaConf
from typing import Any, Dict, List, Optional, Set, Tuple

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import clean_email_text, mask_pii, setup_logging

logger = logging.getLogger(__name__)

class HubspotCrawler(Crawler):
    """
    Unified HubSpot crawler for both email-only and full CRM data extraction.
    Optimized for Vectara RAG systems with hierarchical references.
    """

    def __init__(self, cfg: OmegaConf, endpoint: str, corpus_key: str, api_key: str) -> None:
        """Initialize the crawler with configuration and API credentials."""
        super().__init__(cfg, endpoint, corpus_key, api_key)
        self.hubspot_api_key = self.cfg.hubspot_crawler.hubspot_api_key
        self.hubspot_customer_id = self.cfg.hubspot_crawler.hubspot_customer_id

        # Determine crawler mode
        self.mode = self.cfg.hubspot_crawler.get('mode', 'crm')  # 'crm' or 'emails'

        # API configuration
        self.api_base_url = "https://api.hubapi.com/crm/v3/objects"
        self.headers = {
            "Authorization": f"Bearer {self.hubspot_api_key}",
            "Content-Type": "application/json"
        }

        # Cache for denormalized data
        self.companies_cache = {}
        self.contacts_cache = {}

        # Parse date filters
        self.start_date, self.end_date = self._parse_date_filters()

        # Track indexing statistics
        self.stats = {
            'deals_indexed': 0,
            'companies_indexed': 0,
            'contacts_indexed': 0,
            'tickets_indexed': 0,
            'engagements_indexed': 0,
            'emails_indexed': 0,  # Added for email-only mode
            'total_errors': 0,
            'filtered_by_date': 0
        }

    def _parse_date_filters(self) -> Tuple[Optional[dt], Optional[dt]]:
        """Parse start and end date filters from configuration."""
        start_date = None
        end_date = None

        # Parse start date
        start_date_str = self.cfg.hubspot_crawler.get('start_date', None)
        if start_date_str:
            start_date = self._parse_date_string(start_date_str)
            if start_date:
                logger.info(f"Start date filter: {start_date.strftime('%Y-%m-%d')}")

        # Parse end date
        end_date_str = self.cfg.hubspot_crawler.get('end_date', None)
        if end_date_str:
            end_date = self._parse_date_string(end_date_str)
            if end_date:
                # Set to end of day
                end_date = end_date.replace(hour=23, minute=59, second=59)
                logger.info(f"End date filter: {end_date.strftime('%Y-%m-%d')}")
        else:
            # Default to today at end of day if start_date is set but end_date is not
            if start_date:
                end_date = dt.now().replace(hour=23, minute=59, second=59)
                logger.info(f"End date defaulted to today: {end_date.strftime('%Y-%m-%d')}")

        return start_date, end_date

    def _parse_date_string(self, date_str: str) -> Optional[dt]:
        """Parse a date string in YYYY-MM-DD format."""
        if not date_str:
            return None

        try:
            return dt.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"Invalid date format: {date_str}. Expected format: YYYY-MM-DD")
            return None

    def _is_within_date_range(self, date_str: str) -> bool:
        """Check if a date string is within the configured date range."""
        if not self.start_date and not self.end_date:
            return True  # No date filtering

        if not date_str:
            return True  # Include items without dates

        try:
            # Parse the date string from HubSpot (usually in ISO format)
            # Remove timezone info to make it naive for comparison
            if 'T' in date_str:
                # ISO format with time
                item_date = dt.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
            else:
                # Just date
                item_date = dt.strptime(date_str, '%Y-%m-%d')

            # Check against date range
            if self.start_date and item_date < self.start_date:
                return False
            if self.end_date and item_date > self.end_date:
                return False

            return True
        except (ValueError, AttributeError) as e:
            logger.debug(f"Could not parse date {date_str}: {e}")
            # If we can't parse the date, include the item
            return True

    def crawl(self) -> None:
        """Main crawl orchestration method with mode support.

        Supports two modes:
        - 'emails': Only crawl email engagements
        - 'crm': Full CRM crawling with all object types
        """
        logger.info(f"Starting HubSpot Crawler in '{self.mode}' mode.")
        if self.mode == 'emails':
            logger.info("Email-only mode: Will only index email engagements.")
        self._crawl_crm()  # Use the same method for both modes

    def _crawl_crm(self) -> None:
        """CRM crawling with support for filtering by mode."""
        logger.info("PII masking will be applied to all engagement content.")

        if self.start_date or self.end_date:
            logger.info(f"Date filtering enabled: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'no start'} to {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'no end'}")

        # Determine number of Ray workers
        ray_workers = self.cfg.hubspot_crawler.get("ray_workers", 0)
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        try:
            # NEW APPROACH: Start with deals to identify relevant companies/contacts
            logger.info("Step 1: Fetching all deals to identify relevant companies and contacts...")
            deals, involved_company_ids, involved_contact_ids = self._fetch_deals_and_extract_relationships()
            logger.info(f"Found {len(deals)} deals involving {len(involved_company_ids)} companies and {len(involved_contact_ids)} contacts")

            # Initialize Ray once if we're using it
            if ray_workers > 0:
                self.indexer.p = self.indexer.browser = None
                if not ray.is_initialized():
                    ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
                    logger.info(f"Initialized Ray with {ray_workers} workers")

            # Skip companies, contacts, deals, and tickets in email-only mode
            if self.mode != 'emails':
                # Only fetch and index companies that are involved in deals
                logger.info("Step 2: Fetching and indexing deal-related companies...")
                self._fetch_and_index_relevant_companies(involved_company_ids, ray_workers)
                logger.info(f"✓ Companies indexed: {self.stats['companies_indexed']}")

                # Only fetch and index contacts that are involved in deals
                logger.info("Step 3: Fetching and indexing deal-related contacts...")
                self._fetch_and_index_relevant_contacts(involved_contact_ids, ray_workers)
                logger.info(f"✓ Contacts indexed: {self.stats['contacts_indexed']}")

                # Now index the deals with cached company/contact data
                logger.info("Step 4: Indexing deals with enriched data...")
                self._index_deals(deals, ray_workers)
                logger.info(f"✓ Deals indexed: {self.stats['deals_indexed']}")

                # Optionally still index tickets and engagements
                logger.info("Step 5: Crawling and indexing tickets...")
                self._crawl_tickets(ray_workers)
                logger.info(f"✓ Tickets indexed: {self.stats['tickets_indexed']}")
            else:
                # In email-only mode, still cache companies and contacts for context
                logger.info("Step 2: Caching companies for email context...")
                self._cache_companies_for_context(involved_company_ids)

                logger.info("Step 3: Caching contacts for email context...")
                self._cache_contacts_for_context(involved_contact_ids)

            # Process engagement objects (emails only in email mode, all types otherwise)
            step_num = "4" if self.mode == 'emails' else "6"
            logger.info(f"Step {step_num}: Crawling and indexing {'emails' if self.mode == 'emails' else 'engagements'}...")
            self._crawl_engagements(ray_workers)
            logger.info(f"✓ Engagements indexed: {self.stats['engagements_indexed']}")

            # Shutdown Ray if it was initialized
            if ray_workers > 0 and ray.is_initialized():
                ray.shutdown()
                logger.info("Ray shutdown complete")

            # Log final statistics
            logger.info("=" * 50)
            logger.info("FINAL CRAWL STATISTICS:")
            logger.info(f"  Deals indexed: {self.stats['deals_indexed']}")
            logger.info(f"  Companies indexed: {self.stats['companies_indexed']}")
            logger.info(f"  Contacts indexed: {self.stats['contacts_indexed']}")
            logger.info(f"  Tickets indexed: {self.stats['tickets_indexed']}")
            logger.info(f"  Engagements indexed: {self.stats['engagements_indexed']}")
            logger.info(f"  Items filtered by date: {self.stats['filtered_by_date']}")
            logger.info(f"  Total errors: {self.stats['total_errors']}")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Critical error during crawl: {str(e)}")
            self.stats['total_errors'] += 1
            raise

    def _fetch_deals_and_extract_relationships(self) -> Tuple[List[Dict], Set[str], Set[str]]:
        """Fetch all deals and extract unique company and contact IDs.

        Returns:
            Tuple of (deals_with_associations, involved_company_ids, involved_contact_ids)
        """
        deal_properties = [
            "dealname", "amount", "dealstage", "pipeline", "closedate",
            "dealtype", "hs_forecast_probability",
            "createdate", "hs_lastmodifieddate", "hubspot_owner_id",
            "description", "hs_next_step"
        ]

        # Fetch all deals with date filtering
        deals = self._fetch_all_objects("deals", deal_properties, date_field="createdate")
        logger.info(f"Fetched {len(deals)} deals after date filtering")

        # Fetch associations for all deals and extract unique IDs
        deals_with_associations = []
        involved_company_ids = set()
        involved_contact_ids = set()

        logger.info("Fetching associations for all deals...")
        for i, deal in enumerate(deals):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing deal {i + 1}/{len(deals)}")

            try:
                associations = self._get_associations(deal["id"], "deal")
                deals_with_associations.append((deal, associations))

                # Extract company and contact IDs
                involved_company_ids.update(associations.get("companies", []))
                involved_contact_ids.update(associations.get("contacts", []))

            except Exception as e:
                logger.error(f"Error fetching associations for deal {deal['id']}: {str(e)}")
                deals_with_associations.append((deal, {"companies": [], "contacts": [], "tickets": []}))

        return deals_with_associations, involved_company_ids, involved_contact_ids

    def _fetch_and_index_relevant_companies(self, company_ids: Set[str], ray_workers: int = 0) -> None:
        """Fetch and index only companies that are involved in deals.

        Args:
            company_ids: Set of company IDs to fetch
            ray_workers: Number of Ray workers to use
        """
        if not company_ids:
            logger.info("No companies to fetch")
            return

        company_properties = [
            "name", "domain", "industry", "annualrevenue", "numberofemployees",
            "city", "state", "country", "phone", "website", "lifecyclestage",
            "hubspot_owner_id", "createdate", "hs_lastmodifieddate",
            "description"
        ]

        logger.info(f"Fetching {len(company_ids)} companies involved in deals...")
        companies = []
        companies_with_associations = []

        # Fetch companies in batches (HubSpot API might have limits on batch size)
        company_id_list = list(company_ids)
        batch_size = 100  # HubSpot typically allows 100 objects per batch request

        for i in range(0, len(company_id_list), batch_size):
            batch_ids = company_id_list[i:i + batch_size]
            logger.info(f"Fetching company batch {i // batch_size + 1}/{(len(company_id_list) - 1) // batch_size + 1}")

            # Fetch companies by IDs
            for comp_id in batch_ids:
                try:
                    url = f"{self.api_base_url}/companies/{comp_id}"
                    params = {"properties": ",".join(company_properties)}
                    response = requests.get(url, headers=self.headers, params=params)

                    if response.status_code == 200:
                        company = response.json()
                        companies.append(company)

                        # Cache for denormalization
                        self.companies_cache[comp_id] = company.get("properties", {})

                        # Get associations
                        associations = self._get_associations(comp_id, "company")
                        companies_with_associations.append((company, associations))
                    else:
                        logger.warning(f"Failed to fetch company {comp_id}: {response.status_code}")

                except Exception as e:
                    logger.error(f"Error fetching company {comp_id}: {str(e)}")

        logger.info(f"Fetched {len(companies)} companies out of {len(company_ids)} requested")

        # Process and index companies with Ray if enabled
        if ray_workers > 0 and companies_with_associations:
            self._process_companies_with_ray(companies_with_associations, ray_workers)
        else:
            for company, associations in companies_with_associations:
                try:
                    doc = self._build_company_document(company, associations)
                    if self._index_document(doc):
                        self.stats['companies_indexed'] += 1
                except Exception as e:
                    logger.error(f"Error processing company {company['id']}: {str(e)}")
                    self.stats['total_errors'] += 1

    def _fetch_and_index_relevant_contacts(self, contact_ids: Set[str], ray_workers: int = 0) -> None:
        """Fetch and index only contacts that are involved in deals.

        Args:
            contact_ids: Set of contact IDs to fetch
            ray_workers: Number of Ray workers to use
        """
        if not contact_ids:
            logger.info("No contacts to fetch")
            return

        contact_properties = [
            "firstname", "lastname", "email", "phone", "jobtitle", "company",
            "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
            "createdate", "hs_lastmodifieddate", "lastactivitydate"
        ]

        logger.info(f"Fetching {len(contact_ids)} contacts involved in deals...")
        contacts = []
        contacts_with_associations = []

        # Fetch contacts in batches
        contact_id_list = list(contact_ids)
        batch_size = 100

        for i in range(0, len(contact_id_list), batch_size):
            batch_ids = contact_id_list[i:i + batch_size]
            logger.info(f"Fetching contact batch {i // batch_size + 1}/{(len(contact_id_list) - 1) // batch_size + 1}")

            for cont_id in batch_ids:
                try:
                    url = f"{self.api_base_url}/contacts/{cont_id}"
                    params = {"properties": ",".join(contact_properties)}
                    response = requests.get(url, headers=self.headers, params=params)

                    if response.status_code == 200:
                        contact = response.json()
                        contacts.append(contact)

                        # Cache for denormalization
                        self.contacts_cache[cont_id] = contact.get("properties", {})

                        # Get associations
                        associations = self._get_associations(cont_id, "contact")
                        contacts_with_associations.append((contact, associations))
                    else:
                        logger.warning(f"Failed to fetch contact {cont_id}: {response.status_code}")

                except Exception as e:
                    logger.error(f"Error fetching contact {cont_id}: {str(e)}")

        logger.info(f"Fetched {len(contacts)} contacts out of {len(contact_ids)} requested")

        # Process and index contacts with Ray if enabled
        if ray_workers > 0 and contacts_with_associations:
            self._process_contacts_with_ray(contacts_with_associations, ray_workers)
        else:
            for contact, associations in contacts_with_associations:
                try:
                    doc = self._build_contact_document(contact, associations)
                    if self._index_document(doc):
                        self.stats['contacts_indexed'] += 1
                except Exception as e:
                    logger.error(f"Error processing contact {contact['id']}: {str(e)}")
                    self.stats['total_errors'] += 1

    def _index_deals(self, deals_with_associations: List[Tuple[Dict, Dict]], ray_workers: int = 0) -> None:
        """Index all deals with enriched company and contact data.

        Args:
            deals_with_associations: List of (deal, associations) tuples
            ray_workers: Number of Ray workers to use
        """
        logger.info(f"Indexing {len(deals_with_associations)} deals with enriched data...")

        if ray_workers > 0 and deals_with_associations:
            self._process_deals_with_ray(deals_with_associations, self.companies_cache, self.contacts_cache, ray_workers)
        else:
            for deal, associations in deals_with_associations:
                try:
                    doc = self._build_deal_document(deal, associations)
                    if self._index_document(doc):
                        self.stats['deals_indexed'] += 1
                except Exception as e:
                    logger.error(f"Error processing deal {deal['id']}: {str(e)}")
                    self.stats['total_errors'] += 1

    def _cache_companies(self, ray_workers: int = 0) -> None:
        """Cache company data for denormalization and index companies with optional Ray support."""
        company_properties = [
            "name", "domain", "industry", "annualrevenue", "numberofemployees",
            "city", "state", "country", "phone", "website", "lifecyclestage",
            "hubspot_owner_id", "createdate", "hs_lastmodifieddate",
            "description"
        ]

        companies = self._fetch_all_objects("companies", company_properties, date_field="createdate")
        logger.info(f"Found {len(companies)} companies to cache and index after date filtering.")

        # First cache all companies for denormalization
        for company in companies:
            company_id = company["id"]
            self.companies_cache[company_id] = company.get("properties", {})

        # Fetch ALL associations upfront in the main thread
        logger.info("Fetching associations for all companies...")
        companies_with_associations = []
        for i, company in enumerate(companies):
            if (i + 1) % 100 == 0:
                logger.info(f"Fetched associations for {i + 1}/{len(companies)} companies")

            try:
                associations = self._get_associations(company["id"], "company")
                companies_with_associations.append((company, associations))
            except Exception as e:
                logger.error(f"Error fetching associations for company {company['id']}: {str(e)}")
                companies_with_associations.append((company, {"contacts": [], "deals": [], "tickets": []}))

        logger.info(f"Fetched associations for all {len(companies)} companies")

        # Now process and index companies with Ray if enabled
        if ray_workers > 0:
            self._process_companies_with_ray(companies_with_associations, ray_workers)
        else:
            for company, associations in companies_with_associations:
                try:
                    # Build and index document
                    doc = self._build_company_document(company, associations)

                    if self._index_document(doc):
                        self.stats['companies_indexed'] += 1

                except Exception as e:
                    logger.error(f"Error processing company {company['id']}: {str(e)}")
                    self.stats['total_errors'] += 1
                    continue

        logger.info(f"Cached and indexed {len(self.companies_cache)} companies.")

    def _process_companies_with_ray(self, companies_with_associations: List[Tuple[Dict, Dict]], ray_workers: int) -> None:
        """Process companies using Ray for parallel processing.

        Args:
            companies_with_associations: List of (company, associations) tuples
            ray_workers: Number of Ray workers to use
        """
        logger.info(f"Using {ray_workers} ray workers to process {len(companies_with_associations)} companies")

        # Put shared data in Ray object store
        logger.info(f"About to put companies_cache in Ray. Cache size: {len(self.companies_cache)}")
        companies_cache_id = ray.put(self.companies_cache if self.companies_cache else {})
        logger.info(f"Type of companies_cache_id: {type(companies_cache_id)}, value: {companies_cache_id}")

        # Create actor pool
        actors = [ray.remote(HubspotObjectProcessor).remote(self.cfg, self.indexer, 'company') for _ in range(ray_workers)]
        for a in actors:
            logger.info(f"Calling setup with companies_cache_id type: {type(companies_cache_id)}")
            a.setup.remote(companies_cache_id, None, None)
        pool = ray.util.ActorPool(actors)

        # Process companies in parallel - now with pre-fetched associations
        results = list(pool.map(
            lambda a, data: a.process_company_with_associations.remote(data[0], data[1]),
            companies_with_associations
        ))

        # Update stats
        for indexed, errors in results:
            if indexed:
                self.stats['companies_indexed'] += 1
            if errors:
                self.stats['total_errors'] += errors

    def _cache_contacts(self, ray_workers: int = 0) -> None:
        """Cache contact data for denormalization and index contacts with optional Ray support."""
        contact_properties = [
            "firstname", "lastname", "email", "phone", "jobtitle", "company",
            "lifecyclestage", "hs_lead_status", "hubspot_owner_id",
            "createdate", "hs_lastmodifieddate", "lastactivitydate"
        ]

        contacts = self._fetch_all_objects("contacts", contact_properties, date_field="createdate")
        logger.info(f"Found {len(contacts)} contacts to cache and index after date filtering.")

        # First cache all contacts for denormalization
        for contact in contacts:
            contact_id = contact["id"]
            self.contacts_cache[contact_id] = contact.get("properties", {})

        # Fetch ALL associations upfront in the main thread
        logger.info("Fetching associations for all contacts...")
        contacts_with_associations = []
        for i, contact in enumerate(contacts):
            if (i + 1) % 500 == 0:
                logger.info(f"Fetched associations for {i + 1}/{len(contacts)} contacts")

            try:
                associations = self._get_associations(contact["id"], "contact")
                contacts_with_associations.append((contact, associations))
            except Exception as e:
                logger.error(f"Error fetching associations for contact {contact['id']}: {str(e)}")
                contacts_with_associations.append((contact, {"companies": [], "deals": [], "tickets": []}))

        logger.info(f"Fetched associations for all {len(contacts)} contacts")

        # Now process and index contacts with Ray if enabled
        if ray_workers > 0:
            self._process_contacts_with_ray(contacts_with_associations, ray_workers)
        else:
            for contact, associations in contacts_with_associations:
                try:
                    # Build and index document
                    doc = self._build_contact_document(contact, associations)

                    if self._index_document(doc):
                        self.stats['contacts_indexed'] += 1

                except Exception as e:
                    logger.error(f"Error processing contact {contact['id']}: {str(e)}")
                    self.stats['total_errors'] += 1
                    continue

        logger.info(f"Cached and indexed {len(self.contacts_cache)} contacts.")

    def _process_contacts_with_ray(self, contacts_with_associations: List[Tuple[Dict, Dict]], ray_workers: int) -> None:
        """Process contacts using Ray for parallel processing.

        Args:
            contacts_with_associations: List of (contact, associations) tuples
            ray_workers: Number of Ray workers to use
        """
        logger.info(f"Using {ray_workers} ray workers to process {len(contacts_with_associations)} contacts")

        # Put shared data in Ray object store
        companies_cache_id = ray.put(self.companies_cache)
        contacts_cache_id = ray.put(self.contacts_cache)

        # Create actor pool
        actors = [ray.remote(HubspotObjectProcessor).remote(self.cfg, self.indexer, 'contact') for _ in range(ray_workers)]
        for a in actors:
            a.setup.remote(companies_cache_id, contacts_cache_id, None)
        pool = ray.util.ActorPool(actors)

        # Process contacts in parallel - now with pre-fetched associations
        results = list(pool.map(
            lambda a, data: a.process_contact_with_associations.remote(data[0], data[1]),
            contacts_with_associations
        ))

        # Update stats
        for indexed, errors in results:
            if indexed:
                self.stats['contacts_indexed'] += 1
            if errors:
                self.stats['total_errors'] += errors

    def _crawl_deals(self, ray_workers: int = 0) -> None:
        """Crawl and index all deals with optional Ray support."""
        deal_properties = [
            "dealname", "amount", "dealstage", "pipeline", "closedate",
            "dealtype", "hs_forecast_probability",
            "createdate", "hs_lastmodifieddate", "hubspot_owner_id",
            "description", "hs_next_step"
        ]

        deals = self._fetch_all_objects("deals", deal_properties, date_field="createdate")
        logger.info(f"Found {len(deals)} deals to process after date filtering.")

        if ray_workers > 0:
            self._process_deals_with_ray(deals, ray_workers)
        else:
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

    def _process_deals_with_ray(self, deals_with_associations: List[Tuple[Dict, Dict]], companies_cache: Dict[str, Dict], contacts_cache: Dict[str, Dict], ray_workers: int) -> None:
        """Process deals in parallel using Ray with pre-fetched associations.

        Args:
            deals_with_associations: List of (deal, associations) tuples
            companies_cache: Companies cache dictionary
            contacts_cache: Contacts cache dictionary
            ray_workers: Number of Ray workers to use
        """
        logger.info(f"Using {ray_workers} ray workers to process {len(deals_with_associations)} deals")

        # Put shared data into Ray object store
        companies_cache_id = ray.put(companies_cache)
        contacts_cache_id = ray.put(contacts_cache)

        # Initialize Ray actors
        actors = []
        for _ in range(ray_workers):
            actor = ray.remote(HubspotObjectProcessor).remote(
                self.cfg, self.indexer, "deal"
            )
            actors.append(actor)

        for actor in actors:
            actor.setup.remote(companies_cache_id, contacts_cache_id, None)

        pool = ray.util.ActorPool(actors)

        # Process deals in parallel with pre-fetched associations
        results = list(pool.map(
            lambda a, data: a.process_deal_with_associations.remote(data[0], data[1]),
            deals_with_associations
        ))

        # Update stats
        for indexed, errors in results:
            if indexed:
                self.stats['deals_indexed'] += 1
            if errors:
                self.stats['total_errors'] += errors



    def _crawl_engagements(self, ray_workers: int = 0) -> None:
        """Crawl and index engagements with optional Ray support."""
        logger.info("Starting to fetch engagements.")

        # HubSpot Engagements API v3 endpoint
        api_endpoint = "https://api.hubapi.com/crm/v3/objects"

        # Define engagement types to crawl based on mode
        if self.mode == 'emails':
            engagement_types = ["emails"]  # Only process emails in email-only mode
        else:
            engagement_types = ["emails", "calls", "meetings", "notes", "tasks"]  # All types in CRM mode

        for engagement_type in engagement_types:
            logger.info(f"Crawling {engagement_type}...")

            # Properties vary by engagement type
            properties = self._get_engagement_properties(engagement_type)

            # Fetch all engagements of this type
            # For engagements, use hs_createdate as the date field
            engagements = self._fetch_all_objects(engagement_type, properties, date_field="hs_createdate")
            logger.info(f"Found {len(engagements)} {engagement_type} to process after date filtering.")

            if ray_workers > 0:
                self._process_engagements_with_ray(engagements, engagement_type, ray_workers)
            else:
                for engagement in engagements:
                    try:
                        # Get associations
                        associations = self._get_engagement_associations(engagement["id"], engagement_type)

                        # Build document
                        doc = self._build_engagement_document(engagement, engagement_type, associations)

                        # Skip empty engagements
                        if self._is_engagement_empty(doc, engagement_type):
                            logger.debug(f"Skipping empty {engagement_type} {engagement['id']}")
                            continue

                        if self._index_document(doc):
                                self.stats['engagements_indexed'] += 1
                    except Exception as e:
                        logger.error(f"Error processing {engagement_type} {engagement['id']}: {str(e)}")
                        self.stats['total_errors'] += 1
                        continue

    def _process_engagements_with_ray(self, engagements: List[Dict], engagement_type: str, ray_workers: int) -> None:
        """Process engagements using Ray for parallel processing."""
        logger.info(f"Using {ray_workers} ray workers for {engagement_type}")

        # Put shared data in Ray object store
        companies_cache_id = ray.put(self.companies_cache)
        contacts_cache_id = ray.put(self.contacts_cache)
        date_filters_id = ray.put((self.start_date, self.end_date))

        # Create actor pool
        actors = [ray.remote(HubspotObjectProcessor).remote(self.cfg, self.indexer, 'engagement') for _ in range(ray_workers)]
        for a in actors:
            a.setup.remote(companies_cache_id, contacts_cache_id, date_filters_id)
        pool = ray.util.ActorPool(actors)

        # Process engagements in parallel
        results = list(pool.map(lambda a, eng: a.process_engagement.remote(eng, engagement_type), engagements))

        # Update stats
        for indexed, errors in results:
            if indexed:
                self.stats['engagements_indexed'] += 1
            if errors:
                self.stats['total_errors'] += errors

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
            company_ids = [f"company_{cid}" for cid in associations["companies"]]
            for comp_id in associations["companies"]:
                if comp_id in self.companies_cache:
                    company_names.append(self.companies_cache[comp_id].get("name", ""))
        
        # Get contact names
        if "contacts" in associations and associations["contacts"]:
            contact_ids = [f"contact_{cid}" for cid in associations["contacts"][:10]]
            for cont_id in associations["contacts"][:10]:
                if cont_id in self.contacts_cache:
                    cont_data = self.contacts_cache[cont_id]
                    full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
                    if full_name:
                        contact_names.append(full_name)
        
        # Get deal IDs (we don't cache deals, so just store IDs)
        if "deals" in associations:
            deal_ids = [f"deal_{did}" for did in associations["deals"][:10]]
        
        # Get ticket IDs
        if "tickets" in associations:
            ticket_ids = [f"ticket_{tid}" for tid in associations["tickets"][:10]]
        
        # Build the title based on engagement type
        title = self._get_engagement_title(engagement_type, properties, company_names, contact_names)

        # Build document structure
        # Use 'core' for shorter engagements (calls, tasks), 'structured' for longer content (emails, meetings, notes)
        doc_type = "core" if engagement_type in ["calls", "tasks"] else "structured"
        doc = {
            "type": doc_type,
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
                # Apply PII masking
                text = mask_pii(text)
                text = clean_email_text(text)  # Full email content
            
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
                # Apply PII masking to call notes
                body = mask_pii(body)
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
                # Apply PII masking to meeting notes
                body = mask_pii(body)
                content += f"Notes: {body}"
            return content
            
        elif engagement_type == "notes":
            body = properties.get("hs_note_body", "No content")
            # Apply PII masking to notes
            if body and body != "No content":
                body = mask_pii(body)
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
                # Apply PII masking to task details
                body = mask_pii(body)
                content += f"Details: {body}"
            return content
        
        return "No content available."

    def _is_engagement_empty(self, doc: Dict, engagement_type: str) -> bool:
        """Check if an engagement document has meaningful content.

        Returns True if the engagement should be skipped due to lack of content.
        """
        # Check the main content section
        sections = doc.get("sections", [])
        if not sections:
            return True

        # Get the main content text (usually first section)
        main_content = ""
        for section in sections:
            if section.get("title") == "Engagement Details":
                main_content = section.get("text", "")
                break

        # Type-specific empty checks
        if engagement_type == "emails":
            # For emails, check if there's actual email text beyond the subject
            if "No content available" in main_content or "Content:" not in main_content:
                return True
            # Extract content after "Content:" and check if it's meaningful
            if "Content:" in main_content:
                email_content = main_content.split("Content:")[-1].strip()
                if not email_content or len(email_content) < 10:
                    return True

        elif engagement_type == "notes":
            # For notes, check if there's actual note body
            if "Note: No content" in main_content or len(main_content) < 20:
                return True

        elif engagement_type == "meetings":
            # For meetings, check if there's meeting body/notes
            if "Notes:" not in main_content or "Meeting:" in main_content and len(main_content) < 50:
                return True

        elif engagement_type == "calls":
            # For calls, having just direction and duration might be okay, but check for notes
            if "Notes:" not in main_content and len(main_content) < 30:
                return True

        elif engagement_type == "tasks":
            # For tasks, check if there's actual task details
            if "Details:" not in main_content and len(main_content) < 40:
                return True

        return False

    def _generate_engagement_context(self, engagement_type: str, properties: Dict,
                                    companies: List[str], contacts: List[str]) -> str:
        """Generate context information for the engagement."""
        timestamp = properties.get("hs_timestamp", "")
        owner = properties.get("hubspot_owner_id", "")
        
        context = f"This {engagement_type.rstrip('s')} "
        
        if timestamp:
            context += f"occurred on {timestamp}. "
        
        if companies:
            context += f"Related to companies: {', '.join(companies)}. "
        
        if contacts:
            context += f"Involves contacts: {', '.join(contacts)}. "
        
        if owner:
            context += f"Assigned to: {owner}."
        
        return context if context else "No additional context available."

    def _crawl_tickets(self, ray_workers: int = 0) -> None:
        """Crawl and index support tickets with optional Ray support."""
        ticket_properties = [
            "subject", "hs_ticket_priority", "hs_pipeline_stage",
            "createdate", "hs_lastmodifieddate", "closed_date",
            "hs_resolution", "hubspot_owner_id", "content"
        ]

        tickets = self._fetch_all_objects("tickets", ticket_properties, date_field="createdate")
        logger.info(f"Found {len(tickets)} tickets to process after date filtering.")

        if ray_workers > 0:
            self._process_tickets_with_ray(tickets, ray_workers)
        else:
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

    def _process_tickets_with_ray(self, tickets: List[Dict], ray_workers: int) -> None:
        """Process tickets using Ray for parallel processing."""
        logger.info(f"Using {ray_workers} ray workers for tickets")

        # Put shared data in Ray object store
        companies_cache_id = ray.put(self.companies_cache)
        contacts_cache_id = ray.put(self.contacts_cache)
        date_filters_id = ray.put((self.start_date, self.end_date))

        # Create actor pool
        actors = [ray.remote(HubspotObjectProcessor).remote(self.cfg, self.indexer, 'ticket') for _ in range(ray_workers)]
        for a in actors:
            a.setup.remote(companies_cache_id, contacts_cache_id, date_filters_id)
        pool = ray.util.ActorPool(actors)

        # Process tickets in parallel
        results = list(pool.map(lambda a, ticket: a.process_ticket.remote(ticket), tickets))

        # Update stats
        for indexed, errors in results:
            if indexed:
                self.stats['tickets_indexed'] += 1
            if errors:
                self.stats['total_errors'] += errors

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
            for comp_id in associations["companies"]:
                company_ids.append(f"company_{comp_id}")
                if comp_id in self.companies_cache:
                    comp_data = self.companies_cache[comp_id]
                    company_names.append(comp_data.get("name", ""))
                    if not primary_company_name:
                        primary_company_name = comp_data.get("name", "")
                        primary_company_industry = comp_data.get("industry", "")
        
        # Get contact details
        contact_names = []
        contact_ids = []
        primary_contact_name = None
        primary_contact_title = None

        if "contacts" in associations:
            for cont_id in associations["contacts"][:10]:  # Limit to 10 contacts
                contact_ids.append(f"contact_{cont_id}")
                if cont_id in self.contacts_cache:
                    cont_data = self.contacts_cache[cont_id]
                    full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
                    if full_name:
                        contact_names.append(full_name)
                        if not primary_contact_name:
                            primary_contact_name = full_name
                            primary_contact_title = cont_data.get("jobtitle", "")
        
        # Get associated ticket IDs
        ticket_ids = []
        if "tickets" in associations:
            ticket_ids = [f"ticket_{tid}" for tid in associations["tickets"][:10]]  # Limit to 10 tickets
        
        # Basic deal metrics
        amount = float(properties.get("amount", 0) or 0)
        probability = float(properties.get("hs_forecast_probability", 0) or 0)

        # Build document structure
        doc = {
            "type": "core",
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
                "contact_names": contact_names,
                "primary_contact_name": primary_contact_name,
                "primary_contact_title": primary_contact_title,
                
                # Hierarchical Reference Structure (for navigation)
                "linked_company_ids": company_ids,
                "linked_contact_ids": contact_ids,
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
                    "text": self._generate_deal_summary(properties, primary_company_name, primary_contact_name, primary_contact_title)
                },
                {
                    "title": "Key Information",
                    "text": self._generate_deal_key_info(properties, company_names, contact_names)
                }
            ]
        }
        
        return doc

    def _build_company_document(self, company: Dict, associations: Dict) -> Dict:
        """Build a simplified company document."""
        properties = company.get("properties", {})
        company_id = company["id"]

        # Get associated contact names
        contact_names = []
        contact_ids = []
        for cont_id in associations.get("contacts", [])[:20]:  # Limit to 20 contacts
            contact_ids.append(f"contact_{cont_id}")
            if cont_id in self.contacts_cache:
                cont_data = self.contacts_cache[cont_id]
                full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
                if full_name:
                    contact_names.append(full_name)

        # Get associated IDs
        deal_ids = [f"deal_{did}" for did in associations.get("deals", [])][:20]  # Limit to 20 deals
        ticket_ids = [f"ticket_{tid}" for tid in associations.get("tickets", [])][:10]  # Limit to 10 tickets

        deal_count = len(associations.get("deals", []))
        contact_count = len(associations.get("contacts", []))
        
        # Basic company metrics
        annual_revenue = float(properties.get("annualrevenue", 0) or 0)
        employee_count = int(properties.get("numberofemployees", 0) or 0)
        
        doc = {
            "type": "core",
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
                "contact_names": contact_names,  # Names of associated contacts

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

        # Get associated company names
        company_names = []
        company_ids = []
        company_name = None  # Primary company for display
        if "companies" in associations and associations["companies"]:
            for comp_id in associations["companies"]:
                company_ids.append(f"company_{comp_id}")
                if comp_id in self.companies_cache:
                    comp_name = self.companies_cache[comp_id].get("name", "")
                    if comp_name:
                        company_names.append(comp_name)
                        if not company_name:  # Set first as primary
                            company_name = comp_name
        
        # Get associated deals and tickets
        deal_ids = [f"deal_{did}" for did in associations.get("deals", [])][:10]  # Limit to 10 deals
        ticket_ids = [f"ticket_{tid}" for tid in associations.get("tickets", [])][:10]  # Limit to 10 tickets
        
        doc = {
            "type": "core",
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
                "company_name": company_name or properties.get("company", ""),  # Primary company for display
                "company_names": company_names,  # All associated companies
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
        company_names = []
        contact_names = []
        company_name = None  # Primary company name for display
        contact_name = None  # Primary contact name for display
        company_ids = []
        contact_ids = []
        deal_ids = []

        if "companies" in associations and associations["companies"]:
            company_ids = [f"company_{cid}" for cid in associations["companies"]]
            for comp_id in associations["companies"]:
                if comp_id in self.companies_cache:
                    comp_name = self.companies_cache[comp_id].get("name", "")
                    if comp_name:
                        company_names.append(comp_name)
                        if not company_name:  # Set first as primary
                            company_name = comp_name

        # Get contact details
        if "contacts" in associations and associations["contacts"]:
            contact_ids = [f"contact_{cid}" for cid in associations["contacts"][:10]]
            for cont_id in associations["contacts"][:10]:
                if cont_id in self.contacts_cache:
                    cont_data = self.contacts_cache[cont_id]
                    full_name = f"{cont_data.get('firstname', '')} {cont_data.get('lastname', '')}".strip()
                    if full_name:
                        contact_names.append(full_name)
                        if not contact_name:  # Set first as primary
                            contact_name = full_name
        
        if "deals" in associations:
            deal_ids = [f"deal_{did}" for did in associations["deals"][:10]]
        
        doc = {
            "type": "core",
            "id": f"ticket_{ticket_id}",
            "title": f"Ticket: {properties.get('subject', 'No Subject')} - {company_name or 'Unknown Company'}",
            "metadata": {
                "object_type": "ticket",
                "ticket_id": ticket_id,
                "subject": properties.get("subject", ""),
                "priority": properties.get("hs_ticket_priority", ""),
                "stage": properties.get("hs_pipeline_stage", ""),
                "company_name": company_name,  # Primary company for display
                "contact_name": contact_name,  # Primary contact for display
                "company_names": company_names,  # All associated companies
                "contact_names": contact_names,  # All associated contacts

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
            info += f"Associated companies: {', '.join(companies)}. "
        
        if contacts:
            info += f"Key contacts: {', '.join(contacts)}. "
        
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

    # Email-only mode helper methods
    def _cache_companies_for_context(self, company_ids: Set[str]) -> None:
        """Cache company data for context in email-only mode."""
        if not company_ids:
            return

        properties = ["name", "domain", "industry"]
        for comp_id in company_ids:
            try:
                url = f"{self.api_base_url}/companies/{comp_id}"
                response = requests.get(url, headers=self.headers, params={"properties": ",".join(properties)})
                if response.status_code == 200:
                    company = response.json()
                    self.companies_cache[comp_id] = company.get("properties", {})
            except Exception as e:
                logger.debug(f"Failed to cache company {comp_id}: {e}")

    def _cache_contacts_for_context(self, contact_ids: Set[str]) -> None:
        """Cache contact data for context in email-only mode."""
        if not contact_ids:
            return

        properties = ["firstname", "lastname", "email", "jobtitle"]
        for cont_id in contact_ids:
            try:
                url = f"{self.api_base_url}/contacts/{cont_id}"
                response = requests.get(url, headers=self.headers, params={"properties": ",".join(properties)})
                if response.status_code == 200:
                    contact = response.json()
                    self.contacts_cache[cont_id] = contact.get("properties", {})
            except Exception as e:
                logger.debug(f"Failed to cache contact {cont_id}: {e}")

    # Utility methods
    def _fetch_all_objects(self, object_type: str, properties: List[str], date_field: str = None) -> List[Dict[str, Any]]:
        """Fetch all records for a given HubSpot CRM object type with pagination and optional date filtering.

        Args:
            object_type: The type of HubSpot object to fetch
            properties: List of properties to retrieve
            date_field: The field to use for date filtering (e.g., 'createdate', 'hs_createdate')
        """
        all_objects = []
        after_token = None
        total_fetched = 0
        total_filtered = 0

        logger.info(f"Starting to fetch all '{object_type}' objects.")

        # Log date filtering configuration
        if date_field and (self.start_date or self.end_date):
            logger.info(f"Date filter active: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'no start'} to {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'no end'}")
            logger.info(f"Using field '{date_field}' for date filtering (client-side)")

        # Standard API approach (same as original PR implementation)
        api_endpoint = f"{self.api_base_url}/{object_type}"

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
                total_fetched += len(results)

                # Apply date filtering if configured
                if date_field and (self.start_date or self.end_date):
                    filtered_results = []
                    for obj in results:
                        date_value = obj.get("properties", {}).get(date_field)
                        if self._is_within_date_range(date_value):
                            filtered_results.append(obj)
                        else:
                            total_filtered += 1
                            self.stats['filtered_by_date'] += 1
                            # Log sample of filtered items for debugging
                            if total_filtered <= 5:
                                logger.debug(f"Filtered out {object_type} with {date_field}={date_value}")
                    results = filtered_results

                    if len(results) != len(data.get("results", [])):
                        logger.info(f"Date filter: kept {len(results)} out of {len(data.get('results', []))} {object_type} objects")

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

        if total_filtered > 0:
            logger.info(f"Date filtering summary: Filtered out {total_filtered} '{object_type}' objects, kept {len(all_objects)} objects")
            logger.info(f"Date range used: {self.start_date.strftime('%Y-%m-%d') if self.start_date else 'no start'} to {self.end_date.strftime('%Y-%m-%d') if self.end_date else 'no end'}")
        logger.info(f"Finished fetching. Found a total of {len(all_objects)} '{object_type}' objects after filtering.")
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


class HubspotObjectProcessor:
    """Ray actor for processing HubSpot objects in parallel."""

    def __init__(self, cfg: OmegaConf, indexer: Indexer, object_type: str):
        self.cfg = cfg
        self.indexer = indexer
        self.object_type = object_type
        self.hubspot_customer_id = cfg.hubspot_crawler.hubspot_customer_id
        self.api_base_url = "https://api.hubapi.com/crm/v3/objects"
        self.headers = {
            "Authorization": f"Bearer {cfg.hubspot_crawler.hubspot_api_key}",
            "Content-Type": "application/json"
        }
        self.companies_cache = {}
        self.contacts_cache = {}
        self.start_date = None
        self.end_date = None
        self.logger = logging.getLogger(__name__)

    def setup(self, companies_cache_id, contacts_cache_id, date_filters_id=None):
        """Setup the processor with shared caches from Ray object store."""
        self.indexer.setup()
        setup_logging()

        # Get caches from Ray object store - handle both ObjectRefs and direct values
        if companies_cache_id is not None:
            # Check if it's already a dict (shouldn't happen, but defensive programming)
            if isinstance(companies_cache_id, dict):
                self.logger.warning(f"companies_cache_id is already a dict, not an ObjectRef!")
                self.companies_cache = companies_cache_id
            else:
                # It should be an ObjectRef
                try:
                    self.companies_cache = ray.get(companies_cache_id)
                except Exception as e:
                    self.logger.error(f"Failed to get companies_cache from Ray: {e}")
                    self.logger.error(f"Type was: {type(companies_cache_id)}")
                    self.companies_cache = {}
        else:
            self.companies_cache = {}

        if contacts_cache_id is not None:
            if isinstance(contacts_cache_id, dict):
                self.logger.warning(f"contacts_cache_id is already a dict, not an ObjectRef!")
                self.contacts_cache = contacts_cache_id
            else:
                try:
                    self.contacts_cache = ray.get(contacts_cache_id)
                except Exception as e:
                    self.logger.error(f"Failed to get contacts_cache from Ray: {e}")
                    self.contacts_cache = {}
        else:
            self.contacts_cache = {}

        if date_filters_id is not None:
            if isinstance(date_filters_id, tuple):
                self.logger.warning(f"date_filters_id is already a tuple, not an ObjectRef!")
                self.start_date, self.end_date = date_filters_id
            else:
                try:
                    self.start_date, self.end_date = ray.get(date_filters_id)
                except Exception as e:
                    self.logger.error(f"Failed to get date_filters from Ray: {e}")
                    self.start_date = None
                    self.end_date = None
        else:
            self.start_date = None
            self.end_date = None

    def process_company_with_associations(self, company: Dict, associations: Dict) -> Tuple[bool, int]:
        """Process a single company with pre-fetched associations.

        This is the optimized version that doesn't make API calls.
        """
        errors = 0
        indexed = False
        try:
            # Build document with pre-fetched associations
            doc = self._build_company_document(company, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing company {company['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_company(self, company: Dict) -> Tuple[bool, int]:
        """Process a single company (legacy method that fetches associations)."""
        errors = 0
        indexed = False
        try:
            # Get associations
            associations = self._get_associations(company["id"], "company")

            # Build document
            doc = self._build_company_document(company, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing company {company['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_contact_with_associations(self, contact: Dict, associations: Dict) -> Tuple[bool, int]:
        """Process a single contact with pre-fetched associations.

        This is the optimized version that doesn't make API calls.
        """
        errors = 0
        indexed = False
        try:
            # Build document with pre-fetched associations
            doc = self._build_contact_document(contact, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing contact {contact['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_deal(self, deal: Dict) -> Tuple[bool, int]:
        """Process a single deal."""
        errors = 0
        indexed = False
        try:
            # Get associations
            associations = self._get_associations(deal["id"], "deal")

            # Build document
            doc = self._build_deal_document(deal, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing deal {deal['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_deal_with_associations(self, deal: Dict, associations: Dict) -> Tuple[bool, int]:
        """Process a single deal with pre-fetched associations.

        This is the optimized version that doesn't make API calls.
        """
        errors = 0
        indexed = False
        try:
            # Build document with pre-fetched associations
            doc = self._build_deal_document(deal, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing deal {deal['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_contact(self, contact: Dict) -> Tuple[bool, int]:
        """Process a single contact."""
        errors = 0
        indexed = False
        try:
            # Get associations
            associations = self._get_associations(contact["id"], "contact")

            # Build document
            doc = self._build_contact_document(contact, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing contact {contact['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_ticket(self, ticket: Dict) -> Tuple[bool, int]:
        """Process a single ticket."""
        errors = 0
        indexed = False
        try:
            # Get associations
            associations = self._get_associations(ticket["id"], "ticket")

            # Build document
            doc = self._build_ticket_document(ticket, associations)

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing ticket {ticket['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    def process_engagement(self, engagement: Dict, engagement_type: str) -> Tuple[bool, int]:
        """Process a single engagement."""
        errors = 0
        indexed = False
        try:
            # Get associations
            associations = self._get_engagement_associations(engagement["id"], engagement_type)

            # Build document
            doc = self._build_engagement_document(engagement, engagement_type, associations)

            # Skip empty engagements
            if self._is_engagement_empty(doc, engagement_type):
                self.logger.debug(f"Skipping empty {engagement_type} {engagement['id']}")
                return False, 0

            # Index document
            indexed = self.indexer.index_document(doc)

        except Exception as e:
            self.logger.error(f"Error processing {engagement_type} {engagement['id']}: {str(e)}")
            errors = 1

        return indexed, errors

    # Copy all the building and helper methods from the main class
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
                self.logger.debug(f"Error getting associations for {object_type} {object_id}: {e}")

        return associations

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
                self.logger.debug(f"Error getting associations for {engagement_type} {engagement_id}: {e}")

        return associations

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
            "type": "core",
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
                    "text": self._generate_company_overview_text(properties)
                },
                {
                    "title": "Key Information",
                    "text": self._generate_company_key_info_text(properties, deal_count, contact_count)
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
            company_ids = [f"company_{cid}" for cid in associations["companies"]]
            comp_id = associations["companies"][0]
            if comp_id in self.companies_cache:
                company_name = self.companies_cache[comp_id].get("name", "")

        # Get associated deals and tickets
        deal_ids = [f"deal_{did}" for did in associations.get("deals", [])][:10]  # Limit to 10 deals
        ticket_ids = [f"ticket_{tid}" for tid in associations.get("tickets", [])][:10]  # Limit to 10 tickets

        doc = {
            "type": "core",
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
                "company_name": company_name or properties.get("company", ""),  # Primary company for display
                "company_names": company_names,  # All associated companies
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
                    "text": self._generate_contact_profile_text(properties, company_name)
                },
                {
                    "title": "Contact Information",
                    "text": self._generate_contact_info_text(properties, associations)
                }
            ]
        }

        return doc

    def _build_deal_document(self, deal: Dict, associations: Dict) -> Dict:
        """Build a simplified deal document with denormalized data."""
        # Delegate to the main class method since it needs complex caching logic
        # Import locally to avoid circular dependency
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from crawlers.hubspot_crawler import HubspotCrawler

        # Create a minimal crawler instance just for the method call
        # We pass empty strings for unused parameters to avoid initializing unnecessary components
        deal_crawler = object.__new__(HubspotCrawler)
        deal_crawler.companies_cache = self.companies_cache
        deal_crawler.contacts_cache = self.contacts_cache
        deal_crawler.hubspot_customer_id = self.hubspot_customer_id
        return deal_crawler._build_deal_document(deal, associations)

    def _build_ticket_document(self, ticket: Dict, associations: Dict) -> Dict:
        """Build a simplified ticket document."""
        # Delegate to the main class method
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from crawlers.hubspot_crawler import HubspotCrawler

        ticket_crawler = object.__new__(HubspotCrawler)
        ticket_crawler.companies_cache = self.companies_cache
        ticket_crawler.contacts_cache = self.contacts_cache
        ticket_crawler.hubspot_customer_id = self.hubspot_customer_id
        return ticket_crawler._build_ticket_document(ticket, associations)

    def _build_engagement_document(self, engagement: Dict, engagement_type: str, associations: Dict) -> Dict:
        """Build an engagement document."""
        # Delegate to the main class method
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from crawlers.hubspot_crawler import HubspotCrawler

        engagement_crawler = object.__new__(HubspotCrawler)
        engagement_crawler.companies_cache = self.companies_cache
        engagement_crawler.contacts_cache = self.contacts_cache
        engagement_crawler.hubspot_customer_id = self.hubspot_customer_id
        return engagement_crawler._build_engagement_document(engagement, engagement_type, associations)

    def _generate_company_overview_text(self, properties: Dict) -> str:
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

    def _generate_company_key_info_text(self, properties: Dict, deals: int, contacts: int) -> str:
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

    def _generate_contact_profile_text(self, properties: Dict, company: str) -> str:
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

    def _generate_contact_info_text(self, properties: Dict, associations: Dict) -> str:
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

    def _is_engagement_empty(self, doc: Dict, engagement_type: str) -> bool:
        """Check if an engagement document has meaningful content.

        Returns True if the engagement should be skipped due to lack of content.
        """
        # Check the main content section
        sections = doc.get("sections", [])
        if not sections:
            return True

        # Get the main content text (usually first section)
        main_content = ""
        for section in sections:
            if section.get("title") == "Engagement Details":
                main_content = section.get("text", "")
                break

        # Type-specific empty checks
        if engagement_type == "emails":
            # For emails, check if there's actual email text beyond the subject
            if "No content available" in main_content or "Content:" not in main_content:
                return True
            # Extract content after "Content:" and check if it's meaningful
            if "Content:" in main_content:
                email_content = main_content.split("Content:")[-1].strip()
                if not email_content or len(email_content) < 10:
                    return True

        elif engagement_type == "notes":
            # For notes, check if there's actual note body
            if "Note: No content" in main_content or len(main_content) < 20:
                return True

        elif engagement_type == "meetings":
            # For meetings, check if there's meeting body/notes
            if "Notes:" not in main_content or "Meeting:" in main_content and len(main_content) < 50:
                return True

        elif engagement_type == "calls":
            # For calls, having just direction and duration might be okay, but check for notes
            if "Notes:" not in main_content and len(main_content) < 30:
                return True

        elif engagement_type == "tasks":
            # For tasks, check if there's actual task details
            if "Details:" not in main_content and len(main_content) < 40:
                return True

        return False

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