import sys
import unittest
from unittest.mock import MagicMock

# core.summary (pulled in transitively) imports cairosvg, whose native libcairo
# isn't present in all dev environments. Stub it out, matching the other tests.
sys.modules.setdefault('cairosvg', MagicMock())

from crawlers.hubspot_crawler import HubspotObjectProcessor


class TestBuildContactDocument(unittest.TestCase):
    """Regression: HubspotObjectProcessor._build_contact_document referenced an
    undefined `company_names`, raising NameError on every contact built by the
    Ray actor. Verify it no longer raises and populates the list from the
    companies cache."""

    def _make_processor(self, companies_cache):
        p = HubspotObjectProcessor.__new__(HubspotObjectProcessor)
        p.companies_cache = companies_cache
        p.hubspot_customer_id = "123"
        # Section text generators are out of scope for this regression.
        p._generate_contact_profile_text = MagicMock(return_value="profile")
        p._generate_contact_info_text = MagicMock(return_value="info")
        return p

    def test_company_names_populated_from_cache(self):
        p = self._make_processor({"c1": {"name": "Acme"}, "c2": {"name": "Globex"}})
        contact = {"id": "42", "properties": {"firstname": "Ada", "lastname": "Lovelace"}}
        associations = {"companies": ["c1", "c2"]}

        doc = p._build_contact_document(contact, associations)

        meta = doc["metadata"]
        self.assertEqual(meta["company_names"], ["Acme", "Globex"])
        self.assertEqual(meta["company_name"], "Acme")  # primary = first
        self.assertEqual(meta["linked_company_ids"], ["company_c1", "company_c2"])

    def test_company_not_in_cache_is_skipped(self):
        p = self._make_processor({"c1": {"name": "Acme"}})
        contact = {"id": "9", "properties": {}}
        associations = {"companies": ["c1", "missing"]}

        doc = p._build_contact_document(contact, associations)
        self.assertEqual(doc["metadata"]["company_names"], ["Acme"])

    def test_no_companies_yields_empty_list(self):
        p = self._make_processor({})
        doc = p._build_contact_document({"id": "7", "properties": {}}, {})
        self.assertEqual(doc["metadata"]["company_names"], [])
        self.assertEqual(doc["metadata"]["company_name"], "")


if __name__ == "__main__":
    unittest.main()
