import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Some transitive imports (core.summary) require cairosvg, which pulls in a
# native libcairo that isn't present in all dev environments. Stub it out.
sys.modules.setdefault('cairosvg', MagicMock())

from googleapiclient.errors import HttpError

from crawlers.gdrive_crawler import (
    DRIVE_LABELS_SCOPE,
    DRIVE_READONLY_SCOPE,
    FILTER_STAGES,
    GdriveCrawler,
    UserWorker,
    _union_perms_by_id,
    build_scopes,
    canonical_save_name,
    extract_acl_metadata,
    extract_folder_id,
    gdrive_content_hash,
    resolve_root_folders,
)


class TestUnionPermsById(unittest.TestCase):
    def test_dedupes_by_id_preserving_first_seen_order(self):
        perms = [_perm("a"), _perm("b"), _perm("a", role="writer")]
        out = _union_perms_by_id(perms)
        self.assertEqual([p["id"] for p in out], ["a", "b"])
        # first-seen wins: the later 'a' (role=writer) is dropped.
        self.assertNotIn("role", out[0])

    def test_shared_seen_unions_across_streams(self):
        seen = set()
        first = _union_perms_by_id([_perm("a"), _perm("b")], seen=seen)
        second = _union_perms_by_id([_perm("b"), _perm("c")], seen=seen)
        self.assertEqual([p["id"] for p in first], ["a", "b"])
        self.assertEqual([p["id"] for p in second], ["c"])
        self.assertEqual(seen, {"a", "b", "c"})

    def test_keeps_entries_without_id(self):
        out = _union_perms_by_id([{"type": "anyone"}, {"type": "anyone"}])
        self.assertEqual(len(out), 2)


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

    def test_fetch_labels_alone_does_not_add_labels_scope(self):
        """fetch_labels without enabled should NOT request the extra Labels
        consent — labels are only ever read inside the ABAC-enabled branch."""
        scopes = build_scopes({"fetch_labels": True})
        self.assertNotIn(DRIVE_LABELS_SCOPE, scopes)

    def test_enabled_and_fetch_labels_adds_labels_scope(self):
        scopes = build_scopes({"enabled": True, "fetch_labels": True})
        self.assertIn(DRIVE_LABELS_SCOPE, scopes)

    def test_enabled_without_fetch_labels_omits_labels_scope(self):
        scopes = build_scopes({"enabled": True})
        self.assertEqual(scopes, [DRIVE_READONLY_SCOPE])


class TestCanonicalSaveName(unittest.TestCase):
    """Mime type is authoritative for routing the file to the right parser:
    when we recognise the mime, the local save name must end in the canonical
    extension regardless of whatever the Drive filename does (or doesn't) say.
    Filenames in Drive are user-controlled — trailing dots, made-up extensions,
    and unrelated suffixes like ``.bak`` are all common."""

    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def test_trailing_dot_filename_gets_canonical_extension(self):
        # "Vulnerability and Patch Management Policy." with PDF mime — the
        # production case that triggered this whole fix.
        self.assertTrue(canonical_save_name("Policy.", self.PDF).endswith(".pdf"))
        self.assertNotIn("..", canonical_save_name("Policy.", self.PDF))

    def test_wrong_extension_gets_canonical_appended(self):
        # The user-controlled extension is preserved (good for debugging) but
        # the canonical one is appended so downstream extension whitelists pass.
        out = canonical_save_name("report.xyz", self.PDF)
        self.assertTrue(out.endswith(".pdf"))

    def test_missing_extension_gets_canonical_appended(self):
        self.assertEqual(canonical_save_name("weekly report", self.PDF), "weekly report.pdf")

    def test_double_extension_gets_canonical_appended(self):
        # ``.bak`` is preserved; downstream sees ``.docx`` and routes correctly.
        out = canonical_save_name("draft.docx.bak", self.DOCX)
        self.assertTrue(out.endswith(".docx"))

    def test_correct_extension_unchanged(self):
        # No double-suffix when the filename already matches.
        self.assertEqual(canonical_save_name("already.pdf", self.PDF), "already.pdf")
        self.assertEqual(canonical_save_name("data.xlsx", self.XLSX), "data.xlsx")

    def test_correct_extension_case_insensitive(self):
        # Drive returns mixed-case extensions ("REPORT.PDF"); canonical match
        # is case-insensitive so we don't double-suffix.
        self.assertEqual(canonical_save_name("REPORT.PDF", self.PDF), "REPORT.PDF")

    def test_unknown_mime_leaves_name_untouched(self):
        # If we don't recognise the mime type and stdlib can't guess one, the
        # name is returned (sans trailing dots) so save_local_file can still try.
        self.assertEqual(
            canonical_save_name("thing.foo", "application/x-unknown-blob"),
            "thing.foo",
        )

    def test_unknown_mime_strips_trailing_dot(self):
        # Trailing dots must always be normalized, even when we can't pick a
        # canonical extension. Otherwise os.path.splitext("file.bin.") yields
        # ("file.bin", ".") and save_local_file drops the real ".bin" extension,
        # causing the downstream whitelist to drop a file we could have routed.
        self.assertEqual(
            canonical_save_name("file.bin.", "application/x-unknown-blob"),
            "file.bin",
        )

    def test_none_mime_returns_name_unchanged(self):
        self.assertEqual(canonical_save_name("plain", None), "plain")

    def test_none_mime_strips_trailing_dot(self):
        # Same trailing-dot hazard when the file arrives with no mime at all.
        self.assertEqual(canonical_save_name("file.bin.", None), "file.bin")


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

    def test_shared_drive_source_recorded(self):
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
        self.assertEqual(meta["acl_readers"], ["u@x.com"])
        self.assertNotIn("acl_inherited_resolved", meta)

    def test_group_grant_recorded_without_expansion(self):
        f = {
            "permissions": [
                _perm("p1", type="group", role="reader", emailAddress="eng@x.com"),
            ]
        }
        meta = extract_acl_metadata(f)
        self.assertEqual(meta["acl_groups"], ["eng@x.com"])
        self.assertNotIn("acl_expanded_users", meta)

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

def _make_worker(abac=None, permission_display_filter=None, root_folder_ids=None):
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
    worker.shared_cache = MagicMock()
    worker.date_threshold = None
    worker.permission_display_filter = permission_display_filter
    worker.use_ray = False
    worker.abac = abac or {}
    worker._abac_enabled = worker.abac.get('enabled', True)
    worker._abac_resolve_inherited = worker.abac.get('resolve_inherited', False)
    worker._abac_include_anyone = worker.abac.get('include_anyone', True)
    worker._abac_fetch_labels = worker.abac.get('fetch_labels', False)
    worker._abac_shared_drive_admin_access = worker.abac.get('shared_drive_admin_access', False)
    worker._root_folder_ids = list(root_folder_ids or [])
    worker._folder_acl_cache = {}
    worker._drive_perms_cache = {}
    worker._label_defs = None
    worker._stats = {k: 0 for k in FILTER_STAGES}
    return worker


class TestReconcileOAuthScopes(unittest.TestCase):
    """The repo's token generator grants drive.readonly only, so enabling
    fetch_labels would otherwise kill every refresh with invalid_scope. The
    worker must drop the labels scope (and label fetching) when the saved token
    wasn't granted it, and only then."""

    def _token_file(self, scopes):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"refresh_token": "x", "scopes": scopes}, f)
        self.addCleanup(os.unlink, path)
        return path

    def test_drops_labels_scope_when_token_lacks_it(self):
        w = _make_worker(abac={"enabled": True, "fetch_labels": True})
        path = self._token_file([DRIVE_READONLY_SCOPE])
        requested = [DRIVE_READONLY_SCOPE, DRIVE_LABELS_SCOPE]
        with self.assertLogs("crawlers.gdrive_crawler", level="WARNING") as cm:
            result = w._reconcile_oauth_scopes(path, requested)
        self.assertEqual(result, [DRIVE_READONLY_SCOPE])
        self.assertFalse(w._abac_fetch_labels)
        self.assertTrue(any("Drive Labels scope" in m for m in cm.output))

    def test_keeps_labels_scope_when_granted(self):
        w = _make_worker(abac={"enabled": True, "fetch_labels": True})
        path = self._token_file([DRIVE_READONLY_SCOPE, DRIVE_LABELS_SCOPE])
        requested = [DRIVE_READONLY_SCOPE, DRIVE_LABELS_SCOPE]
        result = w._reconcile_oauth_scopes(path, requested)
        self.assertEqual(result, requested)
        self.assertTrue(w._abac_fetch_labels)

    def test_passthrough_when_labels_not_requested(self):
        # No labels in the request: nothing to reconcile, token file untouched.
        w = _make_worker(abac={"enabled": True})
        result = w._reconcile_oauth_scopes("/does/not/exist", [DRIVE_READONLY_SCOPE])
        self.assertEqual(result, [DRIVE_READONLY_SCOPE])
        self.assertFalse(w._abac_fetch_labels)

    def test_missing_file_passes_scopes_through(self):
        # Can't read grants: leave scopes as-is so get_oauth_credentials raises
        # the real FileNotFoundError instead of silently dropping labels.
        w = _make_worker(abac={"enabled": True, "fetch_labels": True})
        requested = [DRIVE_READONLY_SCOPE, DRIVE_LABELS_SCOPE]
        result = w._reconcile_oauth_scopes("/does/not/exist", requested)
        self.assertEqual(result, requested)
        self.assertTrue(w._abac_fetch_labels)


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


class TestResolvePermissionDisplayFilter(unittest.TestCase):
    """Boundary check on the config-loading path: misconfigured scalar strings
    must fail loudly instead of being silently split into characters."""

    def _crawler(self, gdrive_dict):
        c = GdriveCrawler.__new__(GdriveCrawler)
        c.cfg = MagicMock()
        c.cfg.gdrive_crawler = gdrive_dict
        return c

    def test_string_value_raises_typeerror(self):
        c = self._crawler({"permission_display_filter": "Vectara"})
        with self.assertRaises(TypeError):
            c._resolve_permission_display_filter()

    def test_list_value_passes_through(self):
        c = self._crawler({"permission_display_filter": ["Vectara", "all"]})
        self.assertEqual(
            c._resolve_permission_display_filter(), ["Vectara", "all"]
        )

    def test_explicit_null_disables_filter(self):
        c = self._crawler({"permission_display_filter": None})
        self.assertIsNone(c._resolve_permission_display_filter())

    def test_unset_defaults_to_no_filter(self):
        """Pinning the default: when the config key is absent, no display-name
        gate is applied. Earlier versions defaulted to ['Vectara','all'], which
        silently dropped most files for non-Vectara tenants."""
        c = self._crawler({})
        self.assertIsNone(c._resolve_permission_display_filter())


def _wire_drive_permissions(worker, responses_by_drive):
    """Install a fake service.permissions().list that returns the canned
    response keyed by fileId. Each response is either a dict (single page)
    or an HttpError (raised on .execute())."""
    def fake_list(**params):
        drive_id = params["fileId"]
        outcome = responses_by_drive[drive_id]
        exec_mock = MagicMock()
        if isinstance(outcome, HttpError):
            exec_mock.execute.side_effect = outcome
        else:
            exec_mock.execute.return_value = outcome
        return exec_mock

    worker.service.permissions = MagicMock()
    worker.service.permissions.return_value.list = MagicMock(side_effect=fake_list)
    return worker.service.permissions.return_value.list


class TestResolveParentAcl(unittest.TestCase):
    def test_shared_drive_fetches_drive_permissions(self):
        """A Shared Drive file with no per-file grants must surface the drive's
        member ACL, since Drive's `files.list` does not propagate drive-level
        grants onto file `permissions` arrays."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {
            "D1": {
                "permissions": [
                    _perm("dp1", type="group", role="writer", emailAddress="eng@x.com"),
                    _perm("dp2", type="user", role="organizer", emailAddress="ofer@x.com"),
                ]
            },
            # The file itself carries no extra grants (permissions.list returns
            # only what it inherits, already covered by the drive membership).
            "FILE1": {"permissions": []},
        })
        perms, source = w._resolve_parent_acl(
            {"id": "FILE1", "driveId": "D1", "parents": ["F1"]}
        )
        self.assertEqual(source, "shared_drive")
        self.assertEqual(sorted(p["id"] for p in perms), ["dp1", "dp2"])

    def test_shared_drive_cached_per_drive(self):
        """Two files in the same Shared Drive share one permissions.list call."""
        w = _make_worker(abac={"enabled": True})
        list_mock = _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="group", role="writer", emailAddress="eng@x.com")]},
        })
        w._resolve_parent_acl({"driveId": "D1"})
        w._resolve_parent_acl({"driveId": "D1"})
        self.assertEqual(list_mock.call_count, 1)

    def test_shared_drive_separate_drives_separate_fetches(self):
        """Two Shared Drives are cached independently."""
        w = _make_worker(abac={"enabled": True})
        list_mock = _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="group", role="writer", emailAddress="a@x.com")]},
            "D2": {"permissions": [_perm("dp2", type="group", role="writer", emailAddress="b@x.com")]},
        })
        perms1, _ = w._resolve_parent_acl({"driveId": "D1"})
        perms2, _ = w._resolve_parent_acl({"driveId": "D2"})
        self.assertEqual([p["id"] for p in perms1], ["dp1"])
        self.assertEqual([p["id"] for p in perms2], ["dp2"])
        self.assertEqual(list_mock.call_count, 2)

    def test_shared_drive_403_marks_partial(self):
        """When the delegated user lacks fileOrganizer on the drive, the
        permissions.list call 403s. We must not crash the crawl — instead
        return (empty, partial) so the file still indexes but operators can
        spot the gap via the acl_source metadata."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {"D1": _make_http_error(403)})
        perms, source = w._resolve_parent_acl({"driveId": "D1"})
        self.assertEqual(perms, [])
        self.assertEqual(source, "shared_drive_partial")

    def test_shared_drive_partial_is_cached(self):
        """A failing permissions.list call should be cached too — retrying
        once per file in the drive would just amplify the error and slow
        the crawl. Auth state doesn't change mid-run."""
        w = _make_worker(abac={"enabled": True})
        list_mock = _wire_drive_permissions(w, {"D1": _make_http_error(403)})
        w._resolve_parent_acl({"driveId": "D1"})
        w._resolve_parent_acl({"driveId": "D1"})
        self.assertEqual(list_mock.call_count, 1)

    def test_shared_drive_pagination_unioned(self):
        """permissions.list paginates. Make sure we walk all pages."""
        w = _make_worker(abac={"enabled": True})
        pages = [
            {"permissions": [_perm("dp1", type="user", role="reader", emailAddress="a@x.com")],
             "nextPageToken": "tok"},
            {"permissions": [_perm("dp2", type="user", role="reader", emailAddress="b@x.com")]},
        ]
        def fake_list(**params):
            page = pages.pop(0)
            exec_mock = MagicMock()
            exec_mock.execute.return_value = page
            return exec_mock
        w.service.permissions = MagicMock()
        w.service.permissions.return_value.list = MagicMock(side_effect=fake_list)
        perms, source = w._resolve_parent_acl({"driveId": "D1"})
        self.assertEqual(source, "shared_drive")
        self.assertEqual(sorted(p["id"] for p in perms), ["dp1", "dp2"])

    def test_shared_drive_admin_access_passed_when_enabled(self):
        """With shared_drive_admin_access on, permissions.list is issued with
        useDomainAdminAccess=True so a domain-admin delegated user can read the
        drive's members without a per-drive fileOrganizer role."""
        w = _make_worker(abac={"enabled": True, "shared_drive_admin_access": True})
        list_mock = _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="group", role="writer", emailAddress="eng@x.com")]},
        })
        w._resolve_parent_acl({"driveId": "D1"})
        self.assertTrue(list_mock.call_args.kwargs.get("useDomainAdminAccess"))

    def test_shared_drive_admin_access_omitted_by_default(self):
        """Default off: the param must not be sent, preserving prior behavior."""
        w = _make_worker(abac={"enabled": True})
        list_mock = _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="group", role="writer", emailAddress="eng@x.com")]},
        })
        w._resolve_parent_acl({"driveId": "D1"})
        self.assertNotIn("useDomainAdminAccess", list_mock.call_args.kwargs)

    def test_shared_drive_file_surfaces_inherited_folder_group(self):
        """Regression for the reported bug: a group granted on an intermediate
        folder is inherited by a descendant file, but Drive does not populate
        the File resource's `permissions` for shared-drive items (files.list
        returns permissions=[]). `permissions.list` on the file returns the
        inherited grant (permissionDetails.inherited=True), so it must land in
        acl_groups."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {
            "D1": {"permissions": [
                _perm("dp1", type="user", role="organizer", emailAddress="ofer@x.com"),
            ]},
            "FILE1": {"permissions": [
                _perm("fg1", type="group", role="reader", emailAddress="eng@x.com",
                      permissionDetails=[{"permissionType": "folder", "inherited": True,
                                          "inheritedFrom": "F1"}]),
            ]},
        })
        file_obj = {"id": "FILE1", "driveId": "D1", "parents": ["F1"]}
        perms, source = w._resolve_parent_acl(file_obj)
        self.assertEqual(source, "shared_drive")
        self.assertEqual(sorted(p["id"] for p in perms), ["dp1", "fg1"])
        # End-to-end: the inherited folder group must show up in acl_groups.
        meta = extract_acl_metadata(file_obj, parent_permissions=perms, source=source)
        self.assertEqual(meta["acl_groups"], ["eng@x.com"])
        self.assertEqual(meta["acl_readers"], ["ofer@x.com"])

    def test_shared_drive_file_direct_group_grant(self):
        """A group shared directly onto the file (item-level sharing) surfaces
        via permissions.list even though files.list reports permissions=[]."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="user", role="reader", emailAddress="a@x.com")]},
            "FILE1": {"permissions": [
                _perm("fg1", type="group", role="writer", emailAddress="team@x.com",
                      permissionDetails=[{"permissionType": "file", "inherited": False}]),
            ]},
        })
        perms, source = w._resolve_parent_acl(
            {"id": "FILE1", "driveId": "D1", "parents": ["D1"]}
        )
        self.assertEqual(source, "shared_drive")
        self.assertEqual(sorted(p["id"] for p in perms), ["dp1", "fg1"])

    def test_shared_drive_file_perms_deduped_against_drive_members(self):
        """A drive-membership grant also returned (inherited) by the file's
        permissions.list must not be double-counted — dedup by permission id."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {
            "D1": {"permissions": [
                _perm("dp1", type="user", role="organizer", emailAddress="ofer@x.com"),
            ]},
            "FILE1": {"permissions": [
                # Same id as the drive member, surfaced again as inherited.
                _perm("dp1", type="user", role="organizer", emailAddress="ofer@x.com",
                      permissionDetails=[{"permissionType": "member", "inherited": True}]),
                _perm("fg1", type="group", role="reader", emailAddress="eng@x.com"),
            ]},
        })
        perms, source = w._resolve_parent_acl(
            {"id": "FILE1", "driveId": "D1", "parents": ["F1"]}
        )
        self.assertEqual(source, "shared_drive")
        self.assertEqual(sorted(p["id"] for p in perms), ["dp1", "fg1"])

    def test_shared_drive_file_perms_403_marks_partial(self):
        """If the file's own permissions.list can't be read, drive membership
        still surfaces but the source downgrades to shared_drive_partial."""
        w = _make_worker(abac={"enabled": True})
        _wire_drive_permissions(w, {
            "D1": {"permissions": [_perm("dp1", type="user", role="reader", emailAddress="a@x.com")]},
            "FILE1": _make_http_error(403),
        })
        perms, source = w._resolve_parent_acl(
            {"id": "FILE1", "driveId": "D1", "parents": ["F1"]}
        )
        self.assertEqual(source, "shared_drive_partial")
        self.assertEqual([p["id"] for p in perms], ["dp1"])

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

    def test_text_label_renders_value_not_list(self):
        """Drive returns text/integer/dateString field values as arrays. They
        must render as `Title=value`, not `Title=['value']`."""
        w = _make_worker(abac={"fetch_labels": True})
        w._label_defs = {
            "L1": {"title": "Notes", "fields": {"F1": {"title": "Comment", "choices": {}}}}
        }
        resp = {"labels": [{"id": "L1", "fields": {"F1": {"text": ["hello"]}}}]}
        exec_mock = MagicMock()
        exec_mock.execute.return_value = resp
        w.service.files.return_value.listLabels = MagicMock(return_value=exec_mock)
        self.assertEqual(w._fetch_labels("file1"), ["Notes=hello"])

    def test_listlabels_error_returns_empty(self):
        w = _make_worker(abac={"fetch_labels": True})
        w._label_defs = {}
        exec_mock = MagicMock()
        exec_mock.execute.side_effect = _make_http_error(403)
        w.service.files.return_value.listLabels = MagicMock(return_value=exec_mock)
        self.assertEqual(w._fetch_labels("file1"), [])


class TestExtractFolderId(unittest.TestCase):
    def test_bare_id_passed_through(self):
        self.assertEqual(extract_folder_id("1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ"),
                         "1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ")

    def test_standard_folder_url(self):
        url = "https://drive.google.com/drive/folders/1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ"
        self.assertEqual(extract_folder_id(url), "1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ")

    def test_user_scoped_folder_url(self):
        url = "https://drive.google.com/drive/u/0/folders/1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ"
        self.assertEqual(extract_folder_id(url), "1Z5X4D5DFIeo-xEThXTkN0V4tL96EqORQ")

    def test_url_with_query_and_hash(self):
        url = "https://drive.google.com/drive/folders/abc_DEF-123?resourcekey=xyz#shared"
        self.assertEqual(extract_folder_id(url), "abc_DEF-123")

    def test_trailing_slash(self):
        url = "https://drive.google.com/drive/folders/abc_DEF-123/"
        self.assertEqual(extract_folder_id(url), "abc_DEF-123")

    def test_empty_returns_empty(self):
        self.assertEqual(extract_folder_id(""), "")
        self.assertIsNone(extract_folder_id(None))


class TestResolveRootFolders(unittest.TestCase):
    """Config-typing boundary on the root_folder key.

    A misconfigured scalar (int, dict) must fail loudly rather than degrade
    silently to a no-op crawl, the same pattern TestResolvePermissionDisplayFilter
    enforces for the display-name gate.
    """

    def test_none_returns_empty(self):
        self.assertEqual(resolve_root_folders(None), [])

    def test_empty_string_returns_empty(self):
        self.assertEqual(resolve_root_folders(""), [])

    def test_empty_list_returns_empty(self):
        self.assertEqual(resolve_root_folders([]), [])

    def test_single_bare_id_string(self):
        self.assertEqual(resolve_root_folders("abc_DEF-123"), ["abc_DEF-123"])

    def test_single_url_string(self):
        url = "https://drive.google.com/drive/folders/abc_DEF-123"
        self.assertEqual(resolve_root_folders(url), ["abc_DEF-123"])

    def test_list_of_mixed_entries_extracted(self):
        url = "https://drive.google.com/drive/folders/abc_DEF-123"
        out = resolve_root_folders([url, "0AJb-TGGUWsU4Uk9PVA"])
        self.assertEqual(out, ["abc_DEF-123", "0AJb-TGGUWsU4Uk9PVA"])

    def test_list_deduped_in_order(self):
        url = "https://drive.google.com/drive/folders/abc_DEF-123"
        out = resolve_root_folders([url, "abc_DEF-123", "xyz789"])
        self.assertEqual(out, ["abc_DEF-123", "xyz789"])

    def test_non_string_scalar_raises(self):
        with self.assertRaises(TypeError):
            resolve_root_folders(123)
        with self.assertRaises(TypeError):
            resolve_root_folders({"id": "abc"})

    def test_list_with_non_string_entry_raises(self):
        with self.assertRaises(TypeError):
            resolve_root_folders(["abc", 42])

    def test_listconfig_accepted(self):
        """OmegaConf wraps YAML lists in ListConfig before they reach the
        crawler — strict isinstance(list, tuple) rejects them. Pin the
        accepted-type contract here so we don't have to relearn this from a
        docker-logs traceback again."""
        from omegaconf import OmegaConf
        cfg = OmegaConf.create({
            "root_folder": [
                "https://drive.google.com/drive/folders/abc_DEF-123",
                "0AJb-TGGUWsU4Uk9PVA",
            ],
        })
        out = resolve_root_folders(cfg.root_folder)
        self.assertEqual(out, ["abc_DEF-123", "0AJb-TGGUWsU4Uk9PVA"])


class TestListSubtree(unittest.TestCase):
    """BFS traversal of a folder's descendants via `files().list`."""

    FOLDER_MIME = "application/vnd.google-apps.folder"
    SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

    def _wire_service(self, worker, tree):
        """Install a fake files().list that returns `tree[folder_id]` per query.

        `tree` maps parent folder id -> list of child file dicts (each with id,
        name, mimeType, and whatever else the test cares about). The query is
        parsed for the `'<id>' in parents` term to pick which bucket to return.
        """
        def fake_list(**params):
            q = params.get("q", "")
            parent = q.split("'")[1]  # "'<id>' in parents and ..."
            children = tree.get(parent, [])
            exec_mock = MagicMock()
            exec_mock.execute.return_value = {"files": list(children), "nextPageToken": None}
            return exec_mock

        worker.service.files = MagicMock()
        worker.service.files.return_value.list = MagicMock(side_effect=fake_list)
        return worker.service.files.return_value.list

    def test_bfs_collects_files_across_subfolders(self):
        w = _make_worker(root_folder_ids=["ROOT"])
        tree = {
            "ROOT": [
                {"id": "F1", "name": "sub1", "mimeType": self.FOLDER_MIME},
                {"id": "D1", "name": "a.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
            "F1": [
                {"id": "F2", "name": "sub2", "mimeType": self.FOLDER_MIME},
                {"id": "D2", "name": "b.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
            "F2": [
                {"id": "D3", "name": "c.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
        }
        self._wire_service(w, tree)

        files = w._list_subtree(w.service, "ROOT", "2020-01-01T00:00:00Z")
        ids = sorted(f["id"] for f in files)
        self.assertEqual(ids, ["D1", "D2", "D3"])

    def test_shortcuts_are_not_followed(self):
        w = _make_worker(root_folder_ids=["ROOT"])
        tree = {
            "ROOT": [
                {"id": "S1", "name": "link", "mimeType": self.SHORTCUT_MIME,
                 "shortcutDetails": {"targetId": "OUTSIDE"}},
                {"id": "D1", "name": "a.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
            # If the crawler wrongly followed the shortcut target, this would surface.
            "OUTSIDE": [
                {"id": "LEAK", "name": "leak.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
        }
        list_mock = self._wire_service(w, tree)

        files = w._list_subtree(w.service, "ROOT", "2020-01-01T00:00:00Z")
        ids = [f["id"] for f in files]
        self.assertEqual(ids, ["D1"])
        # Ensure we never queried children of OUTSIDE.
        queried_parents = [call.kwargs["q"].split("'")[1] for call in list_mock.call_args_list]
        self.assertNotIn("OUTSIDE", queried_parents)

    def test_query_filters_files_by_mtime_but_keeps_folders(self):
        """Server-side query must retain folders regardless of modifiedTime."""
        w = _make_worker(root_folder_ids=["ROOT"])
        self._wire_service(w, {"ROOT": []})
        w._list_subtree(w.service, "ROOT", "2026-01-01T00:00:00Z")

        list_mock = w.service.files.return_value.list
        q = list_mock.call_args.kwargs["q"]
        self.assertIn("'ROOT' in parents", q)
        self.assertIn("trashed=false", q)
        self.assertIn("mimeType='application/vnd.google-apps.folder'", q)
        self.assertIn("modifiedTime > '2026-01-01T00:00:00Z'", q)

    def test_display_filter_applied_to_files(self):
        w = _make_worker(root_folder_ids=["ROOT"], permission_display_filter=["Vectara"])
        tree = {
            "ROOT": [
                {"id": "D1", "name": "a.pdf", "mimeType": "application/pdf",
                 "permissions": [{"displayName": "Vectara"}]},
                {"id": "D2", "name": "b.pdf", "mimeType": "application/pdf",
                 "permissions": [{"displayName": "Other"}]},
            ],
        }
        self._wire_service(w, tree)
        files = w._list_subtree(w.service, "ROOT", "2020-01-01T00:00:00Z")
        self.assertEqual([f["id"] for f in files], ["D1"])

    def test_cycle_does_not_infinite_loop(self):
        w = _make_worker(root_folder_ids=["ROOT"])
        # F1 is a child of ROOT and (pathologically) lists ROOT as a child too.
        tree = {
            "ROOT": [{"id": "F1", "name": "sub", "mimeType": self.FOLDER_MIME}],
            "F1":   [{"id": "ROOT", "name": "cycle", "mimeType": self.FOLDER_MIME}],
        }
        self._wire_service(w, tree)
        files = w._list_subtree(w.service, "ROOT", "2020-01-01T00:00:00Z")
        self.assertEqual(files, [])


class TestCollectListableFiles(unittest.TestCase):
    """Dispatch between the user-wide list_files() sweep and per-root subtree
    walks. The multi-root case unions results and dedups by file id so a file
    that lives under two configured roots (e.g. a shortcut tree and the
    original) is indexed only once."""

    FOLDER_MIME = "application/vnd.google-apps.folder"

    def _wire_subtree(self, worker, tree):
        def fake_list(**params):
            q = params.get("q", "")
            parent = q.split("'")[1]
            exec_mock = MagicMock()
            exec_mock.execute.return_value = {"files": list(tree.get(parent, [])), "nextPageToken": None}
            return exec_mock

        worker.service.files = MagicMock()
        worker.service.files.return_value.list = MagicMock(side_effect=fake_list)

    def test_no_roots_calls_list_files(self):
        w = _make_worker(root_folder_ids=None)
        w.list_files = MagicMock(return_value=[{"id": "X"}])
        out = w._collect_listable_files("2020-01-01T00:00:00Z")
        w.list_files.assert_called_once()
        self.assertEqual([f["id"] for f in out], ["X"])

    def test_single_root_walks_subtree(self):
        w = _make_worker(root_folder_ids=["ROOT"])
        tree = {
            "ROOT": [
                {"id": "D1", "name": "a.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
        }
        self._wire_subtree(w, tree)
        w.list_files = MagicMock()
        out = w._collect_listable_files("2020-01-01T00:00:00Z")
        w.list_files.assert_not_called()
        self.assertEqual([f["id"] for f in out], ["D1"])

    def test_multiple_roots_union_dedup(self):
        w = _make_worker(root_folder_ids=["A", "B"])
        # SHARED appears under both roots; must be returned exactly once.
        tree = {
            "A": [
                {"id": "D1", "name": "a.pdf", "mimeType": "application/pdf", "permissions": []},
                {"id": "SHARED", "name": "x.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
            "B": [
                {"id": "SHARED", "name": "x.pdf", "mimeType": "application/pdf", "permissions": []},
                {"id": "D2", "name": "b.pdf", "mimeType": "application/pdf", "permissions": []},
            ],
        }
        self._wire_subtree(w, tree)
        out = w._collect_listable_files("2020-01-01T00:00:00Z")
        ids = [f["id"] for f in out]
        self.assertEqual(sorted(ids), ["D1", "D2", "SHARED"])
        self.assertEqual(ids.count("SHARED"), 1)


class TestFilterCounters(unittest.TestCase):
    """Each filter gate must (a) increment the right bucket and (b) leave
    the other buckets alone. Without this, the per-user summary line silently
    drifts from reality the moment a new gate is added."""

    FOLDER_MIME = "application/vnd.google-apps.folder"

    def _wire_service(self, worker, tree):
        def fake_list(**params):
            parent = params.get("q", "").split("'")[1]
            children = tree.get(parent, [])
            exec_mock = MagicMock()
            exec_mock.execute.return_value = {"files": list(children), "nextPageToken": None}
            return exec_mock

        worker.service.files = MagicMock()
        worker.service.files.return_value.list = MagicMock(side_effect=fake_list)

    def test_listed_counts_every_file_returned_by_drive(self):
        """listed must reflect pre-display-filter Drive output, not survivors."""
        w = _make_worker(root_folder_ids=["ROOT"], permission_display_filter=["Vectara"])
        tree = {
            "ROOT": [
                {"id": "D1", "name": "ok.pdf", "mimeType": "application/pdf",
                 "permissions": [{"displayName": "Vectara"}]},
                {"id": "D2", "name": "blocked.pdf", "mimeType": "application/pdf",
                 "permissions": [{"displayName": "Other"}]},
                {"id": "D3", "name": "blocked2.pdf", "mimeType": "application/pdf",
                 "permissions": [{"displayName": "Random"}]},
            ],
        }
        self._wire_service(w, tree)
        w._list_subtree(w.service, "ROOT", "2020-01-01T00:00:00Z")

        self.assertEqual(w._stats['listed'], 3)
        self.assertEqual(w._stats['display_name_dropped'], 2)

    def test_record_drop_rejects_unknown_bucket(self):
        """Typo guard: misspelled bucket names must blow up the test suite,
        not silently increment a phantom counter."""
        w = _make_worker()
        with self.assertRaises(KeyError):
            w._record_drop('typo_dropped', {'id': 'x', 'name': 'y', 'mimeType': 'z'}, 'reason')

    def test_summary_logs_all_stages(self):
        """The summary line is the operator's primary diagnostic — every
        bucket must be present so a drop never goes unreported."""
        w = _make_worker()
        w._stats['listed'] = 4
        w._stats['display_name_dropped'] = 1
        w._stats['indexed'] = 3

        import logging as _logging
        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w._log_filter_summary("user@example.com")

        summary = next(line for line in cm.output if "filter summary" in line)
        self.assertIn("user=user@example.com", summary)
        for stage in FILTER_STAGES:
            self.assertIn(f"{stage}=", summary)
        self.assertIn("listed=4", summary)
        self.assertIn("display_name_dropped=1", summary)
        self.assertIn("indexed=3", summary)

    def test_record_indexed_increments_only_indexed(self):
        w = _make_worker()
        w._record_indexed({'id': 'x', 'name': 'y'})
        self.assertEqual(w._stats['indexed'], 1)
        for stage in FILTER_STAGES:
            if stage != 'indexed':
                self.assertEqual(w._stats[stage], 0, f"unexpected increment of {stage}")

    def test_record_indexed_verbose_logs_acl_fields(self):
        """When ABAC is on and verbose is true, the per-file indexed line must
        carry every acl_* value so operators can confirm what the indexer
        shipped to the corpus."""
        import logging as _logging
        w = _make_worker()
        w._abac_enabled = True
        w.crawler = MagicMock()
        w.crawler.verbose = True
        file_metadata = {
            'acl_owners': ['a@x.com'],
            'acl_readers': ['b@x.com', 'c@x.com'],
            'acl_groups': ['eng@x.com'],
            'acl_domains': ['x.com'],
            'acl_is_public': False,
            'acl_is_org_wide': True,
            'acl_labels': ['Sensitivity=Confidential'],
            'acl_source': 'shared_drive',
        }

        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w._record_indexed({'id': 'x', 'name': 'y'}, file_metadata)

        line = next(ln for ln in cm.output if 'gdrive indexed' in ln)
        self.assertIn("file='y'", line)
        self.assertIn("id=x", line)
        self.assertIn("acl_source='shared_drive'", line)
        self.assertIn("acl_is_public=False", line)
        self.assertIn("acl_is_org_wide=True", line)
        self.assertIn("acl_owners=['a@x.com']", line)
        self.assertIn("'b@x.com'", line)
        self.assertIn("'c@x.com'", line)
        self.assertIn("acl_groups=['eng@x.com']", line)
        self.assertIn("acl_domains=['x.com']", line)
        self.assertIn("acl_labels=['Sensitivity=Confidential']", line)

    def test_record_indexed_verbose_logs_raw_permissions(self):
        """Raw permissions[] must appear on the verbose indexed line regardless
        of ABAC state, so operators can debug acl_* derivation (and inspect what
        Drive actually returned) even when ABAC is off. parent_permissions
        is appended only when non-empty."""
        import logging as _logging
        w = _make_worker()
        w._abac_enabled = False
        w.crawler = MagicMock()
        w.crawler.verbose = True
        perms = [
            {'id': 'p1', 'type': 'user', 'role': 'owner', 'emailAddress': 'a@x.com'},
            {'id': 'p2', 'type': 'domain', 'role': 'reader', 'domain': 'x.com'},
        ]

        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w._record_indexed({'id': 'x', 'name': 'y', 'permissions': perms})

        line = next(ln for ln in cm.output if 'gdrive indexed' in ln)
        self.assertIn("permissions=", line)
        self.assertIn("'a@x.com'", line)
        self.assertIn("'domain'", line)
        self.assertNotIn("parent_permissions=", line)

        # Non-empty parent_permissions => the parent_permissions= token appears.
        parent = [{'id': 'pp1', 'type': 'group', 'role': 'reader', 'emailAddress': 'eng@x.com'}]
        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm2:
            w._record_indexed(
                {'id': 'x', 'name': 'y', 'permissions': perms},
                parent_permissions=parent,
            )
        line2 = next(ln for ln in cm2.output if 'gdrive indexed' in ln)
        self.assertIn("parent_permissions=", line2)
        self.assertIn("'eng@x.com'", line2)

    def test_record_indexed_verbose_no_acl_when_abac_disabled(self):
        """ABAC off => keep the line compact even if file_metadata is passed.
        Guards against accidentally bloating the log for non-ABAC corpora."""
        import logging as _logging
        w = _make_worker()
        w._abac_enabled = False
        w.crawler = MagicMock()
        w.crawler.verbose = True
        file_metadata = {'acl_source': 'shared_drive', 'acl_owners': ['a@x.com']}

        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w._record_indexed({'id': 'x', 'name': 'y'}, file_metadata)

        line = next(ln for ln in cm.output if 'gdrive indexed' in ln)
        self.assertNotIn('acl_', line)

    def test_record_indexed_not_verbose_emits_no_line(self):
        """Verbose gate stays in force regardless of ABAC state."""
        import logging as _logging
        w = _make_worker()
        w._abac_enabled = True
        w.crawler = MagicMock()
        w.crawler.verbose = False
        # assertLogs requires at least one record; emit a sentinel so the
        # context manager doesn't raise, then confirm no 'gdrive indexed' line.
        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            _logging.getLogger('crawlers.gdrive_crawler').info('sentinel')
            w._record_indexed({'id': 'x', 'name': 'y'}, {'acl_source': 'shared_drive'})

        self.assertFalse(any('gdrive indexed' in ln for ln in cm.output))

    def test_dataframe_failure_records_index_error_not_indexed(self):
        """process_dataframe_file returns False on parser-init failure, unsupported
        files, and caught exceptions — none of which re-raise. The outer code must
        honor that signal, otherwise the summary line over-reports indexed and
        never increments index_error for dataframe failures."""
        w = _make_worker()
        w._summarize_images = False
        w.df_parser = MagicMock()
        w._abac_enabled = False
        w.crawler = MagicMock()
        w.crawler.verbose = False
        w.cfg.get = MagicMock(return_value={})

        file = {"id": "CSV_ID", "name": "salaries.csv", "mimeType": "text/csv"}

        with patch.object(w, "save_local_file", return_value=("/tmp/salaries.csv", None)), \
             patch("crawlers.gdrive_crawler.process_dataframe_file", return_value=False), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        self.assertEqual(w._stats['indexed'], 0)
        self.assertEqual(w._stats['index_error'], 1)


# ----- crawl_file routing: images, CSV/XLSX, Google Sheets -----


def _make_crawl_worker(summarize_images=False):
    """Worker wired for crawl_file tests (df_parser, summarize_images, no ABAC)."""
    w = _make_worker()
    w._summarize_images = summarize_images
    w.df_parser = MagicMock()
    w._abac_enabled = False
    w.crawler = MagicMock()
    w.crawler.verbose = False
    w.cfg.get = MagicMock(return_value={})
    return w


class TestCrawlFileRouting(unittest.TestCase):
    """Covers the three gaps that dropped 4/12 files from the demo dataset:
    Google Sheets export, CSV/XLSX dataframe routing, standalone image admission."""

    def _fake_save(self, path):
        """save_local_file replacement: records (file_id, name, mime) and returns (path, None)."""
        calls = []

        def save(file_id, name, mime_type=None):
            calls.append((file_id, name, mime_type))
            return path, None

        return save, calls

    def test_google_sheet_exports_as_xlsx(self):
        """Native Sheets must be exported with the xlsx MIME type + name suffix,
        mirroring the Docs->docx and Slides->pptx branches."""
        w = _make_crawl_worker()
        save, calls = self._fake_save("/tmp/budget-tracker.xlsx")

        file = {
            "id": "SHEET_ID",
            "name": "Budget Tracker",
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            pdf_mock.return_value = True
            w.crawl_file(file)

        self.assertEqual(len(calls), 1)
        _, passed_name, passed_mime = calls[0]
        self.assertEqual(passed_name, "Budget Tracker.xlsx")
        self.assertEqual(
            passed_mime,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        # Sheet exported as xlsx flows through the dataframe route, not index_file.
        pdf_mock.assert_called_once()
        w.indexer.index_file.assert_not_called()

    def test_csv_routes_to_dataframe_path(self):
        """A .csv file must go through process_dataframe_file, not index_file."""
        w = _make_crawl_worker()
        save, _ = self._fake_save("/tmp/salaries.csv")

        file = {
            "id": "CSV_ID",
            "name": "salaries.csv",
            "mimeType": "text/csv",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            pdf_mock.return_value = True
            w.crawl_file(file)

        pdf_mock.assert_called_once()
        self.assertEqual(pdf_mock.call_args.kwargs["file_path"], "/tmp/salaries.csv")
        self.assertEqual(pdf_mock.call_args.kwargs["doc_id"], "CSV_ID")
        self.assertEqual(pdf_mock.call_args.kwargs["source_name"], "gdrive")
        self.assertIs(pdf_mock.call_args.kwargs["df_parser"], w.df_parser)
        w.indexer.index_file.assert_not_called()

    def test_xlsx_routes_to_dataframe_path(self):
        """An .xlsx (incl. Sheets exported to xlsx) must go through the dataframe route."""
        w = _make_crawl_worker()
        save, _ = self._fake_save("/tmp/budget-tracker.xlsx")

        file = {
            "id": "XLSX_ID",
            "name": "Budget Tracker",  # Sheet export adds .xlsx to name
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            pdf_mock.return_value = True
            w.crawl_file(file)

        pdf_mock.assert_called_once()
        self.assertEqual(pdf_mock.call_args.kwargs["file_path"], "/tmp/budget-tracker.xlsx")
        w.indexer.index_file.assert_not_called()

    def test_png_admitted_when_summarize_images_enabled(self):
        """With summarize_images=True the crawler passes images to index_file,
        where file_processor routes them to ImageFileParser."""
        w = _make_crawl_worker(summarize_images=True)
        save, _ = self._fake_save("/tmp/logo.png")

        file = {
            "id": "PNG_ID",
            "name": "logo.png",
            "mimeType": "image/png",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        w.indexer.index_file.assert_called_once()
        self.assertEqual(w.indexer.index_file.call_args.kwargs["filename"], "/tmp/logo.png")

    def test_png_rejected_when_summarize_images_disabled(self):
        """Without the flag, images are filtered at the extension-whitelist step
        (the process-stage MIME filter also removes them; this guards crawl_file)."""
        w = _make_crawl_worker(summarize_images=False)
        save, _ = self._fake_save("/tmp/logo.png")

        file = {
            "id": "PNG_ID",
            "name": "logo.png",
            "mimeType": "image/png",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        w.indexer.index_file.assert_not_called()
        pdf_mock.assert_not_called()

    def test_docx_still_uses_index_file(self):
        """Regression guard: Google Docs (exported as .docx) must continue
        to use the standard index_file path, not the dataframe route."""
        w = _make_crawl_worker()
        save, calls = self._fake_save("/tmp/meeting-notes.docx")

        file = {
            "id": "DOC_ID",
            "name": "Meeting Notes",
            "mimeType": "application/vnd.google-apps.document",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        # Export called with .docx suffix and wordprocessingml mime.
        _, passed_name, passed_mime = calls[0]
        self.assertEqual(passed_name, "Meeting Notes.docx")
        self.assertEqual(
            passed_mime,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        w.indexer.index_file.assert_called_once()
        pdf_mock.assert_not_called()

    def test_index_file_uses_drive_file_id_as_doc_id(self):
        # The Drive file.id is immutable, so passing it as the indexer doc_id
        # guarantees a re-crawl of the same file upserts the same Vectara
        # document. Without an explicit id the indexer falls back to
        # slugify(uri), which silently rebinds if the synthetic URL format
        # ever changes — see get_gdrive_url() and core/indexer.py index_file().
        w = _make_crawl_worker()
        save, _ = self._fake_save("/tmp/meeting-notes.docx")

        file = {
            "id": "STABLE_DRIVE_ID",
            "name": "Meeting Notes",
            "mimeType": "application/vnd.google-apps.document",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        w.indexer.index_file.assert_called_once()
        self.assertEqual(
            w.indexer.index_file.call_args.kwargs.get("id"),
            "STABLE_DRIVE_ID",
        )

    def test_extension_synthesized_from_mime_when_name_lacks_extension(self):
        # Regression: Drive files uploaded without a filename extension were
        # being dropped as `unsupported_ext_dropped` even when the mime type
        # was authoritative (e.g. "Burlington office floor plan" with mime
        # application/pdf). Now the crawler appends an extension derived from
        # the mime so the downstream extension whitelist accepts the file.
        w = _make_crawl_worker()
        save, calls = self._fake_save("/tmp/burlington-office-floor-plan.pdf")

        file = {
            "id": "PDF_ID",
            "name": "Burlington office floor plan",
            "mimeType": "application/pdf",
        }

        with patch.object(w, "save_local_file", side_effect=save), \
             patch("crawlers.gdrive_crawler.process_dataframe_file") as pdf_mock, \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        # save_local_file was called with a .pdf-suffixed name even though
        # the original Drive name had no extension.
        self.assertEqual(len(calls), 1)
        _, passed_name, _ = calls[0]
        self.assertTrue(passed_name.endswith('.pdf'),
                        f"expected .pdf-suffixed name, got {passed_name!r}")
        # File was admitted to indexing (not dropped).
        w.indexer.index_file.assert_called_once()
        pdf_mock.assert_not_called()


def _make_export_http_error(status: int, reason: str) -> HttpError:
    """Build an HttpError whose `error_details` carries a single reason — the
    shape Drive's export endpoint returns when a file exceeds the size limit
    or isn't downloadable in the requested mime."""
    resp = MagicMock()
    resp.status = status
    resp.reason = "mocked"
    content = json.dumps({
        "error": {
            "code": status,
            "message": "mocked",
            "errors": [{"reason": reason, "message": "mocked"}],
        }
    }).encode()
    return HttpError(resp=resp, content=content)


def _wire_download(worker, results):
    """Install service.files().export_media and .get_media stubs that pop one
    entry from ``results`` per call. Each entry is either bytes (yielded to
    the chunked downloader so the function returns a BytesIO) or an HttpError
    (raised inside the MediaIoBaseDownload loop). Returns the MediaIoBaseDownload
    patcher plus per-method call-args lists for assertions."""
    export_calls = []
    get_calls = []
    pending = list(results)

    def make_request():
        return MagicMock(name="request")

    def fake_export_media(fileId, mimeType):
        export_calls.append({"fileId": fileId, "mimeType": mimeType})
        return make_request()

    def fake_get_media(fileId):
        get_calls.append({"fileId": fileId})
        return make_request()

    worker.service.files = MagicMock()
    worker.service.files.return_value.export_media = MagicMock(side_effect=fake_export_media)
    worker.service.files.return_value.get_media = MagicMock(side_effect=fake_get_media)

    def fake_downloader(byte_stream, request):
        outcome = pending.pop(0)
        instance = MagicMock()
        if isinstance(outcome, HttpError):
            instance.next_chunk.side_effect = outcome
        else:
            byte_stream.write(outcome)
            instance.next_chunk.return_value = (None, True)
        return instance

    return patch('crawlers.gdrive_crawler.MediaIoBaseDownload', side_effect=fake_downloader), \
        export_calls, get_calls


class TestDownloadOrExportFile(unittest.TestCase):
    """The PDF fallback for oversized Google Workspace exports must go through
    files().export_media (which uses the auto-refreshing service credential),
    not a raw requests.get against the exportLinks URL with a stale Bearer
    token — the latter was the source of the 401s the user reported."""

    def test_normal_export_returns_bytes(self):
        w = _make_worker()
        patcher, export_calls, _ = _wire_download(w, [b"%PDF-1.4 hello"])
        with patcher:
            stream, err = w.download_or_export_file(
                "FID",
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        self.assertIsNone(err)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), b"%PDF-1.4 hello")
        self.assertEqual(len(export_calls), 1)

    def test_oversized_export_retries_as_pdf_via_export_media(self):
        """Primary export 403s with fileNotDownloadable → retry with
        mimeType='application/pdf' via export_media (not raw HTTP)."""
        w = _make_worker()
        err = _make_export_http_error(403, "fileNotDownloadable")
        patcher, export_calls, _ = _wire_download(w, [err, b"%PDF retry bytes"])
        with patcher:
            stream, ret_err = w.download_or_export_file(
                "FID",
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
        self.assertIsNone(ret_err)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.read(), b"%PDF retry bytes")
        # Two export_media calls: original, then PDF fallback. The
        # download_or_export_file source has no `import requests`, so any
        # regression that re-introduced the raw exportLinks fallback would
        # fail at import time before this test ran.
        self.assertEqual(len(export_calls), 2)
        self.assertEqual(export_calls[1]["mimeType"], "application/pdf")

    def test_oversized_export_size_limit_also_retries_as_pdf(self):
        """The other Drive reason that triggers the fallback."""
        w = _make_worker()
        err = _make_export_http_error(403, "exportSizeLimitExceeded")
        patcher, export_calls, _ = _wire_download(w, [err, b"%PDF"])
        with patcher:
            stream, ret_err = w.download_or_export_file("FID", mime_type="application/x-foo")
        self.assertIsNone(ret_err)
        self.assertEqual(stream.read(), b"%PDF")
        self.assertEqual(len(export_calls), 2)

    def test_pdf_fallback_also_failing_surfaces_error(self):
        """If both export attempts fail, the function returns the second error
        verbatim so the operator can see the real failure."""
        w = _make_worker()
        err1 = _make_export_http_error(403, "fileNotDownloadable")
        err2 = _make_export_http_error(500, "internalError")
        patcher, _, _ = _wire_download(w, [err1, err2])
        with patcher:
            stream, ret_err = w.download_or_export_file("FID", mime_type="application/x-foo")
        self.assertIsNone(stream)
        self.assertIn("500", ret_err or "")

    def test_get_media_path_no_pdf_fallback(self):
        """No mime → get_media path → unrelated 404 must NOT trigger the PDF
        fallback (which only makes sense for Workspace export attempts)."""
        w = _make_worker()
        err = _make_export_http_error(404, "notFound")
        patcher, export_calls, get_calls = _wire_download(w, [err])
        with patcher:
            stream, ret_err = w.download_or_export_file("FID", mime_type=None)
        self.assertIsNone(stream)
        self.assertEqual(len(export_calls), 0)
        self.assertEqual(len(get_calls), 1)
        self.assertIn("404", ret_err or "")

    def test_unrelated_403_returns_error_without_pdf_retry(self):
        """A 403 whose reason isn't size/notDownloadable (e.g. a permission
        problem) must not loop forever retrying as PDF."""
        w = _make_worker()
        err = _make_export_http_error(403, "insufficientPermissions")
        patcher, export_calls, _ = _wire_download(w, [err])
        with patcher:
            stream, _ = w.download_or_export_file("FID", mime_type="application/x-foo")
        self.assertIsNone(stream)
        # Only the primary call; no PDF retry.
        self.assertEqual(len(export_calls), 1)


class TestAbacConfigLogging(unittest.TestCase):
    """When ACL fields look empty in production (no acl_groups / acl_domains /
    acl_labels), operators currently have no way to tell whether (a) the file
    genuinely has no group/domain grants, (b) the feature is disabled in
    config, or (c) the Labels scope wasn't requested. A one-line per-worker
    summary at setup() makes the config state self-evident in the logs."""

    def test_setup_logs_abac_flags(self):
        import logging as _logging
        w = _make_worker(abac={
            'enabled': True,
            'resolve_inherited': True,
            'fetch_labels': False,
            'include_anyone': True,
        })
        w.indexer = MagicMock()
        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w.setup()
        line = next((ln for ln in cm.output if 'abac' in ln.lower()), None)
        self.assertIsNotNone(line, f"expected an ABAC config line, got: {cm.output}")
        self.assertIn("enabled=True", line)
        self.assertIn("resolve_inherited=True", line)
        self.assertIn("fetch_labels=False", line)

    def test_setup_log_present_when_abac_disabled(self):
        """Even with ABAC off, log the state so operators can confirm 'all
        acl_* fields empty' is expected, not a missing feature."""
        import logging as _logging
        w = _make_worker(abac={'enabled': False})
        w.indexer = MagicMock()
        with self.assertLogs('crawlers.gdrive_crawler', level=_logging.INFO) as cm:
            w.setup()
        line = next((ln for ln in cm.output if 'abac' in ln.lower()), None)
        self.assertIsNotNone(line)
        self.assertIn("enabled=False", line)


class TestApplyMimeGate(unittest.TestCase):
    """Google Workspace types that Drive cannot return content for (Forms,
    Sites, Maps, Jamboard, Fusion Tables) must be dropped at the mime gate
    with the `mime_dropped` bucket — not later as `download_failed`, which
    misleads operators into expecting the file to retry."""

    def test_form_dropped_at_mime_gate_not_download(self):
        w = _make_worker()
        w._summarize_images = False
        file = {
            "id": "FORM_ID",
            "name": "Cloud Central Feedback Form",
            "mimeType": "application/vnd.google-apps.form",
        }
        kept = w._apply_mime_gate([file])
        self.assertEqual(kept, [])
        self.assertEqual(w._stats['mime_dropped'], 1)
        self.assertEqual(w._stats['download_failed'], 0)

    def test_site_map_jam_fusiontable_all_dropped(self):
        w = _make_worker()
        w._summarize_images = False
        unexportable = [
            ("S1", "application/vnd.google-apps.site"),
            ("M1", "application/vnd.google-apps.map"),
            ("J1", "application/vnd.google-apps.jam"),
            ("F1", "application/vnd.google-apps.fusiontable"),
        ]
        files = [{"id": fid, "name": fid, "mimeType": mt} for fid, mt in unexportable]
        kept = w._apply_mime_gate(files)
        self.assertEqual(kept, [])
        self.assertEqual(w._stats['mime_dropped'], len(unexportable))

    def test_drawing_passes_mime_gate(self):
        """Drawings DO export (to PNG/PDF), so they must continue through —
        not get caught by the unexportable list."""
        w = _make_worker()
        w._summarize_images = False
        file = {
            "id": "DRAW_ID",
            "name": "Architecture sketch",
            "mimeType": "application/vnd.google-apps.drawing",
        }
        kept = w._apply_mime_gate([file])
        self.assertEqual(kept, [file])
        self.assertEqual(w._stats['mime_dropped'], 0)

    def test_pdf_and_docx_pass_through(self):
        """Sanity check: normal documents survive the gate."""
        w = _make_worker()
        w._summarize_images = False
        files = [
            {"id": "P1", "name": "a.pdf", "mimeType": "application/pdf"},
            {"id": "D1", "name": "Doc", "mimeType": "application/vnd.google-apps.document"},
        ]
        kept = w._apply_mime_gate(files)
        self.assertEqual([f["id"] for f in kept], ["P1", "D1"])

    def test_audio_video_archive_still_dropped(self):
        """Regression: legacy prefix-based drops must keep working."""
        w = _make_worker()
        w._summarize_images = False
        files = [
            {"id": "A", "name": "song.mp3", "mimeType": "audio/mpeg"},
            {"id": "V", "name": "clip.mp4", "mimeType": "video/mp4"},
            {"id": "Z", "name": "bundle.zip", "mimeType": "application/zip"},
        ]
        kept = w._apply_mime_gate(files)
        self.assertEqual(kept, [])
        self.assertEqual(w._stats['mime_dropped'], 3)


class TestDiagnosticPropagation(unittest.TestCase):
    """When indexer.index_file / process_dataframe_file return False the gdrive
    crawler should surface the underlying reason (Indexer.last_error /
    DataframeParser.last_error) in the [index_error] drop record — not the
    generic "returned False" string."""

    def test_index_file_failure_surfaces_indexer_last_error(self):
        w = _make_crawl_worker()
        w.indexer.index_file.return_value = False
        w.indexer.last_error = "_index_file failed: HTTP 503 from Vectara API"

        file = {"id": "PDF_ID", "name": "report.pdf", "mimeType": "application/pdf"}

        captured = []
        original = w._record_drop

        def capture(bucket, file_obj, reason):
            captured.append((bucket, reason))
            return original(bucket, file_obj, reason)

        with patch.object(w, "save_local_file", return_value=("/tmp/report.pdf", None)), \
             patch.object(w, "_record_drop", side_effect=capture), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        self.assertEqual(len(captured), 1)
        bucket, reason = captured[0]
        self.assertEqual(bucket, 'index_error')
        self.assertIn("HTTP 503", reason)

    def test_dataframe_failure_surfaces_df_parser_last_error(self):
        w = _make_crawl_worker()
        w.df_parser.last_error = "process_dataframe_file exception: bad header row"

        file = {"id": "CSV_ID", "name": "data.csv", "mimeType": "text/csv"}

        captured = []
        original = w._record_drop

        def capture(bucket, file_obj, reason):
            captured.append((bucket, reason))
            return original(bucket, file_obj, reason)

        with patch.object(w, "save_local_file", return_value=("/tmp/data.csv", None)), \
             patch("crawlers.gdrive_crawler.process_dataframe_file", return_value=False), \
             patch.object(w, "_record_drop", side_effect=capture), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        self.assertEqual(len(captured), 1)
        bucket, reason = captured[0]
        self.assertEqual(bucket, 'index_error')
        self.assertIn("bad header row", reason)

    def test_download_failure_surfaces_http_error_reason(self):
        # save_local_file now propagates the actual HTTP error from
        # download_or_export_file rather than the generic "no bytes" string.
        w = _make_crawl_worker()

        file = {"id": "PDF_ID", "name": "report.pdf", "mimeType": "application/pdf"}

        captured = []
        original = w._record_drop

        def capture(bucket, file_obj, reason):
            captured.append((bucket, reason))
            return original(bucket, file_obj, reason)

        with patch.object(w, "save_local_file", return_value=(None, "HttpError 403: insufficientFilePermissions")), \
             patch.object(w, "_record_drop", side_effect=capture), \
             patch("crawlers.gdrive_crawler.safe_remove_file"):
            w.crawl_file(file)

        self.assertEqual(len(captured), 1)
        bucket, reason = captured[0]
        self.assertEqual(bucket, 'download_failed')
        self.assertIn("HttpError 403", reason)


class TestGdriveContentHash(unittest.TestCase):
    """Google-native docs (Docs/Sheets/Slides) are exported on each crawl and the export
    bytes are not stable across runs, so hashing them defeats incremental skipping. Use
    Drive's modifiedTime as the content signal for native files; let the indexer hash the
    bytes for binary files (whose bytes are stable)."""

    def test_native_doc_uses_modified_time(self):
        f = {"mimeType": "application/vnd.google-apps.document", "modifiedTime": "2026-06-19T00:00:00Z"}
        self.assertEqual(gdrive_content_hash(f), "gdrive-native:2026-06-19T00:00:00Z")

    def test_native_presentation_and_spreadsheet(self):
        for mime in ("application/vnd.google-apps.presentation",
                     "application/vnd.google-apps.spreadsheet"):
            h = gdrive_content_hash({"mimeType": mime, "modifiedTime": "t"})
            self.assertEqual(h, "gdrive-native:t")

    def test_binary_returns_none(self):
        # PDF/image: stable bytes -> let the indexer hash the file (return None).
        self.assertIsNone(gdrive_content_hash(
            {"mimeType": "application/pdf", "modifiedTime": "t", "md5Checksum": "abc"}))

    def test_native_without_modified_time_returns_none(self):
        self.assertIsNone(gdrive_content_hash({"mimeType": "application/vnd.google-apps.document"}))


if __name__ == "__main__":
    unittest.main()
