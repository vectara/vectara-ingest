# Jira Crawler

The Jira crawler indexes issues from Jira Cloud, Server, and Data Center instances with full support for issue descriptions, comments, attachments, and custom fields.

## Overview

- **Crawler Type**: `jira`
- **Authentication**: Basic auth (username/password or API token)
- **API Support**: Jira REST API v2 and v3
- **Issue Content**: Descriptions, comments, attachments, and metadata
- **Attachment Types**: Images and documents (PDFs, DOCX, XLSX, etc.)
- **Format Support**: Atlassian Document Format (ADF) parsing for rich content

## Use Cases

- Knowledge base from tracked issues
- Bug tracking and resolution history
- Feature request documentation
- Technical specifications from Jira issues
- Problem resolution archives
- Team documentation from issue discussions

## Getting Started: API Authentication

### Get Your Jira API Credentials

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

### Setting Environment Variables

Store your credentials securely as environment variables:

```bash
# For Jira Cloud
export JIRA_USERNAME="your-email@example.com"
export JIRA_PASSWORD="your-api-token"  # NOT your Jira password

# For Jira Server/Data Center
export JIRA_USERNAME="jira_service_account"
export JIRA_PASSWORD="your-jira-password"
```

The crawler will automatically read these from your environment.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-issues

crawling:
  crawler_type: jira

jira_crawler:
  # Jira instance URL (without trailing slash)
  jira_base_url: "https://your-company.atlassian.net"

  # Credentials (read from environment: JIRA_USERNAME, JIRA_PASSWORD)
  jira_username: "${JIRA_USERNAME}"
  jira_password: "${JIRA_PASSWORD}"

  # JQL query to filter issues
  jira_jql: "project = MY AND resolution = Unresolved"

  # API version (2 or 3)
  api_version: 3

  # Maximum results per page
  max_results: 100
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: jira-kb
  reindex: false
  verbose: true

crawling:
  crawler_type: jira

jira_crawler:
  jira_base_url: "https://jira.example.com"
  jira_username: "${JIRA_USERNAME}"
  jira_password: "${JIRA_PASSWORD}"

  # Advanced JQL query with multiple conditions
  jira_jql: 'project = "Engineering" AND type = Bug AND created >= -30d'

  # API version selection
  api_version: 3  # Use v3 for Cloud (recommended), v2 for Server

  # Custom field selection
  fields:
    - summary
    - description
    - comment
    - attachment
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
    - customfield_10001  # Custom fields supported

  # Pagination
  max_results: 100  # Per page (max 100 for API v2, no limit for v3)

  # Attachment processing
  include_image_attachments: true   # PNG, JPG, GIF, etc.
  include_document_attachments: true # PDF, DOCX, XLSX, etc.

doc_processing:
  # NOTE: This section applies ONLY to attachments
  # Issue descriptions/comments use vectara.chunking_strategy

  doc_parser: unstructured
  do_ocr: false
  parse_tables: true
  summarize_images: true

  use_core_indexing: false  # Use structured indexing for better chunking
  process_locally: true

metadata:
  source: jira
  environment: production
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `jira_base_url` | string | Yes | - | Jira instance URL (https://your-company.atlassian.net) |
| `jira_username` | string | Yes | - | Jira username or email (Cloud) |
| `jira_password` | string | Yes | - | Jira password or API token |
| `jira_jql` | string | Yes | - | JQL query to filter issues |
| `api_version` | int | No | `3` | Jira API version (2 or 3) |
| `fields` | list | No | [default fields] | Fields to extract from issues |
| `max_results` | int | No | `100` | Results per page for pagination |
| `include_image_attachments` | bool | No | `true` | Index image attachments |
| `include_document_attachments` | bool | No | `false` | Index document attachments |

## Default Fields Extracted

If you don't specify custom `fields`, the crawler extracts:

- `summary` - Issue title
- `description` - Issue description (ADF format)
- `comment` - Issue comments (ADF format)
- `project` - Project information
- `issuetype` - Issue type (Bug, Story, Task, etc.)
- `status` - Current status (Open, In Progress, Closed, etc.)
- `priority` - Issue priority
- `reporter` - Who reported the issue
- `assignee` - Assigned team member
- `created` - Creation date
- `updated` - Last update date
- `resolutiondate` - Resolution date
- `labels` - Issue labels
- `attachment` - Attached files

## How It Works

### Issue Processing

1. **Query Execution**: Fetches issues matching your JQL query
2. **ADF Parsing**: Extracts text from Atlassian Document Format descriptions and comments
3. **Metadata Extraction**: Collects project, status, assignee, and other fields
4. **Comment Extraction**: Includes all comments with author information
5. **Indexing**: Sends structured issue data to Vectara

### Attachment Processing

For each attachment:
1. **Type Detection**: Identifies if it's an image or document
2. **Download**: Fetches the attachment content from Jira
3. **Processing**: Processes based on type:
   - **Images**: Can be summarized by AI if `summarize_images: true`
   - **Documents**: Extracted and chunked by unstructured parser
4. **Metadata**: Indexes with parent issue information
5. **Cleanup**: Removes temporary files

### Metadata Captured

The crawler automatically indexes:

- **Issue Key**: Unique issue identifier (e.g., "PROJ-123")
- **Summary**: Issue title
- **Project**: Project name
- **Type**: Issue type (Bug, Story, Task, Epic, etc.)
- **Status**: Current workflow status
- **Priority**: Issue priority level
- **Reporter**: Issue creator name
- **Assignee**: Currently assigned team member
- **Created**: Issue creation timestamp
- **Updated**: Last modification timestamp
- **Resolved**: Resolution date (if closed)
- **Labels**: Issue labels/tags
- **URL**: Link to browse issue in Jira
- **Source**: Always "jira"

## JQL Query Examples

### Basic Queries

```yaml
# All unresolved issues in a project
jira_jql: "project = MYPROJ AND resolution = Unresolved"

# Issues closed in the last 30 days
jira_jql: "project = MYPROJ AND updated >= -30d AND status = Closed"

# All issues with a specific label
jira_jql: "project = MYPROJ AND labels = documentation"

# Issues assigned to specific team member
jira_jql: "project = MYPROJ AND assignee = john@example.com"
```

### Advanced Queries

```yaml
# Multiple projects, only certain types
jira_jql: 'project in (PROJ1, PROJ2) AND type in (Bug, Epic) AND status != Closed'

# Issues with specific priority and recent activity
jira_jql: 'priority >= High AND updated >= -7d'

# Complex conditions with text search
jira_jql: 'project = MYPROJ AND text ~ "performance" AND resolution = Unresolved'

# Issues with attachments
jira_jql: 'project = MYPROJ AND attachments > 0'

# Issues updated in a date range
jira_jql: 'project = MYPROJ AND updated >= "2024-01-01" AND updated <= "2024-12-31"'
```

### Documentation-Focused Queries

```yaml
# Issues marked as documentation
jira_jql: 'project = DOCS AND type = "Technical Documentation"'

# Feature specifications
jira_jql: 'project = PROJ AND type = Story AND labels = specification'

# Design decisions and ADRs
jira_jql: 'project = ARCH AND type = Decision'

# API documentation from issues
jira_jql: 'text ~ API AND labels = documentation'
```

## Cloud vs Server/Data Center

### Jira Cloud

- **API Version**: Use API v3 (recommended)
- **Authentication**: Email + API token
- **Limitations**: Some advanced features may be Cloud-only
- **Base URL**: `https://your-company.atlassian.net`

```yaml
jira_crawler:
  jira_base_url: "https://your-company.atlassian.net"
  jira_username: "your-email@example.com"
  jira_password: "${JIRA_API_TOKEN}"  # NOT password
  api_version: 3
```

### Jira Server/Data Center

- **API Version**: Use API v2 (Cloud supports both v2 and v3)
- **Authentication**: Username + password (or service account)
- **Self-Hosted**: Full control over configuration
- **Base URL**: `https://jira.example.com` or internal domain

```yaml
jira_crawler:
  jira_base_url: "https://jira.example.com"
  jira_username: "service_account"
  jira_password: "${JIRA_PASSWORD}"
  api_version: 2
```

### API Version Differences

| Feature | API v2 | API v3 |
|---------|--------|--------|
| **Availability** | Server, Cloud | Cloud (recommended) |
| **Pagination** | Offset-based (`startAt`) | Token-based (`nextPageToken`) |
| **Fields** | Standard fields only | Support for custom fields |
| **Performance** | Slightly slower | Optimized for speed |
| **Modern Features** | Limited | Full support |

## Attachment Handling

### Image Attachments

Supported image types: PNG, JPG, JPEG, GIF, BMP, WEBP, SVG

```yaml
jira_crawler:
  include_image_attachments: true

doc_processing:
  summarize_images: true  # Use AI to describe images
```

When enabled:
- Images are downloaded from Jira
- Optionally summarized by AI models
- Indexed with parent issue metadata
- Searchable through Vectara

### Document Attachments

Supported document types: PDF, DOCX, XLSX, PPTX, TXT, MD, DOC, XLS, PPT

```yaml
jira_crawler:
  include_document_attachments: true

doc_processing:
  doc_parser: unstructured  # Extract text from documents
  parse_tables: true        # Parse tables in documents
  use_core_indexing: false  # Structured indexing for better chunking
```

When enabled:
- Documents are downloaded and parsed
- Tables are extracted and indexed
- Proper chunking preserves document structure
- Full metadata preserved

### Disabling Attachments

To skip all attachment processing:

```yaml
jira_crawler:
  include_image_attachments: false
  include_document_attachments: false
```

This speeds up indexing if you only need issue text.

### Attachment Metadata

Each indexed attachment includes:

- `attachment_id` - Unique Jira attachment ID
- `filename` - Original file name
- `mime_type` - File MIME type
- `file_size` - File size in bytes
- `created` - Upload date
- `attachment_author` - Who uploaded it
- `parent_issue` - Parent issue key
- `attachment_type` - "image" or "document"
- All parent issue metadata

## Custom Field Extraction

### Adding Custom Fields

To index custom fields, specify them by their ID:

```yaml
jira_crawler:
  fields:
    # Standard fields
    - summary
    - description
    - comment
    - project
    - status

    # Custom fields (use their IDs)
    - customfield_10001  # Custom select field
    - customfield_10002  # Custom text area
    - customfield_10003  # Custom date field
```

### Finding Custom Field IDs

1. Go to your Jira instance
2. Edit an issue and inspect the field ID in the HTML (e.g., `customfield_10001`)
3. Or use the Jira REST API:

```bash
curl -u "username:password" \
  "https://your-company.atlassian.net/rest/api/3/field"
```

### Custom Field Example

```yaml
jira_crawler:
  jira_base_url: "https://company.atlassian.net"
  jira_jql: "project = TECH"
  fields:
    - summary
    - description
    - comment
    - project
    - issuetype
    - status
    - customfield_10001  # "Technical Debt Level"
    - customfield_10002  # "API Endpoint"
    - customfield_10003  # "Performance Impact"
```

## Performance Tips for Large Instances

### 1. Use Targeted JQL Queries

Instead of fetching all issues:

```yaml
# Bad: Fetches everything
jira_jql: "project = MYPROJ"

# Good: Only relevant issues
jira_jql: "project = MYPROJ AND status != Backlog AND updated >= -90d"
```

### 2. Batch by Project or Status

Create separate configs for different categories:

```yaml
# config/jira-bugs.yaml
jira_crawler:
  jira_jql: "project = MYPROJ AND type = Bug AND resolution = Unresolved"

# config/jira-docs.yaml
jira_crawler:
  jira_jql: "project = DOCS AND type = Documentation"
```

### 3. Disable Unnecessary Attachments

Skip attachments if you only need issue text:

```yaml
jira_crawler:
  include_image_attachments: false
  include_document_attachments: false
```

### 4. Tune Pagination

Adjust `max_results` based on issue complexity:

```yaml
jira_crawler:
  # Smaller batches for complex issues with many attachments
  max_results: 50

  # Larger batches for simple issues
  max_results: 100
```

### 5. Use Efficient Chunking

For attachments:

```yaml
doc_processing:
  use_core_indexing: false  # Structured for better performance
  unstructured_config:
    chunking_strategy: by_title  # Semantic boundaries
    chunk_size: 3000             # Reasonable chunk size
```

### 6. Schedule Off-Peak Runs

Run large crawls during off-hours to minimize impact:

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/jira-large.yaml default
```

### 7. Monitor Memory Usage

For instances with thousands of issues:

```yaml
# Process locally to save memory
doc_processing:
  process_locally: true
```

### 8. Reindex Strategy

On subsequent runs, use appropriate reindex settings:

```yaml
vectara:
  # First run: create new corpus
  reindex: true

  # Subsequent runs: only index new/updated issues
  reindex: false
```

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized`

**Solutions**:
1. Verify API token is correct (Cloud only)
2. For Cloud, use email address, not username
3. Ensure password is NOT your Jira password (use API token)
4. Check credentials are set in environment variables:
   ```bash
   echo $JIRA_USERNAME
   echo $JIRA_PASSWORD
   ```
5. Verify user has API access enabled

### No Issues Found

**Error**: Crawler runs but indexes 0 issues

**Solutions**:
1. Check JQL query syntax:
   ```bash
   # Test in Jira UI first
   ```
2. Verify project key is correct:
   - Go to Project Settings > Details
   - Confirm the project key
3. Try simpler JQL:
   ```yaml
   jira_jql: "project = MYPROJ"
   ```
4. Check user has permission to see issues
5. Verify issue status values (case-sensitive):
   ```bash
   # List available statuses
   curl -u "user:token" "https://company.atlassian.net/rest/api/3/status"
   ```

### Attachment Download Fails

**Error**: `Failed to process attachment`

**Solutions**:
1. Verify attachment file types are supported
2. Check file size isn't too large
3. Ensure user has attachment download permissions
4. Try disabling attachments to verify issue content works:
   ```yaml
   include_image_attachments: false
   include_document_attachments: false
   ```

### ADF Parsing Issues

**Error**: `Failed to extract description for PROJ-123`

**Solutions**:
1. This is usually non-fatal; descriptions may be in plain text
2. Check logs for specific ADF parsing errors
3. Try a different sample issue to verify format
4. Contact Jira support if issue seems malformed

### SSL Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:
1. For self-signed certificates in dev:
   ```yaml
   jira_crawler:
     ssl_verify: false
   ```
2. For proper certificates, update your CA bundle
3. For on-prem Jira, work with IT to configure proper certs

### Rate Limiting

**Error**: `429 Too Many Requests`

**Solutions**:
1. Jira Cloud has rate limits (standard 10 requests/second)
2. Reduce batch size:
   ```yaml
   jira_crawler:
     max_results: 50  # Instead of 100
   ```
3. Add delays between API calls if doing multiple runs
4. For Data Center, check with admin for rate limits

## Best Practices

### 1. Start with Small Crawls

```yaml
# Test with a single project first
jira_jql: "project = TEST LIMIT 10"
```

Then expand to production:

```yaml
# Production query
jira_jql: "project = PROD AND updated >= -30d"
```

### 2. Use Descriptive Metadata

```yaml
metadata:
  source: jira
  environment: production
  jira_instance: "company.atlassian.net"
  sync_frequency: "daily"
```

### 3. Organize By Project

Create separate configs for large Jira instances:

```
config/
  jira-engineering.yaml
  jira-product.yaml
  jira-operations.yaml
```

### 4. Document Your JQL

Add comments to explain your query:

```yaml
jira_crawler:
  # Fetch all open bugs and stories updated in last 90 days
  # Excludes old/backlog items to focus on active work
  jira_jql: |
    project = MYPROJ
    AND type in (Bug, Story)
    AND status != Backlog
    AND updated >= -90d
```

### 5. Version Your Configurations

Track configuration changes:

```yaml
metadata:
  version: "1.0"
  created_date: "2024-01-15"
  last_updated: "2024-11-18"
  notes: "Initial Jira ingest setup"
```

### 6. Regular Reindexing

For most cases, periodic fresh crawls work best:

```bash
# Weekly full reindex
0 1 * * 0 cd /path && bash run.sh config/jira-prod.yaml default

# Or use reindex flag for incremental updates
vectara:
  reindex: false  # Only new/updated issues
```

### 7. Monitor Indexing

Watch logs for issues:

```bash
# Monitor crawler in real-time
docker logs -f vingest

# Or check specific errors
grep "Error" logs/ingest.log
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/jira-issues.yaml
```

Enter your configuration (see examples above).

### Set Environment Variables

```bash
export JIRA_USERNAME="your-email@example.com"
export JIRA_PASSWORD="your-api-token"
```

### Run the Crawler

```bash
# Run the crawler
bash run.sh config/jira-issues.yaml default

# Monitor progress
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/jira-issues.yaml default

# Twice weekly
0 2 * * 1,4 cd /path/to/vectara-ingest && bash run.sh config/jira-issues.yaml default
```

Or use your preferred scheduler (GitHub Actions, Jenkins, etc.).

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Complete Examples

### Example 1: Simple Unresolved Issues

```yaml
# Simple config: Index all open bugs
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
  max_results: 50

metadata:
  issue_type: bug
  priority: high
```

Save as `config/jira-bugs.yaml` and run:

```bash
bash run.sh config/jira-bugs.yaml default
```

### Example 2: Technical Documentation

```yaml
# Documentation from Jira
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
    AND type in (Documentation, Specification)
    AND status = Published
  api_version: 3
  max_results: 100

doc_processing:
  use_core_indexing: false

metadata:
  content_type: technical_documentation
  source: jira
```

### Example 3: Complete with Attachments

```yaml
# Full-featured config with attachments
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
  content_types:
    - issues
    - attachments
    - comments
```

Save as `config/jira-full.yaml` and run:

```bash
bash run.sh config/jira-full.yaml default
```

## API Reference

### Supported Jira Instances

- **Jira Cloud**: Full support for API v2 and v3
- **Jira Server**: Support for API v2 (legacy, no longer sold)
- **Jira Data Center**: Support for API v2 and v3

### JQL Resources

- [Jira Query Language (JQL) Documentation](https://support.atlassian.com/jira-service-desk-cloud/articles/reference-the-jira-query-language-jql/)
- [JQL Field Names and Values](https://support.atlassian.com/jira-cloud-platform/articles/advanced-searching-using-jql/)
- [JQL Functions](https://support.atlassian.com/jira-cloud-platform/articles/use-advanced-search-with-jql/)

### Jira REST API

- [Jira API v3 Documentation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Jira API v2 Documentation](https://docs.atlassian.com/software/jira/docs/api/REST/2.0/)
- [Atlassian Document Format (ADF)](https://developer.atlassian.com/cloud/jira/platform/apis/document/adf/)
