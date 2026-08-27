# RSS Crawler

The RSS crawler indexes content from RSS and Atom feeds with date-based filtering and parallel processing support.

## Overview

- **Crawler Type**: `rss`
- **Authentication**: None required
- **Parallel Processing**: Ray workers supported
- **Rate Limiting**: Configurable delay

## Use Cases

- News aggregation from multiple sources
- Blog content ingestion
- Podcast show notes and transcripts
- Content monitoring and archival
- RSS feed consolidation

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: news-corpus

crawling:
  crawler_type: rss

rss_crawler:
  # RSS feed URLs (list or single string)
  rss_pages:
    - https://example.com/feed.xml
    - https://news.example.com/rss

  # Number of days to look back
  days_past: 30

  # Delay in seconds between requests
  delay: 1

  # Source identifier for metadata
  source: my-news-source
```

### Advanced Configuration

```yaml
rss_crawler:
  # Multiple feeds
  rss_pages:
    - https://techcrunch.com/feed/
    - https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml
    - https://feeds.arstechnica.com/arstechnica/index

  # Crawl articles from last 90 days
  days_past: 90

  # Rate limiting: 2 seconds between requests
  delay: 2

  # Source name for metadata
  source: tech-news

  # Parallel processing with Ray
  ray_workers: 4

  # Override scrape method (optional)
  scrape_method: playwright
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `rss_pages` | list/string | Yes | - | RSS feed URL(s) |
| `days_past` | int | Yes | - | Number of days to look back |
| `delay` | int | Yes | - | Delay between requests (seconds) |
| `source` | string | Yes | - | Source identifier for metadata |
| `ray_workers` | int | No | `0` | Number of parallel workers (0=sequential) |
| `scrape_method` | string | No | - | Override default scrape method |

## How It Works

1. **Feed Parsing**: Fetches and parses RSS/Atom feeds
2. **Date Filtering**: Filters articles based on `days_past` setting
3. **Deduplication**: Skips already-processed URLs
4. **Content Extraction**: Visits each article URL and extracts content
5. **Indexing**: Sends content to Vectara with metadata

## Metadata Captured

The crawler automatically extracts and indexes:

- **Title**: Article title from RSS feed
- **Author**: Author name (if available)
- **Publication Date**: `pubDate` or `published` from feed
- **URL**: Link to the original article
- **Source**: Your configured `source` value
- **Description**: RSS description/summary (if available)

## Examples

### News Aggregation

```yaml
vectara:
  corpus_key: news-aggregator
  remove_boilerplate: true  # Remove ads and navigation

crawling:
  crawler_type: rss

rss_crawler:
  rss_pages:
    - https://rss.cnn.com/rss/cnn_topstories.rss
    - https://feeds.bbci.co.uk/news/world/rss.xml
    - https://feeds.reuters.com/reuters/topNews
  days_past: 7
  delay: 2
  source: world-news
  ray_workers: 0

metadata:
  category: news
  language: en
```

### Blog Content

```yaml
rss_crawler:
  rss_pages:
    - http://www.paulgraham.com/rss.html
  days_past: 365
  delay: 1
  source: pg-essays
```

### Podcast Show Notes

```yaml
rss_crawler:
  rss_pages:
    - https://feeds.simplecast.com/54nAGcIl  # The Changelog
  days_past: 180
  delay: 1
  source: podcasts
```

### Multiple Sources with Parallel Processing

```yaml
rss_crawler:
  rss_pages:
    - https://hnrss.org/frontpage
    - https://www.reddit.com/r/technology/.rss
    - https://lobste.rs/rss
  days_past: 30
  delay: 1
  source: tech-communities
  ray_workers: 3  # Process 3 feeds in parallel
```

## Date Filtering

The `days_past` parameter controls how far back to look:

```yaml
rss_crawler:
  days_past: 7   # Last week
  days_past: 30  # Last month
  days_past: 365 # Last year
  days_past: 1000 # ~3 years
```

Articles published before the cutoff date are skipped.

## Rate Limiting

The `delay` parameter adds a pause between article indexing:

```yaml
rss_crawler:
  delay: 1  # 1 second between articles (60/minute)
  delay: 2  # 2 seconds between articles (30/minute)
  delay: 5  # 5 seconds between articles (12/minute)
```

Use higher delays for:
- Sites with strict rate limiting
- Servers with limited capacity
- Being a good internet citizen

## Parallel Processing

Enable Ray workers for faster processing of multiple feeds:

```yaml
rss_crawler:
  ray_workers: 0   # Sequential processing
  ray_workers: 4   # 4 parallel workers
  ray_workers: -1  # Use all CPU cores
```

!!! note "When to Use Parallel Processing"
    - Multiple RSS feeds (3+)
    - Large feeds with many articles
    - Sufficient system resources (CPU, memory)

## Content Extraction

### Remove Boilerplate

For news sites with ads and navigation:

```yaml
vectara:
  remove_boilerplate: true

rss_crawler:
  # ... rss config ...
```

This uses Goose3 and justext to extract only the main article content.

### Remove Code Blocks

For tech blogs with code examples you don't want indexed:

```yaml
vectara:
  remove_code: true
```

## Handling Feed Formats

The crawler supports:

- **RSS 2.0**: Standard RSS format
- **RSS 1.0**: RDF-based format
- **Atom**: IETF standard format

It automatically detects the format and extracts appropriate fields.

## Troubleshooting

### Feed Not Loading

**Issue**: `Failed to fetch RSS feed`

**Solutions**:
1. Verify the RSS URL in a browser
2. Check for HTTPS/HTTP issues
3. Ensure the feed is publicly accessible
4. Check for rate limiting or blocking

### No Articles Indexed

**Issue**: Crawler runs but indexes no articles

**Solutions**:
1. Increase `days_past` value
2. Check feed actually has recent articles
3. Look for date parsing errors in logs
4. Verify `delay` isn't too aggressive

### Duplicate Articles

**Issue**: Same article indexed multiple times

**Solution**: The crawler uses URL-based deduplication. This shouldn't happen unless:
- URLs have changing query parameters
- The corpus was cleared between runs
- Using `reindex: true`

### Rate Limiting Errors

**Issue**: Getting blocked by website

**Solutions**:
1. Increase `delay` value
2. Reduce `ray_workers` count
3. Add custom `user_agent`:
   ```yaml
   vectara:
     user_agent: "MyBot/1.0 (contact@example.com)"
   ```

## Best Practices

### 1. Start with Recent Content

Begin with shorter time periods:

```yaml
rss_crawler:
  days_past: 7  # Start with one week
```

Then expand to longer periods after testing.

### 2. Use Descriptive Source Names

```yaml
rss_crawler:
  source: tech-news-2024  # Good
  source: feed1           # Bad
```

### 3. Group Related Feeds

Create separate configs for different topics:

```yaml
# config/news-tech.yaml
rss_crawler:
  source: tech-news
  rss_pages: [...]

# config/news-business.yaml
rss_crawler:
  source: business-news
  rss_pages: [...]
```

### 4. Monitor Feed Changes

Websites sometimes change their RSS feed URLs. Periodically verify feeds are still active.

### 5. Use Metadata for Organization

```yaml
metadata:
  category: news
  topic: technology
  language: en
  indexed_date: "2024-01-01"
```

## Running the Crawler

```bash
# Create your config
vim config/rss-news.yaml

# Run the crawler
bash run.sh config/rss-news.yaml default

# Monitor progress
docker logs -f vingest
```

## Scheduling Regular Crawls

For continuous news monitoring, schedule regular runs:

```bash
# Run daily at 6 AM
0 6 * * * cd /path/to/vectara-ingest && bash run.sh config/rss-news.yaml default
```

Or use a CI/CD system like GitHub Actions to run on schedule.

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Website Crawler](website.md) - For crawling linked articles' full content
- [Deployment](../deployment/docker.md) - Running in production

## Complete Example

```yaml
# Complete RSS crawler configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: news-corpus
  reindex: false
  verbose: true
  remove_boilerplate: true
  remove_code: false
  timeout: 90

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: false
  summarize_images: false

crawling:
  crawler_type: rss

rss_crawler:
  rss_pages:
    - https://techcrunch.com/feed/
    - https://www.theverge.com/rss/index.xml
  days_past: 30
  delay: 2
  source: tech-news
  ray_workers: 0

metadata:
  category: technology
  content_type: news
  language: en
```

Save as `config/tech-news-rss.yaml` and run:

```bash
bash run.sh config/tech-news-rss.yaml default
```
