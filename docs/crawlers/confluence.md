# Confluence Crawler

The Confluence crawler indexes pages, blog posts, and attachments from Atlassian Confluence. It supports both Confluence Cloud and Confluence Data Center/Server deployments with powerful CQL-based filtering.

<div class="crawler-info-cards">
  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
      </div>
      <strong>Crawler Type</strong>
    </div>
    <code>confluence</code> (Cloud) or <code>confluencedatacenter</code> (Server)
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
      </div>
      <strong>Authentication</strong>
    </div>
    <p>API Token (Cloud) or Basic Auth (Server)</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><filter id="filter0"><feFlood flood-color="#4B5563" result="bg" /><feMerge><feMergeNode in="bg"/><feMergeNode in="SourceGraphic"/></feMerge></filter><rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="none"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
      </div>
      <strong>Content Types</strong>
    </div>
    <p>Pages, blog posts, attachments, labels, metadata</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
      </div>
      <strong>Filtering</strong>
    </div>
    <p>CQL (Confluence Query Language) for advanced queries</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>
      </div>
      <strong>Attachments</strong>
    </div>
    <p>PDF, DOCX, PPTX, TXT, HTML, and more</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
      </div>
      <strong>Rate Limiting</strong>
    </div>
    <p>~60 requests/minute (Cloud), configurable (Server)</p>
  </div>
</div>

---


## How It Works

<div class="use-cases-list">
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Authentication</strong> - Connects to Confluence using API token or personal access token</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Content Discovery</strong> - Uses CQL queries to discover pages, blogs, and attachments across specified spaces</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Content Extraction</strong> - Retrieves page body in storage format and converts to clean text</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Metadata Capture</strong> - Extracts page title, space, labels, creator, creation date, and last modified date</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Attachment Handling</strong> - Optionally extracts text from PDF, Word, and other document attachments</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Indexing</strong> - Sends extracted content to Vectara with all captured metadata</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Old Content Removal</strong> - Optionally removes previously indexed content that no longer matches CQL query</span>
  </div>
</div>

---

## Configuration Parameters

### Instance and Query Configuration

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `confluence_base_url` | string | Yes | - | Your Confluence instance URL (e.g., `https://company.atlassian.net/wiki` for Cloud) |
| `confluence_cql` | string | Yes | - | CQL query to filter content (e.g., `space = "DOCS" and type IN (page, blogpost)`) |
| `confluence_include_attachments` | boolean | No | `false` | Index attachments (PDFs, DOCX, PPTX, etc.) |

### Authentication

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `confluence_username` | string | Yes | Email (Cloud) or username (Server) - loaded from `CONFLUENCE_USERNAME` |
| `confluence_password` | string | Yes | API token (Cloud) or password (Server) - loaded from `CONFLUENCE_PASSWORD` |

**Note:** Authentication credentials should be stored in `secrets.toml` and loaded via environment variables.

### Data Center Specific

*For `confluencedatacenter` crawler only:*

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `body_view` | string | `export_view` | Body format: `export_view`, `styled_view`, or `storage` |

---

## Content Extraction

<div class="content-extraction-grid">
  <div class="extraction-card">
    <h3>Pages and Blog Posts</h3>
    <p>The crawler extracts all Confluence pages and blog posts with full HTML content.</p>

<p><strong>Extracted data:</strong></p>
<ul>
  <li>Full page/blog post content</li>
  <li>Page titles and hierarchy</li>
  <li>Creation and modification timestamps</li>
  <li>Parent page relationships</li>
  <li>Status (current, draft, archived)</li>
  <li>Direct links to Confluence</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Labels and Metadata</h3>
    <p>All Confluence labels are automatically extracted and indexed as searchable metadata.</p>

<p><strong>Extracted labels:</strong></p>
<ul>
  <li>Label names</li>
  <li>Label IDs</li>
  <li>Multiple labels per page</li>
  <li>Label-based filtering support</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>User Information</h3>
    <p>Author and contributor information is preserved for attribution and filtering.</p>

<p><strong>Extracted user data:</strong></p>
<ul>
  <li>Author ID and display name</li>
  <li>Author email</li>
  <li>Owner ID</li>
  <li>Last modifier</li>
  <li>Account type and status</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Space Information</h3>
    <p>Each document includes its Confluence space details for organization.</p>

<p><strong>Extracted space data:</strong></p>
<ul>
  <li>Space name</li>
  <li>Space ID</li>
  <li>Space key</li>
  <li>Space type</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Attachments</h3>
    <p>When enabled, the crawler indexes various file types attached to pages.</p>

<p><strong>Supported formats:</strong></p>
<ul>
  <li>Documents: PDF, DOC, DOCX, ODT, RTF</li>
  <li>Presentations: PPT, PPTX</li>
  <li>Text: TXT, HTML, HTM, MD</li>
  <li>eBooks: EPUB</li>
</ul>

<p><strong>Note:</strong> Images, videos, and executables are skipped.</p>
  </div>

  <div class="extraction-card">
    <h3>Links</h3>
    <p>Multiple link types are extracted for each page for different access patterns.</p>

<p><strong>Link types:</strong></p>
<ul>
  <li><code>webui</code> - Public view link</li>
  <li><code>editui</code> - Edit page link</li>
  <li><code>edituiv2</code> - Alternative edit UI</li>
  <li><code>tinyui</code> - Short URL format</li>
</ul>
  </div>
</div>

## Getting Started

<div class="info-box-prerequisites">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
  <div>
    <p><strong>Before you begin:</strong></p>
    <ul>
      <li>Set up your Vectara account and create a corpus</li>
      <li>Generate a Confluence API token (see <a href="#getting-a-confluence-api-token">below</a>)</li>
      <li>Identify the Confluence spaces you want to index</li>
    </ul>
  </div>
</div>

<div class="quick-start-card">
  <h3>Quick Start</h3>
  <p>Here's the simplest way to index a Confluence space:</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: my-confluence
  remove_boilerplate: true

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"
  confluence_cql: 'space = "DOCS" and type IN (page, blogpost)'

metadata:
  source: confluence
```

<p><strong>Add credentials to <code>secrets.toml</code>:</strong></p>

```toml
[default]
CONFLUENCE_USERNAME = "your-email@example.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0..."  # Your API token
```

<p><strong>Run:</strong></p>

```bash
bash run.sh config/confluence.yaml default
```

</div>

### Getting a Confluence API Token

The Confluence crawler requires an API token (not your account password).

**For Confluence Cloud:**

1. Visit [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Give it a label (e.g., "Vectara Ingest")
4. Copy the generated token (starts with `ATATT`)
5. Add to `secrets.toml` as shown above

**For Confluence Server/Data Center:**

Contact your Confluence administrator to generate an API token or enable basic authentication.

---

## CQL Query Language

Confluence Query Language (CQL) provides powerful filtering capabilities for selecting exactly the content you want to index.

### Basic Space Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Single space</h4>

```cql
space = "DOCS"
```

<p>Index all content in the DOCS space.</p>
</div>

<div class="cql-example-card">
  <h4>Multiple spaces</h4>

```cql
space IN ("DOCS", "API", "WIKI")
```

<p>Index content from multiple spaces.</p>
</div>

<div class="cql-example-card">
  <h4>Space by key</h4>

```cql
space.key = ENGINEERING
```

<p>Use space key instead of name.</p>
</div>

</div>

### Content Type Filtering

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Pages only</h4>

```cql
space = "DOCS" and type = page
```
</div>

<div class="cql-example-card">
  <h4>Blog posts only</h4>

```cql
space = "DOCS" and type = blogpost
```
</div>

<div class="cql-example-card">
  <h4>Pages and blogs</h4>

```cql
space = "DOCS" and type IN (page, blogpost)
```

<p></div></p>
</div>

### Time-Based Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Recently modified</h4>

```cql
lastModified >= -30d
```

<p>Pages modified in last 30 days.</p>
</div>

<div class="cql-example-card">
  <h4>Created this year</h4>

```cql
created >= 2024-01-01
```
</div>

<div class="cql-example-card">
  <h4>Since specific date</h4>

```cql
lastModified >= "2024-06-01"
```

<p></div></p>
</div>

### Label and Status Filtering

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>By label</h4>

```cql
label = "documentation"
```
</div>

<div class="cql-example-card">
  <h4>Multiple labels</h4>

```cql
label IN ("api", "v2", "public")
```
</div>

<div class="cql-example-card">
  <h4>Published only</h4>

```cql
status = current
```

<p>Exclude drafts and archived.</p>
</div>

</div>

### Advanced Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>With attachments</h4>

```cql
hasAttachments = true
```
</div>

<div class="cql-example-card">
  <h4>By creator</h4>

```cql
creator = "john.doe"
```
</div>

<div class="cql-example-card">
  <h4>Complex filter</h4>

```cql
space IN ("DOCS", "API")
and type IN (page, blogpost)
and status = current
and lastModified >= -7d
```

<p></div></p>
</div>

### Testing CQL Queries

Before using a CQL query in your configuration, test it in Confluence:

1. In Confluence, click **Content** → **Search**
2. Switch to **Advanced Search**
3. Enter your CQL query
4. Verify it returns the expected results

---

## Examples

### Example 1: Basic Documentation Space

<div class="example-card" markdown="1">

**Use Case:** Index a single documentation space with all pages and blog posts.

**Best For:** Small to medium documentation projects, team wikis

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: team-docs
  remove_boilerplate: true

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"
  confluence_cql: 'space = "DOCS" and type IN (page, blogpost) and status = current'
  confluence_include_attachments: false

metadata:
  source: confluence
  space: DOCS
  environment: production
```

**Setup and run:**

```bash
# Create secrets.toml
cat > secrets.toml <<EOF
[default]
CONFLUENCE_USERNAME = "your-email@example.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0your-api-token"
EOF

# Run crawler
bash run.sh config/team-docs.yaml default
```

**What this does:**

- Indexes all pages and blog posts from DOCS space
- Excludes drafts and archived pages
- Skips attachments for faster crawling
- Preserves labels and metadata

</div>

### Example 2: Multi-Space Knowledge Base with Attachments

<div class="example-card" markdown="1">

**Use Case:** Index multiple spaces with PDF and document attachments for comprehensive search.

**Best For:** Enterprise knowledge bases, support documentation, policy documents

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: knowledge-base
  remove_boilerplate: true
  chunking_strategy: sentence
  chunk_size: 512

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"

  # Index multiple departments
  confluence_cql: >
    space IN ("HR", "ENGINEERING", "PRODUCT", "SUPPORT")
    and type IN (page, blogpost)
    and status = current

  # Include all attachments
  confluence_include_attachments: true

metadata:
  source: confluence
  environment: production
  indexed_date: "2024-11-21"
```

**Setup and run:**

```bash
# Add credentials to secrets.toml
cat > secrets.toml <<EOF
[default]
CONFLUENCE_USERNAME = "service-account@company.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0your-api-token"
EOF

# Run crawler
bash run.sh config/knowledge-base.yaml default

# Monitor progress
docker logs -f vingest
```

**What this does:**

- Indexes 4 different spaces (HR, Engineering, Product, Support)
- Includes PDFs, DOCX, PPTX attachments
- Only indexes published content (excludes drafts)
- Uses sentence-based chunking for better search results
- Adds custom metadata for tracking

**Pro tips:**

- Use a service account for better token management
- Attachments significantly increase indexing time
- Consider splitting large spaces into separate crawls

</div>

### Example 3: Incremental Daily Updates

<div class="example-card" markdown="1">

**Use Case:** Daily scheduled updates to index only recently changed content.

**Best For:** Keeping search index fresh, CI/CD pipelines, scheduled maintenance

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: confluence-daily
  reindex: false  # Don't delete old documents

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"

  # Only pages modified in last 2 days (buffer for timezone issues)
  confluence_cql: >
    type IN (page, blogpost)
    and status = current
    and lastModified >= -2d

  confluence_include_attachments: true

metadata:
  source: confluence
  update_type: incremental
```

**Setup and run:**

```bash
# Add credentials to secrets.toml
cat > secrets.toml <<EOF
[default]
CONFLUENCE_USERNAME = "your-email@example.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0your-api-token"
EOF

# Run manually
bash run.sh config/confluence-daily.yaml default

# Or schedule with cron (daily at 2 AM)
# 0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/confluence-daily.yaml default
```

**What this does:**

- Indexes only pages modified in last 2 days
- Updates existing documents without deleting corpus
- Includes attachments for complete updates
- Runs quickly (fewer documents to process)

**Performance breakdown:**

- **Initial run:** Indexes all recent changes
- **Subsequent runs:** Only new/modified content
- **Recommended schedule:** Daily during off-peak hours

</div>

### Example 4: Label-Based API Documentation

<div class="example-card" markdown="1">

**Use Case:** Index only public-facing API documentation marked with specific labels.

**Best For:** Developer portals, public documentation, versioned APIs

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: api-docs-public
  remove_boilerplate: true

crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://company.atlassian.net/wiki"

  # Only API space with public label
  confluence_cql: >
    space = "API"
    and type = page
    and label IN ("public", "published")
    and status = current

  confluence_include_attachments: true

metadata:
  source: confluence
  visibility: public
  content_type: api-documentation
  space: API
```

**Setup and run:**

```bash
# Create secrets.toml
cat > secrets.toml <<EOF
[default]
CONFLUENCE_USERNAME = "api-docs@company.com"
CONFLUENCE_PASSWORD = "ATATT3xFfGF0your-api-token"
EOF

# Run crawler
bash run.sh config/api-docs.yaml default
```

**What this does:**

- Indexes only API space pages
- Filters to pages labeled "public" or "published"
- Excludes internal/draft documentation
- Includes specification attachments (PDFs, etc.)

**Pro tips:**

- Use consistent labeling strategy in Confluence
- Create separate corpus for internal vs public docs
- Test CQL query in Confluence before running

</div>

---

## Confluence Cloud vs Server/Data Center

### Confluence Cloud

**Configuration:**

```yaml
crawling:
  crawler_type: confluence

confluence_crawler:
  confluence_base_url: "https://workspace.atlassian.net/wiki"
  confluence_cql: 'space = "DOCS"'
```

**Characteristics:**

- URL format: `https://*.atlassian.net/wiki`
- Authentication: Email + API token (recommended)
- API: REST API v2
- Rate limits: ~60 requests/minute
- Body format: `anonymous_export_view` (HTML)

### Confluence Server/Data Center

**Configuration:**

```yaml
crawling:
  crawler_type: confluencedatacenter

confluencedatacenter:
  base_url: "http://confluence.internal:8090"
  confluence_cql: 'space = "DOCS"'
  body_view: "export_view"  # or "styled_view", "storage"
```

**Characteristics:**

- URL format: Custom (e.g., `http://internal:8090`)
- Authentication: Username + password or API token
- API: REST API v1
- Rate limits: Configurable by admin
- Body formats: Multiple options

---

## Troubleshooting

<div class="troubleshoot-card">
  <h3>Authentication Failures</h3>
  <p><strong>Symptom:</strong> 401 Unauthorized errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Verify API token starts with <code>ATATT</code> (not password)</li>
    <li>Check email/username is correct</li>
    <li>Ensure token hasn't expired</li>
    <li>For Data Center, verify basic auth is enabled</li>
    <li>Test credentials manually with curl or Postman</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Invalid CQL Errors</h3>
  <p><strong>Symptom:</strong> 400 Bad Request with CQL errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Test CQL query in Confluence UI first</li>
    <li>Check for proper quote usage (single vs double)</li>
    <li>Verify space names/keys are exact matches</li>
    <li>Ensure field names are correct (e.g., <code>lastModified</code> not <code>lastUpdated</code>)</li>
    <li>Review <a href="https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/">CQL documentation</a></li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>No Content Indexed</h3>
  <p><strong>Symptom:</strong> Crawler completes but no documents indexed</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Verify CQL query returns results in Confluence UI</li>
    <li>Check user has read permissions on spaces</li>
    <li>Ensure space names in CQL match exactly</li>
    <li>Try simpler query: <code>type IN (page, blogpost)</code></li>
    <li>Enable <code>verbose: true</code> for detailed logs</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Rate Limiting (429)</h3>
  <p><strong>Symptom:</strong> Too Many Requests errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Confluence Cloud limit: ~60 requests/minute</li>
    <li>Add delays between requests (built-in)</li>
    <li>Crawl during off-peak hours</li>
    <li>Split large spaces into multiple crawls</li>
    <li>Contact support for higher limits (Cloud)</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Slow Crawling</h3>
  <p><strong>Symptom:</strong> Crawler takes too long</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Disable attachments: <code>confluence_include_attachments: false</code></li>
    <li>Use more specific CQL (fewer results)</li>
    <li>Filter by date: <code>lastModified >= -30d</code></li>
    <li>Reduce chunk size for faster processing</li>
    <li>Check network connectivity to Confluence</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Memory Issues</h3>
  <p><strong>Symptom:</strong> Out of memory, process crashes</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Disable or limit attachments</li>
    <li>Reduce chunk size in Vectara config</li>
    <li>Increase Docker memory allocation</li>
    <li>Index in batches using date-based CQL</li>
    <li>Split spaces into separate crawls</li>
  </ul>
</div>

## Best Practices

<div class="best-practice-grid">

  <div class="best-practice-card">
    <h3>Start with Single Space</h3>
    <p>Begin with one space to validate your setup:</p>

```yaml
confluence_cql: 'space = "TEST" and type = page'
```

<p>Once validated, expand to more spaces.</p>
  </div>

  <div class="best-practice-card">
    <h3>Test CQL Queries First</h3>
    <p>Always test CQL in Confluence UI before using in config:</p>
<ol>
<li>Content → Search → Advanced</li>
<li>Enter CQL query</li>
<li>Verify results</li>
</ol>
  </div>

  <div class="best-practice-card">
    <h3>Use Service Accounts</h3>
    <p>For production:</p>
<ul>
<li>Create dedicated Confluence service account</li>
<li>Generate API token for that account</li>
<li>Easier token rotation and auditing</li>
</ul>
  </div>

  <div class="best-practice-card">
    <h3>Incremental Updates</h3>
    <p>For large spaces, use date-based incremental updates:</p>

```yaml
confluence_cql: 'lastModified >= -1d'
```

<p>Schedule daily to keep index fresh.</p>
  </div>

  <div class="best-practice-card">
    <h3>Label Strategy</h3>
    <p>Maintain consistent labeling in Confluence:</p>
<ul>
<li>Use labels to mark public/internal content</li>
<li>Filter by labels for selective indexing</li>
<li>Document label conventions</li>
</ul>
  </div>

  <div class="best-practice-card">
    <h3>Monitor Performance</h3>
    <p>Track crawl metrics:</p>

```bash
# Enable verbose logging
vectara:
  verbose: true

# Monitor in real-time
docker logs -f vingest
```
  </div>

</div>

---

## Additional Resources

- [CQL Reference](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
- [Confluence Cloud API](https://developer.atlassian.com/cloud/confluence/rest/intro/)
- [API Token Management](https://id.atlassian.com/manage-profile/security/api-tokens)
- [Confluence Data Center API](https://developer.atlassian.com/server/confluence/confluence-server-rest-api-overview/)
