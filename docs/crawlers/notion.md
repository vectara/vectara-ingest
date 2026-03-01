# Notion Crawler

The Notion crawler indexes content from your Notion workspace, automatically discovering and extracting text from all accessible pages and their nested content blocks.

## Overview

- **Crawler Type**: `notion`
- **Authentication**: Notion API key (via integration)
- **Content Extraction**: Paragraphs, headings, lists, code blocks, and nested content
- **Page Discovery**: Automatic workspace-wide page discovery
- **Deduplication**: Built-in URL-based deduplication
- **Reporting**: Optional crawl reports with indexed and removed pages

## Use Cases

- Index company knowledge bases and internal documentation
- Archive Notion workspaces for search and retrieval
- Create searchable databases of project notes and meeting notes
- Build team wikis and knowledge management systems
- Backup and archive important Notion content
- Generate embeddings for AI-powered search across Notion pages

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: notion-knowledge-base

crawling:
  crawler_type: notion

notion_crawler:
  # Notion integration API key (set via NOTION_API_KEY environment variable)
  notion_api_key: ${NOTION_API_KEY}

  # Optional: Enable crawl report
  crawl_report: false

  # Optional: Remove pages not in current crawl
  remove_old_content: false
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: notion-docs
  reindex: false
  verbose: true

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: false

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}

  # Generate detailed report of all indexed pages
  crawl_report: true

  # Output directory for reports
  output_dir: vectara_ingest_output

  # Automatically remove pages that were previously indexed
  # but are not in the current crawl (useful for keeping corpus in sync)
  remove_old_content: true

metadata:
  source: internal-notion
  content_type: documentation
  workspace: engineering-team
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `notion_api_key` | string | Yes | - | Notion integration API key (recommend setting via `NOTION_API_KEY` environment variable) |
| `crawl_report` | boolean | No | `false` | Generate a report listing all indexed pages |
| `output_dir` | string | No | `vectara_ingest_output` | Directory where crawl reports are saved |
| `remove_old_content` | boolean | No | `false` | Automatically remove pages from corpus that are no longer in Notion |

## How It Works

1. **Authentication**: Connects to Notion using the provided API key
2. **Page Discovery**: Uses Notion Search API to discover all accessible pages in the workspace
3. **Content Extraction**: For each page:
   - Retrieves all child blocks (paragraphs, headings, lists, code blocks, etc.)
   - Recursively extracts text from nested blocks
   - Skips child pages (these are discovered separately)
4. **Title Extraction**: Intelligently extracts page title from:
   - Standard `title` property
   - `Name` property (common in databases)
   - First title-type property found
5. **Indexing**: Sends each page as a document to Vectara with extracted content
6. **Cleanup** (optional): If `remove_old_content` is enabled, removes any previously indexed pages that no longer exist in Notion
7. **Reporting** (optional): Generates reports listing indexed and removed pages

## Metadata Captured

The crawler automatically extracts and indexes:

- **ID**: Notion page ID (unique identifier)
- **Title**: Page title from Notion properties
- **URL**: Notion page URL (shareable link)
- **Source**: `notion` (or configured source in metadata)
- **Content**: All text from paragraphs, headings, lists, code blocks, and nested content
- **Custom Metadata**: Any additional metadata fields configured in the YAML

## Supported Content Types

The Notion crawler extracts text from:

- **Paragraphs**: Regular text content
- **Headings**: Heading 1, 2, and 3 levels
- **Lists**: Bulleted and numbered lists with nesting
- **Code Blocks**: Code with language specification
- **Quotes**: Blockquote content
- **Callouts**: Callout blocks (preserved as text)
- **Dividers**: Noted in content separation
- **Nested Blocks**: Recursively extracts content from block children
- **Databases**: Entries in database pages (via discovery)

The crawler skips:
- Child pages (discovered separately via Search API)
- Embedded content that requires API limitations
- Media blocks (images, videos - metadata only)

## Examples

### Simple Knowledge Base

```yaml
vectara:
  corpus_key: company-wiki
  reindex: false

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}

metadata:
  source: company-knowledge-base
  content_type: documentation
```

### Team Documentation with Reports

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: engineering-docs
  reindex: false
  verbose: true

doc_processing:
  model: openai
  model_name: gpt-4o

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}
  crawl_report: true
  output_dir: reports
  remove_old_content: false

metadata:
  team: engineering
  category: documentation
  language: en
```

### Production Setup with Content Cleanup

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: prod-knowledge-base
  reindex: false
  verbose: false

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}
  crawl_report: true
  output_dir: /var/log/vectara
  remove_old_content: true

metadata:
  source: notion-prod
  environment: production
  indexed_date: "2024-01-01"
```

### Multi-Team Setup with Separate Corpora

```yaml
# config/notion-engineering.yaml
vectara:
  corpus_key: notion-engineering-team

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}

metadata:
  team: engineering
  department: technical
```

```yaml
# config/notion-marketing.yaml
vectara:
  corpus_key: notion-marketing-team

crawling:
  crawler_type: notion

notion_crawler:
  notion_api_key: ${NOTION_API_KEY}

metadata:
  team: marketing
  department: business
```

## Authentication Setup

### Step 1: Create a Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click "Create new integration"
3. Give it a name (e.g., "Vectara Crawler")
4. Select the workspace where your pages are located
5. Click "Submit"
6. On the integration page, copy the **Internal Integration Token** (this is your API key)

### Step 2: Set the Environment Variable

Add your API key to your environment:

```bash
export NOTION_API_KEY="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Or add to `.env` file:

```
NOTION_API_KEY=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Or set in `secrets.toml`:

```toml
[default]
NOTION_API_KEY = "secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### Step 3: Share Pages with the Integration

For the crawler to access pages, you must share them with your integration:

**For individual pages:**
1. Open the Notion page
2. Click "Share" button (top right)
3. Search for your integration name
4. Click to add it
5. Copy the link (optional, not needed for crawler)

**For workspaces (recommended):**
1. Go to Workspace Settings
2. Click "Integrations" or "Members & Guests"
3. Add your integration
4. Grant appropriate permissions

**Important**: The integration can only access pages that have been explicitly shared with it. Pages not shared will be skipped.

### Permissions Needed

The Notion integration requires:
- `read` access to pages
- `read` access to page content and blocks
- `read` access to databases (if using database pages)

The integration does NOT need write permissions for read-only access.

## Content Extraction Details

### Block Text Extraction

The crawler uses the `get_block_text()` function to recursively extract text:

```
For each block:
1. Check if block has rich_text content
2. Extract plain_text from all rich_text items
3. If block has children, recursively process children
4. Combine all text with spaces
```

This ensures nested lists, quoted text, and complex formatting are preserved as plain text.

### Title Extraction Strategy

The crawler tries multiple strategies to find the page title:

```
1. Check for 'title' property of type 'title'
2. Check for 'Name' property (common in database entries)
3. Scan all properties for first title-type property
4. Default to empty string if no title found
```

This handles variations in how Notion pages store titles.

### URL Deduplication

Each page is identified by its Notion page ID. If the same page is crawled multiple times:
- First crawl: Page is indexed
- Subsequent crawls: Page is updated (using URL-based deduplication)
- Duplicate detection prevents redundant indexing

## Crawl Reports

When `crawl_report: true`, two files are generated:

### pages_indexed.txt

Lists all pages that were successfully indexed:

```
page-id-1: https://www.notion.so/page-title-xxxxx
page-id-2: https://www.notion.so/another-page-xxxxx
page-id-3: https://www.notion.so/third-page-xxxxx
```

Uses this for:
- Auditing indexed content
- Tracking crawl progress
- Verifying expected pages were found

### pages_removed.txt

Lists pages that were removed from the corpus (only when `remove_old_content: true`):

```
Page with ID page-id-1: https://www.notion.so/deleted-page-xxxxx
Page with ID page-id-2: https://www.notion.so/archived-page-xxxxx
```

Uses this for:
- Understanding what was removed
- Auditing corpus changes
- Reconciliation

## Troubleshooting

### API Key Issues

**Problem**: `Invalid API key` or `Unauthorized`

**Solutions**:
1. Verify you copied the full token from Notion Integrations page
2. Check token hasn't expired (regenerate if needed)
3. Ensure `NOTION_API_KEY` environment variable is set correctly:
   ```bash
   echo $NOTION_API_KEY  # Should print your token
   ```
4. Try regenerating the token in Notion Integrations

### No Pages Found

**Problem**: Crawler runs but finds 0 pages

**Solutions**:
1. Verify the integration has been shared with pages:
   - Open a page you want indexed
   - Click "Share"
   - Look for your integration in the list
   - If not there, add it
2. Check integration has read permissions:
   - Go to Integrations page
   - Click your integration
   - Verify it has read access
3. Ensure pages are in the workspace where integration was created
4. Try making a test page in the workspace and sharing it

### Permission Denied

**Problem**: `Page not found` or `Permission denied` errors in logs

**Solutions**:
1. Share the page with your integration:
   ```
   Page -> Share -> Search for integration name -> Add
   ```
2. For database pages, ensure the database itself is shared
3. For child pages, make sure parent pages are also shared
4. Check that integration wasn't removed from page:
   - Click Share
   - Look for integration name in list

### Empty Pages

**Problem**: Page is indexed but has no content

**Solutions**:
1. Verify page actually has content in Notion
2. Check for permission issues on nested blocks
3. Ensure blocks aren't using unsupported types (media-only pages will appear empty)
4. Check logs for warnings about skipped blocks

### Slow Crawling

**Problem**: Crawler is running very slowly

**Solutions**:
1. Reduce number of pages (temporarily)
2. Check network connectivity
3. Verify Notion API isn't being rate-limited:
   - Wait a few minutes and retry
   - Notion allows 3 requests/second average
4. Check system resources (CPU, memory)
5. Consider breaking into smaller crawls with separate integrations

### Integration Token Errors

**Problem**: `Invalid integration token` or token rejected

**Solutions**:
1. Don't include `Bearer` prefix - just the token itself
2. Check for spaces or extra characters
3. Regenerate token:
   - Go to Notion Integrations
   - Click your integration
   - Click "Regenerate secret"
   - Copy new token
4. Ensure token is for the correct workspace

## Performance Considerations

### Rate Limiting

Notion API enforces:
- **3 requests/second average** (burst up to 10/second)
- Crawler respects these limits automatically

For large workspaces:
- Crawl time scales linearly with number of pages
- Nested content increases extraction time per page
- Network latency affects overall speed

### Memory Usage

Memory depends on:
- Number of pages (metadata in memory)
- Average page size (blocks and children)
- Number of concurrent indexing operations

For very large workspaces (10,000+ pages):
- Consider breaking into multiple crawls
- Monitor system memory during crawl

### Optimization Tips

1. **Filter pages at source**: Create separate workspaces/integrations for different teams
2. **Use metadata efficiently**: Add filtering metadata at crawl time rather than in Notion
3. **Schedule regular crawls**: Use `remove_old_content: true` to keep corpus in sync
4. **Enable verbose logging**: Set `verbose: true` to track progress

## Best Practices

### 1. Organize Your Notion Workspace

Structure pages logically before crawling:

```
Workspace Root
├── Engineering Docs
│   ├── API Documentation
│   ├── Architecture
│   └── Deployment Guides
├── Product Docs
│   ├── Features
│   └── Roadmap
└── Team Info
    ├── Onboarding
    └── Policies
```

This makes management easier and helps with content discovery.

### 2. Use Consistent Naming

Give pages clear, descriptive titles:

```
Good titles:
- "Python Best Practices Guide 2024"
- "Database Schema v2.3"
- "Q4 Planning: Engineering Team"

Avoid:
- "Notes"
- "TODO"
- "Random Stuff"
```

### 3. Share with Integration Before Crawling

```
For each page to index:
1. Open page
2. Click Share
3. Find your integration
4. Add it
```

You can't access pages that aren't shared, so do this first.

### 4. Use Metadata for Organization

Add meaningful metadata in config:

```yaml
metadata:
  team: engineering
  department: platform
  category: documentation
  language: en
  version: "1.0"
```

This helps organize and filter results in Vectara.

### 5. Enable Reports for Auditing

```yaml
notion_crawler:
  crawl_report: true
  output_dir: /var/log/crawls
```

Review reports to verify expected pages were indexed.

### 6. Use remove_old_content Carefully

```yaml
notion_crawler:
  remove_old_content: true  # Dangerous on first run!
```

**First crawl**: Set to `false` to verify pages
**Subsequent crawls**: Set to `true` to keep corpus in sync

### 7. Handle Large Workspaces

For 1000+ pages:

```yaml
notion_crawler:
  # Create separate integration for each team
  notion_api_key: ${NOTION_API_KEY_ENGINEERING}

crawling:
  crawler_type: notion

metadata:
  team: engineering
```

This makes management easier and prevents timeout issues.

### 8. Regular Sync Strategy

```bash
# Daily sync (update existing content)
0 2 * * * bash run.sh config/notion-daily.yaml default

# Weekly full reindex (remove deleted pages)
0 3 * * 0 bash run.sh config/notion-weekly.yaml default
```

With config:
```yaml
notion_crawler:
  remove_old_content: true
  crawl_report: true
```

### 9. Monitor for Errors

Check logs for issues:

```bash
bash run.sh config/notion-docs.yaml default 2>&1 | tee crawl.log
```

Look for:
- Permission errors (fix sharing)
- Missing blocks (check Notion page)
- Slow crawls (check network)

### 10. Document Your Setup

Create a runbook:

```markdown
# Notion Crawler Setup

## Integration
- Name: "Vectara Crawler"
- Created: 2024-01-15
- Workspace: "Company Knowledge Base"

## Pages Included
- Engineering documentation
- Product roadmap
- Team policies

## Shared With
- Engineering team
- Product team
- Management

## Scheduled Runs
- Daily at 2 AM (sync updates)
- Weekly Sunday 3 AM (full reindex)

## Reports
- Stored in: /var/log/crawls/
- Review after each run
```

## Running the Crawler

### Basic Usage

```bash
# Create your config
vim config/notion-docs.yaml

# Run the crawler
bash run.sh config/notion-docs.yaml default

# Monitor progress
docker logs -f vingest
```

### With Environment Variable

```bash
export NOTION_API_KEY="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
bash run.sh config/notion-docs.yaml default
```

### With Docker

```bash
docker run \
  -e NOTION_API_KEY="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -v $(pwd)/config:/home/vectara/config \
  vectara-ingest \
  bash run.sh config/notion-docs.yaml default
```

## Scheduling Regular Crawls

### Using Cron

Add to crontab:

```bash
# Daily sync at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/notion-docs.yaml default

# Weekly full reindex on Sunday at 3 AM
0 3 * * 0 cd /path/to/vectara-ingest && bash run.sh config/notion-full-sync.yaml default
```

### Using GitHub Actions

Create `.github/workflows/notion-crawl.yml`:

```yaml
name: Notion Crawler

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Notion crawler
        env:
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          VECTARA_API_KEY: ${{ secrets.VECTARA_API_KEY }}
        run: |
          bash run.sh config/notion-docs.yaml default
```

### Using Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: notion-crawler
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: crawler
            image: vectara-ingest:latest
            env:
            - name: NOTION_API_KEY
              valueFrom:
                secretKeyRef:
                  name: notion-secrets
                  key: api-key
            - name: VECTARA_API_KEY
              valueFrom:
                secretKeyRef:
                  name: vectara-secrets
                  key: api-key
            command:
            - bash
            - run.sh
            - config/notion-docs.yaml
            - default
          restartPolicy: OnFailure
```

## Limitations

### Current Limitations

- **Media content**: Images and videos are skipped (metadata-only)
- **Embedded content**: External embeds may not be extracted
- **Database filters**: Database pages show all entries (no filtering)
- **Synced blocks**: Content appears in source location only
- **Access control**: Can't crawl pages not explicitly shared
- **Rate limiting**: Notion API limits to 3 requests/second average

### Not Supported

- Crawling private workspaces without integration
- API tokens from user accounts (must use integration tokens)
- Real-time sync (scheduled crawls only)
- Partial page crawling (entire pages are crawled)

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Confluence Crawler](confluence.md) - For Confluence documentation
- [GitHub Crawler](github.md) - For GitHub repositories
- [RSS Crawler](rss.md) - For RSS feeds and content
- [Deployment](../deployment/docker.md) - Production deployment
- [Vectara API Docs](https://docs.vectara.com) - Vectara platform documentation

## Complete Example

Here's a production-ready configuration for a company knowledge base:

```yaml
# Complete Notion crawler configuration
# File: config/notion-knowledge-base.yaml

vectara:
  endpoint: api.vectara.io
  corpus_key: company-knowledge-base
  reindex: false
  verbose: true
  remove_boilerplate: false
  timeout: 120

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: false
  chunk_size: 400

crawling:
  crawler_type: notion

notion_crawler:
  # API key loaded from environment variable
  notion_api_key: ${NOTION_API_KEY}

  # Generate detailed reports
  crawl_report: true

  # Save reports to timestamped directory
  output_dir: /var/log/vectara/crawls

  # Remove pages from corpus that are no longer in Notion
  # (set to false on first run, then true for subsequent runs)
  remove_old_content: false

metadata:
  source: internal-notion
  content_type: documentation
  workspace: company-kb
  environment: production
  language: en
  created_date: "2024-01-01"

# Custom metadata for filtering
custom_metadata:
  - name: team
    value: all-teams
  - name: category
    value: knowledge-base
```

### Running the Complete Example

```bash
# Set your API keys
export NOTION_API_KEY="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export VECTARA_API_KEY="your-vectara-api-key"

# Run the crawler
bash run.sh config/notion-knowledge-base.yaml default

# Monitor output
docker logs -f vingest

# Check reports
ls /var/log/vectara/crawls/
cat /var/log/vectara/crawls/pages_indexed.txt
```

### First Run Checklist

Before running for the first time:

- [ ] Created Notion integration
- [ ] Copied API key
- [ ] Set `NOTION_API_KEY` environment variable
- [ ] Shared pages with integration
- [ ] Created config file
- [ ] Verified Vectara corpus exists
- [ ] Set `remove_old_content: false` (safety check)
- [ ] Tested with small set of pages
- [ ] Reviewed `pages_indexed.txt` report
- [ ] Verified pages appear in Vectara search

### Ongoing Operations

```bash
# Check crawl status
tail -f crawl.log

# Verify pages indexed
wc -l /var/log/vectara/crawls/pages_indexed.txt

# Review any removed pages
cat /var/log/vectara/crawls/pages_removed.txt

# Re-run if needed
bash run.sh config/notion-knowledge-base.yaml default
```

## Support

For issues with:

- **Notion API**: Check [Notion API documentation](https://developers.notion.com)
- **Vectara integration**: See [Vectara documentation](https://docs.vectara.com)
- **Vectara Ingest**: Visit [GitHub repository](https://github.com/vectara/vectara-ingest)

## FAQ

### Q: Can I crawl multiple Notion workspaces?

A: Create separate integrations for each workspace and run multiple crawler instances with different configs and API keys.

### Q: How often should I re-crawl?

A: Depends on content update frequency. Daily for frequently-updated docs, weekly for stable content.

### Q: Does crawling delete pages from Notion?

A: No, crawling only reads content. Nothing in Notion is modified.

### Q: Can I use user API tokens instead of integration tokens?

A: No, only integration tokens are supported for crawler access.

### Q: What happens if a page is deleted in Notion?

A: If `remove_old_content: true`, it's removed from corpus on next crawl. If false, it stays in corpus.

### Q: Can I filter which pages are crawled?

A: Currently, all shared pages are crawled. Create a separate integration/workspace to limit scope.

### Q: Does the crawler preserve page formatting?

A: No, all content is converted to plain text. Formatting (bold, italic, etc.) is lost but content remains.

### Q: Can I crawl pages shared with me in a workspace I don't own?

A: No, the integration must be added to the workspace by someone with admin access.
