# API Keys & Tokens Authentication

API keys and personal access tokens are the most common authentication methods for web APIs. They provide simple, straightforward authentication without the complexity of OAuth.

## Overview

API keys are unique identifiers that authenticate requests to APIs. They're typically:

- Generated from the service's web interface
- Long random strings (e.g., `ghp_abc123...`)
- Stored in your secrets.toml file
- Sent with each API request

## Crawlers Using API Keys

| Crawler | Authentication Type | Documentation |
|---------|-------------------|---------------|
| **Jira** | API Token | [Guide](../crawlers/jira.md) |
| **GitHub** | Personal Access Token | [Guide](../crawlers/github.md) |
| **Confluence** | API Token | [Guide](../crawlers/confluence.md) |
| **ServiceNow** | API Key / Username+Password | [Guide](../crawlers/servicenow.md) |
| **Notion** | Integration Token | [Guide](../crawlers/notion.md) |
| **HubSpot** | Private App Token | [Guide](../crawlers/hubspot.md) |

---

## Jira API Token Setup

### Step 1: Generate API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Label: "Vectara Ingest"
4. Click **Create**
5. Copy the token (shown only once)

### Step 2: Add to secrets.toml

```toml
[default]
JIRA_USERNAME = "your-email@company.com"
JIRA_PASSWORD = "your-api-token"
```

**Note**: Despite the name "PASSWORD", use your API token here, not your actual password.

### Step 3: Verify Access

Test with curl:

```bash
curl -u your-email@company.com:your-api-token \
  https://your-domain.atlassian.net/rest/api/3/myself
```

Should return your user profile.

---

## GitHub Personal Access Token Setup

### Step 1: Generate Token

1. Go to [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
2. Click **Generate new token** → **Generate new token (classic)**
3. Note: "Vectara Ingest"
4. Select scopes:
   - `repo` - Full repository access
   - `read:org` - Read org data (if indexing org repos)
   - `read:user` - Read user profile
5. Click **Generate token**
6. Copy the token (starts with `ghp_`)

### Step 2: Add to secrets.toml

```toml
[default]
GITHUB_TOKEN = "ghp_abc123..."
```

### Step 3: Verify Access

Test with curl:

```bash
curl -H "Authorization: token ghp_abc123..." \
  https://api.github.com/user
```

Should return your user profile.

---

## Confluence API Token Setup

### Step 1: Generate API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **Create API token**
3. Label: "Vectara Ingest Confluence"
4. Click **Create**
5. Copy the token

### Step 2: Add to secrets.toml

```toml
[default]
CONFLUENCE_USERNAME = "your-email@company.com"
CONFLUENCE_PASSWORD = "your-api-token"
```

### Step 3: Verify Access

```bash
curl -u your-email@company.com:your-api-token \
  https://your-domain.atlassian.net/wiki/rest/api/space
```

Should list available spaces.

---

## ServiceNow Authentication

ServiceNow supports multiple authentication methods:

### Option 1: Basic Auth (Username + Password)

```toml
[default]
SERVICENOW_USERNAME = "your-username"
SERVICENOW_PASSWORD = "your-password"
```

### Option 2: API Key (Recommended)

1. Log into ServiceNow
2. Navigate to **System OAuth → Application Registry**
3. Click **New** → **Create an OAuth API endpoint for external clients**
4. Fill in:
   - Name: "Vectara Ingest"
   - Refresh Token Lifespan: 365 days
5. Generate credentials

```toml
[default]
SERVICENOW_API_KEY = "your-api-key"
```

---

## HubSpot Private App Token Setup

### Step 1: Create Private App

1. Go to HubSpot **Settings → Integrations → Private Apps**
2. Click **Create a private app**
3. Basic Info:
   - Name: "Vectara Ingest"
   - Description: "Index HubSpot CRM data"

### Step 2: Set Scopes

Under **Scopes** tab, select:

**CRM:**
- `crm.objects.companies.read`
- `crm.objects.contacts.read`
- `crm.objects.deals.read`
- `crm.objects.owners.read`

**Other:**
- `crm.schemas.companies.read`
- `crm.schemas.contacts.read`
- `crm.schemas.deals.read`

### Step 3: Create App

1. Click **Create app**
2. Copy the access token (shown once)

### Step 4: Add to secrets.toml

```toml
[default]
HUBSPOT_API_KEY = "pat-na1-abc123..."
```

---

## Token Storage Best Practices

### secrets.toml Structure

```toml
# Default profile (used by default)
[default]
api_key = "vectara-api-key"

# Service-specific tokens
JIRA_USERNAME = "user@company.com"
JIRA_PASSWORD = "jira-api-token"
GITHUB_TOKEN = "ghp_github_token"
CONFLUENCE_USERNAME = "user@company.com"
CONFLUENCE_PASSWORD = "confluence-token"
SERVICENOW_USERNAME = "username"
SERVICENOW_PASSWORD = "password"
HUBSPOT_API_KEY = "pat-na1-token"

# Development environment
[dev]
api_key = "dev-vectara-key"
JIRA_USERNAME = "dev@company.com"
JIRA_PASSWORD = "dev-token"

# Production environment
[prod]
api_key = "prod-vectara-key"
JIRA_USERNAME = "prod@company.com"
JIRA_PASSWORD = "prod-token"
```

### File Permissions

Set restrictive permissions:

```bash
chmod 600 secrets.toml
```

### Git Ignore

Add to `.gitignore`:

```gitignore
secrets.toml
*.token
*.key
```

---

## Token Permissions & Scopes

### Jira

**Required Permissions:**
- Read access to projects
- Read access to issues
- Read attachments (if indexing)

**Scope**: API token has same permissions as your user account

### GitHub

**Recommended Scopes:**
- `repo` - Read repositories (required)
- `read:org` - Read organization data
- `read:user` - Read user profiles

**Minimal Scope**: `public_repo` (public repos only)

### Confluence

**Required Permissions:**
- Read access to spaces
- View pages and blogs
- Download attachments (if indexing)

**Scope**: API token inherits user permissions

### HubSpot

**Minimum Scopes:**
- `crm.objects.contacts.read`
- `crm.objects.companies.read`
- `crm.objects.deals.read`

**Optional Scopes:**
- `crm.objects.custom.read` - Custom objects
- `tickets` - Support tickets

---

## Troubleshooting

### "Unauthorized" or "401" Errors

**Check Token Validity:**
```bash
# Jira
curl -u email:token https://domain.atlassian.net/rest/api/3/myself

# GitHub
curl -H "Authorization: token TOKEN" https://api.github.com/user

# Confluence
curl -u email:token https://domain.atlassian.net/wiki/rest/api/space
```

**Common Causes:**
- Token expired or revoked
- Incorrect token in secrets.toml
- Wrong username (for Jira/Confluence)
- Typo in token string

### "Forbidden" or "403" Errors

**Check Permissions:**
- Jira: User must have project access
- GitHub: Token needs `repo` scope
- Confluence: User must have space access
- HubSpot: App needs proper scopes

**Solution**: Regenerate token with correct permissions

### Token Not Found

**Verify secrets.toml:**
```bash
# Check file exists
ls -la secrets.toml

# Verify key names (case-sensitive)
cat secrets.toml
```

**Common Issues:**
- Wrong profile (dev vs prod vs default)
- Typo in key name
- Missing [default] section

### Rate Limiting

Most APIs have rate limits:

| Service | Rate Limit | Solution |
|---------|------------|----------|
| **Jira** | 150-300 req/min | Use `num_per_second` in config |
| **GitHub** | 5000 req/hour (authenticated) | Use API token |
| **Confluence** | 150-300 req/min | Add delays between requests |
| **HubSpot** | 100 req/10sec | Configure rate limiting |

**Configuration:**
```yaml
jira_crawler:
  num_per_second: 2  # Limit to 2 requests/second
```

---

## Security Best Practices

### Token Generation

- ✅ **Use descriptive names** ("Vectara Ingest - Production")
- ✅ **Set expiration dates** when possible
- ✅ **Document token purpose**

### Token Storage

- ✅ **Never commit to git**
- ✅ **Use environment variables in CI/CD**
- ✅ **Encrypt at rest**
- ✅ **Restrict file permissions** (chmod 600)

### Token Management

- ✅ **Rotate regularly** (every 90 days)
- ✅ **Revoke unused tokens**
- ✅ **Use separate tokens per environment**
- ✅ **Monitor API usage**

### Least Privilege

- ✅ **Request minimum scopes needed**
- ✅ **Use read-only permissions when possible**
- ✅ **Create service accounts for production**
- ✅ **Avoid using personal tokens in production**

---

## Token Rotation

### Jira & Confluence

Atlassian API tokens don't expire but should be rotated periodically:

1. Generate new token
2. Update secrets.toml with new token
3. Test crawler
4. Revoke old token

### GitHub

Personal access tokens can expire:

1. Set expiration date when creating
2. Regenerate before expiration
3. Update secrets.toml
4. Delete old token

### HubSpot

Private app tokens don't expire:

1. Create new private app (for rotation)
2. Copy new token
3. Update secrets.toml
4. Delete old private app

---

## Related Documentation

- [Jira Crawler](../crawlers/jira.md)
- [GitHub Crawler](../crawlers/github.md)
- [Confluence Crawler](../crawlers/confluence.md)
- [ServiceNow Crawler](../crawlers/servicenow.md)
- [HubSpot Crawler](../crawlers/hubspot.md)
- [Secrets Management](../secrets-management.md)
- [Authentication Overview](index.md)
