# Twitter/X Crawler

The Twitter/X crawler indexes tweets from specified user accounts, extracting engagement metrics, user profile information, and tweet content with optional mention removal.

## Overview

- **Crawler Type**: `twitter`
- **Authentication**: Bearer Token (Twitter/X API v2)
- **API Support**: Twitter API v2
- **Content Types**: Tweets, user profiles, engagement metrics
- **Metadata Capture**: Author, creation date, engagement stats (retweets, replies, likes, quotes)
- **Filtering**: Automatic retweet exclusion, optional mention removal

## Use Cases

- Social media monitoring and analytics
- Tweet-based knowledge bases
- Public sentiment analysis
- Influencer content curation
- Real-time news and updates indexing
- Brand mentions and discussions tracking
- Twitter thread archives

## Getting Started: API Authentication

### Get Your Twitter/X Bearer Token

The Twitter crawler requires a Bearer Token from the Twitter API v2 for authentication. This provides access to recent tweets and user data.

#### Creating a Bearer Token

1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Sign in with your Twitter/X account (create one if needed)
3. Create a new app or select an existing app
4. Navigate to the **Keys and tokens** section
5. Copy your **Bearer Token** (starts with `AAAA` or `AAAAAx...`)
6. Keep this token secure and never share it

#### Bearer Token Requirements

The token needs these minimum permissions:

- **Tweet Read v2**: Access to recent tweets (last 7 days)
  - Read public tweets
  - Search recent tweets
  - Access tweet metrics
  - Best for recent tweet discovery

### Setting Environment Variables

Store your token securely as an environment variable:

```bash
export TWITTER_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAA%..."
```

The crawler will automatically read this from your environment.

**Security Note**: Never commit tokens to version control. Use environment variables or a secrets management system.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-tweets

crawling:
  crawler_type: twitter

twitter_crawler:
  # Bearer token for Twitter API v2
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"

  # List of user handles to crawl (without @ symbol)
  userhandles:
    - "user1"
    - "user2"

  # Number of tweets to fetch per user
  num_tweets: 100

  # Remove mentions from tweet text
  clean_tweets: true
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: twitter

twitter_crawler:
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"

  userhandles:
    - "technewstoday"
    - "industry_expert"
    - "thought_leader"

  # Fetch up to 1000 recent tweets per user
  num_tweets: 1000

  # Clean @mentions from tweet text
  clean_tweets: true

metadata:
  source: twitter
  environment: production
  content_types:
    - tweets
    - user_profiles
    - engagement_data
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `twitter_bearer_token` | string | Yes | - | Twitter API v2 Bearer Token |
| `userhandles` | list | Yes | - | List of Twitter user handles to crawl (without @ symbol) |
| `num_tweets` | int | No | `100` | Number of tweets to fetch per user (max ~1000 depending on API) |
| `clean_tweets` | bool | No | `true` | Remove @mentions from tweet text for cleaner indexing |

## Tweet Data Collection

### Tweets Indexed

The crawler automatically indexes tweets with:

- **Text**: Tweet content (optionally cleaned of mentions)
- **Author**: Tweet author username
- **Created**: Tweet creation timestamp
- **Metrics**: Engagement statistics
- **Language**: Tweet language code
- **Geolocation**: Geographic information if available

### User Profile Information

The crawler captures user profile metadata:

- **Username**: User's Twitter handle
- **Account Created**: When the account was created
- **Followers**: Current follower count
- **Following**: Number of accounts followed
- **Tweet Count**: Total tweets from the account
- **Description**: User bio/description
- **Location**: User's stated location
- **Verified**: Verification status

### Engagement Metrics

Each indexed tweet includes:

- **Retweet Count**: Number of retweets
- **Reply Count**: Number of replies
- **Like Count**: Number of likes
- **Quote Count**: Number of quote tweets
- **Language**: Detected language of the tweet

### Tweet Filtering

The crawler applies automatic filtering:

- **Excludes Retweets**: Only original tweets and quoted tweets
- **Removes Mentions**: Optionally strips @mentions from text
- **Recent Tweets**: Accesses tweets from the last 7 days (Twitter API limitation)

## Tweet Text Cleaning

### Mention Removal

When `clean_tweets: true`, the crawler removes @mentions:

```
Original: "@user1 Check out this article @user2 just shared"
Cleaned: "Check out this article just shared"
```

This improves:
- Relevance of indexed content
- Reduced noise in search results
- Better semantic understanding

### Enabling/Disabling Cleaning

```yaml
# Enable cleaning (default)
twitter_crawler:
  clean_tweets: true

# Disable to preserve original mentions
twitter_crawler:
  clean_tweets: false
```

## How It Works

### Crawl Process

1. **Authentication**: Initializes Twitter API v2 client with Bearer Token
2. **User Lookup**: Retrieves user information for each specified handle
3. **Search Tweets**: Searches recent tweets for each user (excluding retweets)
4. **Fetch Metrics**: Retrieves engagement metrics for each tweet
5. **Clean Text**: Optionally removes @mentions from tweet content
6. **Index Documents**: Sends grouped tweets to Vectara with user metadata

### API Requests

The crawler makes these API calls:

```
GET /2/users/by/username/{username}  (Get user info)
GET /2/tweets/search/recent           (Search user's tweets)
```

Each request includes:
- `query`: User handle with `-is:retweet` filter
- `tweet_fields`: Requested fields (public_metrics, author_id, lang, geo, entities)
- `max_results`: Up to 100 tweets per request with pagination

### Rate Limiting

Twitter API v2 rate limits:
- **Recent tweets search**: 450 requests per 15 minutes (per user endpoint context)
- **User lookup**: 300 requests per 15 minutes

The crawler respects these limits through built-in handling.

### Document Structure

Each user's tweets are indexed as a single document:

```
Document ID: tweets-{username}
Title: top {num_tweets} tweets of {username}
Metadata:
  - username
  - account_created_at
  - followers_count
  - following_count
  - tweet_count
  - description
  - location
  - verified
  - url
  - source

Sections: (One per tweet)
  - text: {cleaned tweet content}
  - author: {username}
  - created_at: {timestamp}
  - retweet_count: {count}
  - reply_count: {count}
  - like_count: {count}
  - quote_count: {count}
  - lang: {language_code}
```

## Pagination and Tweet Limits

### Tweet Fetching

The crawler handles pagination automatically:

- **Max Results Per Request**: 50 tweets (Twitter API default)
- **Pagination**: Uses `next_token` to fetch subsequent pages
- **Total Per User**: Limited by `num_tweets` configuration
- **API Constraint**: Recent tweets endpoint (last 7 days only)

### Configuration Examples

```yaml
# Fetch 100 tweets per user (default)
num_tweets: 100

# Fetch 500 tweets per user
num_tweets: 500

# Fetch max available (typically ~1000)
num_tweets: 1000
```

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized` or `Forbidden`

**Solutions**:
1. Verify Bearer Token is correct:
   ```bash
   echo $TWITTER_BEARER_TOKEN
   ```
2. Check token hasn't expired (regenerate if needed)
3. Verify token is set in environment:
   ```bash
   echo "Token: $TWITTER_BEARER_TOKEN"
   ```
4. Confirm token format (should start with `AAAA...`)

### User Not Found

**Error**: `404 Not Found` for user

**Solutions**:
1. Verify user handle spelling (case-insensitive)
   ```bash
   # Correct: twitter.com/username
   userhandles:
     - "username"
   ```
2. Ensure user handle doesn't include @ symbol:
   ```yaml
   # Correct
   userhandles: ["elon"]

   # Incorrect
   userhandles: ["@elon"]
   ```
3. Check account exists and is not suspended
4. Verify account is public or accessible with token permissions

### Rate Limit Exceeded

**Error**: `429 Too Many Requests`

**Solutions**:
1. Wait for rate limit window to reset (typically 15 minutes)
2. Reduce number of users being crawled:
   ```yaml
   userhandles:
     - "user1"
     - "user2"  # Instead of 50+ users
   ```
3. Reduce `num_tweets` per user:
   ```yaml
   num_tweets: 100  # Instead of 1000
   ```
4. Split crawls across multiple runs:
   ```yaml
   # twitter-batch1.yaml
   userhandles: ["user1", "user2", "user3"]

   # twitter-batch2.yaml
   userhandles: ["user4", "user5", "user6"]
   ```

### No Tweets Found

**Error**: Empty results for a user

**Solutions**:
1. Verify user has public tweets (check @mentions)
2. Check if tweets exist within last 7 days (API limitation)
3. Verify user handle is correct
4. Test API access manually:
   ```bash
   curl -H "Authorization: Bearer $TWITTER_BEARER_TOKEN" \
     "https://api.twitter.com/2/tweets/search/recent?query=from:username"
   ```

### Tweets Not Indexed

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Check configuration for typos
2. Verify tweet text isn't being fully cleaned away
3. Review logs for API errors
4. Test with a well-known public account (e.g., @twitter)

## Performance Tips

### 1. Batch Users Efficiently

Instead of crawling many users in one run:

```yaml
# Inefficient: Too many users at once
userhandles:
  - "user1"
  - "user2"
  # ... 50 more users

# Better: Focused list
userhandles:
  - "active_user1"
  - "active_user2"
  - "active_user3"
```

### 2. Optimize Tweet Volume

Adjust `num_tweets` based on needs:

```yaml
# Light crawl: Recent tweets only
num_tweets: 50

# Standard crawl
num_tweets: 100

# Comprehensive crawl
num_tweets: 500
```

### 3. Separate Crawl Configurations

Create different configs for different purposes:

```yaml
# twitter-tech.yaml
userhandles:
  - "techcrunch"
  - "verge"
num_tweets: 100

# twitter-news.yaml
userhandles:
  - "bbc"
  - "reuters"
num_tweets: 100
```

### 4. Schedule Off-Peak Runs

Run crawls during off-hours to avoid rate limits:

```bash
# Run daily at 3 AM
0 3 * * * cd /path/to/vectara-ingest && bash run.sh config/twitter.yaml default
```

### 5. Consider Tweet Language

Filter for specific languages during search if needed:

```yaml
# Current implementation fetches all languages
# Language data is captured in metadata for filtering
```

## Best Practices

### 1. Always Use Environment Variables for Tokens

```bash
# DO: Use environment variables
export TWITTER_BEARER_TOKEN="AAAA..."

# DO NOT: Hard-code in config
twitter_bearer_token: "AAAA..."  # WRONG!

# DO NOT: Commit to version control
git add config/twitter.yaml  # Contains token - WRONG!
```

### 2. Use Descriptive User Lists

```yaml
# Clear and organized
userhandles:
  - "official_account"
  - "news_source"
  - "industry_leader"
```

### 3. Include Metadata

```yaml
metadata:
  source: twitter
  environment: production
  content_types:
    - tweets
    - user_profiles
  sync_frequency: "daily"
  use_case: "news_monitoring"
```

### 4. Test Before Production

Start with a single well-known account:

```yaml
userhandles: ["twitter"]  # Official Twitter account
num_tweets: 50
```

Then expand:

```yaml
userhandles: ["twitter", "user2", "user3"]
num_tweets: 100
```

### 5. Monitor Indexing

Check logs during execution:

```bash
bash run.sh config/twitter.yaml default
# Monitor for:
# - Authentication errors
# - Successful tweet indexing
# - User profile data capture
```

### 6. Clean Tweet Configuration

Enable cleaning for better search results:

```yaml
# Recommended: Remove noise from mentions
clean_tweets: true

# Alternative: Preserve original content
clean_tweets: false
```

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/twitter-crawl.yaml
```

### Set Environment Variables

```bash
export TWITTER_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAA%..."
```

### Run the Crawler

```bash
# Run with your config
bash run.sh config/twitter-crawl.yaml default

# Monitor logs
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 3 AM
0 3 * * * cd /path/to/vectara-ingest && bash run.sh config/twitter-crawl.yaml default

# Twice daily
0 3,15 * * * cd /path/to/vectara-ingest && bash run.sh config/twitter-crawl.yaml default

# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/twitter-crawl.yaml default
```

## Complete Examples

### Example 1: Single User Basic Crawl

```yaml
# config/twitter-basic.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-single-user

crawling:
  crawler_type: twitter

twitter_crawler:
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"
  userhandles:
    - "username"
  num_tweets: 100
  clean_tweets: true

metadata:
  source: twitter
  environment: production
```

Run with:
```bash
export TWITTER_BEARER_TOKEN="AAAA..."
bash run.sh config/twitter-basic.yaml default
```

### Example 2: Multiple Tech Accounts

```yaml
# config/twitter-tech.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-tech-news
  reindex: false
  verbose: true

crawling:
  crawler_type: twitter

twitter_crawler:
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"

  userhandles:
    - "techcrunch"
    - "verge"
    - "ArsTechnica"
    - "theinformation"

  num_tweets: 200
  clean_tweets: true

metadata:
  source: twitter
  environment: production
  content_types:
    - tech_news
    - industry_updates
  sync_frequency: daily
```

### Example 3: News and Media Sources

```yaml
# config/twitter-news.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-news-updates
  reindex: false

crawling:
  crawler_type: twitter

twitter_crawler:
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"

  userhandles:
    - "reuters"
    - "BBCNews"
    - "AP"
    - "NPR"
    - "WSJ"

  num_tweets: 150
  clean_tweets: true

metadata:
  source: twitter
  content_types:
    - news
    - breaking_updates
  environment: production
```

### Example 4: Influencer and Expert Tweets

```yaml
# config/twitter-influencers.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: twitter-influencer-insights
  reindex: false

crawling:
  crawler_type: twitter

twitter_crawler:
  twitter_bearer_token: "${TWITTER_BEARER_TOKEN}"

  userhandles:
    - "elonmusk"
    - "timcook"
    - "satyanadella"
    - "jack"

  num_tweets: 100
  clean_tweets: false  # Keep mentions for context

metadata:
  source: twitter
  content_types:
    - executive_insights
    - industry_perspectives
  environment: production
```

### Example 5: Batch Processing Multiple Crawls

```bash
# twitter-batch-crawl.sh
#!/bin/bash

export TWITTER_BEARER_TOKEN="AAAA..."

# Crawl different groups of users
bash run.sh config/twitter-tech.yaml default
sleep 60  # Wait between crawls

bash run.sh config/twitter-news.yaml default
sleep 60

bash run.sh config/twitter-influencers.yaml default

echo "All Twitter crawls completed"
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Twitter API Resources

- [Twitter API v2 Documentation](https://developer.twitter.com/en/docs/twitter-api)
- [Tweet Search Documentation](https://developer.twitter.com/en/docs/twitter-api/tweets/search-tweets/integrate/build-a-query)
- [API Authentication](https://developer.twitter.com/en/docs/authentication/oauth-2-0)
- [Rate Limiting](https://developer.twitter.com/en/docs/projects/overview#rate-limits)
- [Tweepy Documentation](https://docs.tweepy.org/en/stable/)
