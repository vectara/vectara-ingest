import sys
import unittest
from unittest.mock import MagicMock, patch

# Some transitive imports (core.summary) require cairosvg, which pulls in a
# native libcairo that isn't present in all dev environments. Stub it out.
sys.modules.setdefault('cairosvg', MagicMock())

from googleapiclient.errors import HttpError

from crawlers.gdrive_crawler import (
    ADMIN_GROUP_MEMBER_SCOPE,
    DRIVE_LABELS_SCOPE,
    DRIVE_READONLY_SCOPE,
    UserWorker,
    build_scopes,
    extract_acl_metadata,
)


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    resp.reason = "mocked"
    return HttpError(resp=resp, content=b"{}")


def _perm(pid, **kw):
    out = {"id": pid}
    out.update(kw)
    return out


class TestBuildScopes(unittest.TestCase):
    def test_default_only_drive_readonly(self):
        self.assertEqual(build_scopes(None), [DRIVE_READONLY_SCOPE])
        self.assertEqual(build_scopes({}), [DRIVE_READONLY_SCOPE])

    def test_expand_groups_adds_admin_scope(self):
        scopes = build_scopes({"expand_groups": True})
        self.assertIn(ADMIN_GROUP_MEMBER_SCOPE, scopes)
        self.assertNotIn(DRIVE_LABELS_SCOPE, scopes)

    def test_fetch_labels_adds_labels_scope(self):
        scopes = build_scopes({"fetch_labels": True})
        self.assertIn(DRIVE_LABELS_SCOPE, scopes)
        self.assertNotIn(ADMIN_GROUP_MEMBER_SCOPE, scopes)

    def test_both_optional_scopes(self):
        scopes = build_scopes({"expand_groups": True, "fetch_labels": True})
        self.assertIn(ADMIN_GROUP_MEMBER_SCOPE, scopes)
        self.assertIn(DRIVE_LABELS_SCOPE, scopes)


class TestExtractAclMetadata(unittest.TestCase):
    def test_anyone_only_marks_public(self):
        f = {"permissions": [_perm("p1", type="anyone", role="reader")]}
        meta = extract_acl_metadata(f)
        self.assertTrue(meta["acl_is_public"])
        self.assertFalse(meta["acl_is_org_wide"])
        self.assertEqual(meta["acl_owners"], [])
        self.assertEqual(meta["acl_readers"], [])

    def test_anyone_suppressed_when_include_anyone_false(self):
        f = {"permissions": [_perm("p1", type="anyone", role="reader")]}
        meta = extract_acl_metadata(f, include_anyone=False)
        self.assertFalse(meta["acl_is_public"])

    def test_domain_grant_sets_org_wide(self):
        f = {
            "permissions": [
                _perm("p1", type="domain", role="reader", domain="vectara.com"),
            ]
        }
        meta = extract_acl_metadata(f)
        self.assertEqual(meta["acl_domains"], ["vectara.com"])
        self.assertTrue(meta["acl_is_org_wide"])
        self.assertFalse(meta["acl_is_public"])

    def test_owner_and_readers_bucketed_and_deleted_excluded(self):
        f = {
            "permissions": [
                _perm("p1", type="user", role="owner", emailAddress="A@x.com"),
                _perm("p2", type="user", role="writer", emailAddress="b@x.com"),
                _perm("p3", type="user", role="commenter", emailAddress="c@x.com"),
                _perm("p4", type="user", role="reader", emailAddress="d@x.com", deleted=True),
            ]
        }
        meta = extract_acl_metadata(f)
        self.assertEqual(meta["acl_owners"], ["a@x.com"])
        self.assertEqual(meta["acl_readers"], ["b@x.com", "c@x.com"])
        self.assertNotIn("d@x.com", meta["acl_readers"])

    def test_shared_drive_source_and_inherited_flag(self):
        f = {
            "permissions": [
                _perm(
                    "p1",
                    type="user",
                    role="reader",
                    emailAddress="u@x.com",
                    permissionDetails=[{"inherited": True}],
                )
            ]
        }
        meta = extract_acl_metadata(f, source="shared_drive")
        self.assertEqual(meta["acl_source"], "shared_drive")
        self.assertTrue(meta["acl_inherited_resolved"])
        self.assertEqual(meta["acl_readers"], ["u@x.com"])

    def test_group_expansion_populates_expanded_users(self):
        f = {
            "permissions": [
                _perm("p1", type="group", role="reader", emailAddress="eng@x.com"),
            ]
        }
        meta = extract_acl_metadata(
            f,
            group_members={"eng@x.com": {"a@x.com", "b@x.com"}},
        )
        self.assertEqual(meta["acl_groups"], ["eng@x.com"])
        self.assertEqual(meta["acl_expanded_users"], ["a@x.com", "b@x.com"])

    def test_parent_permissions_merged_and_deduped(self):
        f = {
            "permissions": [_perm("p1", type="user", role="reader", emailAddress="a@x.com")]
        }
        parent = [
            _perm("p1", type="user", role="reader", emailAddress="a@x.com"),  # dup by id
            _perm("p2", type="group", role="reader", emailAddress="eng@x.com"),
        ]
        meta = extract_acl_metadata(f, parent_permissions=parent)
        self.assertEqual(meta["acl_readers"], ["a@x.com"])
        self.assertEqual(meta["acl_groups"], ["eng@x.com"])

    def test_labels_pass_through(self):
        f = {"permissions": []}
        meta = extract_acl_metadata(f, labels=["Sensitivity=Confidential"])
        self.assertEqual(meta["acl_labels"], ["Sensitivity=Confidential"])

    def test_source_inherited_flag_variants(self):
        f = {"permissions": []}
        self.assertFalse(extract_acl_metadata(f, source="my_drive_direct")["acl_inherited_resolved"])
        self.assertFalse(extract_acl_metadata(f, source="my_drive_partial")["acl_inherited_resolved"])
        self.assertTrue(extract_acl_metadata(f, source="my_drive_resolved")["acl_inherited_resolved"])
        self.assertTrue(extract_acl_metadata(f, source="shared_drive")["acl_inherited_resolved"])


def _make_worker(abac=None, permission_display_filter=None):
    """Construct a UserWorker without touching the real __init__ path."""
    worker = UserWorker.__new__(UserWorker)
    worker.cfg = MagicMock()
    worker.cfg.gdrive_crawler = MagicMock()
    worker.cfg.gdrive_crawler.credentials_file = "/nope"
    worker.cfg.gdrive_crawler.get = MagicMock(
        side_effect=lambda key, default=None: {"auth_type": "service_account"}.get(key, default)
    )
    worker.crawler = MagicMock()
    worker.indexer = MagicMock()
    worker.creds = MagicMock()
    worker.service = MagicMock()
    worker.access_token = None
    worker.shared_cache = MagicMock()
    worker.date_threshold = None
    worker.permission_display_filter = permission_display_filter
    worker.use_ray = False
    worker.abac = abac or {}
    worker._abac_enabled = worker.abac.get('enabled', True)
    worker._abac_resolve_inherited = worker.abac.get('resolve_inherited', False)
    worker._abac_include_anyone = worker.abac.get('include_anyone', True)
    worker._abac_expand_groups = worker.abac.get('expand_groups', False)
    worker._abac_fetch_labels = worker.abac.get('fetch_labels', False)
    worker._folder_acl_cache = {}
    worker._group_member_cache = {}
    worker._admin_service = None
    worker._label_defs = None
    worker._group_expansion_warned = False
    return worker


class TestPermissionDisplayFilter(unittest.TestCase):
    def test_empty_filter_passes_all(self):
        w = _make_worker(permission_display_filter=None)
        self.assertTrue(w._passes_display_filter([]))
        self.assertTrue(w._passes_display_filter([{"displayName": "Random"}]))

    def test_filter_allows_matching_display_name(self):
        w = _make_worker(permission_display_filter=["Vectara", "all"])
        self.assertTrue(w._passes_display_filter([{"displayName": "Vectara"}]))
        self.assertTrue(w._passes_display_filter([{"displayName": "all"}]))

    def test_filter_rejects_non_matching(self):
        w = _make_worker(permission_display_filter=["Vectara"])
        self.assertFalse(w._passes_display_filter([{"displayName": "Other"}]))
        self.assertFalse(w._passes_display_filter([]))


class TestResolveParentAcl(unittest.TestCase):
    def test_shared_drive_skips_walk(self):
        w = _make_worker(abac={"resolve_inherited": True})
        perms, source = w._resolve_parent_acl({"driveId": "D1", "parents": ["F1"]})
        self.assertEqual(perms, [])
        self.assertEqual(source, "shared_drive")
        w.service.files().get.assert_not_called()

    def test_my_drive_direct_when_resolve_disabled(self):
        w = _make_worker(abac={"resolve_inherited": False})
        perms, source = w._resolve_parent_acl({"parents": ["F1"]})
        self.assertEqual(perms, [])
        self.assertEqual(source, "my_drive_direct")
        w.service.files().get.assert_not_called()

    def test_three_level_walk_unions_and_caches(self):
        w = _make_worker(abac={"resolve_inherited": True})

        folder_responses = {
            "F1": {"id": "F1", "parents": ["F2"], "permissions": [_perm("a", type="group", role="reader", emailAddress="eng@x.com")]},
            "F2": {"id": "F2", "parents": ["F3"], "permissions": [_perm("b", type="user", role="reader", emailAddress="alice@x.com")]},
            "F3": {"id": "F3", "parents": [], "permissions": [_perm("c", type="domain", role="reader", domain="x.com")]},
        }

        def fake_get(fileId, fields, supportsAllDrives):
            exec_mock = MagicMock()
            exec_mock.execute.return_value = folder_responses[fileId]
            return exec_mock

        w.service.files = MagicMock()
        w.service.files.return_value.get = MagicMock(side_effect=fake_get)

        perms, source = w._resolve_parent_acl({"parents": ["F1"]})
        self.assertEqual(source, "my_drive_resolved")
        ids = sorted(p["id"] for p in perms)
        self.assertEqual(ids, ["a", "b", "c"])

        # Second call should hit the cache: no new get invocations
        before = w.service.files.return_value.get.call_count
        perms2, source2 = w._resolve_parent_acl({"parents": ["F1"]})
        after = w.service.files.return_value.get.call_count
        self.assertEqual(before, after)
        self.assertEqual(sorted(p["id"] for p in perms2), ["a", "b", "c"])
        self.assertEqual(source2, "my_drive_resolved")

    def test_walk_http_error_yields_partial(self):
        w = _make_worker(abac={"resolve_inherited": True})

        def fake_get(fileId, fields, supportsAllDrives):
            exec_mock = MagicMock()
            exec_mock.execute.side_effect = _make_http_error(403)
            return exec_mock

        w.service.files = MagicMock()
        w.service.files.return_value.get = MagicMock(side_effect=fake_get)

        perms, source = w._resolve_parent_acl({"parents": ["F1"]})
        self.assertEqual(perms, [])
        self.assertEqual(source, "my_drive_partial")


class TestExpandGroup(unittest.TestCase):
    def test_missing_admin_user_returns_empty(self):
        w = _make_worker(abac={"expand_groups": True, "admin_delegated_user": ""})
        self.assertEqual(w._expand_group("eng@x.com"), set())

    def test_expand_paginates_and_skips_nested_group_entries(self):
        w = _make_worker(abac={"expand_groups": True, "admin_delegated_user": "admin@x.com"})

        admin_service = MagicMock()
        pages = [
            {"members": [
                {"email": "a@x.com", "type": "USER"},
                {"email": "nested@x.com", "type": "GROUP"},
            ], "nextPageToken": "tok"},
            {"members": [
                {"email": "b@x.com", "type": "USER"},
            ]},
        ]

        def fake_list(**kwargs):
            exec_mock = MagicMock()
            exec_mock.execute.return_value = pages[0] if "pageToken" not in kwargs else pages[1]
            return exec_mock

        admin_service.members.return_value.list = MagicMock(side_effect=fake_list)

        with patch.object(UserWorker, "_get_admin_service", return_value=admin_service):
            result = w._expand_group("eng@x.com")
        self.assertEqual(result, {"a@x.com", "b@x.com"})

    def test_expand_http_error_swallowed(self):
        w = _make_worker(abac={"expand_groups": True, "admin_delegated_user": "admin@x.com"})
        admin_service = MagicMock()
        exec_mock = MagicMock()
        exec_mock.execute.side_effect = _make_http_error(403)
        admin_service.members.return_value.list = MagicMock(return_value=exec_mock)
        with patch.object(UserWorker, "_get_admin_service", return_value=admin_service):
            result = w._expand_group("eng@x.com")
        self.assertEqual(result, set())

    def test_cached_results_reused(self):
        w = _make_worker(abac={"expand_groups": True, "admin_delegated_user": "admin@x.com"})
        w._group_member_cache["eng@x.com"] = {"a@x.com"}
        with patch.object(UserWorker, "_get_admin_service") as admin:
            result = w._expand_group("eng@x.com")
        self.assertEqual(result, {"a@x.com"})
        admin.assert_not_called()


class TestFetchLabels(unittest.TestCase):
    def test_selection_label_renders_title_equals_value(self):
        w = _make_worker(abac={"fetch_labels": True})
        w._label_defs = {
            "L1": {
                "title": "Sensitivity",
                "fields": {
                    "F1": {
                        "title": "Level",
                        "choices": {"C1": "Confidential"},
                    }
                },
            }
        }
        resp = {
            "labels": [
                {"id": "L1", "fields": {"F1": {"selection": ["C1"]}}},
            ]
        }
        exec_mock = MagicMock()
        exec_mock.execute.return_value = resp
        w.service.files.return_value.listLabels = MagicMock(return_value=exec_mock)

        out = w._fetch_labels("file1")
        self.assertEqual(out, ["Sensitivity=Confidential"])

    def test_listlabels_error_returns_empty(self):
        w = _make_worker(abac={"fetch_labels": True})
        w._label_defs = {}
        exec_mock = MagicMock()
        exec_mock.execute.side_effect = _make_http_error(403)
        w.service.files.return_value.listLabels = MagicMock(return_value=exec_mock)
        self.assertEqual(w._fetch_labels("file1"), [])


if __name__ == "__main__":
    unittest.main()
