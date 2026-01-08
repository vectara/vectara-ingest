# MediaWiki Crawler

The MediaWiki crawler performs breadth-first search (BFS) crawling of MediaWiki-based wikis (Wikipedia, Mediawiki, etc.), discovering and indexing pages while respecting domain boundaries and crawl depth limits.

## Overview

- **Crawler Type**: `mediawiki`
- **Authentication**: Optional Bearer token (for private wikis)
- **API Support**: MediaWiki Action API
- **Content Types**: Wiki pages, internal links, revision history
- **Metadata Capture**: Author, creation/modification dates, URLs, edit history
- **Crawl Strategy**: Breadth-first search with depth limiting

## Use Cases

- Wikipedia knowledge base indexing
- Internal wiki documentation
- Project wikis and knowledge bases
- MediaWiki instances (private or public)
- Intranet knowledge management systems
- Community documentation archives
- Research and reference material

## Getting Started: API Authentication

### Public Wiki Access (No Authentication)

Public wikis like Wikipedia require no authentication. The crawler accesses the public MediaWiki API.

```yaml
mediawiki_crawler:
  source_urls:
    - "https://en.wikipedia.org/wiki/Artificial_intelligence"
    - "https://en.wikipedia.org/wiki/Machine_learning"
```

### Private Wiki Access (Bearer Token)

For private MediaWiki installations, provide a Bearer token:

#### Creating a Bearer Token

1. Log in to your MediaWiki instance
2. Go to **Preferences > Developer settings** or admin panel
3. Generate an OAuth token or API token
4. Copy the token value

#### Token Setup

```bash
export MEDIAWIKI_API_KEY="your_bearer_token_here"
```

**Security Note**: Never commit tokens to version control.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: mediawiki-pages

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  # API URL for the MediaWiki instance
  api_url: "https://en.wikipedia.org/w/api.php"

  # Starting pages (full wiki URLs)
  source_urls:
    - "https://en.wikipedia.org/wiki/Artificial_intelligence"
    - "https://en.wikipedia.org/wiki/Machine_learning"

  # How many links deep to follow
  depth: 2

  # Maximum number of pages to index
  n_pages: 100

mediawiki_api_key: "${MEDIAWIKI_API_KEY}"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: mediawiki-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://en.wikipedia.org/w/api.php"

  source_urls:
    - "https://en.wikipedia.org/wiki/Artificial_intelligence"

  depth: 3
  n_pages: 500

mediawiki_api_key: "${MEDIAWIKI_API_KEY}"

metadata:
  source: mediawiki
  environment: production
  content_types:
    - wiki_articles
    - reference_material
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `api_url` | string | Yes | - | MediaWiki API URL (e.g., `https://en.wikipedia.org/w/api.php`) |
| `source_urls` | list | Yes | - | Starting page URLs (full URLs with wiki domain) |
| `depth` | int | No | `2` | How many link levels deep to follow (0-10 typical) |
| `n_pages` | int | No | `100` | Maximum pages to index (capped at 1000) |
| `mediawiki_api_key` | string | No | - | Bearer token for private wikis (env var recommended) |

## BFS Crawling Strategy

### Overview

The crawler uses breadth-first search to discover and index pages:

1. **Initialize Queue**: Starting pages added to queue with depth 0
2. **Process Pages**: Remove page from queue, fetch content
3. **Check Domain**: Verify page is same domain as source
4. **Extract Links**: Find internal links on page
5. **Enqueue Links**: Add new links to queue with depth+1
6. **Continue**: Repeat until queue empty or page limit reached

### Depth Limiting

```yaml
depth: 0  # Only starting URLs
depth: 1  # Starting pages + direct links
depth: 2  # Two levels of links (default)
depth: 3  # Three levels deep
```

**Examples**:

```
Depth 0: https://example.com/wiki/AI
         (1 page)

Depth 1: https://example.com/wiki/AI
         ├─ https://example.com/wiki/Machine_Learning
         ├─ https://example.com/wiki/Deep_Learning
         └─ https://example.com/wiki/Neural_Networks
         (4 pages)

Depth 2: Previous + all links from level 1 pages
         (20+ pages possible)
```

### Domain Restriction

The crawler maintains **same-domain restriction**:

- **Starting URL**: `https://example.com/wiki/Page`
- **Allowed**: Any page on `example.com` domain
- **Blocked**: External links to other domains

This prevents:
- Crawling external websites
- Leaving your wiki
- Uncontrolled crawl explosion

## Pages Indexed

### Page Information

Each indexed wiki page includes:

- **Title**: Page title
- **URL**: Full wiki page URL
- **Content**: Page text (extracted from HTML)
- **Last Editor**: Username of last editor
- **Last Edit Time**: When page was last modified
- **Source**: Always "mediawiki"

### Content Extraction

The crawler extracts from wiki pages:

- **Article text**: Full page content
- **Structured content**: Tables, lists, formatted text
- **Excludes**: Navigation, sidebars, metadata boxes

### Metadata Captured

```
Document ID: {page_title}
Title: {page_title}
Metadata:
  - url: {full_wiki_url}
  - last_edit_time: {ISO_timestamp}
  - last_edit_user: {editor_username}
  - source: mediawiki

Sections:
  - text: {extracted_page_content}
```

## API Requests

### MediaWiki API Endpoints

The crawler uses the MediaWiki Action API:

```
GET /api.php?action=query&prop=info|revisions|extracts&titles=PageTitle
```

**Query Parameters**:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `action` | `query` | Standard API query |
| `prop` | `info\|revisions\|extracts` | Request page info, revisions, extracted text |
| `titles` | Page name | Which page to fetch |
| `inprop` | `url` | Include full page URL |
| `rvprop` | `timestamp\|user` | Get revision timestamp and editor |
| `explaintext` | `1` | Return plain text, not HTML |
| `format` | `json` | Return JSON format |

### Link Discovery

Additional API call to fetch links from pages:

```
GET /api.php?action=query&prop=links&titles=PageTitle&pllimit=max
```

**Features**:
- Fetches all internal links
- Filters by namespace (0 = article namespace)
- Handles pagination with `plcontinue`

### Pagination

Links are paginated with continuation token:

```
First request: /api.php?action=query&prop=links&titles=Page
Response includes: { "continue": { "plcontinue": "token" } }

Next request: /api.php?action=query&prop=links&titles=Page&plcontinue=token
```

## How It Works

### Crawl Process

1. **Parse Source URLs**:
   - Extract domain and page title from each URL
   - Add to BFS queue with depth 0

2. **BFS Loop** (while queue has items and pages < n_pages):
   - Dequeue page (title, depth, domain)
   - Sleep 1 second (polite crawling)
   - Fetch page and links via API

3. **Validation**:
   - Check page has sufficient content (>10 chars)
   - Verify domain matches source domain
   - Skip if fails validation

4. **Indexing**:
   - Create document with page metadata
   - Index with Vectara
   - Increment success counter

5. **Link Processing**:
   - If depth < max_depth:
     - Add discovered links to queue
     - Mark as seen (prevent duplicates)
     - Continue BFS

6. **Completion**:
   - Stop when n_pages indexed or queue empty
   - Log total indexed count

### Document Structure

Each page becomes an indexed document:

```json
{
  "id": "Page_Title",
  "title": "Page Title",
  "description": "",
  "metadata": {
    "url": "https://example.com/wiki/Page_Title",
    "last_edit_time": "2024-11-18T10:30:00Z",
    "last_edit_user": "editor_username",
    "source": "mediawiki"
  },
  "sections": [
    {
      "text": "Full page content extracted from wiki..."
    }
  ]
}
```

### Rate Limiting

- **Polite Crawling**: 1-second delay between requests
- **Per Crawl**: Configurable via `n_pages` limit
- **API**: MediaWiki has generous rate limits
- **Behavior**: Respectful crawling recommended

## Troubleshooting

### No Pages Indexed

**Error**: Crawler completes with 0 pages indexed

**Solutions**:

1. **Verify API URL**:
   ```bash
   curl "https://example.com/w/api.php?action=query&format=json"
   ```
   Should return JSON response

2. **Check Source URLs**:
   ```yaml
   source_urls:
     - "https://en.wikipedia.org/wiki/Artificial_intelligence"  # Correct
     # NOT: "Artificial_intelligence" or missing domain
   ```

3. **Verify API access**:
   ```bash
   curl "https://en.wikipedia.org/w/api.php?action=query&titles=Main_Page&format=json"
   ```

4. **Check content threshold**:
   - Pages with <10 characters are skipped
   - Verify source pages have content

5. **Review logs**:
   ```bash
   docker logs -f vingest | grep -i "mediawiki\|indexed"
   ```

### Domain Mismatch Errors

**Error**: Pages being skipped with "domain mismatch"

**Solutions**:

1. **Source URL domain**:
   ```yaml
   # Good: Consistent domain
   source_urls:
     - "https://en.wikipedia.org/wiki/AI"
     - "https://en.wikipedia.org/wiki/ML"

   # Bad: Mixed domains
   source_urls:
     - "https://en.wikipedia.org/wiki/AI"
     - "https://es.wikipedia.org/wiki/IA"  # Different domain!
   ```

2. **Internal links**:
   - Check page doesn't redirect to different domain
   - Some pages redirect (handled gracefully)

3. **Multiple wikis**:
   - Create separate configs for different domains
   - Run independently

### Connection/SSL Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:

For **self-signed certificates**:
```yaml
mediawiki_crawler:
  verify_ssl: false  # If available
```

For **public wikis**: Should work without changes

### Slow Crawling

**Problem**: Crawl takes very long

**Causes and Solutions**:

1. **Large number of pages**:
   ```yaml
   n_pages: 100  # Reduce from 500
   depth: 1      # Reduce from 3
   ```

2. **Deep crawl**:
   ```yaml
   depth: 1  # Shallower crawl
   ```

3. **Network latency**:
   - Normal for Wikipedia: 0.5-2 seconds per page
   - Includes 1-second polite delay
   - 100 pages = ~2 minutes typical

4. **Large pages**:
   - Some wiki pages have extensive content
   - Text extraction takes time
   - Accept as expected behavior

### Out of Memory

**Error**: Memory limit exceeded

**Solutions**:

1. **Reduce page limit**:
   ```yaml
   n_pages: 50  # Instead of 500
   ```

2. **Reduce depth**:
   ```yaml
   depth: 1  # Instead of 3
   ```

3. **Increase Docker memory**:
   ```bash
   docker run -m 4g ...  # 4GB memory
   ```

## Performance Tips

### 1. Balance Coverage and Speed

```yaml
# Quick crawl (1-2 minutes)
n_pages: 50
depth: 1

# Standard crawl (5-10 minutes)
n_pages: 100
depth: 2

# Comprehensive crawl (20+ minutes)
n_pages: 500
depth: 3
```

### 2. Choose Starting Pages Carefully

```yaml
# Focused crawl
source_urls:
  - "https://en.wikipedia.org/wiki/Machine_Learning"

# Broader crawl
source_urls:
  - "https://en.wikipedia.org/wiki/Artificial_intelligence"
  - "https://en.wikipedia.org/wiki/Computer_science"
```

### 3. Optimize for Wikipedia

```yaml
# For Wikipedia crawling
api_url: "https://en.wikipedia.org/w/api.php"
n_pages: 200
depth: 2  # Good balance
```

### 4. Schedule Off-Peak

```bash
# Run daily at 3 AM
0 3 * * * cd /path/to/vectara-ingest && bash run.sh config/mediawiki.yaml default
```

### 5. Multiple Wikis Separately

```bash
# Different crawls for different wikis
bash run.sh config/wiki-main.yaml default
sleep 120
bash run.sh config/wiki-docs.yaml default
```

## Best Practices

### 1. Use Complete URLs for Source

```yaml
# Correct: Full URL with page title
source_urls:
  - "https://en.wikipedia.org/wiki/Machine_Learning"

# Incorrect: Missing page or domain
source_urls:
  - "Machine_Learning"  # WRONG
  - "https://en.wikipedia.org"  # Just domain
```

### 2. Start Small, Expand Carefully

```yaml
# Test with few pages
n_pages: 10
depth: 1

# Then expand
n_pages: 100
depth: 2
```

### 3. Meaningful Metadata

```yaml
metadata:
  source: mediawiki
  environment: production
  wiki_type: "public"
  wiki_domain: "en.wikipedia.org"
  content_types:
    - reference
    - educational
  sync_frequency: weekly
```

### 4. Monitor Page Discovery

Watch the BFS discovery process:

```bash
docker logs -f vingest | grep -i "indexed\|checking"
```

### 5. Handle Private Wikis Securely

```bash
# Use environment variable for token
export MEDIAWIKI_API_KEY="token_here"

# Not in config file
# mediawiki_api_key: "token"  # WRONG!
```

### 6. Test API Access First

```bash
# Verify API is accessible and working
curl "https://en.wikipedia.org/w/api.php?action=query&titles=Main_Page&format=json"

# Should return JSON with page data
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/mediawiki-crawl.yaml
```

### Set Environment Variables (if needed)

```bash
export MEDIAWIKI_API_KEY="your_token_here"  # For private wikis only
```

### Run the Crawler

```bash
# Run with your config
bash run.sh config/mediawiki-crawl.yaml default

# Monitor logs
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 3 AM
0 3 * * * cd /path/to/vectara-ingest && bash run.sh config/mediawiki-crawl.yaml default

# Weekly on Sunday
0 3 * * 0 cd /path/to/vectara-ingest && bash run.sh config/mediawiki-crawl.yaml default

# Every 3 days
0 3 */3 * * cd /path/to/vectara-ingest && bash run.sh config/mediawiki-crawl.yaml default
```

## Complete Examples

### Example 1: Wikipedia AI Topics

```yaml
# config/mediawiki-ai.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: wikipedia-ai

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://en.wikipedia.org/w/api.php"

  source_urls:
    - "https://en.wikipedia.org/wiki/Artificial_intelligence"
    - "https://en.wikipedia.org/wiki/Machine_learning"
    - "https://en.wikipedia.org/wiki/Deep_learning"

  depth: 2
  n_pages: 200

metadata:
  source: mediawiki
  environment: production
  topic: ai
```

### Example 2: Internal Company Wiki

```yaml
# config/mediawiki-company.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: company-wiki
  reindex: false

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://internal.company.com/w/api.php"

  source_urls:
    - "https://internal.company.com/wiki/Documentation"
    - "https://internal.company.com/wiki/Procedures"

  depth: 3
  n_pages: 500

mediawiki_api_key: "${MEDIAWIKI_API_KEY}"

metadata:
  source: mediawiki
  environment: production
  wiki_type: internal
  access_level: internal
```

### Example 3: Quick Wikipedia Crawl

```yaml
# config/mediawiki-quick.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: wikipedia-quick

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://en.wikipedia.org/w/api.php"

  source_urls:
    - "https://en.wikipedia.org/wiki/Science"

  depth: 1
  n_pages: 50

metadata:
  source: mediawiki
  environment: production
```

### Example 4: Comprehensive Knowledge Base

```yaml
# config/mediawiki-comprehensive.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: wikipedia-knowledge-base
  reindex: true
  verbose: true

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://en.wikipedia.org/w/api.php"

  source_urls:
    - "https://en.wikipedia.org/wiki/Technology"
    - "https://en.wikipedia.org/wiki/Science"
    - "https://en.wikipedia.org/wiki/History"

  depth: 2
  n_pages: 500

metadata:
  source: mediawiki
  environment: production
  content_types:
    - reference
    - educational
    - comprehensive
  sync_frequency: weekly
```

### Example 5: Multiple Wiki Crawl Script

```bash
# mediawiki-batch-crawl.sh
#!/bin/bash

# Technology topics
bash run.sh config/mediawiki-tech.yaml default
sleep 120

# Science topics
bash run.sh config/mediawiki-science.yaml default
sleep 120

# History topics
bash run.sh config/mediawiki-history.yaml default

echo "All MediaWiki crawls completed"
```

### Example 6: Production Setup with Error Handling

```yaml
# config/mediawiki-production.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: mediawiki-prod
  reindex: false
  verbose: true

crawling:
  crawler_type: mediawiki

mediawiki_crawler:
  api_url: "https://en.wikipedia.org/w/api.php"

  source_urls:
    - "https://en.wikipedia.org/wiki/Main_Page"

  depth: 2
  n_pages: 300

metadata:
  source: mediawiki
  environment: production
  version: "1.0"
  created_date: "2024-11-18"
  backup_enabled: true
  error_notification: "ops@company.com"
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## MediaWiki API Resources

- [MediaWiki Action API Documentation](https://www.mediawiki.org/wiki/API:Main_page)
- [Query API Reference](https://www.mediawiki.org/wiki/API:Query)
- [Extract Module](https://www.mediawiki.org/wiki/Extension:TextExtracts)
- [Page Links Query](https://www.mediawiki.org/wiki/API:Query#Querying_page_links)
- [Wikipedia API Guide](https://en.wikipedia.org/wiki/Wikipedia:API)
- [API Sandbox](https://en.wikipedia.org/wiki/Special:ApiSandbox)
