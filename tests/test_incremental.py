"""Tests for incremental reindexing (core/incremental.py + indexer/spider wiring).

Covers the corpus-as-manifest design: the composite content+metadata+config fingerprint,
the cheap-signal comparator, the deletion safety guard (partial-crawl / sub-doc / scoping),
the always-on content hash, _list_docs surfacing + source scoping, the indexer skip/stamp
hook, and the sitemap <lastmod> parser.
"""
import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault('cairosvg', MagicMock())

from core.incremental import (
    compute_fingerprint, config_signature, build_manifest, source_is_newer,
    plan_deletions, ManifestEntry,
)
from core.indexer_utils import extract_last_modified


class TestComputeFingerprint(unittest.TestCase):
    def test_same_inputs_same_fingerprint(self):
        a = compute_fingerprint("h", {"url": "u", "acl_groups": ["g1"]}, "cfg")
        b = compute_fingerprint("h", {"url": "u", "acl_groups": ["g1"]}, "cfg")
        self.assertEqual(a, b)

    def test_content_change_changes_fingerprint(self):
        a = compute_fingerprint("h1", {"url": "u"}, "cfg")
        b = compute_fingerprint("h2", {"url": "u"}, "cfg")
        self.assertNotEqual(a, b)

    def test_metadata_only_change_changes_fingerprint(self):
        # The GDrive ACL case: identical bytes, different acl_groups must re-index.
        a = compute_fingerprint("h", {"url": "u", "acl_groups": ["g1"]}, "cfg")
        b = compute_fingerprint("h", {"url": "u", "acl_groups": ["g2"]}, "cfg")
        self.assertNotEqual(a, b)

    def test_config_change_changes_fingerprint(self):
        a = compute_fingerprint("h", {"url": "u"}, "cfgA")
        b = compute_fingerprint("h", {"url": "u"}, "cfgB")
        self.assertNotEqual(a, b)

    def test_reserved_keys_excluded(self):
        # Stamping our own fields back into metadata must not perturb the fingerprint.
        base = compute_fingerprint("h", {"url": "u", "acl_groups": ["g1"]}, "cfg")
        stamped = compute_fingerprint("h", {
            "url": "u", "acl_groups": ["g1"],
            "fingerprint": "x", "content_hash": "y", "source": "s",
            "last_updated": "2024-01-01", "file_name": "f", "parent_doc_id": "p",
        }, "cfg")
        self.assertEqual(base, stamped)

    def test_volatile_keys_excluded(self):
        # Per-run volatile fields (RSS crawl_date, sitemap_lastmod) must not enter the
        # fingerprint, else every run would look changed.
        base = compute_fingerprint("h", {"url": "u"}, "cfg")
        with_volatile = compute_fingerprint("h", {
            "url": "u", "crawl_date": "2024-06-18", "crawl_date_int": 1718668800,
            "sitemap_lastmod": "2024-06-10",
        }, "cfg")
        self.assertEqual(base, with_volatile)


class TestConfigSignature(unittest.TestCase):
    def _cfg(self, doc_processing=None, vectara=None):
        from omegaconf import OmegaConf
        return OmegaConf.create({
            "doc_processing": doc_processing or {},
            "vectara": vectara or {},
        })

    def test_stable_and_sensitive(self):
        a = config_signature(self._cfg({"doc_parser": "docling", "extract_metadata": ["q1"]}))
        b = config_signature(self._cfg({"doc_parser": "docling", "extract_metadata": ["q1"]}))
        c = config_signature(self._cfg({"doc_parser": "docling", "extract_metadata": ["q2"]}))
        d = config_signature(self._cfg({"doc_parser": "unstructured", "extract_metadata": ["q1"]}))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)   # extract_metadata change
        self.assertNotEqual(a, d)   # doc_parser change

    def test_irrelevant_keys_ignored(self):
        a = config_signature(self._cfg({"doc_parser": "docling"}, {"corpus_key": "k1"}))
        b = config_signature(self._cfg({"doc_parser": "docling"}, {"corpus_key": "k2"}))
        self.assertEqual(a, b)


class TestSourceIsNewer(unittest.TestCase):
    def test_iso_and_date(self):
        self.assertTrue(source_is_newer("2024-02-01", "2024-01-01"))
        self.assertFalse(source_is_newer("2024-01-01", "2024-01-01"))
        self.assertFalse(source_is_newer("2024-01-01", "2024-02-01"))

    def test_rfc822(self):
        self.assertTrue(source_is_newer("Tue, 01 Feb 2024 00:00:00 GMT",
                                        "Mon, 01 Jan 2024 00:00:00 GMT"))

    def test_epoch(self):
        self.assertTrue(source_is_newer(2000, 1000))
        self.assertFalse(source_is_newer(1000, 2000))

    def test_fail_safe_on_missing_or_garbage(self):
        self.assertTrue(source_is_newer(None, "2024-01-01"))      # missing current -> fetch
        self.assertTrue(source_is_newer("2024-01-01", None))      # missing stored -> fetch
        self.assertTrue(source_is_newer("garbage", "2024-01-01")) # unparseable -> fetch

    def test_mixed_iso_zulu(self):
        self.assertTrue(source_is_newer("2024-02-01T00:00:00Z", "2024-01-01"))


class TestPlanDeletions(unittest.TestCase):
    def _manifest(self):
        return {
            "a": ManifestEntry(doc_id="a"),
            "b": ManifestEntry(doc_id="b"),
            "c": ManifestEntry(doc_id="c"),
            "d": ManifestEntry(doc_id="d"),
            "a_img_0": ManifestEntry(doc_id="a_img_0", parent_doc_id="a"),
        }

    def test_deletes_only_orphans(self):
        to_del, refused = plan_deletions(self._manifest(), {"a", "b", "c"}, True, 0.5)
        self.assertFalse(refused)
        self.assertEqual(set(to_del), {"d"})

    def test_subdoc_kept_when_parent_present(self):
        to_del, _ = plan_deletions(self._manifest(), {"a", "b", "c"}, True, 0.5)
        self.assertNotIn("a_img_0", to_del)

    def test_subdoc_deleted_when_parent_absent(self):
        # 'a' removed at source -> its image sub-doc should go too. ratio 0 to bypass guard.
        to_del, refused = plan_deletions(self._manifest(), {"b", "c", "d"}, True, 0.0)
        self.assertFalse(refused)
        self.assertIn("a_img_0", to_del)
        self.assertIn("a", to_del)

    def test_ratio_guard_refuses_partial_crawl(self):
        to_del, refused = plan_deletions(self._manifest(), {"a"}, True, 0.5)
        self.assertTrue(refused)
        self.assertEqual(to_del, [])

    def test_incomplete_listing_refuses(self):
        to_del, refused = plan_deletions(self._manifest(), {"a", "b", "c"}, False, 0.5)
        self.assertTrue(refused)
        self.assertEqual(to_del, [])

    def test_ratio_zero_disables_guard(self):
        to_del, refused = plan_deletions(self._manifest(), {"a"}, True, 0.0)
        self.assertFalse(refused)
        self.assertEqual(set(to_del), {"b", "c", "d"})  # a_img_0 kept (parent a present)

    def test_empty_manifest_noop(self):
        to_del, refused = plan_deletions({}, set(), True, 0.5)
        self.assertEqual(to_del, [])
        self.assertFalse(refused)

    def test_ratio_counts_primaries_only(self):
        # 2 primary files + 8 image sub-docs in corpus; this crawl saw both files. The ratio
        # must compare 2 present vs 2 primaries (1.0), not 2 vs 10 (0.2) which would refuse.
        m = {"f1": ManifestEntry(doc_id="f1"), "f2": ManifestEntry(doc_id="f2")}
        for i in range(8):
            m[f"f1_img_{i}"] = ManifestEntry(doc_id=f"f1_img_{i}", parent_doc_id="f1")
        to_del, refused = plan_deletions(m, {"f1", "f2"}, True, 0.5)
        self.assertFalse(refused)
        self.assertEqual(to_del, [])

    def test_file_crawler_subdoc_kept_via_present_keys(self):
        # File crawlers key present_keys on the same doc_id used as a sub-doc's parent_doc_id,
        # and the parent file itself may have no primary doc (split PDF). The sub-doc must be
        # kept when its parent key is present.
        m = {
            "split_part_0": ManifestEntry(doc_id="split_part_0", parent_doc_id="bigfile-key"),
            "split_part_1": ManifestEntry(doc_id="split_part_1", parent_doc_id="bigfile-key"),
        }
        to_del, refused = plan_deletions(m, {"bigfile-key"}, True, 0.0)
        self.assertFalse(refused)
        self.assertEqual(to_del, [])


class TestExtractLastModifiedHash(unittest.TestCase):
    def test_hash_present_in_every_branch(self):
        # date-bearing HTML (meta tag) still carries a content_hash
        with_date = extract_last_modified("u", '<meta http-equiv="last-modified" content="Mon, 01 Jan 2024 00:00:00 GMT"><p>x</p>')
        self.assertIn("content_hash", with_date)
        self.assertTrue(with_date["content_hash"])
        # no-date HTML (hash fallback branch)
        no_date = extract_last_modified("u", "<html><body>hello</body></html>")
        self.assertIn("content_hash", no_date)
        self.assertEqual(no_date["detection_method"], "hash")

    def test_hash_changes_with_content(self):
        h1 = extract_last_modified("u", "<p>a</p>")["content_hash"]
        h2 = extract_last_modified("u", "<p>b</p>")["content_hash"]
        h_same = extract_last_modified("u", "<p>a</p>")["content_hash"]
        self.assertNotEqual(h1, h2)
        self.assertEqual(h1, h_same)


class TestIndexerIncrementalHook(unittest.TestCase):
    """Indexer._incremental_skip + _list_docs surfacing, without a real Indexer __init__."""

    def _indexer(self, incremental=True):
        from core.indexer import Indexer
        ix = Indexer.__new__(Indexer)
        ix.incremental = incremental
        ix.source_tag = "website"
        ix.config_sig = "CFG"
        ix.last_skip_reason = None
        ix.verbose = False
        ix.api_url = "https://api.example.test"
        ix.corpus_key = "ck"
        ix.api_key = "key"
        ix.x_source = "vectara-ingest-website"
        ix.session = MagicMock()
        return ix

    def test_skip_stamps_nothing_when_disabled(self):
        ix = self._indexer(incremental=False)
        md = {"url": "u"}
        skipped = ix._incremental_skip("h", md, prior_fingerprint="whatever")
        self.assertFalse(skipped)
        self.assertNotIn("fingerprint", md)
        self.assertNotIn("content_hash", md)

    def test_stamps_and_no_skip_when_changed(self):
        ix = self._indexer()
        md = {"url": "u"}
        fp = compute_fingerprint("h", {"url": "u"}, "CFG")
        skipped = ix._incremental_skip("h", md, prior_fingerprint="different")
        self.assertFalse(skipped)
        self.assertEqual(md["fingerprint"], fp)
        self.assertEqual(md["content_hash"], "h")
        self.assertEqual(md["source"], "website")

    def test_skips_when_fingerprint_matches(self):
        ix = self._indexer()
        md = {"url": "u"}
        fp = compute_fingerprint("h", {"url": "u"}, "CFG")
        skipped = ix._incremental_skip("h", md, prior_fingerprint=fp)
        self.assertTrue(skipped)
        self.assertEqual(ix.last_skip_reason, "unchanged")

    def test_metadata_change_breaks_match(self):
        ix = self._indexer()
        stored_fp = compute_fingerprint("h", {"url": "u", "acl_groups": ["g1"]}, "CFG")
        md = {"url": "u", "acl_groups": ["g2"]}  # ACL changed
        skipped = ix._incremental_skip("h", md, prior_fingerprint=stored_fp)
        self.assertFalse(skipped)  # must re-index to refresh ACLs

    def test_idempotent_when_already_stamped(self):
        ix = self._indexer()
        md = {"url": "u", "fingerprint": "preexisting"}
        skipped = ix._incremental_skip("h", md, prior_fingerprint="preexisting")
        self.assertFalse(skipped)  # short-circuits: upstream already decided

    def test_subdoc_stamp(self):
        ix = self._indexer()
        sub = {"image_id": "x"}
        ix.stamp_subdoc_metadata(sub, "parent123")
        self.assertEqual(sub["parent_doc_id"], "parent123")
        self.assertEqual(sub["source"], "website")
        self.assertTrue(ix.was_skipped() is False)  # no skip happened

    def test_index_document_skips_unchanged(self):
        # notion-style structured doc: index_document(prior_fingerprint=...) must skip an
        # unchanged document (matching fingerprint) without POSTing.
        ix = self._indexer()
        ix.static_metadata = None
        ix.use_core_indexing = False
        ix.cfg = MagicMock()
        ix._last_response_status = None
        doc = {"id": "p1", "metadata": {"url": "u", "title": "t"}, "sections": [{"text": "hello"}]}
        content_hash = __import__("hashlib").md5("hello".encode()).hexdigest()
        fp = compute_fingerprint(content_hash, {"url": "u", "title": "t"}, "CFG")
        ok = ix.index_document(dict(doc, metadata=dict(doc["metadata"])), prior_fingerprint=fp)
        self.assertTrue(ok)
        self.assertEqual(ix.last_skip_reason, "unchanged")
        ix.session.post.assert_not_called()

    def test_list_docs_surfaces_fields_no_auto_filter(self):
        ix = self._indexer()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "documents": [
                {"id": "d1", "metadata": {"url": "u1", "source": "website", "fingerprint": "f1",
                                          "content_hash": "c1", "last_updated": "2024-01-01"}},
                {"id": "d2", "metadata": {"url": "u2"}},  # missing keys -> None
            ],
            "metadata": {"page_key": None},
        }
        ix.session.get.return_value = resp
        docs = ix._list_docs()
        self.assertEqual(docs[0]["fingerprint"], "f1")
        self.assertEqual(docs[0]["source"], "website")
        self.assertIsNone(docs[1]["fingerprint"])  # no KeyError
        self.assertIsNone(docs[1]["parent_doc_id"])
        # No automatic metadata_filter is sent (source-scoping is client-side, so it does not
        # depend on the corpus having `source` as a filter attribute).
        _, kwargs = ix.session.get.call_args
        self.assertNotIn("metadata_filter", kwargs["params"])


class TestBuildManifest(unittest.TestCase):
    def test_url_keyed_normalizes(self):
        ix = MagicMock()
        ix._list_docs.return_value = [
            {"id": "d1", "url": "https://ex.com/A%20B", "source": "website", "fingerprint": "f1",
             "content_hash": "c1", "last_updated": "2024-01-01", "parent_doc_id": None},
            {"id": "d2", "url": None, "source": "website", "fingerprint": None,
             "content_hash": None, "last_updated": None, "parent_doc_id": None},  # skipped (no url)
        ]
        m = build_manifest(ix, key="url", source="website")
        self.assertEqual(len(m), 1)
        entry = next(iter(m.values()))
        self.assertEqual(entry.fingerprint, "f1")

    def test_id_keyed(self):
        ix = MagicMock()
        ix._list_docs.return_value = [
            {"id": "file123", "url": "s3://b/k", "source": "S3", "fingerprint": "f1",
             "content_hash": "c1", "last_updated": None, "parent_doc_id": None},
        ]
        m = build_manifest(ix, key="id", source="S3")
        self.assertIn("file123", m)

    def test_source_scoping_is_client_side(self):
        # A corpus shared by two crawlers: build_manifest(source="website") must include only
        # the website docs, regardless of any list-API filter support.
        ix = MagicMock()
        ix._list_docs.return_value = [
            {"id": "w1", "url": "https://a", "source": "website", "fingerprint": "f1",
             "content_hash": None, "last_updated": None, "parent_doc_id": None},
            {"id": "s1", "url": "https://b", "source": "docs", "fingerprint": "f2",
             "content_hash": None, "last_updated": None, "parent_doc_id": None},
            {"id": "n1", "url": "https://c", "source": None, "fingerprint": None,
             "content_hash": None, "last_updated": None, "parent_doc_id": None},  # legacy, no source
        ]
        m = build_manifest(ix, key="url", source="website")
        self.assertEqual(len(m), 1)
        self.assertEqual(next(iter(m.values())).doc_id, "w1")
        # Unscoped (legacy remove_old_content) returns everything with a url.
        m_all = build_manifest(ix, key="url", source=None)
        self.assertEqual(len(m_all), 3)


class TestSitemapLastmod(unittest.TestCase):
    def test_parses_lastmod_pairs(self):
        import core.spider as spider
        xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b'<url><loc>https://ex.com/a</loc><lastmod>2024-01-01</lastmod></url>'
            b'<url><loc>https://ex.com/b</loc></url>'
            b'</urlset>'
        )
        orig = spider._download
        spider._download = lambda url, session=None: xml
        try:
            pairs = spider.sitemap_to_urls_with_meta("https://ex.com/sitemap.xml")
        finally:
            spider._download = orig
        d = dict(pairs)
        self.assertEqual(d["https://ex.com/a"], "2024-01-01")
        self.assertIsNone(d["https://ex.com/b"])


if __name__ == "__main__":
    unittest.main()
