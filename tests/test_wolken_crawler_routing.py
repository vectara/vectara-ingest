from unittest.mock import MagicMock

from tests.test_wolken_crawler import _make_crawler


def _make_routing_crawler():
    crawler = _make_crawler()
    crawler.corpus_key = "default-wolken-kb"
    crawler.endpoint = "https://api.vectara.io"
    crawler.api_key = "test-api-key"
    crawler.mode = "multi_corpus"
    crawler.corpus_mappings = {
        "vcf-wolken-kb": ["VMware Cloud Foundation"],
        "tanzu-wolken-kb": ["Tanzu"],
    }
    crawler.product_fields = ["productname", "articleOtherInfo.products"]
    crawler.metadata_product_key = "product"
    crawler.acl_fields = ["entitlements", "articleOtherInfo.accessGroups"]
    crawler.entitlements_metadata_key = "entitlements"
    crawler.default_entitlements = ["public"]
    crawler.indexers = {
        "default-wolken-kb": MagicMock(),
        "vcf-wolken-kb": MagicMock(),
        "tanzu-wolken-kb": MagicMock(),
    }
    return crawler


class TestWolkenRoutingAndAcl:

    def test_extract_products_from_json_string_and_nested_fields(self):
        crawler = _make_routing_crawler()
        details = {
            "productname": '["VMware Cloud Foundation", "Tanzu"]',
            "articleOtherInfo": {
                "products": ["VMware Cloud Foundation", "Aria"]
            },
        }

        products = crawler._extract_products(details)

        assert products == ["VMware Cloud Foundation", "Tanzu", "Aria"]

    def test_extract_entitlements_from_defaults_and_configured_fields(self):
        crawler = _make_routing_crawler()
        details = {
            "entitlements": "premium, support",
            "articleOtherInfo": {
                "accessGroups": ["vcf-users", {"name": "admins"}]
            },
        }

        entitlements = crawler._extract_entitlements(details)

        assert entitlements == ["public", "premium", "support", "vcf-users", "admins"]

    def test_determine_target_corpora_routes_to_all_matching_mappings(self):
        crawler = _make_routing_crawler()
        details = {
            "productname": '["VMware Cloud Foundation", "Tanzu"]',
        }

        target_corpora = crawler._determine_target_corpora(details)

        assert target_corpora == ["vcf-wolken-kb", "tanzu-wolken-kb"]

    def test_determine_target_corpora_falls_back_to_primary_corpus(self):
        crawler = _make_routing_crawler()
        details = {
            "articleId": 123,
            "productname": '["Unmapped Product"]',
        }

        target_corpora = crawler._determine_target_corpora(details)

        assert target_corpora == ["default-wolken-kb"]

    def test_index_article_adds_target_corpus_metadata_per_destination(self):
        crawler = _make_routing_crawler()
        details = {"productname": '["VMware Cloud Foundation", "Tanzu"]'}
        metadata = {"source": "wolken_kb", "entitlements": ["public"]}

        succeeded = crawler._index_article(
            doc_id="wolken-kb-123",
            texts=["body"],
            titles=["Introduction"],
            metadata=metadata,
            title="Article title",
            details=details,
            article={},
        )

        assert succeeded is True
        crawler.indexers["vcf-wolken-kb"].index_segments.assert_called_once()
        crawler.indexers["tanzu-wolken-kb"].index_segments.assert_called_once()
        assert (
            crawler.indexers["vcf-wolken-kb"].index_segments.call_args.kwargs["doc_metadata"]["target_corpus"]
            == "vcf-wolken-kb"
        )
        assert (
            crawler.indexers["tanzu-wolken-kb"].index_segments.call_args.kwargs["doc_metadata"]["target_corpus"]
            == "tanzu-wolken-kb"
        )
