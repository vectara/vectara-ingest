# ServiceNow Crawler

The ServiceNow crawler indexes knowledge base articles, incidents, tickets, and other table data from your ServiceNow instance. It supports authentication via basic auth and provides flexible table selection, filtering, and attachment processing.

## Overview

- **Crawler Type**: `servicenow`
- **Authentication**: Basic auth (username/password)
- **Content Source**: Knowledge base articles, incidents, tickets, and custom tables
- **Attachment Support**: PDF, DOCX, XLSX, PPTX, and other document formats
- **Query Support**: Advanced filtering with ServiceNow query syntax
- **Features**: Pagination, custom field extraction, metadata preservation

## Use Cases

- Knowledge base indexing and search
- Incident management documentation
- Ticket history and resolution archives
- Custom table content indexing
- Service catalog integration
- Compliance and audit documentation

## Getting Started: Authentication

### Create ServiceNow Credentials

ServiceNow uses basic authentication with a username and password. You can use:

1. **Your personal ServiceNow username and password** (not recommended for production)
2. **A service account** created specifically for API access (recommended)

#### For Production Use (Service Account)

Contact your ServiceNow administrator to create a service account with the following permissions:

- Read access to the tables you want to index
- Access to the REST API (`api/now/table/` endpoints)
- Permission to read attachments (if `servicenow_process_attachments` is enabled)

### Setting Environment Variables

Store your credentials securely as environment variables:

```bash
export SERVICENOW_USERNAME="vectara_service_account"
export SERVICENOW_PASSWORD="your-servicenow-password"
```

The crawler will automatically read these from your environment.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: servicenow-kb

crawling:
  crawler_type: servicenow

servicenow_crawler:
  # ServiceNow instance URL (without trailing slash)
  servicenow_instance_url: "https://dev189594.service-now.com"

  # Credentials (read from environment: SERVICENOW_USERNAME, SERVICENOW_PASSWORD)
  servicenow_username: "${SERVICENOW_USERNAME}"
  servicenow_password: "${SERVICENOW_PASSWORD}"

  # Process attachments (PDFs, DOCX, etc.)
  servicenow_process_attachments: true

  # Page size for pagination
  servicenow_pagesize: 100
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: servicenow-advanced
  reindex: false
  verbose: true

crawling:
  crawler_type: servicenow

servicenow_crawler:
  # Instance URL
  servicenow_instance_url: "https://your-instance.service-now.com"

  # Credentials
  servicenow_username: "${SERVICENOW_USERNAME}"
  servicenow_password: "${SERVICENOW_PASSWORD}"

  # Advanced query filtering
  servicenow_query: "ORDERBYDESCpublished_on^active=true"

  # Attachment processing
  servicenow_process_attachments: true

  # Pagination settings
  servicenow_pagesize: 100

  # Fields to ignore in metadata (optional)
  servicenow_ignore_fields:
    - text
    - short_description
    - html

doc_processing:
  doc_parser: unstructured
  do_ocr: false
  parse_tables: true
  summarize_images: true
  use_core_indexing: false
  process_locally: true

metadata:
  source: servicenow
  environment: production
  instance: "your-instance.service-now.com"
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `servicenow_instance_url` | string | Yes | - | ServiceNow instance URL (https://your-instance.service-now.com) |
| `servicenow_username` | string | Yes | - | ServiceNow username for basic auth |
| `servicenow_password` | string | Yes | - | ServiceNow password for basic auth |
| `servicenow_query` | string | No | - | Advanced query filter (ServiceNow QL syntax) |
| `servicenow_process_attachments` | bool | No | `false` | Index attachments (PDFs, DOCX, etc.) |
| `servicenow_pagesize` | int | No | `100` | Results per page for pagination |
| `servicenow_ignore_fields` | list | No | `['text', 'short_description']` | Fields to exclude from metadata |

## ServiceNow Instance Setup

### URL Format

Your ServiceNow instance URL should be in the format:

```
https://{instance}.service-now.com
```

Examples:
- `https://dev189594.service-now.com`
- `https://company-prod.service-now.com`
- `https://internal-servicenow.acme.com`

Do NOT include a trailing slash or path.

### Verifying Instance Access

Before using the crawler, verify you can access your instance:

```bash
# Test basic connectivity
curl -u "username:password" \
  "https://your-instance.service-now.com/api/now/table/kb_knowledge?sysparm_limit=1"
```

If successful, you'll receive a JSON response with knowledge base articles.

## How It Works

### Article Processing Workflow

1. **Query Execution**: Retrieves articles from `kb_knowledge` table using ServiceNow API
2. **Pagination**: Automatically pages through results using `sysparm_offset` and `sysparm_limit`
3. **HTML Generation**: Creates temporary HTML files containing article text and title
4. **Indexing**: Sends HTML content to Vectara with metadata
5. **Attachment Processing** (optional):
   - Queries `sys_attachment` table for related attachments
   - Filters for supported file types
   - Downloads and indexes each attachment
   - Cleans up temporary files

### Supported Tables

The crawler primarily indexes the **Knowledge Base (`kb_knowledge`)** table by default. The knowledge base table contains:

- **Article ID** (`number`): Unique article identifier
- **Title** (`short_description`): Article title
- **Content** (`text`): Full article text (HTML format)
- **Author** (`author`): Article creator
- **Created** (`created_on`): Publication date
- **Updated** (`updated_on`): Last modification date
- **Status** (`active`): Whether article is active

### Custom Query Filtering

To filter articles, use ServiceNow's encoded query syntax in the `servicenow_query` parameter:

```yaml
servicenow_crawler:
  # Only index active articles, newest first
  servicenow_query: "ORDERBYDESCpublished_on^active=true"

  # Only articles updated in the last 30 days
  servicenow_query: "updated_on>javascript:gs.dateAddDays(null,-30)^active=true"

  # Only articles by specific author
  servicenow_query: "author=john.doe@example.com^active=true"

  # Only articles in specific categories
  servicenow_query: "category=IT^ORcategory=Security^active=true"
```

### Query Parameter Examples

The crawler uses the following query parameters:

| Parameter | Purpose | Example |
|-----------|---------|---------|
| `sysparm_offset` | Starting position | `sysparm_offset=0` |
| `sysparm_limit` | Results per page | `sysparm_limit=100` |
| `sysparm_query` | Encoded query filter | `sysparm_query=active=true` |

These are automatically handled by the crawler during pagination.

## Attachment Handling

### Enabling Attachment Indexing

```yaml
servicenow_crawler:
  servicenow_process_attachments: true
```

When enabled, the crawler:

1. Fetches attachments for each indexed article from the `sys_attachment` table
2. Filters by supported file types (see below)
3. Downloads each attachment
4. Extracts text and indexes as separate documents
5. Links attachments to parent article via metadata

### Supported File Types

The crawler supports the following attachment formats:

| Category | Extensions |
|----------|-----------|
| Documents | `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf` |
| Presentations | `.ppt`, `.pptx` |
| Spreadsheets | `.xlsx`, `.xls` |
| Text/Web | `.txt`, `.md`, `.html`, `.htm`, `.lxml` |
| eBooks | `.epub` |

**Unsupported Types:** Images (`.jpg`, `.png`, `.gif`), videos, audio, and executables are skipped.

### Attachment Metadata

Each indexed attachment includes:

```yaml
# Parent article information
article_doc_id: "KB0123456"
table_name: "kb_knowledge"

# Attachment details
file_name: "implementation_guide.pdf"
file_size: 2048576
sys_id: "96c27c0a0a0a0a1b001a2b3c"

# Timestamps
created_on: "2024-01-15T10:30:00Z"
updated_on: "2024-01-15T10:30:00Z"

# Additional fields (if not in ignore list)
content_type: "application/pdf"
download_link: "https://instance.service-now.com/api/now/attachment/96c27c0a0a0a0a1b001a2b3c/file"
```

### Disabling Attachments

To skip attachment processing and speed up indexing:

```yaml
servicenow_crawler:
  servicenow_process_attachments: false
```

## Knowledge Base vs Incident Management

### Knowledge Base (`kb_knowledge`)

The default table indexed by the crawler. Best for:

- User-facing documentation
- How-to articles
- Best practices
- FAQ and troubleshooting guides

**Characteristics:**
- Curated and published content
- Author-controlled quality
- Searchable by users
- Typically more structured

```yaml
# Knowledge base configuration
servicenow_query: "active=true^ORDERBYDESCpublished_on"
```

### Incident Management

For incident tickets, you would need to modify the table query. This crawler focuses on knowledge base by default, but ServiceNow contains many tables:

- `incident` - IT Service Management incidents
- `change_request` - Change management tickets
- `problem` - Problem management records
- `cmdb_ci_*` - Configuration items

To extend the crawler to other tables, contact Vectara support or submit a feature request.

## Custom Fields and Metadata

### Excluding Fields from Metadata

By default, the crawler includes all article fields in metadata. To exclude large fields:

```yaml
servicenow_crawler:
  servicenow_ignore_fields:
    - text                    # Exclude article body (already in content)
    - short_description       # Exclude description (already in title)
    - html                    # Exclude HTML content
    - large_text_field        # Exclude custom field
```

The default ignore list is: `['text', 'short_description']`

### Adding Custom Fields

All article fields are automatically indexed. To see available fields:

1. Log into ServiceNow
2. Navigate to Knowledge Base table
3. Right-click column header and select "Columns" to see field names
4. Add to your configuration (unless in `servicenow_ignore_fields`)

### Metadata Preserved

For each article, the crawler indexes:

- **Article Number**: Unique identifier
- **Title**: Short description
- **Author**: Article creator
- **Created Date**: Publication date
- **Updated Date**: Last modification
- **Active Status**: Whether article is active
- **Categories**: Article categorization
- **Workflow State**: Current workflow status
- **URL**: Link to article in ServiceNow UI
- **All Custom Fields**: Any additional fields in your instance

## Performance Considerations

### 1. Optimize Query Filters

Instead of fetching all articles:

```yaml
# Bad: Indexes everything (slow)
servicenow_query: ""

# Good: Only active articles (faster)
servicenow_query: "active=true"

# Better: Only recent active articles (much faster)
servicenow_query: "active=true^updated_on>javascript:gs.dateAddDays(null,-90)"
```

### 2. Tune Page Size

Adjust `servicenow_pagesize` based on average article size:

```yaml
servicenow_crawler:
  # Smaller pages for large attachments
  servicenow_pagesize: 50

  # Larger pages for simple articles
  servicenow_pagesize: 200
```

- **Smaller pages (25-50)**: Better for articles with large attachments
- **Larger pages (100-200)**: Better for simple text-only articles
- **Default (100)**: Good balance for most cases

### 3. Disable Unnecessary Attachments

Skip attachments if you only need article text:

```yaml
servicenow_crawler:
  servicenow_process_attachments: false
```

This significantly speeds up indexing.

### 4. Exclude Large Fields

Don't index fields you don't need:

```yaml
servicenow_crawler:
  servicenow_ignore_fields:
    - text                # Already in document content
    - short_description   # Already in title
    - large_image_field   # If you don't need images
    - raw_html            # Raw HTML you don't search
```

### 5. Incremental Updates

For large instances, use date-based filtering:

```yaml
# First run: Index everything
servicenow_query: "active=true"

# Subsequent runs: Only recent changes
servicenow_query: "active=true^updated_on>javascript:gs.dateAddDays(null,-7)"

# Set reindex to false to preserve old articles
vectara:
  reindex: false
```

### 6. Schedule Off-Peak Runs

Run large crawls during off-hours:

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/servicenow.yaml default
```

### 7. Monitor Resource Usage

For instances with thousands of articles:

```yaml
doc_processing:
  process_locally: true      # Save memory
  chunk_size: 2000           # Reasonable chunk size
```

### 8. Connection Pooling

The crawler uses retry logic and connection pooling:

- Automatic retries on network failures
- HTTP Keep-Alive for connection reuse
- Configurable timeout values

## Authentication Details

### Basic Authentication

The crawler uses HTTP Basic Authentication:

```
Authorization: Basic base64(username:password)
```

Your credentials are:
- **Username**: ServiceNow username
- **Password**: ServiceNow password

### Service Accounts (Recommended)

For production deployments, create a service account:

1. In ServiceNow, navigate to **System Security > Users**
2. Create new user with:
   - User name: `vectara_service_account` (or similar)
   - Account type: Integration user
   - Email: `vectara@your-company.com`
   - Password: Complex, random password

3. Grant permissions:
   - Read access to `kb_knowledge` table
   - Read access to `sys_attachment` table
   - Access to `/api/now/table/` endpoints

4. Store credentials in environment variables:
   ```bash
   export SERVICENOW_USERNAME="vectara_service_account"
   export SERVICENOW_PASSWORD="generated-password"
   ```

### SSL/TLS Verification

By default, SSL certificates are verified. For development or self-signed certificates:

```yaml
servicenow_crawler:
  ssl_verify: false  # Not recommended for production
```

For proper certificate handling:

```yaml
servicenow_crawler:
  ssl_ca_bundle: "/path/to/ca-bundle.crt"
```

## Troubleshooting

### Authentication Failed (401 Unauthorized)

**Error**: `401 Unauthorized`

**Solutions**:
1. Verify username and password are correct
2. Check credentials are set in environment variables:
   ```bash
   echo $SERVICENOW_USERNAME
   echo $SERVICENOW_PASSWORD
   ```
3. Verify user has API access enabled
4. Test credentials manually:
   ```bash
   curl -u "username:password" \
     "https://your-instance.service-now.com/api/now/table/kb_knowledge?sysparm_limit=1"
   ```

### No Content Found

**Error**: Crawler runs but indexes 0 articles

**Solutions**:
1. Verify instance URL is correct
2. Check instance is accessible from your network
3. Verify article count in ServiceNow:
   - Navigate to Knowledge Base
   - Check if articles exist and are active
4. Try simpler query:
   ```yaml
   servicenow_query: "active=true"
   ```
5. Check user permissions on `kb_knowledge` table

### Connection Timeout

**Error**: `Connection timeout` or `Unable to connect`

**Solutions**:
1. Verify instance URL is correct (no trailing slash)
2. Check network connectivity:
   ```bash
   ping your-instance.service-now.com
   ```
3. Verify firewall allows outbound HTTPS
4. Check ServiceNow instance status
5. Increase timeout if network is slow:
   ```bash
   # Adjust in crawler code if needed
   ```

### Attachment Processing Fails

**Error**: `Failed to download attachment` or `Unsupported file type`

**Solutions**:
1. Verify attachment file types are supported
2. Check attachment file size isn't too large
3. Ensure user has permission to read `sys_attachment` table
4. Try disabling attachments to verify article content works:
   ```yaml
   servicenow_process_attachments: false
   ```

### Query Syntax Error

**Error**: `Invalid query` or no results

**Solutions**:
1. Test query in ServiceNow UI:
   - Navigate to Knowledge Base
   - Click "Search" or "Advanced Search"
   - Test your query syntax
2. Verify ServiceNow encoded query syntax
3. Common issues:
   - Missing `^` separators: Use `^` not `&`
   - Spaces in queries: URL encode if needed
   - Wrong field names: Check field names are correct

### SSL Certificate Error

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:
1. For self-signed certificates in dev:
   ```yaml
   servicenow_crawler:
     ssl_verify: false
   ```
2. For proper certificates, update CA bundle
3. Contact IT to verify certificate is valid

### Rate Limiting

**Error**: `429 Too Many Requests`

**Solutions**:
1. ServiceNow has rate limits (varies by instance)
2. Increase page size or batch size
3. Add delay between API calls if doing multiple runs
4. Contact ServiceNow admin for rate limit information

## Best Practices

### 1. Use Service Accounts

Never use personal credentials for automated crawlers:

```yaml
# Good: Service account
servicenow_username: "${SERVICENOW_USERNAME}"

# Bad: Personal email
servicenow_username: "john.doe@company.com"
```

### 2. Start with Targeted Queries

```yaml
# First: Test with small dataset
servicenow_query: "active=true^ORDERBYDESCpublished_on^sysparm_limit=10"

# Then: Expand to production
servicenow_query: "active=true^ORDERBYDESCpublished_on"
```

### 3. Exclude Unnecessary Fields

```yaml
servicenow_crawler:
  servicenow_ignore_fields:
    - text                # Content already in document
    - short_description   # Title already indexed
    - internal_notes      # Internal-only content
    - workflow_state      # Redundant with status
```

### 4. Version Your Configurations

Track configuration changes:

```yaml
metadata:
  version: "1.0"
  created_date: "2024-01-15"
  last_updated: "2024-11-18"
  notes: "Initial ServiceNow KB ingest setup"
```

### 5. Use Incremental Updates

For ongoing maintenance:

```yaml
vectara:
  reindex: false  # Only new/updated articles

servicenow_crawler:
  # Sync only recent changes
  servicenow_query: "active=true^updated_on>javascript:gs.dateAddDays(null,-7)"
```

### 6. Monitor Crawl Progress

Check logs for performance:

```bash
# Monitor crawler in real-time
docker logs -f vingest

# Check for errors
grep "Error" logs/ingest.log
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/servicenow-kb.yaml
```

Enter your configuration (see examples above).

### Set Environment Variables

```bash
export SERVICENOW_USERNAME="vectara_service_account"
export SERVICENOW_PASSWORD="your-password"
```

### Run the Crawler

```bash
# Run the crawler
bash run.sh config/servicenow-kb.yaml default

# Monitor progress
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/servicenow-kb.yaml default

# Twice weekly
0 2 * * 1,4 cd /path/to/vectara-ingest && bash run.sh config/servicenow-kb.yaml default
```

Or use your preferred scheduler (GitHub Actions, Jenkins, etc.).

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Complete Examples

### Example 1: Simple Knowledge Base

```yaml
# Simple config: Index all active KB articles
vectara:
  endpoint: api.vectara.io
  corpus_key: servicenow-kb

crawling:
  crawler_type: servicenow

servicenow_crawler:
  servicenow_instance_url: "https://dev189594.service-now.com"
  servicenow_username: "${SERVICENOW_USERNAME}"
  servicenow_password: "${SERVICENOW_PASSWORD}"
  servicenow_process_attachments: false

metadata:
  source: servicenow
  content_type: knowledge_base
```

Save as `config/servicenow-simple.yaml` and run:

```bash
bash run.sh config/servicenow-simple.yaml default
```

### Example 2: With Attachments

```yaml
# Full-featured config with attachments
vectara:
  endpoint: api.vectara.io
  corpus_key: servicenow-full
  reindex: false
  verbose: true

crawling:
  crawler_type: servicenow

servicenow_crawler:
  servicenow_instance_url: "https://your-instance.service-now.com"
  servicenow_username: "${SERVICENOW_USERNAME}"
  servicenow_password: "${SERVICENOW_PASSWORD}"

  # Index only recent active articles
  servicenow_query: "active=true^updated_on>javascript:gs.dateAddDays(null,-90)"

  # Process attachments
  servicenow_process_attachments: true
  servicenow_pagesize: 100

  # Exclude unnecessary fields
  servicenow_ignore_fields:
    - text
    - short_description
    - html

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

metadata:
  source: servicenow
  environment: production
  sync_frequency: daily
```

Save as `config/servicenow-full.yaml` and run:

```bash
bash run.sh config/servicenow-full.yaml default
```

### Example 3: Incremental Daily Updates

```yaml
# Incremental daily update configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: servicenow-daily
  reindex: false  # Only update new/modified articles

crawling:
  crawler_type: servicenow

servicenow_crawler:
  servicenow_instance_url: "https://your-instance.service-now.com"
  servicenow_username: "${SERVICENOW_USERNAME}"
  servicenow_password: "${SERVICENOW_PASSWORD}"

  # Only fetch articles updated in the last day
  servicenow_query: "active=true^updated_on>javascript:gs.dateAddDays(null,-1)^ORDERBYDESCupdated_on"

  servicenow_process_attachments: true
  servicenow_pagesize: 50

doc_processing:
  process_locally: true

metadata:
  source: servicenow
  environment: production
  sync_frequency: daily
  last_sync: "2024-11-18"
```

Run daily via cron:

```bash
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/servicenow-daily.yaml default
```

## API Reference

### ServiceNow Instance Requirements

- **Minimum Version**: ServiceNow Quebec or later (for REST API v2)
- **Required Modules**: Knowledge Management or Service Portal
- **API Access**: REST API must be enabled
- **Authentication**: Basic auth enabled

### Tables

| Table | Purpose | Use Case |
|-------|---------|----------|
| `kb_knowledge` | Knowledge base articles | Default - user documentation, how-tos |
| `sys_attachment` | File attachments | Supporting documents for articles |

### Query Syntax

ServiceNow uses encoded query syntax with the following operators:

| Operator | Meaning | Example |
|----------|---------|---------|
| `^` | AND | `active=true^category=IT` |
| `^OR` | OR | `active=true^ORcategory=IT` |
| `!=` | Not equals | `status!=draft` |
| `>` | Greater than | `updated_on>2024-01-01` |
| `<` | Less than | `created_on<2024-12-31` |
| `LIKE` | Contains | `title LIKEperformance` |
| `ORDERBY` | Sort ascending | `ORDERBYcreated_on` |
| `ORDERBYDESC` | Sort descending | `ORDERBYDESCupdated_on` |

### REST API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/api/now/table/{table}` | Query records |
| `/api/now/attachment/{sys_id}/file` | Download attachment |
| `/api/now/table/sys_attachment` | Query attachments |

### Resources

- [ServiceNow REST API Documentation](https://docs.servicenow.com/bundle/tokyo-application-development/page/develop/dev_guide/concept/c_TableAPI.html)
- [ServiceNow Query Syntax](https://docs.servicenow.com/bundle/tokyo-platform-administration/page/administer/reference/concept/c_Queries.html)
- [ServiceNow Knowledge Management](https://docs.servicenow.com/bundle/tokyo-it-service-management/page/product_overview/knowledge-management.html)
