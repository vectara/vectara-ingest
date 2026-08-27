# Google Drive Crawler

The Google Drive crawler indexes files from Google Drive, including support for Google Docs, Slides, and traditional file formats. It offers two authentication modes: service account with domain-wide delegation for multi-user crawling or OAuth for single-user scenarios.

## Overview

- **Crawler Type**: `gdrive`
- **Authentication**: Service account (domain-wide delegation) or OAuth 2.0
- **Features**: Multi-user support, permission filtering, date filtering, Google Docs/Slides export, parallel processing
- **Supported Files**: .doc, .docx, .ppt, .pptx, .pdf, .odt, .txt, .html, .md, .rtf, .epub, .lxml
- **Shared Drives**: Full support for Google Workspace shared drives
- **Parallel Processing**: Ray-based parallel crawling for large deployments

## Use Cases

- Knowledge base from company Google Drive
- Documentation and procedure manuals
- Project files and deliverables
- Shared team resources and training materials
- Multi-user document repositories
- Compliance and audit trail documentation

## Authentication Methods

The Google Drive crawler supports two authentication methods:

### 1. Service Account (Recommended for Production)

Uses a service account with domain-wide delegation to access files across multiple users in your Google Workspace domain. This method allows crawling files from multiple users without individual OAuth consent.

**Best for:**
- Multi-user environments
- Automated, unattended crawling
- Google Workspace organizations

### 2. OAuth 2.0 (Simpler Setup)

Uses personal Google account credentials. Requires per-user authentication but simpler to set up for testing or single-user scenarios.

**Best for:**
- Single-user crawling
- Personal Google Drive
- Quick testing and evaluation
- Non-Workspace accounts

---

## Getting Started: Service Account Authentication

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Log in with your Google Workspace admin account
3. Click the project selector dropdown at the top
4. Click **NEW PROJECT**
5. Enter project name: `Vectara Google Drive Crawler` (or your preferred name)
6. Click **CREATE**

### Step 2: Enable the Google Drive API

1. In the Google Cloud Console, navigate to **APIs & Services** > **Library**
2. Search for `Google Drive API`
3. Click on the result
4. Click **ENABLE**

Wait a few moments for the API to be enabled.

### Step 3: Create a Service Account

1. In the Google Cloud Console, navigate to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** at the top
3. Select **Service Account**
4. Fill in the service account details:
   - **Service account name**: `vectara-gdrive-crawler`
   - **Service account ID**: (auto-populated)
   - **Description**: `Service account for Vectara Google Drive crawler`
5. Click **CREATE AND CONTINUE**

### Step 4: Grant Permissions to Service Account

1. On the "Grant this service account access to project" step:
   - Under "Select a role", search for and select **Editor** (or create a custom role with Drive API access)
   - Click **CONTINUE**
2. Click **DONE**

### Step 5: Create and Download the Private Key

1. In the Google Cloud Console, navigate to **APIs & Services** > **Credentials**
2. Under "Service Accounts", click on the service account you just created
3. Click on the **KEYS** tab
4. Click **ADD KEY** > **Create new key**
5. Select **JSON** as the key type
6. Click **CREATE**
7. A JSON file downloads automatically - save it as `credentials.json`
8. Move the file to your vectara-ingest directory: `cp credentials.json /path/to/vectara-ingest/`

The JSON file contains your private key and should look like:
```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "vectara-gdrive-crawler@your-project-id.iam.gserviceaccount.com",
  "client_id": "1234567890",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

### Step 6: Enable Domain-Wide Delegation

1. In the Google Cloud Console, navigate to **APIs & Services** > **Credentials**
2. Under "Service Accounts", click on your service account
3. Click on the **DETAILS** tab
4. Under "Domain-wide delegation", click **ENABLE DOMAIN-WIDE DELEGATION**
5. A dialog will appear:
   - **User consent screen**: Click **CONFIGURE CONSENT SCREEN**
   - Set the application name and contact information
   - Under "Scopes", click **ADD OR REMOVE SCOPES**
   - In the search box, enter `Google Drive API`
   - Select `https://www.googleapis.com/auth/drive.readonly`
   - Click **UPDATE**
6. Back on the service account page, confirm domain-wide delegation is enabled

### Step 7: Grant Domain-Wide Delegation Scopes

1. Go to your Google Workspace Admin Console (admin.google.com)
2. Navigate to **Security** > **API Controls** > **Domain-wide delegation**
3. Click **Add new**
4. Enter:
   - **Client ID**: Copy from your service account (APIs & Services > Credentials > Service Account > Client ID)
   - **OAuth Scopes**: `https://www.googleapis.com/auth/drive.readonly`
5. Click **AUTHORIZE**

This grants the service account access to read all Google Drive files in your domain.

### Step 8: Identify Delegated Users

List the email addresses of users whose Google Drive files you want to crawl:

```yaml
gdrive_crawler:
  delegated_users:
    - alice@company.com
    - bob@company.com
    - charlie@company.com
```

---

## Getting Started: OAuth Authentication

For a simpler setup without domain-wide delegation, use OAuth. See [Google Drive OAuth Setup Guide](../advanced/gdrive-oauth-setup.md) for complete instructions.

### Quick OAuth Setup

1. **Create OAuth credentials in Google Cloud Console**:
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - APIs & Services > Credentials > + CREATE CREDENTIALS > OAuth client ID
   - Choose "Desktop app"
   - Download the JSON file

2. **Generate OAuth token**:
   ```bash
   python scripts/gdrive/generate_oauth_token.py
   ```
   This will open a browser for you to authorize the application and create `credentials.json`

3. **Configure with OAuth token**:
   ```yaml
   gdrive_crawler:
     auth_type: oauth
     credentials_file: credentials.json
   ```

---

## Configuration

### Service Account Configuration (Multi-User)

Create a configuration file (e.g., `gdrive-config.yaml`):

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: gdrive
  reindex: false
  verbose: false

crawling:
  crawler_type: gdrive

gdrive_crawler:
  # Authentication method
  auth_type: service_account

  # Path to service account credentials JSON
  credentials_file: credentials.json

  # Users whose Google Drive to crawl
  # Service account must have delegated access to these users
  delegated_users:
    - alice@company.com
    - bob@company.com
    - charlie@company.com

  # Files modified in the last N days
  # Default: 7 days if not specified
  days_back: 7

  # Permission filtering: only index files shared with these entities
  # 'Vectara' = shared with Vectara group
  # 'all' = publicly accessible / shared with everyone
  # Or specify individual email addresses
  permissions:
    - Vectara
    - all

  # Optional: parallel processing with Ray
  # 0 = no parallelization (default)
  # N = use N worker processes
  ray_workers: 0
```

### OAuth Configuration (Single User)

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: gdrive
  reindex: false
  verbose: false

crawling:
  crawler_type: gdrive

gdrive_crawler:
  # Use OAuth authentication (single user only)
  auth_type: oauth

  # Path to OAuth credentials JSON
  # Generate with: python scripts/gdrive/generate_oauth_token.py
  credentials_file: credentials.json

  # Files modified in the last N days
  days_back: 7

  # Permission filtering (same as service account mode)
  permissions:
    - Vectara
    - all

  # Optional: parallel processing with Ray
  ray_workers: 0
```

### Configuration Parameters Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `auth_type` | string | `service_account` | Authentication method: `service_account` or `oauth` |
| `credentials_file` | string | Required | Path to credentials JSON file |
| `delegated_users` | list | Required (service_account) | Email addresses to crawl (service account only) |
| `days_back` | integer | 7 | Only crawl files modified in last N days |
| `permissions` | list | `['Vectara', 'all']` | Permission display names to filter on |
| `ray_workers` | integer | 0 | Number of parallel Ray workers (0 = no parallelization) |

---

## Permission Filtering

The crawler can filter files based on their sharing permissions. This is useful to crawl only specific groups or public files.

### Understanding Permissions

In Google Drive, each file has a list of people and groups it's shared with. Each has a "display name" which the crawler uses to filter.

### Permission Filter Options

#### Default Configuration
```yaml
permissions:
  - Vectara
  - all
```
This indexes only files shared with the "Vectara" group or shared publicly ("all").

#### Public Files Only
```yaml
permissions:
  - all
```
Index only publicly accessible files.

#### Specific Group or User
```yaml
permissions:
  - Engineering
  - john@company.com
```
Index files shared with the "Engineering" group or john@company.com.

#### All Files (No Permission Filter)
```yaml
permissions:
  - Vectara
  - all
  - Engineering
  - sales@company.com
  # Add all groups/users whose files should be indexed
```

### How to Find Permission Display Names

To see which groups and users files are shared with:

1. Open a file in Google Drive
2. Click **Share** or the share icon
3. Look at the list of people/groups and their display names
4. Use those exact names in the `permissions` configuration

---

## Google Docs and Slides Support

The crawler automatically exports Google Workspace documents to standard formats for indexing:

- **Google Docs** → Exported as `.docx` (Microsoft Word format)
- **Google Slides** → Exported as `.pptx` (Microsoft PowerPoint format)
- **Google Sheets** → Not supported (spreadsheets are excluded)

### Export Behavior

When the crawler encounters a Google Workspace document:

1. It calls the Google Drive API with an export MIME type
2. Google generates the file in the requested format
3. The crawler downloads and indexes the generated file
4. The file is automatically removed after indexing

### Large Document Handling

For very large Google Docs/Slides (>100MB), Google may return an error. The crawler will:

1. Attempt to export via the standard API
2. If that fails, attempt to download via the exportLinks endpoint
3. Fall back to PDF format if available
4. Log a warning and skip the file if all export attempts fail

---

## Supported File Types

The crawler indexes the following file types:

| Category | Formats |
|----------|---------|
| Documents | `.doc`, `.docx`, `.pdf`, `.odt`, `.txt`, `.rtf` |
| Presentations | `.ppt`, `.pptx` |
| Web Content | `.html`, `.md` |
| E-books | `.epub` |
| Markup | `.lxml` |

### Excluded File Types

The crawler automatically excludes:

- **Media**: Images (`.png`, `.jpg`, `.gif`, etc.), audio, video
- **Archives**: `.zip`, `.rar`, `.7z`
- **Code**: `.py`, `.js`, `.java`, `.cpp` and code-related files
- **Folders**: Google Drive folders
- **Executables**: `.exe`, `.bin`
- **Design**: Adobe InDesign files (`.indd`)
- **Web**:  CSS, JavaScript, PHP, SQL files

To index documents with images or perform OCR, configure the document processing settings:

```yaml
doc_processing:
  do_ocr: true           # Extract text from images
  parse_tables: true     # Extract structured tables
  summarize_images: true # Generate descriptions for images
```

---

## Shared Drives Support

The crawler supports Google Workspace Shared Drives. Files in shared drives are crawled automatically using:

```yaml
gdrive_crawler:
  delegated_users:
    - shared-drive-service-account@domain.com
```

### Crawling Shared Drives

To crawl files from a shared drive:

1. Share the drive with your service account
2. Grant the service account at least Viewer access
3. Add the shared drive service account email to `delegated_users`

The crawler uses the `corpora: 'allDrives'` and `includeItemsFromAllDrives: True` parameters to include shared drive files in the results.

---

## Date Filtering

The `days_back` parameter limits crawling to recently modified files, useful for incremental updates:

```yaml
gdrive_crawler:
  # Only crawl files modified in the last 14 days
  days_back: 14
```

### Behavior

- Files modified more recently than `now() - days_back` are included
- Files not modified in the specified period are excluded
- Useful for incremental crawls: run with `days_back: 1` for daily updates

### Examples

```yaml
# Crawl only today's changes
days_back: 1

# Crawl last week's changes
days_back: 7

# Crawl last month (30 days)
days_back: 30

# Crawl all files (no time limit)
days_back: 9999
```

---

## Parallel Processing with Ray

For large Google Drive installations, use Ray to parallelize crawling across multiple workers:

```yaml
gdrive_crawler:
  # Enable 4 parallel workers
  ray_workers: 4

  # For delegated users, each worker processes different users
  delegated_users:
    - alice@company.com
    - bob@company.com
    - charlie@company.com
    - diana@company.com
```

### Configuration Guidelines

| ray_workers | Use Case |
|-------------|----------|
| 0 | Single-threaded (default), testing, or small drives |
| 1-2 | Light parallelization on laptops or small servers |
| 4-8 | Standard multi-core systems (2-4 cores per worker) |
| 16+ | High-performance servers with many cores |

### Ray Worker Distribution

- When `ray_workers` > 0, the crawler initializes Ray with that many worker processes
- Each worker processes delegated users independently
- A shared cache prevents duplicate indexing across workers
- Workers are pooled and reused for efficiency

### Performance Considerations

**Memory**: Each Ray worker maintains its own copy of the indexer and crawler objects. Ensure sufficient memory:

```
Total Memory Needed ≈ Base Memory + (ray_workers × Per-Worker Overhead)
Rough Estimate: 4GB base + (4GB × number of workers)
```

**I/O**: The crawler respects Google Drive API rate limits. With Ray:
- Multiple workers may hit rate limits faster
- Consider adding delays between requests if rate limited
- Distribute workers across time windows if necessary

**Shared Cache**: Workers use a shared Ray-based cache to avoid processing the same file twice, even with parallel crawling.

### Example: Large Deployment

For a company with 100+ users, use Ray to parallelize:

```yaml
gdrive_crawler:
  auth_type: service_account
  credentials_file: credentials.json

  # Process 10 users in parallel
  ray_workers: 10

  delegated_users:
    - user1@company.com
    - user2@company.com
    # ... up to 100 users
    - user100@company.com

  days_back: 1  # Daily incremental crawl
```

Run time will be approximately `total_users / ray_workers × time_per_user`.

---

## Running the Crawler

### Command Line

```bash
# Basic crawl
python main.py --config gdrive-config.yaml

# Verbose output for debugging
python main.py --config gdrive-config.yaml --verbose

# Reindex all documents (ignores cache)
python main.py --config gdrive-config.yaml --reindex
```

### Docker

```bash
# Build the Docker image
docker build -t vectara-ingest .

# Run with service account
docker run -v /path/to/credentials.json:/home/vectara/env/credentials.json \
  vectara-ingest --config gdrive-config.yaml

# Run with OAuth
docker run -v /path/to/credentials.json:/home/vectara/credentials.json \
  vectara-ingest --config gdrive-config.yaml
```

### Environment Variables

Set Vectara API credentials:

```bash
export VECTARA_API_KEY="your-api-key"
export VECTARA_CUSTOMER_ID="your-customer-id"
export VECTARA_CORPUS_KEY="gdrive"
```

Or use `secrets.toml`:

```toml
[default]
api_key = "your-api-key"
customer_id = "your-customer-id"
```

---

## Metadata Extraction

The crawler extracts the following metadata for each file:

- **id**: Google Drive file ID
- **name**: File name
- **title**: Same as file name
- **created_at**: File creation timestamp
- **last_updated**: Last modification timestamp
- **owners**: Comma-separated list of file owners
- **size**: File size in bytes
- **url**: Link to file in Google Drive
- **source**: Always "gdrive"

This metadata is attached to all chunks from the file and can be used for filtering and display in search results.

---

## Performance Optimization

### Incremental Updates

Use `days_back` for efficient incremental crawls:

```yaml
# Schedule this to run daily
gdrive_crawler:
  days_back: 1
```

This crawls only files modified in the last day, much faster than full re-indexing.

### Cache Management

The crawler maintains an in-memory cache of processed file IDs to avoid re-indexing. The cache is:
- **Per-run**: Cleared when the crawler starts
- **Shared across workers**: Ray workers share a distributed cache
- **File-based**: Can be extended to persist across runs (requires custom implementation)

### Chunking Strategy

For better performance with large documents, configure appropriate chunking:

```yaml
vectara:
  chunking_strategy: sentence  # Recommended
  chunk_size: 512              # Tokens
```

---

## Troubleshooting

### Authentication Issues

**Service Account: "Permission denied" or "Insufficient permissions"**

1. Verify service account email is added as Viewer to shared drives
2. Check domain-wide delegation is enabled:
   - Google Cloud Console > Service Account > DETAILS > Domain-wide delegation
3. Confirm scopes are authorized:
   - Google Workspace Admin Console > Security > API Controls > Domain-wide delegation
4. Verify `delegated_users` emails are valid and exist in your domain

**OAuth: "Token expired" or "Invalid credentials"**

1. Regenerate the OAuth token:
   ```bash
   python scripts/gdrive/generate_oauth_token.py
   ```
2. Ensure the token file is readable and not corrupted
3. Check that the Google account has active access to Google Drive

### File Not Found

**"FileNotFoundError: credentials.json"**

1. Verify the path to `credentials_file` in your config is correct
2. Ensure the file exists and is readable:
   ```bash
   ls -la /path/to/credentials.json
   ```
3. Use absolute paths in configuration:
   ```yaml
   credentials_file: /absolute/path/to/credentials.json
   ```

### No Files Indexed

**Crawler runs but indexes no documents**

1. Check permission filtering:
   ```yaml
   # Try permissive settings for testing
   permissions:
     - Vectara
     - all
     - everyone  # Add common group names
   ```

2. Verify `delegated_users` have files in their Google Drive
3. Check `days_back` is not too restrictive:
   ```yaml
   days_back: 9999  # Crawl all files
   ```

4. Enable verbose logging:
   ```bash
   python main.py --config gdrive-config.yaml --verbose
   ```

5. Check the logs for filtered file types:
   ```bash
   grep "mimeType" vectara_ingest_output/vectara_ingest.log
   ```

### Rate Limiting

**"quotaExceeded" errors in logs**

1. Reduce `ray_workers` to lower concurrent API requests
2. Add delays between requests (crawler will retry automatically)
3. Schedule crawls during off-peak hours
4. Contact Google Cloud support to request quota increase

### Memory Issues

**"Out of memory" with Ray workers**

1. Reduce the number of `ray_workers`:
   ```yaml
   ray_workers: 2  # From 8
   ```

2. Monitor memory usage during crawling:
   ```bash
   # macOS
   top -l 1 -n 5 | grep vectara

   # Linux
   ps aux | grep vectara
   ```

3. Increase system memory or run on a larger instance

### Large File Export Failures

**"exportSizeLimitExceeded" for Google Docs/Slides**

1. This is a Google Drive API limitation for documents over ~100MB
2. The crawler will attempt alternative export methods
3. If all methods fail, the file is skipped
4. These files are logged in the output

---

## Advanced Configuration

### Custom Document Processing

```yaml
vectara:
  # Document processing pipeline
  remove_code: true
  remove_boilerplate: false
  mask_pii: false

doc_processing:
  # Parser: unstructured, llamaparse, google_vertex, etc.
  doc_parser: unstructured

  # OCR for scanned documents
  do_ocr: false

  # Extract structured tables
  parse_tables: true

  # Generate descriptions for images
  summarize_images: false
```

### Metadata Extraction

```yaml
vectara:
  # Extract metadata from documents
  extract_metadata: true

  # Preserve document structure
  preserve_structure: true
```

### Rate Limiting

```bash
# Set custom timeouts in crawler
export VECTARA_TIMEOUT=120  # seconds
```

---

## Security Considerations

### Service Account Credentials

- The service account private key grants access to all Drive files it's authorized for
- Treat `credentials.json` as a secret - do not commit to version control
- Use environment variables or secret management systems (AWS Secrets Manager, HashiCorp Vault, etc.)
- Rotate credentials periodically
- Restrict service account permissions to read-only

### OAuth Tokens

- Tokens are stored in plain JSON - protect with file permissions
- Refresh tokens allow continued access after initial authorization
- Revoke access at https://myaccount.google.com/permissions if needed
- Single-user only - cannot be shared across machines

### Domain-Wide Delegation

- Carefully review which scopes are delegated
- Use read-only scopes only (`https://www.googleapis.com/auth/drive.readonly`)
- Monitor service account usage in Google Cloud Audit Logs
- Revoke delegation if credentials are compromised

### Running in Production

```bash
# Secure file permissions
chmod 600 credentials.json

# Use environment variables instead of storing in config
export GDRIVE_CREDENTIALS=/secure/path/credentials.json

# Run with least-privilege user account
docker run --user vectara vectara-ingest ...
```

---

## Common Use Cases

### Daily Knowledge Base Updates

```yaml
gdrive_crawler:
  auth_type: service_account
  credentials_file: /etc/vectara/credentials.json
  delegated_users:
    - kb-owner@company.com
  days_back: 1
  ray_workers: 2
```

Schedule with cron:
```bash
0 2 * * * cd /opt/vectara && python main.py --config gdrive-daily.yaml >> /var/log/vectara-gdrive.log 2>&1
```

### Multi-Team Parallel Crawl

```yaml
gdrive_crawler:
  auth_type: service_account
  credentials_file: credentials.json
  delegated_users:
    - engineering@company.com
    - sales@company.com
    - marketing@company.com
    - finance@company.com
  ray_workers: 8
  days_back: 7
```

### Departmental Documentation

```yaml
gdrive_crawler:
  auth_type: service_account
  credentials_file: credentials.json
  delegated_users:
    - dept-admin@company.com
  permissions:
    - Engineering  # Only files shared with Engineering group
  days_back: 30
```

### Public Knowledge Base (OAuth)

```yaml
gdrive_crawler:
  auth_type: oauth
  credentials_file: credentials.json
  permissions:
    - all  # Only public files
```

---

## FAQ

**Q: Can I crawl files from multiple Google accounts with OAuth?**

A: No, OAuth supports single-user only. For multiple users, use service account authentication.

**Q: How often should I run the crawler?**

A: Use `days_back: 1` for daily crawls or `days_back: 7` for weekly crawls. Adjust based on your document update frequency.

**Q: Do I need to share individual files with the service account?**

A: For domain-wide delegation with service account, files don't need to be explicitly shared. The service account impersonates delegated users via OAuth scopes.

**Q: What happens if a user is deleted from Google Workspace?**

A: Files owned by deleted users may become inaccessible. The crawler will log warnings for files it can't access.

**Q: Can I crawl Google Sheets?**

A: Google Sheets are excluded by default (MIME type: `application/vnd.google-apps.spreadsheet`). They're complex structured data not suitable for typical document indexing. Consider CSV export or custom processing instead.

**Q: How are file conflicts handled?**

A: Files are identified by unique Google Drive ID. Re-crawling the same file updates it in the corpus (if `reindex: true`).

**Q: Can I filter by file name or folder?**

A: The permission filter is based on sharing permissions. To filter by folder or name, consider exporting files first or using a custom crawler.

---

## Related Documentation

- [Google Drive OAuth Setup](../advanced/gdrive-oauth-setup.md) - Detailed OAuth configuration
- [Configuration Reference](../configuration.md) - All Vectara configuration options
- [Document Processing](../features/document-processing.md) - Configure parsing and OCR
- [Crawlers Overview](index.md) - Other available crawlers
- [Getting Started](../getting-started.md) - Quick start guide

---

## Support

For issues or questions:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review [Google Drive API documentation](https://developers.google.com/drive/api/guides/about-sdk)
3. Ask in our [Discord community](https://discord.com/invite/GFb8gMz6UH)
4. Open an [issue on GitHub](https://github.com/vectara/vectara-ingest/issues)
