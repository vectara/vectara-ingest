# SAML Authentication

SAML (Security Assertion Markup Language) is an enterprise authentication standard for Single Sign-On (SSO). The website crawler supports SAML authentication for accessing content behind enterprise SSO.

## Overview

SAML enables:
- Single Sign-On (SSO) to enterprise websites
- Integration with identity providers (Okta, Azure AD, etc.)
- Secure authentication without storing passwords
- Support for multi-factor authentication (MFA)

## Crawler Support

| Crawler | SAML Support | Documentation |
|---------|-------------|---------------|
| **Website** | ✅ Full support | [Guide](../crawlers/website.md) |

---

## When to Use SAML

**Use SAML authentication for:**
- ✅ Internal company documentation sites
- ✅ Enterprise knowledge bases
- ✅ Intranet content
- ✅ Sites requiring SSO login
- ✅ Azure AD / Okta protected content

**Don't use SAML for:**
- ❌ Public websites
- ❌ API-based crawlers (use API keys)
- ❌ Basic auth sites (use basic auth)

---

## Setup Process

### Step 1: Gather SAML Configuration

Get these details from your IT/security team:

- **Identity Provider URL**: Your SSO login URL
- **Username**: Your SSO username/email
- **Password**: Your SSO password
- **Entity ID**: SAML entity identifier
- **ACS URL**: Assertion Consumer Service URL

### Step 2: Add to secrets.toml

```toml
[default]
SAML_USERNAME = "user@company.com"
SAML_PASSWORD = "your-password"
```

### Step 3: Configure Website Crawler

```yaml
website_crawler:
  urls:
    - "https://internal-docs.company.com"

  # Enable SAML authentication
  auth_type: "saml"

  # SAML configuration
  saml_config:
    idp_url: "https://sso.company.com/saml2"
    sp_entity_id: "https://internal-docs.company.com"
    acs_url: "https://internal-docs.company.com/saml/acs"

  # Credentials from secrets.toml
  username_var: "SAML_USERNAME"
  password_var: "SAML_PASSWORD"
```

### Step 4: Test Authentication

Run the crawler:

```bash
python3 -m vectara_ingest --config config/website.yaml
```

The crawler will:
1. Navigate to the target URL
2. Detect SAML redirect
3. Authenticate with your credentials
4. Access protected content
5. Start indexing

---

## Configuration Options

### Basic SAML Configuration

```yaml
website_crawler:
  urls:
    - "https://internal-wiki.company.com"

  auth_type: "saml"

  saml_config:
    # Identity Provider (IdP) URL
    idp_url: "https://login.company.com/saml"

    # Service Provider (SP) Entity ID
    sp_entity_id: "https://internal-wiki.company.com"

    # Assertion Consumer Service URL
    acs_url: "https://internal-wiki.company.com/saml/callback"

  username_var: "SAML_USERNAME"
  password_var: "SAML_PASSWORD"
```

### Advanced SAML Configuration

```yaml
website_crawler:
  urls:
    - "https://docs.company.com"

  auth_type: "saml"

  saml_config:
    idp_url: "https://sso.company.com/saml2/idp"
    sp_entity_id: "https://docs.company.com"
    acs_url: "https://docs.company.com/saml/acs"

    # Optional: Certificate validation
    verify_ssl: true

    # Optional: SAML attributes
    attributes:
      username_attribute: "email"
      firstname_attribute: "givenName"
      lastname_attribute: "surname"

  username_var: "SAML_USERNAME"
  password_var: "SAML_PASSWORD"

  # Headless mode (recommended for SAML)
  scrape_method: "playwright"

  # Keep session alive
  session_timeout: 3600
```

---

## Common Identity Providers

### Okta

**Configuration:**
```yaml
saml_config:
  idp_url: "https://company.okta.com/app/company_app/exk.../sso/saml"
  sp_entity_id: "https://your-site.com"
  acs_url: "https://your-site.com/saml/acs"
```

**Finding your Okta URLs:**
1. Log into Okta Admin Dashboard
2. Go to **Applications** → Your App
3. Copy **Sign On URL** (idp_url)

### Azure AD

**Configuration:**
```yaml
saml_config:
  idp_url: "https://login.microsoftonline.com/tenant-id/saml2"
  sp_entity_id: "https://your-site.com"
  acs_url: "https://your-site.com/saml/acs"
```

**Finding Azure AD URLs:**
1. Go to Azure Portal → Azure AD
2. **Enterprise Applications** → Your App
3. **Single sign-on** → SAML settings

### OneLogin

**Configuration:**
```yaml
saml_config:
  idp_url: "https://company.onelogin.com/trust/saml2/http-post/sso/..."
  sp_entity_id: "https://your-site.com"
  acs_url: "https://your-site.com/saml/acs"
```

---

## Troubleshooting

### "SAML authentication failed"

**Common Causes:**
- Incorrect IdP URL
- Wrong username/password
- Missing SAML attributes
- SSL certificate issues

**Solutions:**
1. Verify IdP URL is correct
2. Test credentials in browser
3. Check SAML attribute mapping
4. Try `verify_ssl: false` (testing only)

### "Session expired"

**Cause**: SAML session timeout

**Solution:**
```yaml
website_crawler:
  session_timeout: 7200  # 2 hours
  max_retries: 3
```

### "MFA required"

**Issue**: Multi-factor authentication blocks automated login

**Workarounds:**
1. **App Passwords**: Use app-specific password (if supported)
2. **Service Account**: Create account without MFA (if policy allows)
3. **IP Whitelist**: Add crawler server IP to bypass MFA
4. **Remember Device**: Configure long-lived device trust

**Not all MFA can be automated**. Contact your IT team for service account options.

### "Redirect loop"

**Cause**: Misconfigured SAML endpoints

**Solution:**
1. Verify `sp_entity_id` matches exactly
2. Check `acs_url` is correct
3. Ensure SP metadata is registered with IdP

---

## Security Considerations

### Credential Storage

**Best Practices:**
- ✅ Store credentials in secrets.toml
- ✅ Use service accounts (not personal accounts)
- ✅ Rotate passwords regularly
- ✅ Restrict file permissions (chmod 600)

**Never:**
- ❌ Commit credentials to git
- ❌ Use personal passwords
- ❌ Share credentials across environments

### Network Security

**Recommendations:**
- ✅ Run crawler from trusted networks
- ✅ Use VPN if required
- ✅ Enable SSL verification (`verify_ssl: true`)
- ✅ Whitelist crawler IP addresses

### Session Management

**Configure timeouts:**
```yaml
website_crawler:
  session_timeout: 3600  # 1 hour
  max_session_age: 86400  # 24 hours
  reauth_on_failure: true
```

---

## SAML vs Other Authentication

| Feature | SAML | OAuth 2.0 | Basic Auth | API Keys |
|---------|------|-----------|------------|----------|
| **SSO Support** | ✅ Yes | ⚠️ Limited | ❌ No | ❌ No |
| **MFA Support** | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ No |
| **Setup Complexity** | High | Medium | Low | Low |
| **Enterprise** | ✅ Common | ⚠️ Some | ⚠️ Legacy | ✅ Common |
| **Website Crawling** | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| **Automation** | ⚠️ Tricky | ✅ Good | ✅ Easy | ✅ Easy |

**Use SAML when**: Enterprise SSO is required
**Use OAuth**: For API access with delegated auth
**Use Basic Auth**: For simple username/password sites
**Use API Keys**: For API-based crawlers

---

## Related Documentation

- [Website Crawler](../crawlers/website.md)
- [Basic Authentication](basic-auth.md)
- [Authentication Overview](index.md)
- [Secrets Management](../secrets-management.md)
