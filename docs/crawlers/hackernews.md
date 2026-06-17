# Hacker News Crawler

The Hacker News crawler indexes stories and discussions from Hacker News, including all nested comments, with intelligent recency filtering and comprehensive discussion capture.

## Overview

- **Crawler Type**: `hackernews`
- **Authentication**: None required (public API)
- **API Support**: Hacker News Firebase API
- **Content Types**: Stories, comments, discussions
- **Metadata Capture**: Author, creation date, scores, comment threads
- **Filtering**: Date-based filtering, story type filtering, discussion depth

## Use Cases

- Tech industry news aggregation
- Development trends and discussions
- Community sentiment analysis
- Technical knowledge base from discussions
- Innovation tracking
- Startup ecosystem monitoring
- Engineering best practices collection

## Getting Started: API Authentication

### No Authentication Required

The Hacker News API is completely public and requires no authentication. The crawler accesses the public Hacker News Firebase API endpoints.

#### API Access

The Hacker News API is available at:
```
https://hacker-news.firebaseio.com/v0/
```

No API keys, tokens, or credentials are needed.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-stories

crawling:
  crawler_type: hackernews

hackernews_crawler:
  # Maximum number of stories to index
  max_articles: 100

  # Days back to consider (recent activity filtering)
  days_back: 3

  # Enable comprehensive historical crawling
  days_back_comprehensive: false
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-knowledge-base
  reindex: true
  verbose: true

crawling:
  crawler_type: hackernews

hackernews_crawler:
  # Fetch up to 500 stories
  max_articles: 500

  # Only index stories with recent activity within 7 days
  days_back: 7

  # Comprehensive mode: crawl by date (slower, more complete)
  days_back_comprehensive: true

  # SSL/TLS configuration (if needed)
  verify_ssl: true

metadata:
  source: hackernews
  environment: production
  content_types:
    - stories
    - discussions
    - comments
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `max_articles` | int | No | `100` | Maximum number of stories to index (capped at 1000) |
| `days_back` | int | No | `3` | Only index stories/comments newer than N days ago |
| `days_back_comprehensive` | bool | No | `false` | Enable historical crawling by iterating through all items by date |
| `verify_ssl` | bool | No | `true` | Enable SSL/TLS certificate verification |

## Stories and Comments Indexed

### Story Information

The crawler indexes Hacker News stories with:

- **ID**: Unique story identifier
- **Title**: Story title (cleaned of HTML)
- **Text**: Story description/text (if present, HTML converted to text)
- **URL**: Original article URL (if story is a link)
- **Score**: Upvote count
- **Author**: Username who posted the story
- **Date**: When story was posted
- **Comment Count**: Number of discussions

### Comment Threads

All comments on stories are automatically indexed:

- **Text**: Comment content (HTML converted to text)
- **Author**: Username who commented
- **Date**: When comment was posted
- **Score**: Comment upvotes
- **Nested Comments**: Recursively includes replies to comments

### Metadata Captured

Each indexed story includes:

```
Document ID: hn_story_{story_id}
Title: {story_title}
Metadata:
  - source: hackernews
  - title: {story_title}
  - url: {article_url or "https://news.ycombinator.com/item?id={id}"}
  - story_url: {original_story_url}
  - date: {YYYY-MM-DD}
  - by: {author_username}

Sections:
  1. Story text (if present)
  2. Each comment with:
     - text: {comment_content}
     - by: {comment_author}
     - date: {comment_date}
     - url: {direct_comment_link}
```

## Date-Based Filtering

### Recent Activity Mode (Default)

The crawler filters stories based on comment recency:

```yaml
days_back: 3  # Only stories with comments from last 3 days
```

**How it works**:
1. Fetches story from current top/new/best/show/ask lists
2. Retrieves all comments
3. Checks if most recent comment is within `days_back`
4. Skips if all discussion is older than threshold

**Benefits**:
- Focuses on active discussions
- Reduces stale content
- Faster crawling
- Relevant knowledge base

### Comprehensive Historical Mode

Enable historical crawling for complete capture:

```yaml
days_back_comprehensive: true
days_back: 7  # Look back 7 days in archive
```

**How it works**:
1. Queries all items by date (slower iteration)
2. Collects stories from specified date range
3. Indexes with full comment history
4. Captures less popular but valuable content

**Trade-offs**:
- Much slower (iterates through many items)
- More complete coverage
- Higher API request count
- Better for historical analysis

### Configuration Examples

```yaml
# Fresh news focus (last day)
days_back: 1
days_back_comprehensive: false

# Active discussions (last week)
days_back: 7
days_back_comprehensive: false

# Comprehensive weekly archive
days_back: 7
days_back_comprehensive: true

# Deep historical archive (risky - very slow)
days_back: 30
days_back_comprehensive: true
```

## Story Types

The crawler automatically fetches stories from multiple Hacker News sections:

1. **Top Stories** - Currently highest-voted stories
2. **New Stories** - Recently posted stories
3. **Best Stories** - All-time quality stories
4. **Show Stories** - "Show HN" projects and creations
5. **Ask Stories** - Community questions and discussions

Stories may appear in multiple categories and are deduplicated.

## Comment Recursion

### Nested Comments

The crawler recursively indexes nested comment threads:

```
Story: "The Future of AI"
├── Comment by alice: "Great article"
│   ├── Reply by bob: "I disagree because..."
│   │   └── Reply by charlie: "Actually..."
│   └── Reply by dave: "Another perspective"
└── Comment by eve: "Related to my research"
```

All levels are captured and indexed as searchable sections.

### Performance Notes

- Nested comment fetching uses recursive API calls
- One request per comment to fetch details
- Large discussions with 100+ comments impact crawl time
- Error handling skips dead comments/deleted threads

## How It Works

### Crawl Process

1. **Fetch Story Lists**: Retrieves top, new, best, show, and ask story IDs
2. **Deduplicate**: Combines lists and removes duplicates
3. **Limit Count**: Selects up to `max_articles` stories
4. **For Each Story**:
   - Fetches story details from API
   - Converts title/text from HTML to plain text
   - Fetches all comments recursively
   - Checks date filtering criteria
   - Indexes document with Vectara
5. **Complete**: Logs total indexed stories

### API Requests

The crawler makes these API calls:

```
GET /topstories.json           (Top story IDs)
GET /newstories.json           (New story IDs)
GET /beststories.json          (Best story IDs)
GET /showstories.json          (Show HN IDs)
GET /askstories.json           (Ask HN IDs)
GET /item/{id}.json            (Story details)
GET /item/{comment_id}.json    (Comment details - per comment)
GET /maxitem.json              (For comprehensive mode)
```

### Rate Limiting and Performance

- **No rate limiting**: Hacker News API is unrestricted
- **Polite crawling**: Built-in delays (session with retries)
- **Comment fetching**: Slowest part (one request per comment)
- **Optimization**: Comments with no text are skipped

### Document Structure

Each story becomes one indexed document:

```
{
  "id": "hn_story_12345678",
  "title": "How We Built Our Platform",
  "metadata": {
    "source": "hackernews",
    "title": "How We Built Our Platform",
    "url": "https://news.ycombinator.com/item?id=12345678",
    "story_url": "https://example.com/blog/platform",
    "date": "2024-11-18",
    "by": "author_username"
  },
  "sections": [
    {
      "text": "Story description/text content here..."
    },
    {
      "text": "Comment from commenter1: Great article!",
      "metadata": {
        "by": "commenter1",
        "date": "2024-11-18",
        "url": "https://news.ycombinator.com/item?id=12345678#12345679"
      }
    },
    // ... more comments
  ]
}
```

## HTML to Text Conversion

The crawler converts HTML to plain text:

**Story Title**:
```
Raw: "The <em>Future</em> of AI"
Clean: "The Future of AI"
```

**Story Text/Comments**:
```
Raw: "<p>Check this out <a href=\"...\">link</a></p>"
Clean: "Check this out link"
```

This improves:
- Search relevance
- Readability
- Indexing efficiency

## Troubleshooting

### No Stories Found

**Error**: Crawler completes but indexes 0 stories

**Solutions**:
1. Verify configuration is correct:
   ```bash
   grep -A 5 "hackernews_crawler:" config/your-config.yaml
   ```
2. Check `max_articles` value (should be > 0)
3. Verify date filtering isn't too restrictive:
   ```yaml
   days_back: 1    # Very restrictive
   days_back: 7    # Better
   ```
4. Check logs for API errors:
   ```bash
   docker logs -f vingest
   ```

### API Connection Failed

**Error**: `Failed to fetch` or network timeout

**Solutions**:
1. Verify internet connectivity:
   ```bash
   curl https://hacker-news.firebaseio.com/v0/topstories.json
   ```
2. Check if Hacker News API is up (rarely down)
3. Verify SSL/TLS settings:
   ```yaml
   hackernews_crawler:
     verify_ssl: true  # Default
   ```
4. Test with smaller `max_articles`:
   ```yaml
   max_articles: 10  # Instead of 500
   ```

### Slow Crawling

**Problem**: Crawler runs very slowly

**Causes and Solutions**:
1. **Large number of stories**: Reduce `max_articles`
   ```yaml
   max_articles: 50  # Instead of 500
   ```

2. **Comprehensive mode enabled**: Disable if not needed
   ```yaml
   days_back_comprehensive: false
   ```

3. **Many comments per story**: Normal for large discussions
   - Hacker News stories can have 500+ comments
   - Each comment requires separate API call
   - Mitigate by reducing `max_articles`

4. **Network latency**: Use date-based filtering
   ```yaml
   days_back_comprehensive: false  # Faster list-based
   ```

### Out of Memory

**Error**: Java/Python memory error

**Solutions**:
1. Reduce `max_articles`:
   ```yaml
   max_articles: 50  # Instead of 500
   ```
2. Run crawler more frequently with fewer articles
3. Increase Docker memory allocation:
   ```bash
   docker run -m 2g ...  # 2GB memory
   ```

### Duplicate Stories

**Expected behavior**: Some duplication possible

**Why**:
- Stories appear in multiple lists (top, best, new)
- Deduplication happens but may not catch all

**Mitigation**:
- Vectara handles near-duplicate detection
- Document IDs include story ID (prevents exact duplication)
- Acceptable for this use case

## Performance Tips

### 1. Balance Coverage and Speed

```yaml
# Quick crawl (2-5 minutes)
max_articles: 50
days_back: 3
days_back_comprehensive: false

# Standard crawl (5-10 minutes)
max_articles: 100
days_back: 7
days_back_comprehensive: false

# Comprehensive crawl (20+ minutes)
max_articles: 500
days_back: 7
days_back_comprehensive: true
```

### 2. Schedule Regular Crawls

Since HN content changes rapidly, schedule frequent updates:

```bash
# Multiple times daily
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/hackernews.yaml default

# Twice daily
0 6,18 * * * cd /path/to/vectara-ingest && bash run.sh config/hackernews.yaml default
```

### 3. Focus on Active Discussions

```yaml
# Only recently active stories
days_back: 2
days_back_comprehensive: false
max_articles: 100
```

### 4. Optimize Comment Depth

Consider story size when setting `max_articles`:

```yaml
# Fewer stories but complete discussions
max_articles: 50

# More stories, some with fewer comments
max_articles: 200
```

### 5. Monitor Crawl Progress

The crawler logs progress every 20 stories:

```bash
# Watch logs during crawl
docker logs -f vingest | grep "Crawled"
```

## Best Practices

### 1. Enable Reindexing

Hacker News depends on comments for value, so reindex:

```yaml
vectara:
  reindex: true  # Always enabled for hackernews
```

This is automatically set by the crawler.

### 2. Set Appropriate Update Frequency

```bash
# Recommended: Every 6-12 hours
0 */6 * * * bash run.sh config/hackernews.yaml default

# More frequent for breaking news tracking
0 */3 * * * bash run.sh config/hackernews.yaml default
```

### 3. Use Descriptive Metadata

```yaml
metadata:
  source: hackernews
  environment: production
  content_types:
    - tech_news
    - discussions
  sync_frequency: daily
  use_case: "tech_trends_monitoring"
```

### 4. Start Small

Test with minimal settings:

```yaml
max_articles: 10
days_back: 1
days_back_comprehensive: false
```

Then expand:

```yaml
max_articles: 100
days_back: 7
days_back_comprehensive: false
```

### 5. Monitor Indexing

```bash
bash run.sh config/hackernews.yaml default
# Check for:
# - Stories successfully indexed
# - Comment extraction working
# - Date filtering applied
# - API errors or timeouts
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/hackernews-crawl.yaml
```

### Run the Crawler

```bash
# Run with your config
bash run.sh config/hackernews-crawl.yaml default

# Monitor logs
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/hackernews-crawl.yaml default

# Twice daily at specific times
0 6,18 * * * cd /path/to/vectara-ingest && bash run.sh config/hackernews-crawl.yaml default

# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/hackernews-crawl.yaml default
```

## Complete Examples

### Example 1: Quick Daily Crawl

```yaml
# config/hackernews-daily.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-daily

crawling:
  crawler_type: hackernews

hackernews_crawler:
  max_articles: 50
  days_back: 1
  days_back_comprehensive: false

metadata:
  source: hackernews
  environment: production
  sync_frequency: daily
```

Run with:
```bash
bash run.sh config/hackernews-daily.yaml default
```

### Example 2: Comprehensive Weekly Archive

```yaml
# config/hackernews-weekly.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-archive
  reindex: true
  verbose: true

crawling:
  crawler_type: hackernews

hackernews_crawler:
  max_articles: 500
  days_back: 7
  days_back_comprehensive: false

metadata:
  source: hackernews
  environment: production
  content_types:
    - tech_news
    - discussions
  sync_frequency: weekly
```

### Example 3: Active Discussions Focus

```yaml
# config/hackernews-active.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-active-discussions
  reindex: true

crawling:
  crawler_type: hackernews

hackernews_crawler:
  max_articles: 100
  days_back: 3
  days_back_comprehensive: false

metadata:
  source: hackernews
  environment: production
  content_types:
    - active_discussions
```

### Example 4: Historical Deep Crawl

```yaml
# config/hackernews-historical.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hackernews-historical
  reindex: true
  verbose: true

crawling:
  crawler_type: hackernews

hackernews_crawler:
  max_articles: 200
  days_back: 14
  days_back_comprehensive: true

metadata:
  source: hackernews
  environment: production
  content_types:
    - historical_archive
  note: "Comprehensive crawl - may take 30+ minutes"
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Hacker News API Resources

- [Hacker News API Documentation](https://github.com/HackerNews/API)
- [Firebase API Endpoint](https://hacker-news.firebaseio.com/v0/)
- [Hacker News Website](https://news.ycombinator.com/)
- [Stories and Comments Data](https://news.ycombinator.com/item?id=1)
