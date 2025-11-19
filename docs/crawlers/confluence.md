# Confluence Crawler

The Confluence crawler indexes pages, blog posts, and attachments from your Confluence instance. It supports both Confluence Cloud and Confluence Data Center deployments.

## Overview

**Crawler Type:** `confluence` (Cloud) or `confluencedatacenter` (Data Center)

**Supported Content:**
- Pages (all types)
- Blog posts
- Attachments (multiple formats)
- Labels and metadata
- User information (authors, owners)
- Space information

**Key Features:**
- CQL (Confluence Query Language) support for advanced filtering
- Attachment indexing in multiple formats
- Label extraction and indexing
- User and space metadata preservation
- Support for both Cloud and on-premise deployments

## Quick Start

### Basic Configuration

```yaml
vectara:
  corpus_key: confluence
  reindex: true

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://your-workspace.atlassian.net/wiki"
  confluence_cql: 'space = "DOCS" and type IN (page, blogpost)'
  confluence_include_attachments: true
  # Credentials loaded from secrets.toml
```

### Set Your Credentials

Add to `secrets.toml`:

```toml
[default]
CONFLUENCE_USERNAME = "your-email@example.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0..."  # Your API token
```

## Prerequisites

### Getting a Confluence API Token

The Confluence crawler requires an API token for authentication (not your account password).

**For Confluence Cloud:**

1. Visit [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Give it a label (e.g., "Vectara Ingest")
4. Copy the generated token (you'll only see it once)
5. Add to `secrets.toml`:
   ```toml
   CONFLUENCE_USERNAME = "your-email@example.com"
   CONFLUENCE_PASSWORD = "ATATT3xFfGF0..."
   ```

**Important:** The token starts with `ATATT` and is different from your Atlassian password. Always use the API token, never your account password.

**For Confluence Server/Data Center:**

Contact your Confluence administrator to generate an API token, or enable basic auth with your username and password.

## Configuration

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `confluence_base_url` | Your Confluence instance URL | `https://company.atlassian.net/wiki` |
| `confluence_cql` | CQL query to select content | `space = "DOCS"` |
| `confluence_username` | Email (Cloud) or username (Server) | `user@example.com` |
| `confluence_password` | API token (Cloud) or password (Server) | `ATATT3xFfGF0...` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `confluence_include_attachments` | `false` | Index attachments (PDFs, DOCX, etc.) |

### Full Configuration Example

```yaml
vectara:
  corpus_key: confluence
  reindex: true
  create_corpus: false

  # Processing options
  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: confluence

confluence_crawler:
  # Instance Configuration
  confluence_base_url: "https://mycompany.atlassian.net/wiki"

  # Query Configuration
  confluence_cql: 'space IN ("DOCS", "ENG") and type IN (page, blogpost)'

  # Attachment Configuration
  confluence_include_attachments: true

  # Authentication (from secrets.toml)
  # confluence_username: loaded from CONFLUENCE_USERNAME
  # confluence_password: loaded from CONFLUENCE_PASSWORD
```

## CQL Query Examples

Confluence Query Language (CQL) is a powerful query syntax for filtering content. Here are common examples:

### Basic Queries

```cql
# Single space
space = "DOCS"

# Multiple spaces
space IN ("DOCS", "ENGINEERING")

# Specific space key
space.key = WIKI
```

### Content Type Filtering

```cql
# Pages only
space = "DOCS" and type = page

# Blog posts only
space = "DOCS" and type = blogpost

# Pages and blog posts
space = "DOCS" and type IN (page, blogpost)
```

### Date-Based Queries

```cql
# Recently updated pages (last 30 days)
space = "DOCS" and lastModified >= -30d

# Pages created this year
space = "DOCS" and created >= 2024-01-01

# Pages modified since a specific date
space = "DOCS" and lastModified >= "2024-06-01"
```

### Status and Label Filtering

```cql
# Published pages only
space = "DOCS" and status = current

# Pages with specific label
space = "DOCS" and label = "important"

# Pages with multiple labels
space = "DOCS" and label IN ("api", "v2")

# Exclude draft pages
space = "DOCS" and status != draft
```

### Advanced Filtering

```cql
# Pages with attachments
space = "DOCS" and hasAttachments = true

# Pages created by specific user
space = "DOCS" and creator = "john.doe"

# Pages owned by specific user
space = "DOCS" and (owner = "jane.smith" or contributor = "jane.smith")

# Complex query combining multiple filters
space IN ("DOCS", "API")
and type IN (page, blogpost)
and status = current
and lastModified >= -7d
and label = "release-notes"
```

### Checking Query Syntax

You can test your CQL query in Confluence:

1. In your Confluence instance, click "Content"
2. Click "Search" and switch to "Advanced"
3. Enter your CQL query
4. Verify it returns the expected results before using in configuration

## Features

### Pages and Blog Posts

The crawler retrieves both pages and blog posts with:

- Full HTML content in a searchable format
- Page titles and metadata
- Hierarchy information (parent pages)
- Creation and modification timestamps
- Status (published, draft, etc.)
- Direct links to the page in Confluence

### Label Extraction

All Confluence labels are extracted and indexed as metadata:

```yaml
# In metadata for each document:
labels: ["api-reference", "release-v2"]
label_names: ["api-reference", "release-v2"]
label_ids: ["12345", "67890"]
```

### User Information

Author and owner information is automatically preserved:

```yaml
# Extracted user data includes:
authorId: "557058:abc123..."
lastOwnerId: "557058:def456..."
ownerId: "557058:xyz789..."

# Contains user details:
accountId: "557058:abc123..."
email: "author@company.com"
displayName: "John Doe"
accountType: "atlassian"
```

### Space Information

Each page is associated with its Confluence space:

```yaml
spaceName: "Documentation"
spaceId: "123456"
```

### Attachment Support

When `confluence_include_attachments: true`, the crawler downloads and indexes attachments.

**Supported File Types:**

| Format | Extensions |
|--------|-----------|
| Documents | `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf` |
| Presentations | `.ppt`, `.pptx` |
| Text/Web | `.txt`, `.html`, `.htm`, `.md`, `.lxml` |
| eBooks | `.epub` |

Each attachment is indexed as a separate document with:
- Original file metadata
- Direct download link
- Association with parent page
- File type and size information

**Unsupported Types:** Images (.jpg, .png, .gif), videos, and executables are skipped.

### Links

Three types of links are extracted for each page:

| Link Type | Purpose |
|-----------|---------|
| `webui` | Public link to view the page |
| `editui` | Link to edit the page (requires permissions) |
| `edituiv2` | Alternative edit UI link |
| `tinyui` | Short URL format |

## Confluence Cloud vs. Server/Data Center

### Confluence Cloud

- **URL Format:** `https://workspace.atlassian.net/wiki`
- **Authentication:** Email + API token (recommended) or email + password
- **API:** REST API v2
- **Body Format:** `anonymous_export_view` (HTML export format)
- **Token Generation:** Self-service via Atlassian account settings

**Use crawler type:** `confluence`

### Confluence Server/Data Center

- **URL Format:** `http://internal-server:8090` or similar
- **Authentication:** Username + password or API token
- **API:** REST API v1
- **Body Format:** `export_view` or `storage`
- **Token Generation:** Admin must enable API tokens or use basic auth

**Use crawler type:** `confluencedatacenter`

**Config Example for Data Center:**

```yaml
crawling:
  crawler_type: confluencedatacenter

confluencedatacenter:
  base_url: "http://confluence.internal:8090"
  confluence_cql: 'space = "DOCS"'
  confluence_include_attachments: true
  body_view: "export_view"  # Options: export_view, styled_view, storage
```

## Common Use Cases

### Index Entire Knowledge Base

```yaml
confluence_cql: 'type IN (page, blogpost)'
```

Indexes all pages and blog posts across all spaces.

### Index Specific Department

```yaml
confluence_cql: 'space IN ("DOCS", "API-REFERENCE", "TUTORIALS")'
```

Indexes multiple specific spaces.

### Include Only Published Content

```yaml
confluence_cql: 'type IN (page, blogpost) and status = current'
```

Excludes drafts and archived pages.

### Recent Updates Only

```yaml
confluence_cql: 'lastModified >= -7d and type IN (page, blogpost)'
```

Useful for incremental updates (crawl daily, get last 7 days).

### Index with Attachments

```yaml
confluence_cql: 'type IN (page, blogpost) and hasAttachments = true'
confluence_include_attachments: true
```

Focuses on pages that have attachments and indexes them.

### API Documentation

```yaml
confluence_cql: 'space = "API" and type = page and label = "public"'
```

Index only API documentation marked as public.

## Metadata

Each indexed document contains the following metadata:

```yaml
# Content metadata
title: "Page Title"
type: "page"  # or "blogpost"
status: "current"  # or "draft", "archived"
createdAt: "2024-01-15T10:30:00Z"
parentId: "123456"
parentType: "page"  # or "space"

# Confluence identifiers
spaceId: "987654"
spaceName: "Documentation"
id: "page123456"

# Labels
labels: ["release", "api-v2"]
label_names: ["release", "api-v2"]
label_ids: ["12345", "67890"]

# User information
authorId: "557058:abc123..."
author: {
  displayName: "John Doe",
  email: "john@example.com",
  accountId: "557058:abc123..."
}

# Links
links: {
  webui: "https://company.atlassian.net/wiki/spaces/DOCS/pages/123456/Page+Title",
  editui: "https://company.atlassian.net/wiki/pages/editpage.action?pageId=123456",
  edituiv2: "...",
  tinyui: "..."
}

# Document processing
url: "<link to page in Confluence>"
doc_id: "page123456"  # Unique document identifier
```

## Authentication Details

### Confluence Cloud

The crawler uses HTTP Basic Authentication with your email and API token:

```
Authorization: Basic base64(email:api_token)
```

The API token is treated as the "password" in the Basic Auth header.

### Confluence Server/Data Center

Supports:

1. **API Token** (recommended)
   - Admin must enable API token support
   - Same flow as Cloud

2. **Basic Auth**
   - Username and password
   - Less secure, consider API tokens instead

3. **SSL/TLS**
   - Configure via `ssl_verify` in Vectara settings
   - Can be `true` (default), `false`, or path to certificate

## Attachment Processing

When `confluence_include_attachments: true`:

1. Crawler queries each page/blog post for attachments
2. Downloads each supported attachment
3. Extracts text from the file
4. Creates separate document for each attachment
5. Links attachment to parent page via metadata

**Performance Considerations:**

- Large attachments may slow down crawling
- Consider limiting to specific spaces or labels
- Use `confluence_include_attachments: false` if not needed

## Pagination

The crawler automatically handles pagination through large result sets:

- **Page Size:** 25 results per API call
- **Handling:** Automatically follows pagination links
- **No Configuration Needed:** Transparent to user

## Error Handling

Common issues and solutions:

### Authentication Error (401)

```
Error: 401 Unauthorized
```

**Solution:**
- Verify API token is correct (starts with `ATATT`)
- Check email/username is correct
- Ensure token has not expired
- For Data Center, verify basic auth is enabled

### CQL Query Error (400)

```
Error: 400 Bad Request: Invalid CQL
```

**Solution:**
- Test CQL query in Confluence UI first
- Check CQL syntax (proper quotes, valid fields)
- Ensure space names/keys are correct
- See CQL examples above

### URL Not Found (404)

```
Error: 404 Not Found
```

**Solution:**
- Verify `confluence_base_url` is correct
- For Cloud: should end with `/wiki`
- For Data Center: verify server address and port
- Check URL is accessible from your network

### Rate Limiting (429)

```
Error: 429 Too Many Requests
```

**Solution:**
- Reduce concurrent requests if applicable
- Confluence Cloud has rate limits (~60 requests/minute)
- Wait before retrying
- Consider crawling during off-peak hours

### No Results

```
No content indexed
```

**Solution:**
- Verify CQL query returns results in Confluence UI
- Check user permissions (must have read access to spaces)
- Ensure space names/keys in CQL are exact matches
- Try simpler query like `type IN (page, blogpost)`

## Performance Tips

1. **Optimize CQL Queries**
   - Use specific space names rather than broad queries
   - Exclude archived or draft content if not needed
   - Use date filters for incremental updates

2. **Attachment Handling**
   - Disable attachments if not needed (`confluence_include_attachments: false`)
   - Create separate crawlers for different content types
   - Consider file type filtering

3. **Scheduling**
   - Schedule crawls during off-peak hours
   - Use date-based filters for incremental updates
   - Example: `lastModified >= -1d` for daily updates

4. **Resource Allocation**
   - Allocate sufficient memory for large attachments
   - Monitor disk space for temporary files
   - Adjust timeout values for slow networks

## Configuration Reference

See the [Configuration Reference](../configuration.md) for global Vectara settings like chunking strategy, SSL verification, and content processing options.

## Examples

### Basic Example

```yaml
vectara:
  corpus_key: my-confluence

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"
  confluence_cql: 'space = "DOCS"'
```

### With Attachments

```yaml
vectara:
  corpus_key: confluence-with-files

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"
  confluence_cql: 'space IN ("DOCS", "API") and type IN (page, blogpost)'
  confluence_include_attachments: true
```

### Data Center Deployment

```yaml
vectara:
  corpus_key: internal-docs

crawling:
  crawler_type: confluencedatacenter

confluencedatacenter:
  base_url: "http://confluence.internal:8090"
  confluence_cql: 'space = "INTERNAL"'
  confluence_include_attachments: true
  body_view: "export_view"
```

### Daily Incremental Update

```yaml
vectara:
  corpus_key: confluence-daily
  reindex: false  # Only update changed documents

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"
  confluence_cql: 'lastModified >= -1d and type IN (page, blogpost)'
  confluence_include_attachments: true
```

## Troubleshooting

### Slow Crawling

**Symptoms:** Crawler takes very long time

**Solutions:**
- Disable attachments: `confluence_include_attachments: false`
- Use more specific CQL query (fewer results)
- Reduce chunk size for faster processing
- Check network connectivity

### Memory Issues

**Symptoms:** Out of memory errors, process crashes

**Solutions:**
- Reduce chunk size in Vectara config
- Disable or limit attachments
- Increase Docker memory allocation
- Index in smaller batches using CQL date filters

### Missing Content

**Symptoms:** Some pages don't appear in index

**Solutions:**
- Verify CQL query includes those pages
- Check user has read permission on spaces
- Test CQL in Confluence UI
- Check document filtering settings (remove_boilerplate, etc.)

### Character Encoding Issues

**Symptoms:** Special characters display incorrectly

**Solutions:**
- Ensure UTF-8 encoding throughout pipeline
- Check Confluence instance uses UTF-8
- Verify secrets.toml uses UTF-8 encoding

## Limits and Constraints

- **API Limits:** Confluence Cloud has rate limits (~60 requests/minute)
- **Content Size:** Large pages may be chunked multiple times
- **Attachments:** File size limited by available disk space
- **Query Length:** CQL queries must be valid syntax
- **Concurrent Requests:** Limited by API rate limits

## Resources

- [Confluence Cloud Documentation](https://developer.atlassian.com/cloud/confluence/rest/intro/)
- [CQL Reference](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
- [API Token Management](https://id.atlassian.com/manage-profile/security/api-tokens)
- [Confluence Data Center API](https://developer.atlassian.com/server/confluence/confluence-server-rest-api-overview/)

## Related Crawlers

- [Jira Crawler](jira.md) - Index Jira issues and comments
- [Slack Crawler](slack.md) - Index Slack channels and messages
- [Website Crawler](website.md) - Crawl generic websites

## Support

For help with the Confluence crawler:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review your CQL query syntax
3. Verify authentication credentials
4. Check crawler logs for detailed error messages
5. See [Crawlers Overview](index.md) for general crawler help
