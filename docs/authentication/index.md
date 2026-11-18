# Authentication Overview

Vectara-ingest crawlers require authentication to access data from various sources. This section provides comprehensive guides for setting up authentication for different services.

## Authentication Methods

### OAuth 2.0

Used by services that require user authorization and token-based access.

**Crawlers using OAuth:**
- [Google Drive](../crawlers/gdrive.md)
- [Notion](../crawlers/notion.md)
- [Slack](../crawlers/slack.md)

[**→ OAuth 2.0 Setup Guide**](oauth.md)

---

### API Keys & Tokens

The most common authentication method for APIs. Typically involves generating an API key or personal access token from the service.

**Crawlers using API Keys:**
- [Jira](../crawlers/jira.md)
- [GitHub](../crawlers/github.md)
- [Confluence](../crawlers/confluence.md)
- [ServiceNow](../crawlers/servicenow.md)
- [Notion](../crawlers/notion.md)
- [HubSpot CRM](../crawlers/hubspot.md)

[**→ API Keys Setup Guide**](api-keys.md)

---

### Service Accounts

Used for server-to-server authentication without user interaction. Common in Google Cloud Platform services.

**Crawlers using Service Accounts:**
- [Google Drive](../crawlers/gdrive.md) (alternative to OAuth)

[**→ Service Accounts Setup Guide**](service-accounts.md)

---

### SAML Authentication

Enterprise-grade authentication for accessing websites behind SAML Single Sign-On.

**Crawlers using SAML:**
- [Website Crawler](../crawlers/website.md) (optional)

[**→ SAML Setup Guide**](saml.md)

---

### Basic Authentication

Simple username and password authentication for basic HTTP auth.

**Crawlers using Basic Auth:**
- [Website Crawler](../crawlers/website.md) (optional)
- [Database](../crawlers/database.md)

[**→ Basic Auth Setup Guide**](basic-auth.md)

---

## General Setup Process

All authentication methods follow a similar pattern:

1. **Obtain Credentials**
   - Generate API keys, OAuth tokens, or service account files
   - Follow service-specific instructions

2. **Store in secrets.toml**
   - Add credentials to your secrets file
   - Use appropriate environment (default, dev, prod)

3. **Configure Crawler**
   - Reference credentials in crawler config
   - Test connection

4. **Run Crawler**
   - Credentials are automatically loaded
   - Secure handling by vectara-ingest

## Security Best Practices

### Protecting Your Credentials

- ✅ **Never commit secrets.toml to version control**
- ✅ **Use environment variables for CI/CD**
- ✅ **Rotate keys regularly**
- ✅ **Use least-privilege access**
- ✅ **Store service account files securely**

### File Permissions

```bash
# Set restrictive permissions on secrets file
chmod 600 secrets.toml

# For service account JSON files
chmod 600 service-account.json
```

### Environment-Specific Secrets

Use profile-based secrets for different environments:

```toml
# Development
[dev]
api_key = "dev-key-123"

# Production
[prod]
api_key = "prod-key-456"
```

Run with specific profile:
```bash
VECTARA_PROFILE=prod python3 -m vectara_ingest
```

## Troubleshooting

### Common Issues

**Authentication Failed Errors**

1. Verify credentials are correct
2. Check API key has required permissions
3. Ensure OAuth tokens haven't expired
4. Confirm service account has proper roles

**Secrets Not Found**

1. Check secrets.toml is in correct location
2. Verify profile name matches (dev, prod, etc.)
3. Ensure key names match exactly (case-sensitive)

**Permission Denied**

1. Check API key has necessary scopes
2. Verify OAuth app has required permissions
3. Confirm service account has proper IAM roles

## Next Steps

Choose the authentication method for your crawler:

- **[OAuth 2.0 Guide](oauth.md)** - For Google Drive, Notion, Slack
- **[API Keys Guide](api-keys.md)** - For Jira, GitHub, Confluence, etc.
- **[Service Accounts Guide](service-accounts.md)** - For Google Drive (headless)
- **[SAML Guide](saml.md)** - For enterprise websites
- **[Basic Auth Guide](basic-auth.md)** - For simple HTTP auth

---

## Related Documentation

- [Secrets Management](../secrets-management.md) - Detailed guide on managing secrets
- [Configuration Reference](../configuration.md) - Full configuration options
- [Crawler Overview](../crawlers/index.md) - All available crawlers
