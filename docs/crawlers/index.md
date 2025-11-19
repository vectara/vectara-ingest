# Crawlers Overview

Vectara-ingest includes 30+ pre-built crawlers for ingesting data from various sources. Each crawler is designed to handle the specific requirements and authentication methods of its data source.

## Available Crawlers

### Content Management & Documentation

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Website** | Crawl any website with sitemap or URL list | [Guide](website.md) |
| **Docusaurus** | Specialized crawler for Docusaurus documentation sites | [Guide](docs.md) |
| **Notion** | Import Notion workspaces and pages | [Guide](notion.md) |
| **Confluence** | Index Confluence spaces | [Guide](confluence.md) |

### Communication & Collaboration

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Slack** | Ingest Slack channels and messages | [Guide](slack.md) |

### Project Management & Development

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Jira** | Index Jira issues, comments, and attachments | [Guide](jira.md) |
| **GitHub** | Crawl GitHub repositories, issues, and PRs | [Guide](github.md) |
| **ServiceNow** | Ingest ServiceNow tickets and knowledge base | [Guide](servicenow.md) |

### File Storage & Data

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Google Drive** | Crawl Google Drive files and folders | [Guide](gdrive.md) |
| **S3** | Ingest files from Amazon S3 buckets | [Guide](s3.md) |
| **Folder** | Process local file system folders | [Guide](folder.md) |
| **Database** | Query and ingest from SQL databases | [Guide](database.md) |
| **CSV** | Index structured data from CSV/XLSX files | [Guide](csv.md) |

### Content Feeds & News

| Crawler | Description | Guide |
|---------|-------------|-------|
| **RSS** | Crawl RSS and Atom feeds | [Guide](rss.md) |

### CRM & Sales

| Crawler | Description | Guide |
|---------|-------------|-------|
| **HubSpot CRM** | Index HubSpot deals, companies, contacts, and engagements | [Guide](hubspot.md) |

### Financial & Regulatory Data

| Crawler | Description | Guide |
|---------|-------------|-------|
| **EDGAR** | Index SEC financial filings (10-K, 10-Q, 8-K, DEF 14A) | [Guide](edgar.md) |
| **Financial Modeling Prep** | Index financial reports and earnings call transcripts | [Guide](fmp.md) |

### Research & Academic

| Crawler | Description | Guide |
|---------|-------------|-------|
| **arXiv** | Index academic papers and preprints from arXiv | [Guide](arxiv.md) |
| **PubMed Central** | Index biomedical research papers from PMC | [Guide](pmc.md) |

### Social Media & Community

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Twitter/X** | Index tweets and user profiles | [Guide](twitter.md) |
| **Hacker News** | Index stories and comments from HN | [Guide](hackernews.md) |
| **Discourse** | Index forum topics and posts | [Guide](discourse.md) |

### Machine Learning & Data

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Hugging Face Datasets** | Index datasets from Hugging Face Hub | [Guide](hfdataset.md) |

### Media & Video

| Crawler | Description | Guide |
|---------|-------------|-------|
| **YouTube** | Transcribe and index YouTube videos | [Guide](youtube.md) |

### Knowledge Bases & Wikis

| Crawler | Description | Guide |
|---------|-------------|-------|
| **MediaWiki** | Index MediaWiki sites (Wikipedia, etc.) | [Guide](mediawiki.md) |
| **Synapse** | Index Sage Synapse data repositories | [Guide](synapse.md) |

### Batch & Utility

| Crawler | Description | Guide |
|---------|-------------|-------|
| **Bulk Upload** | Batch upload documents via JSON file | [Guide](bulkupload.md) |

## Choosing a Crawler

When selecting a crawler, consider:

1. **Data Source Type**: Does your source match one of the pre-built crawlers?
2. **Authentication**: What authentication method does the source use?
3. **Data Structure**: Is your data hierarchical, flat, or structured?
4. **Update Frequency**: Do you need incremental updates or full re-indexing?

## Common Configuration

All crawlers share a common set of Vectara configuration options including:

- **Connection settings** (endpoint, corpus key, SSL verification)
- **Indexing behavior** (reindex, create corpus)
- **Chunking strategies** (sentence or fixed)
- **Content processing** (boilerplate removal, code removal, PII masking)
- **Document processing** (parsers, table extraction, image processing)
- **Timeouts and performance** settings

**See the [Base Configuration Guide](../configuration-base.md) for complete details on all common options.**

Each crawler also has its own specific configuration parameters documented in their individual pages.

## Crawler-Specific Configuration

Each crawler has its own set of configuration parameters. For example:

### Website Crawler
```yaml
website_crawler:
  urls:
    - https://example.com
  max_depth: 3
```

### RSS Crawler
```yaml
rss_crawler:
  source: my-source
  rss_pages:
    - https://example.com/feed.xml
  days_past: 30
```

### Notion Crawler
```yaml
notion_crawler:
  source: notion
  # Uses NOTION_API_KEY from secrets.toml
```

## Authentication

Most crawlers require authentication. Add credentials to your `secrets.toml`:

```toml
[default]
api_key = "your-vectara-api-key"

# Crawler-specific credentials
NOTION_API_KEY = "secret_..."
JIRA_USERNAME = "user@example.com"
JIRA_PASSWORD = "your-api-token"
GITHUB_TOKEN = "ghp_..."
SLACK_TOKEN = "xoxb-..."
```

See individual crawler guides for specific authentication requirements.

## Creating Custom Crawlers

Don't see a crawler for your data source? You can build your own!

The crawler framework makes it easy to create custom implementations:

1. Extend the `Crawler` base class
2. Implement the `crawl()` method
3. Use the `Indexer` class to send data to Vectara

See the [Custom Crawler Guide](../advanced/custom-crawler.md) for detailed instructions.

## Performance Considerations

### Crawling Speed

- **Parallel Processing**: Many crawlers support concurrent requests
- **Rate Limiting**: Respect source API rate limits
- **Batch Size**: Adjust batch sizes for optimal throughput

### Resource Usage

- **Memory**: Document parsing can be memory-intensive
- **Storage**: Enable `store_docs` to keep local copies
- **Network**: Large files may require increased timeout values

### Docker Resources

When running in Docker, ensure adequate resources:

```bash
# Check Docker resources
docker stats vingest
```

Recommended minimums:
- **Memory**: 4GB (8GB for large documents)
- **CPU**: 2 cores
- **Disk**: 10GB free space

## Crawler Status

All crawlers are actively maintained. Feature support:

| Feature | Support |
|---------|---------|
| Basic Indexing | ✅ All crawlers |
| Incremental Updates | ✅ Most crawlers |
| Attachment Support | ✅ Jira, Notion, Confluence, Slack, GitHub |
| Metadata Extraction | ✅ All crawlers |
| Custom Fields | ✅ Most crawlers |

## Getting Help

Each crawler page includes:

- Configuration examples
- Authentication setup
- Common use cases
- Troubleshooting tips

For additional help:

- Check the [Troubleshooting Guide](../deployment/troubleshooting.md)
- Ask in our [Discord community](https://discord.com/invite/GFb8gMz6UH)
- Open an [issue on GitHub](https://github.com/vectara/vectara-ingest/issues)

## Next Steps

- **Explore Specific Crawlers**: Browse the crawler guides in the sidebar
- **Configure Your Crawler**: See the [Configuration Reference](../configuration.md)
- **Advanced Features**: Learn about [Table Extraction](../features/table-extraction.md), [Image Processing](../features/image-processing.md), and more
- **Deploy**: Check out [Deployment Options](../deployment/docker.md)
