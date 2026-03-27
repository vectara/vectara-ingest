# Discourse Crawler

The Discourse crawler indexes forum topics and discussions from Discourse-powered communities, capturing all posts, metadata, and discussion history with full HTML-to-text conversion.

## Overview

- **Crawler Type**: `discourse`
- **Authentication**: API Key (Discourse forum admin)
- **API Support**: Discourse REST API
- **Content Types**: Topics, posts, discussions
- **Metadata Capture**: Author, creation/modification dates, URLs
- **Content Extraction**: HTML-to-text conversion for all posts

## Use Cases

- Community knowledge base indexing
- Product support documentation
- User discussion archives
- Community best practices and solutions
- FAQ and troubleshooting guides
- Feature request tracking
- Community feedback collection
- Team communication history

## Getting Started: API Authentication

### Get Your Discourse API Key

To access a Discourse forum's API, you need to generate an API key from an admin account.

#### Creating an API Key

1. Log in to your Discourse forum with an admin account
2. Go to **Admin > Plugins > API**
3. Click **New API Key** (or navigate to `/admin/api/keys`)
4. Choose key type:
   - **User-generated key**: For personal use
   - **All users**: For general crawling (recommended)
5. Optionally set scope/permissions (typically leave unrestricted)
6. Copy the **API Key** value
7. Note the **API URL** of your Discourse instance

#### Required Information

You'll need:

1. **Base URL**: Your Discourse instance URL
   ```
   https://discourse.example.com
   https://community.mycompany.com
   ```

2. **API Key**: Generated from admin panel
   ```
   a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
   ```

3. **API Username**: Usually `user@vectara.com` (generic identifier)

### Setting Environment Variables

Store your API credentials securely:

```bash
export DISCOURSE_API_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
export DISCOURSE_BASE_URL="https://discourse.example.com"
```

**Security Note**: Never commit API keys to version control. Use environment variables or a secrets management system.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-forums

crawling:
  crawler_type: discourse

discourse_crawler:
  # Base URL of your Discourse instance
  base_url: "${DISCOURSE_BASE_URL}"

  # API key for authentication
  discourse_api_key: "${DISCOURSE_API_KEY}"

  # Optional: SSL/TLS verification
  verify_ssl: true
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: discourse

discourse_crawler:
  base_url: "${DISCOURSE_BASE_URL}"
  discourse_api_key: "${DISCOURSE_API_KEY}"
  verify_ssl: true

metadata:
  source: discourse
  environment: production
  content_types:
    - topics
    - discussions
    - support
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `base_url` | string | Yes | - | Base URL of Discourse instance (e.g., `https://discourse.example.com`) |
| `discourse_api_key` | string | Yes | - | API key from Discourse admin panel |
| `verify_ssl` | bool | No | `true` | Enable SSL/TLS certificate verification |

## Topics and Posts Indexed

### Topic Information

The crawler indexes Discourse topics with:

- **ID**: Unique topic identifier
- **Title**: Topic title
- **Created**: When topic was created
- **Updated**: When topic was last modified
- **URL**: Direct link to topic in forum
- **Source**: Always "discourse"

### Post Content

Each post within a topic includes:

- **Text**: Full post content (HTML converted to plain text)
- **Title**: Post title (if present)
- **Author**: Username of poster
- **Created**: Post creation timestamp
- **Updated**: Post modification timestamp
- **URL**: Direct link to specific post
- **Source**: Always "discourse"

### Metadata Captured

```
Document ID: topic-{topic_id}
Title: {topic_title}
Metadata:
  - created_at: {YYYY-MM-DD}
  - last_updated: {YYYY-MM-DD}
  - source: discourse
  - url: {discourse_url}/t/{topic_id}

Sections: (One per post)
  1. First post:
     - text: {post_content}
     - created_at: {YYYY-MM-DD}
     - last_updated: {YYYY-MM-DD}
     - poster: {username}
     - poster_name: {display_name}
     - url: {discourse_url}/p/{post_id}

  2. Second post:
     - text: {post_content}
     - created_at: {YYYY-MM-DD}
     - last_updated: {YYYY-MM-DD}
     - poster: {username}
     - poster_name: {display_name}
     - url: {discourse_url}/p/{post_id}
```

## HTML to Text Conversion

The crawler converts Discourse's HTML-formatted post content to plain text:

**Example Conversion**:

```html
<p>Here's my solution:</p>
<pre><code>def hello():
    print("world")</code></pre>
<p>This works great!</p>
```

Converts to:

```
Here's my solution:

def hello():
    print("world")

This works great!
```

This provides:
- Clean, readable content
- Preserved formatting and structure
- Better search relevance
- Efficient indexing

## API Requests and Pagination

### API Endpoints Used

The crawler uses these Discourse API endpoints:

1. **Get Latest Topics**:
   ```
   GET /latest.json
   ```
   Paginated list of latest forum topics

2. **Get Topic Posts**:
   ```
   GET /t/{topic_id}.json
   ```
   Full topic with all posts included

### Pagination

Topics are retrieved in pages:

```
Page 1: /latest.json?page=0
Page 2: /latest.json?page=1
Page 3: /latest.json?page=2
... continues until empty page
```

Each page typically contains 20 topics (Discourse default).

### API Authentication

Requests include credentials in params:

```
GET /latest.json?api_key={api_key}&api_username={username}&page=0
GET /t/{topic_id}.json?api_key={api_key}&api_username={username}
```

## How It Works

### Crawl Process

1. **Fetch Latest Topics**: Retrieves paginated list of all forum topics
   - Starts at page 0
   - Continues until empty page received
   - Collects all topic metadata

2. **For Each Topic**:
   - Fetches full topic data (includes all posts)
   - Creates document with topic metadata
   - Extracts posts with author information
   - Converts HTML to plain text
   - Adds post URLs and timestamps

3. **Index Documents**: Sends each topic and its posts to Vectara
   - One document per topic
   - Multiple sections (one per post)
   - Preserves post author and timing

### Document Structure

Each topic becomes one indexed document:

```
Topic document:
- id: topic-12345
- title: "How do I configure X?"
- metadata:
    created_at: 2024-11-18
    last_updated: 2024-11-20
    source: discourse
    url: https://discourse.example.com/t/how-do-i-configure-x/12345
- sections: [
    {
      text: "I'm trying to configure X but getting error...",
      metadata: {
        created_at: 2024-11-18,
        last_updated: 2024-11-18,
        poster: john_doe,
        poster_name: "John Doe",
        source: discourse,
        url: https://discourse.example.com/p/98765
      }
    },
    {
      text: "Try setting Y to Z...",
      metadata: {
        created_at: 2024-11-18,
        last_updated: 2024-11-18,
        poster: jane_smith,
        poster_name: "Jane Smith",
        source: discourse,
        url: https://discourse.example.com/p/98766
      }
    }
  ]
```

### Rate Limiting

- **Discourse API**: Typically 30 requests per minute (configurable)
- **Crawler behavior**: Respects built-in rate limiting
- **Pagination**: Automatic with page continuation
- **Retry logic**: Built-in error handling and retries

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized` or permission denied

**Solutions**:
1. Verify API key is correct:
   ```bash
   echo $DISCOURSE_API_KEY
   ```
2. Confirm key hasn't been revoked (check admin panel)
3. Verify base URL is correct:
   ```bash
   curl -H "Api-Key: $DISCOURSE_API_KEY" \
     https://your-discourse.com/admin/api/keys
   ```
4. Check key has sufficient permissions (usually requires admin)

### Connection Failed

**Error**: `Failed to connect` or network timeout

**Solutions**:
1. Verify Discourse instance is accessible:
   ```bash
   curl https://your-discourse.com
   ```
2. Check base URL format (should include https://)
3. Verify DNS resolution:
   ```bash
   nslookup your-discourse.com
   ```
4. Check firewall/network rules allow HTTPS traffic
5. Test SSL/TLS if using self-signed certificate:
   ```yaml
   discourse_crawler:
     verify_ssl: false  # Only if necessary
   ```

### No Topics Found

**Error**: Crawler completes but indexes 0 topics

**Solutions**:
1. Verify forum has topics:
   - Access forum directly in browser
   - Check latest topics list isn't empty

2. Verify API key has access:
   ```bash
   curl -H "Api-Key: $DISCOURSE_API_KEY" \
     https://your-discourse.com/latest.json
   ```

3. Check configuration:
   ```yaml
   discourse_crawler:
     base_url: "https://your-discourse.com"  # No trailing slash
     discourse_api_key: "your_key_here"
   ```

4. Review logs for errors:
   ```bash
   docker logs -f vingest
   ```

### SSL/TLS Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Causes and Solutions**:

For **self-signed certificates**:
```yaml
discourse_crawler:
  verify_ssl: false  # Disable verification
```

For **expired/invalid certificates**:
1. Renew certificate on Discourse server
2. Or temporarily disable verification (not recommended for production)

For **corporate/proxy certificates**:
```yaml
discourse_crawler:
  verify_ssl: true  # Use system certificate bundle
```

### Partial Indexing

**Error**: Some topics indexed, others missing

**Possible Causes**:
1. Private topics/categories not accessible with API key
2. Very large topics timing out during fetch
3. Malformed HTML causing parse errors

**Solutions**:
1. Check topic permissions in Discourse admin panel
2. Increase timeout in network configuration
3. Review logs for specific topic failures
4. Verify posts contain valid content

## Performance Tips

### 1. Start with Recent Topics

For large forums, focus on recent activity:

```yaml
# The crawler fetches latest topics first
# Stop after collecting sufficient topics
max_topics: 100  # If implemented
```

Note: Current implementation fetches all topics.

### 2. Schedule Off-Peak Crawls

Run during low-traffic periods:

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/discourse.yaml default
```

### 3. Monitor Large Topics

Topics with hundreds of posts take longer:

```bash
# Watch progress
docker logs -f vingest | grep "Indexed"
```

### 4. Use Reindex Wisely

```yaml
vectara:
  reindex: false  # Avoid unnecessary reindexing
```

### 5. Separate Crawls by Category

If forum is very large, create separate configs:

```yaml
# discourse-support.yaml
# Only crawl support category

# discourse-general.yaml
# General discussion topics
```

## Best Practices

### 1. Secure API Key Storage

```bash
# DO: Use environment variables
export DISCOURSE_API_KEY="..."

# DO NOT: Hard-code in config
discourse_api_key: "key123"  # WRONG!

# DO NOT: Commit to version control
git add config/discourse.yaml  # Contains key - WRONG!
```

### 2. Use Appropriate Update Frequency

```bash
# For frequently updated forums
0 6,12,18 * * * bash run.sh config/discourse.yaml default

# For slower forums
0 */12 * * * bash run.sh config/discourse.yaml default

# For infrequent changes
0 2 * * * bash run.sh config/discourse.yaml default
```

### 3. Include Descriptive Metadata

```yaml
metadata:
  source: discourse
  environment: production
  forum_name: "Community Support"
  forum_url: "https://discourse.example.com"
  sync_frequency: daily
```

### 4. Test with Limited Scope

Start with one forum instance:

```yaml
discourse_crawler:
  base_url: "https://test-forum.example.com"
  discourse_api_key: "${TEST_API_KEY}"
```

Then expand to production.

### 5. Monitor Indexing

```bash
bash run.sh config/discourse.yaml default
# Check for:
# - Topics successfully indexed
# - Post content properly extracted
# - No API authentication errors
# - Reasonable completion time
```

### 6. Handle Multiple Forums

For multiple Discourse instances, create separate configs:

```yaml
# config/discourse-support.yaml
discourse_crawler:
  base_url: "https://support.company.com"
  discourse_api_key: "${SUPPORT_API_KEY}"

# config/discourse-community.yaml
discourse_crawler:
  base_url: "https://community.company.com"
  discourse_api_key: "${COMMUNITY_API_KEY}"
```

Run individually:

```bash
bash run.sh config/discourse-support.yaml default
bash run.sh config/discourse-community.yaml default
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/discourse-crawl.yaml
```

### Set Environment Variables

```bash
export DISCOURSE_BASE_URL="https://discourse.example.com"
export DISCOURSE_API_KEY="your_api_key_here"
```

### Run the Crawler

```bash
# Run with your config
bash run.sh config/discourse-crawl.yaml default

# Monitor logs
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/discourse-crawl.yaml default

# Twice daily
0 2,14 * * * cd /path/to/vectara-ingest && bash run.sh config/discourse-crawl.yaml default

# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/discourse-crawl.yaml default
```

## Complete Examples

### Example 1: Single Community Forum

```yaml
# config/discourse-community.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-community

crawling:
  crawler_type: discourse

discourse_crawler:
  base_url: "${DISCOURSE_BASE_URL}"
  discourse_api_key: "${DISCOURSE_API_KEY}"
  verify_ssl: true

metadata:
  source: discourse
  environment: production
  forum_type: community
```

Run with:
```bash
export DISCOURSE_BASE_URL="https://community.example.com"
export DISCOURSE_API_KEY="key_here"
bash run.sh config/discourse-community.yaml default
```

### Example 2: Company Support Forum

```yaml
# config/discourse-support.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-support
  reindex: false
  verbose: true

crawling:
  crawler_type: discourse

discourse_crawler:
  base_url: "${DISCOURSE_SUPPORT_URL}"
  discourse_api_key: "${DISCOURSE_SUPPORT_KEY}"
  verify_ssl: true

metadata:
  source: discourse
  environment: production
  forum_type: support
  sync_frequency: daily
  content_types:
    - support_articles
    - faqs
    - troubleshooting
```

### Example 3: Product Documentation Forum

```yaml
# config/discourse-docs.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-documentation
  reindex: true

crawling:
  crawler_type: discourse

discourse_crawler:
  base_url: "${DISCOURSE_DOCS_URL}"
  discourse_api_key: "${DISCOURSE_DOCS_KEY}"
  verify_ssl: true

metadata:
  source: discourse
  environment: production
  forum_type: documentation
  sync_frequency: weekly
  content_types:
    - user_guides
    - api_documentation
    - examples
```

### Example 4: Multi-Forum Crawl Script

```bash
# discourse-multi-crawl.sh
#!/bin/bash

# Support forum
export DISCOURSE_BASE_URL="https://support.company.com"
export DISCOURSE_API_KEY="$SUPPORT_API_KEY"
bash run.sh config/discourse-support.yaml default
sleep 120

# Community forum
export DISCOURSE_BASE_URL="https://community.company.com"
export DISCOURSE_API_KEY="$COMMUNITY_API_KEY"
bash run.sh config/discourse-community.yaml default
sleep 120

# Documentation forum
export DISCOURSE_BASE_URL="https://docs.company.com"
export DISCOURSE_API_KEY="$DOCS_API_KEY"
bash run.sh config/discourse-docs.yaml default

echo "All Discourse crawls completed"
```

### Example 5: Production Setup with Error Handling

```yaml
# config/discourse-production.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: discourse-prod-kb
  reindex: false
  verbose: true

crawling:
  crawler_type: discourse

discourse_crawler:
  base_url: "${DISCOURSE_PROD_URL}"
  discourse_api_key: "${DISCOURSE_PROD_KEY}"
  verify_ssl: true

metadata:
  source: discourse
  environment: production
  sync_frequency: daily
  version: "1.0"
  backup_enabled: true
  error_notification: "ops@company.com"
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Discourse API Resources

- [Discourse API Documentation](https://docs.discourse.org/api/)
- [Admin API Keys Setup](https://meta.discourse.org/t/api-keys-in-discourse/96437)
- [API Authentication](https://docs.discourse.org/api/admin/topics)
- [Discourse Installation Guide](https://github.com/discourse/discourse/blob/main/docs/INSTALL.md)
- [Latest Topics Endpoint](https://docs.discourse.org/api/admin/topics)
