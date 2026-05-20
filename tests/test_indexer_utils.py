import unittest

from core.indexer_utils import auth_redirect_reason, is_auth_host, normalize_url_for_metadata


class TestAuthRedirectReason(unittest.TestCase):
    """Tests for sign-in/IdP redirect detection.

    Real-world trigger (sites.google.com private page without valid auth):
    crawler fetches `sites.google.com/d/.../p/.../edit`, gets bounced to
    `accounts.google.com/v3/signin/identifier?continue=...`, and would
    otherwise index the Google sign-in form's HTML as if it were content.
    """

    def test_flags_google_signin_redirect(self):
        reason = auth_redirect_reason(
            "https://sites.google.com/d/abc/p/xyz/edit",
            "https://accounts.google.com/v3/signin/identifier?continue=https%3A%2F%2Fsites.google.com%2Fd%2Fabc%2Fp%2Fxyz%2Fedit",
        )
        self.assertIsNotNone(reason)
        self.assertIn("accounts.google.com", reason)

    def test_flags_okta_subdomain_redirect(self):
        reason = auth_redirect_reason(
            "https://internal.example.com/wiki",
            "https://acme.okta.com/login/sso?fromURI=...",
        )
        self.assertIsNotNone(reason)
        self.assertIn("okta.com", reason)

    def test_flags_microsoftonline_redirect(self):
        reason = auth_redirect_reason(
            "https://example.sharepoint.com/sites/x",
            "https://login.microsoftonline.com/common/oauth2/authorize?...",
        )
        self.assertIsNotNone(reason)

    def test_no_redirect_same_url(self):
        # No domain change — caller did not get bounced.
        self.assertIsNone(auth_redirect_reason(
            "https://example.com/a",
            "https://example.com/a",
        ))

    def test_no_flag_same_domain_login_path(self):
        # Intentionally conservative: same-domain /login is NOT flagged.
        # Plenty of legitimate sites serve login content on their own domain.
        self.assertIsNone(auth_redirect_reason(
            "https://example.com/dashboard",
            "https://example.com/login?next=/dashboard",
        ))

    def test_no_flag_crawling_idp_directly(self):
        # If the user explicitly crawls accounts.google.com, no domain change
        # happened — don't flag.
        self.assertIsNone(auth_redirect_reason(
            "https://accounts.google.com/foo",
            "https://accounts.google.com/bar",
        ))

    def test_no_flag_lookalike_domain(self):
        # 'fakeokta.com' must NOT be matched by the 'okta.com' suffix rule.
        self.assertIsNone(auth_redirect_reason(
            "https://internal.example.com/wiki",
            "https://fakeokta.com/login",
        ))

    def test_handles_missing_urls(self):
        self.assertIsNone(auth_redirect_reason(None, "https://accounts.google.com/x"))
        self.assertIsNone(auth_redirect_reason("https://example.com", None))
        self.assertIsNone(auth_redirect_reason("", ""))


class TestIsAuthHost(unittest.TestCase):
    """`is_auth_host` flags URLs whose host is itself a sign-in / IdP host,
    independent of any prior redirect. Used to drop links like
    `accounts.google.com/SignOutOptions` that are embedded as direct links
    in partially-authenticated pages."""

    def test_flags_accounts_google(self):
        self.assertTrue(is_auth_host(
            "https://accounts.google.com/SignOutOptions?continue=https://sites.google.com/..."
        ))

    def test_flags_okta_subdomain(self):
        self.assertTrue(is_auth_host("https://acme.okta.com/login/sso"))

    def test_does_not_flag_content_host(self):
        self.assertFalse(is_auth_host("https://sites.google.com/d/abc/preview"))

    def test_does_not_flag_lookalike(self):
        # Same suffix-precision guard as auth_redirect_reason.
        self.assertFalse(is_auth_host("https://fakeokta.com/login"))

    def test_handles_missing_or_relative(self):
        self.assertFalse(is_auth_host(None))
        self.assertFalse(is_auth_host(""))
        self.assertFalse(is_auth_host("/relative/path"))


class TestNormalizeUrlForMetadata(unittest.TestCase):
    """Round-trip behavior we now rely on in _remove_old_content_if_needed."""

    def test_decodes_percent_encoded_url(self):
        encoded = "https://accounts.google.com/v3/signin/identifier?continue=https%3A%2F%2Fsites.google.com%2Fd%2Fabc%2Fp%2Fxyz%2Fedit"
        decoded = "https://accounts.google.com/v3/signin/identifier?continue=https://sites.google.com/d/abc/p/xyz/edit"
        self.assertEqual(normalize_url_for_metadata(encoded), decoded)

    def test_decoded_url_is_idempotent(self):
        url = "https://example.com/a b?c=d&e=f"
        self.assertEqual(
            normalize_url_for_metadata(normalize_url_for_metadata(url)),
            normalize_url_for_metadata(url),
        )


if __name__ == "__main__":
    unittest.main()
