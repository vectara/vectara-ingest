# Jira Crawler

The Jira crawler indexes issues from Jira Cloud, Server, and Data Center instances with full support for issue descriptions, comments, attachments, and custom fields.

<div class="crawler-info-cards">
  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
      </div>
      <strong>Crawler Type</strong>
    </div>
    <code>jira</code>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
      </div>
      <strong>Authentication</strong>
    </div>
    <p>Basic auth (username/password or API token)</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><filter id="filter0"><feFlood flood-color="#4B5563" result="bg" /><feMerge><feMergeNode in="bg"/><feMergeNode in="SourceGraphic"/></feMerge></filter><rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="none"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
      </div>
      <strong>Content Types</strong>
    </div>
    <p>Issues, descriptions, comments, attachments, custom fields</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
      </div>
      <strong>Filtering</strong>
    </div>
    <p>JQL (Jira Query Language) for advanced queries</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>
      </div>
      <strong>Attachments</strong>
    </div>
    <p>Images and documents (PDF, DOCX, XLSX, etc.)</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
      </div>
      <strong>API Support</strong>
    </div>
    <p>Jira REST API v2 and v3</p>
  </div>
</div>

---

## How It Works

<div class="use-cases-list">
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Authentication</strong> - Connects to Jira using API token or username/password</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Issue Discovery</strong> - Uses JQL queries to discover issues matching your criteria</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Content Extraction</strong> - Retrieves issue descriptions and comments in Atlassian Document Format (ADF)</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Metadata Capture</strong> - Extracts issue key, project, status, assignee, priority, and custom fields</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Attachment Processing</strong> - Optionally downloads and extracts text from image and document attachments</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Indexing</strong> - Sends extracted content to Vectara with all captured metadata</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Incremental Updates</strong> - Supports incremental crawling by only indexing new/updated issues</span>
  </div>
</div>

---

## Configuration Parameters

### Instance and Query Configuration

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `jira_base_url` | string | Yes | - | Jira instance URL (https://your-company.atlassian.net) |
| `jira_jql` | string | Yes | - | JQL query to filter issues |
| `api_version` | int | No | `3` | Jira API version (2 or 3) |
| `max_results` | int | No | `100` | Results per page for pagination |

### Authentication

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `jira_username` | string | Yes | Email (Cloud) or username (Server) - loaded from `JIRA_USERNAME` |
| `jira_password` | string | Yes | API token (Cloud) or password (Server) - loaded from `JIRA_PASSWORD` |

**Note:** Authentication credentials should be stored in `secrets.toml` and loaded via environment variables.

### Field Selection

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fields` | list | [default fields] | Fields to extract from issues (supports custom fields) |

### Attachment Processing

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_image_attachments` | boolean | `true` | Index image attachments (PNG, JPG, etc.) |
| `include_document_attachments` | boolean | `false` | Index document attachments (PDF, DOCX, XLSX, etc.) |

---

## Content Extraction

<div class="content-extraction-grid">
  <div class="extraction-card">
    <h3>Issue Content</h3>
    <p>The crawler extracts full issue content with rich text formatting.</p>

<p><strong>Extracted data:</strong></p>
<ul>
  <li>Issue summary (title)</li>
  <li>Description in ADF format</li>
  <li>All comments with author info</li>
  <li>Issue status and workflow state</li>
  <li>Priority level</li>
  <li>Direct links to Jira</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Metadata</h3>
    <p>All issue metadata is automatically extracted and indexed for filtering.</p>

<p><strong>Captured metadata:</strong></p>
<ul>
  <li>Issue key (e.g., PROJ-123)</li>
  <li>Project name and key</li>
  <li>Issue type (Bug, Story, Task, etc.)</li>
  <li>Status (Open, In Progress, Closed)</li>
  <li>Priority level</li>
  <li>Reporter and assignee</li>
  <li>Creation and update timestamps</li>
  <li>Resolution date</li>
  <li>Labels/tags</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Custom Fields</h3>
    <p>Supports extraction of any custom fields configured in your Jira instance.</p>

<p><strong>Custom field support:</strong></p>
<ul>
  <li>Text fields</li>
  <li>Select fields (single/multi)</li>
  <li>Number fields</li>
  <li>Date fields</li>
  <li>User picker fields</li>
  <li>Specify by field ID (customfield_10001)</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Image Attachments</h3>
    <p>When enabled, the crawler processes image attachments with optional AI summarization.</p>

<p><strong>Supported formats:</strong></p>
<ul>
  <li>PNG, JPG, JPEG</li>
  <li>GIF, BMP, WEBP</li>
  <li>SVG</li>
</ul>

<p><strong>Processing options:</strong></p>
<ul>
  <li>AI-powered image summarization</li>
  <li>Metadata extraction</li>
  <li>Parent issue linking</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Document Attachments</h3>
    <p>Extracts text content from various document formats.</p>

<p><strong>Supported formats:</strong></p>
<ul>
  <li>PDF documents</li>
  <li>Word: DOC, DOCX</li>
  <li>Excel: XLS, XLSX</li>
  <li>PowerPoint: PPT, PPTX</li>
  <li>Text: TXT, MD</li>
</ul>

<p><strong>Processing features:</strong></p>
<ul>
  <li>Table extraction</li>
  <li>Structured chunking</li>
  <li>OCR support (optional)</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Comments</h3>
    <p>All issue comments are extracted with full author information and timestamps.</p>

<p><strong>Comment data:</strong></p>
<ul>
  <li>Comment body (ADF format)</li>
  <li>Author name and email</li>
  <li>Creation timestamp</li>
  <li>Update timestamp</li>
  <li>Comment ID</li>
  <li>Nested thread support</li>
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
      <li>Generate a Jira API token (see <a href="#getting-your-jira-api-credentials">below</a>)</li>
      <li>Identify the projects or issues you want to index</li>
    </ul>
  </div>
</div>

<div class="quick-start-card">
  <h3>Quick Start</h3>
  <p>Here's the simplest way to index Jira issues:</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-issues
  remove_boilerplate: false

crawling:
  crawler_type: jira

jira_crawler:
  jira_base_url: "https://your-company.atlassian.net"
  jira_jql: "project = MY AND resolution = Unresolved"
  api_version: 3

metadata:
  source: jira
```

<p><strong>Add credentials to <code>secrets.toml</code>:</strong></p>

```toml
[default]
JIRA_USERNAME = "your-email@example.com"
JIRA_PASSWORD = "your-api-token"  # NOT your Jira password
```

<p><strong>Run:</strong></p>

```bash
bash run.sh config/jira-issues.yaml default
```

</div>

### Getting Your Jira API Credentials

#### For Jira Cloud

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile)
2. Click **Security** in the left sidebar
3. Click **Create and manage your API tokens**
4. Click **Create API token**
5. Enter a label (e.g., "Vectara Ingest")
6. Copy the token (you'll only see it once)

Your credentials are:
- **Username**: Your Atlassian email address
- **Password**: The API token you just created (NOT your Jira password)

#### For Jira Server/Data Center

Server and Data Center use the same API endpoints but support different authentication:

- **Option 1**: Create an API token (if supported by your instance)
- **Option 2**: Use your Jira username and password directly
- **Option 3**: Contact your Jira administrator for service account credentials

---

## JQL Query Language

Jira Query Language (JQL) provides powerful filtering capabilities for selecting exactly the issues you want to index.

### Basic Project Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Single project</h4>

```yaml
jira_jql: "project = MYPROJ"
```

<p>Indexes all issues in the MYPROJ project.</p>
</div>

<div class="cql-example-card">
  <h4>Multiple projects</h4>

```yaml
jira_jql: "project IN (PROJ1, PROJ2, PROJ3)"
```

<p>Indexes issues from multiple projects.</p>
</div>

<div class="cql-example-card">
  <h4>By status</h4>

```yaml
jira_jql: "project = MYPROJ AND resolution = Unresolved"
```

<p>Only unresolved (open) issues.</p>
</div>

<div class="cql-example-card">
  <h4>By issue type</h4>

```yaml
jira_jql: "project = MYPROJ AND type IN (Bug, Story)"
```

<p>Only bugs and stories, excluding other issue types.</p>
</div>

</div>

### Time-Based Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Recent updates</h4>

```yaml
jira_jql: "project = MYPROJ AND updated >= -30d"
```

<p><strong>Best for:</strong> Incremental crawls - only issues updated in last 30 days.</p>
</div>

<div class="cql-example-card">
  <h4>Date range</h4>

```yaml
jira_jql: 'project = MYPROJ AND created >= "2024-01-01" AND created <= "2024-12-31"'
```

<p><strong>Best for:</strong> Indexing issues from a specific time period.</p>
</div>

<div class="cql-example-card">
  <h4>Recently closed</h4>

```yaml
jira_jql: "project = MYPROJ AND status = Closed AND updated >= -7d"
```

<p><strong>Best for:</strong> Tracking recently resolved issues.</p>
</div>

<div class="cql-example-card">
  <h4>Created this quarter</h4>

```yaml
jira_jql: "project = MYPROJ AND created >= startOfQuarter()"
```

<p><strong>Best for:</strong> Current quarter reporting and analytics.</p>
</div>

</div>

### Advanced Queries

<div class="cql-examples-grid">

<div class="cql-example-card">
  <h4>Priority filtering</h4>

```yaml
jira_jql: "project = MYPROJ AND priority >= High AND resolution = Unresolved"
```

<p><strong>Use case:</strong> Focus on high-priority open issues.</p>
</div>

<div class="cql-example-card">
  <h4>Text search</h4>

```yaml
jira_jql: 'project = MYPROJ AND text ~ "performance optimization"'
```

<p><strong>Use case:</strong> Issues containing specific keywords in any field.</p>
</div>

<div class="cql-example-card">
  <h4>With attachments</h4>

```yaml
jira_jql: "project = MYPROJ AND attachments > 0"
```

<p><strong>Use case:</strong> Only issues that have file attachments.</p>
</div>

<div class="cql-example-card">
  <h4>Complex conditions</h4>

```yaml
jira_jql: 'project = TECH AND type = Bug AND (priority = Critical OR priority = Blocker) AND status != Closed'
```

<p><strong>Use case:</strong> Critical/blocker bugs that are still open.</p>
</div>

</div>

---

## API Version Comparison

<div class="crawl-methods-grid">
  <div class="method-card">
    <h3>API v3 <span class="recommended-badge">Recommended</span></h3>
    <p>Modern API for Jira Cloud with improved performance.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>jira_crawler:<br>  api_version: 3</code>
    </div>

    <div class="method-section">
      <h4>Best for:</h4>
      <ul>
        <li>Jira Cloud instances</li>
        <li>New integrations</li>
        <li>Better performance needs</li>
        <li>Custom field support</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Features:</h4>
      <ul>
        <li>Token-based pagination</li>
        <li>Full custom field support</li>
        <li>Optimized for speed</li>
        <li>Modern API design</li>
      </ul>
    </div>
  </div>

  <div class="method-card">
    <h3>API v2</h3>
    <p>Legacy API for Server/Data Center compatibility.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>jira_crawler:<br>  api_version: 2</code>
    </div>

    <div class="method-section">
      <h4>Best for:</h4>
      <ul>
        <li>Jira Server instances</li>
        <li>Jira Data Center</li>
        <li>Legacy integrations</li>
        <li>On-premise deployments</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Features:</h4>
      <ul>
        <li>Offset-based pagination</li>
        <li>Standard field support</li>
        <li>Proven stability</li>
        <li>Wide compatibility</li>
      </ul>
    </div>
  </div>
</div>

---

## Attachment Handling

<div class="crawl-methods-grid">
  <div class="method-card">
    <h3>Image Attachments</h3>
    <p>Process image files attached to Jira issues.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>jira_crawler:<br>  include_image_attachments: true<br><br>doc_processing:<br>  summarize_images: true</code>
    </div>

    <div class="method-section">
      <h4>Supported formats:</h4>
      <ul>
        <li>PNG, JPG, JPEG</li>
        <li>GIF, BMP, WEBP</li>
        <li>SVG</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Processing options:</h4>
      <ul>
        <li>AI summarization with GPT-4</li>
        <li>Metadata extraction</li>
        <li>Parent issue linking</li>
        <li>Searchable descriptions</li>
      </ul>
    </div>

    <div class="when-to-use">
      <div class="when-to-use-icon">💡</div>
      <div>
        <h4>When to use</h4>
        <p>Enable when issues contain screenshots, diagrams, or visual documentation</p>
      </div>
    </div>
  </div>

  <div class="method-card">
    <h3>Document Attachments</h3>
    <p>Extract text from document files attached to issues.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>jira_crawler:<br>  include_document_attachments: true<br><br>doc_processing:<br>  doc_parser: unstructured<br>  parse_tables: true</code>
    </div>

    <div class="method-section">
      <h4>Supported formats:</h4>
      <ul>
        <li>PDF documents</li>
        <li>Word: DOC, DOCX</li>
        <li>Excel: XLS, XLSX</li>
        <li>PowerPoint: PPT, PPTX</li>
        <li>Text: TXT, MD</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Processing features:</h4>
      <ul>
        <li>Text extraction</li>
        <li>Table parsing</li>
        <li>Structured chunking</li>
        <li>OCR support (optional)</li>
      </ul>
    </div>

    <div class="when-to-use">
      <div class="when-to-use-icon">💡</div>
      <div>
        <h4>When to use</h4>
        <p>Enable when issues have technical docs, specs, or reports attached</p>
      </div>
    </div>
  </div>
</div>

---

## Configuration Examples

<div class="example-section">
  <h3>Example 1: Simple Bug Tracking</h3>
  <p>Index all unresolved bugs for a knowledge base</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-bugs

crawling:
  crawler_type: jira

jira_crawler:
  jira_base_url: "https://company.atlassian.net"
  jira_username: "${JIRA_USERNAME}"
  jira_password: "${JIRA_PASSWORD}"
  jira_jql: "type = Bug AND resolution = Unresolved"
  api_version: 3
  max_results: 50

metadata:
  source: jira
  issue_type: bug
```
</div>

<div class="example-section">
  <h3>Example 2: Technical Documentation</h3>
  <p>Index documentation issues with attachments</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-docs
  remove_boilerplate: false

crawling:
  crawler_type: jira

jira_crawler:
  jira_base_url: "https://company.atlassian.net"
  jira_username: "${JIRA_USERNAME}"
  jira_password: "${JIRA_PASSWORD}"
  jira_jql: |
    project = "Technical Docs"
    AND type IN (Documentation, Specification)
    AND status = Published
  api_version: 3
  include_image_attachments: true
  include_document_attachments: true

doc_processing:
  doc_parser: unstructured
  parse_tables: true
  summarize_images: true
  use_core_indexing: false

metadata:
  source: jira
  content_type: documentation
```
</div>

<div class="example-section">
  <h3>Example 3: Full-Featured with Custom Fields</h3>
  <p>Complete configuration with all features</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: jira

jira_crawler:
  jira_base_url: "https://company.atlassian.net"
  jira_username: "${JIRA_USERNAME}"
  jira_password: "${JIRA_PASSWORD}"
  jira_jql: |
    project = PROJ
    AND status != Backlog
    AND updated >= -180d
  api_version: 3
  max_results: 100

  # Custom field extraction
  fields:
    - summary
    - description
    - comment
    - project
    - issuetype
    - status
    - priority
    - reporter
    - assignee
    - created
    - updated
    - resolutiondate
    - labels
    - attachment
    - customfield_10001  # Technical Debt Level
    - customfield_10002  # API Endpoint

  # Attachment processing
  include_image_attachments: true
  include_document_attachments: true

doc_processing:
  doc_parser: unstructured
  do_ocr: false
  parse_tables: true
  summarize_images: true
  use_core_indexing: false
  process_locally: true

  unstructured_config:
    chunking_strategy: by_title
    chunk_size: 3000

  model_config:
    text:
      provider: openai
      model_name: "gpt-4-mini"
    vision:
      provider: openai
      model_name: "gpt-4-mini"

metadata:
  source: jira
  environment: production
  sync_frequency: daily
```
</div>

---

## Troubleshooting

<div class="troubleshoot-card">
  <h3>Authentication Failed</h3>
  <p><strong>Symptom:</strong> 401 Unauthorized errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Verify API token is correct (Cloud only)</li>
    <li>For Cloud, use email address, not username</li>
    <li>Ensure password is NOT your Jira password (use API token)</li>
    <li>Check credentials in environment variables: <code>echo $JIRA_USERNAME</code></li>
    <li>Verify user has API access enabled</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>No Issues Found</h3>
  <p><strong>Symptom:</strong> Crawler runs but indexes 0 issues</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Test JQL query in Jira UI first</li>
    <li>Verify project key is correct (check Project Settings > Details)</li>
    <li>Try simpler JQL: <code>project = MYPROJ</code></li>
    <li>Check user has permission to see issues</li>
    <li>Verify status values are case-sensitive</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Attachment Download Fails</h3>
  <p><strong>Symptom:</strong> Failed to process attachment errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Verify attachment file types are supported</li>
    <li>Check file size isn't too large</li>
    <li>Ensure user has attachment download permissions</li>
    <li>Try disabling attachments to verify issue content works</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Rate Limiting (429)</h3>
  <p><strong>Symptom:</strong> Too Many Requests errors</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Jira Cloud has rate limits (standard 10 requests/second)</li>
    <li>Reduce batch size: <code>max_results: 50</code></li>
    <li>Add delays between API calls if doing multiple runs</li>
    <li>For Data Center, check with admin for rate limits</li>
  </ul>
</div>

---

## Best Practices

<div class="best-practice-grid">

  <div class="best-practice-card">
    <h3>Start with Small Crawls</h3>
    <p>Test with a limited query first:</p>

```yaml
jira_jql: "project = TEST LIMIT 10"
```

<p>Then expand to production queries once verified.</p>
  </div>

  <div class="best-practice-card">
    <h3>Use Targeted JQL Queries</h3>
    <p>Instead of fetching all issues:</p>

```yaml
# Good: Only relevant issues
jira_jql: "project = MYPROJ AND status != Backlog AND updated >= -90d"
```
  </div>

  <div class="best-practice-card">
    <h3>Organize By Project</h3>
    <p>Create separate configs for large Jira instances:</p>

```
config/
  jira-engineering.yaml
  jira-product.yaml
  jira-operations.yaml
```
  </div>

  <div class="best-practice-card">
    <h3>Document Your JQL</h3>
    <p>Add comments to explain complex queries:</p>

```yaml
# Fetch all open bugs and stories updated in last 90 days
# Excludes old/backlog items to focus on active work
jira_jql: |
  project = MYPROJ
  AND type in (Bug, Story)
  AND status != Backlog
  AND updated >= -90d
```
  </div>

  <div class="best-practice-card">
    <h3>Regular Incremental Updates</h3>
    <p>Schedule daily crawls with time-based filters:</p>

```yaml
jira_jql: "project = MYPROJ AND updated >= -1d"
```

<p>Schedule daily to keep index fresh.</p>
  </div>

  <div class="best-practice-card">
    <h3>Monitor Indexing</h3>
    <p>Enable verbose logging:</p>

```yaml
vectara:
  verbose: true
```
  </div>
</div>

---

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## External Resources

- [Jira Query Language (JQL) Documentation](https://support.atlassian.com/jira-service-desk-cloud/articles/reference-the-jira-query-language-jql/)
- [Jira API v3 Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Jira API v2 Documentation](https://docs.atlassian.com/software/jira/docs/api/REST/2.0/)
- [Atlassian Document Format (ADF)](https://developer.atlassian.com/cloud/jira/platform/apis/document/adf/)
