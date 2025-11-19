# Slack Crawler

The Slack crawler indexes messages from your Slack workspace, including threaded conversations, user metadata, and channel organization. It supports rate limit handling, parallel processing with Ray, and automatic user ID resolution.

## Overview

- **Crawler Type**: `slack`
- **Authentication**: User token (not bot token)
- **Message Retrieval**: Full pagination support with cursor-based navigation
- **Thread Support**: Automatic retrieval and indexing of threaded replies
- **User Resolution**: Automatic conversion of user IDs to display names
- **Rate Limiting**: Automatic retry handling for 429 responses
- **Channel Filtering**: Skip specific channels from crawling
- **Parallel Processing**: Ray workers supported for large workspaces

## Use Cases

- Build searchable knowledge bases from Slack conversations
- Archive important team discussions and decisions
- Create searchable databases of technical discussions
- Index team documentation shared in Slack
- Analyze conversation history across channels
- Preserve institutional knowledge from Slack archives

## Getting Started: Creating a Slack App and User Token

### Step 1: Create a Slack App

1. Go to [Slack API: Applications](https://api.slack.com/apps)
2. Click "Create New App"
3. Choose "From scratch"
4. Enter an app name (e.g., "Vectara Ingest")
5. Select your workspace
6. Click "Create App"

### Step 2: Configure OAuth Scopes

1. In your app's settings, click "OAuth & Permissions" in the left sidebar
2. Scroll to "Scopes" section
3. Under "User Token Scopes", add these required scopes:
   - `users:read` - Read user information
   - `channels:read` - Read public channel information
   - `groups:read` - Read private channel (group) information
   - `im:read` - Read direct messages
   - `chat:read` - Read message content
   - `users:read.email` - Read user email addresses (optional)

Your final scopes should look like:
```
channels:read
chat:read
groups:read
im:read
users:read
```

### Step 3: Generate User Token

1. Go to "OAuth & Permissions" section
2. Scroll to "User Token Scopes" and verify your scopes are set
3. Click "Generate Token and URLs" button
4. Click "Allow" when prompted by Slack
5. Copy the **User OAuth Token** (starts with `xoxp-`)

**Important**: This is your `SLACK_USER_TOKEN`. Do NOT use the bot token.

### Step 4: Set Environment Variable

Store your token securely:

```bash
export SLACK_USER_TOKEN="xoxp-your-token-here"
```

Or add to `.env` file:
```
SLACK_USER_TOKEN=xoxp-your-token-here
```

### Step 5: Test Your Token

Verify your token works:

```bash
curl -H "Authorization: Bearer xoxp-your-token" https://slack.com/api/auth.test
```

You should see a response with your user info if successful.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-messages

crawling:
  crawler_type: slack

slack_crawler:
  # User token (xoxp-...), loaded from SLACK_USER_TOKEN environment variable
  slack_user_token: ${SLACK_USER_TOKEN}

  # Number of days to look back
  days_past: 30

  # Your workspace URL (e.g., https://yourcompany.slack.com)
  workspace_url: "https://vectara.slack.com"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: slack

slack_crawler:
  # User token from environment
  slack_user_token: ${SLACK_USER_TOKEN}

  # How far back to retrieve messages (days)
  days_past: 90

  # Channels to skip (won't be indexed)
  channels_to_skip:
    - random
    - general
    - off-topic

  # Number of retries on API errors
  retries: 5

  # Your workspace URL
  workspace_url: "https://mycompany.slack.com"

  # Parallel processing with Ray
  # 0 = sequential processing (default)
  # -1 = use all CPU cores
  # N = use N workers
  ray_workers: 4

metadata:
  source: slack
  environment: production
  workspace: engineering-team
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `slack_user_token` | string | Yes | - | Slack user token (starts with `xoxp-`, recommend using `${SLACK_USER_TOKEN}` env var) |
| `days_past` | int | No | None | Number of days to look back for messages (None = all history) |
| `channels_to_skip` | list | No | `[]` | Channel names to exclude from crawling |
| `retries` | int | No | `5` | Number of retries on API errors |
| `workspace_url` | string | No | `"https://vectara.slack.com"` | Base URL of your Slack workspace |
| `ray_workers` | int | No | `0` | Parallel workers: 0=sequential, -1=all cores, N=N workers |

## How It Works

### Message Retrieval Flow

1. **Authentication**: Connects to Slack using the user token
2. **User Resolution**: Fetches all workspace users and creates user ID → display name mapping
3. **Channel Discovery**: Lists all channels the user has access to
4. **Channel Filtering**: Excludes channels in `channels_to_skip`
5. **Message Retrieval**: For each channel:
   - Fetches messages using cursor-based pagination
   - Respects `days_past` filter if configured
   - Handles 429 rate limit errors automatically
6. **Thread Processing**: For messages with replies:
   - Fetches all threaded replies
   - Replaces user IDs with display names
   - Associates replies with parent message
7. **Text Processing**:
   - Cleans up ampersands (`&amp;` → `&`)
   - Removes duplicate URLs
   - Preserves message formatting
8. **Document Creation**: Constructs indexed documents with:
   - Parent message text
   - All threaded replies as sections
   - Rich metadata (author, channel, timestamps)
9. **Indexing**: Sends documents to Vectara
10. **Parallel Processing** (optional): Distributes message processing across Ray workers

### Rate Limiting Handling

When Slack returns a 429 (Too Many Requests) response:
1. Crawler reads the `Retry-After` header
2. Waits for the specified seconds + 1
3. Retries the request
4. Logs the backoff event

This ensures the crawler respects Slack's rate limits without failing.

## Metadata Captured

Each indexed message includes:

- **Channel**: Channel name where message was posted
- **Author**: User who posted the message (resolved from user ID)
- **Message Time**: Timestamp when message was posted
- **URL**: Direct link to message in Slack
- **Latest Reply Time** (if threaded): Timestamp of most recent reply
- **Number of Users Involved** (if threaded): Count of unique repliers
- **Source**: Always "slack"
- **Replier** (for replies): User who posted the reply
- **Reply Time** (for replies): Timestamp of reply

### Example Metadata

```yaml
channel: engineering
author: john.doe
message_time: "2024-10-15 14:32"
url: "https://vectara.slack.com/archives/C01234567/p1234567890"
latest_reply_time: "2024-10-15 16:45"
no_of_users_involved: 3
source: slack
```

## Public vs Private Channels

### Public Channels

User token can access public channels by default. All messages are indexed if the user has joined the channel.

### Private Channels

User token can only access private channels (groups) that:
1. The user is a member of
2. The token has `groups:read` scope

To index a private channel, add the bot/user account to that channel first.

### Direct Messages

With `im:read` scope, the crawler can access:
- Direct messages from users you've messaged
- Group DMs you're a member of

Note: Private channels and DMs are only visible to users with access.

## Thread Handling

### How Threads Are Indexed

Messages with threaded replies are indexed as single documents with multiple sections:

```yaml
Document:
  id: vectara_C12345_1234567890
  title: "john.doe@engineering - 2024-10-15"
  metadata:
    channel: engineering
    author: john.doe
  sections:
    - text: "Here's the main message"
    - text: "First reply here"
      metadata:
        replier: jane.smith
        reply_time: "2024-10-15 14:35"
    - text: "Second reply here"
      metadata:
        replier: bob.jones
        reply_time: "2024-10-15 14:40"
```

### Benefits of Thread Indexing

- Full conversation context is preserved
- Threads are searchable as complete conversations
- Individual replies are indexed as sections
- Metadata tracks individual contributors

### Thread Metadata

Each threaded reply includes:
- `replier` - Person who posted the reply
- `reply_time` - When the reply was posted
- Parent message metadata (channel, source, URL)

## Rate Limiting and Error Handling

### Automatic Rate Limit Handling

The Slack API enforces rate limits:
- **Standard rate limits**: Typically 1 request/second
- **Tier 3 limits**: Up to 60 requests/minute for some endpoints

The crawler automatically handles 429 errors:

```python
if status_code == 429:
    retry_after = int(Retry-After header) + 1
    sleep(retry_after)
    retry_request()
```

### Retry Configuration

```yaml
slack_crawler:
  # Number of retries on API errors (default: 5)
  retries: 5
```

Each API call will retry up to this many times before giving up.

### Handling Incomplete Requests

If a network error occurs (IncompleteRead):
1. Logs the error
2. Waits 30 seconds
3. Retries the request

## Performance with Large Workspaces

### Large Workspace Optimization

For workspaces with 1000+ channels or millions of messages:

#### 1. Use Parallel Processing

```yaml
slack_crawler:
  ray_workers: 4  # Process 4 messages in parallel
```

Benefits:
- Process multiple channels simultaneously
- Reduces total crawl time significantly
- Better CPU utilization

#### 2. Filter by Time

```yaml
slack_crawler:
  days_past: 30  # Only last 30 days instead of all history
```

This dramatically reduces messages to process.

#### 3. Skip Unnecessary Channels

```yaml
slack_crawler:
  channels_to_skip:
    - random
    - general
    - social
    - announcements
    - archive-*
```

Reduces processing load by focusing on important channels.

#### 4. Run During Off-Peak Hours

```bash
# Run daily at 2 AM
0 2 * * * cd /path && bash run.sh config/slack.yaml default
```

#### 5. Batch Large Workspaces

For very large workspaces, create separate configs:

```yaml
# config/slack-engineering.yaml
slack_crawler:
  channels_to_skip: [random, general]
  ray_workers: 4

# config/slack-marketing.yaml
slack_crawler:
  channels_to_skip: [engineering, random, general]
  ray_workers: 4
```

Run them sequentially or on different schedules.

#### 6. Monitor Memory Usage

Large crawls with many Ray workers consume memory. Monitor system:

```bash
watch -n 1 'free -h'  # Watch memory usage
```

Reduce `ray_workers` if memory becomes constrained.

### Performance Benchmarks

Approximate performance on a standard machine:

- **Small workspace** (< 100 channels, < 100k messages): 5-15 minutes
- **Medium workspace** (100-500 channels): 30-90 minutes
- **Large workspace** (500+ channels): 2-8 hours

With `ray_workers: 4`, expect 3-4x speedup.

## User ID Resolution

The crawler automatically converts Slack user IDs to display names.

### How It Works

1. Fetches all users in workspace with `users_list()` API
2. Creates mapping: `user_id` → `display_name_normalized`
3. Replaces user IDs in message text: `<@U123ABC>` → `@john.doe`
4. Uses display name for author metadata

### User ID Format

Slack represents users in two ways:

```
# In message text (converted during crawl)
<@U123ABC45678>   →   @john.doe

# In API responses
user: "U123ABC45678"   →   display_name_normalized: "john.doe"
```

### Handling Deleted Users

If a user is deleted from Slack:
- User ID won't appear in `users_list()` response
- Messages from deleted users default to "bot"
- Their replies still appear but may show as "bot"

This is acceptable as the message content is preserved.

## Channel Filtering

### Skip Channels by Name

```yaml
slack_crawler:
  channels_to_skip:
    - random
    - general
    - off-topic
    - archive-2023
```

Useful for skipping:
- High-volume channels (random, general)
- Archive channels
- Channels with lots of noise
- Channels you don't want indexed

### Access Control

The crawler only indexes channels where the user has access. Channels the user hasn't joined won't be listed by the API.

To crawl a channel:
1. User must be a member
2. User must have `channels:read` (for public) or `groups:read` (for private)
3. Don't add it to `channels_to_skip`

## Parallel Processing with Ray

### Enabling Ray Workers

```yaml
slack_crawler:
  ray_workers: 0   # Sequential (default)
  ray_workers: 4   # 4 parallel workers
  ray_workers: -1  # Use all CPU cores
```

### How It Works

1. Initializes Ray cluster with N workers
2. Each worker gets a copy of user information (via `ray.put()`)
3. Messages are distributed to workers
4. Each worker processes message in parallel
5. Results are aggregated and indexed

### Memory Considerations

Each Ray worker:
- Holds a copy of user data (small)
- Maintains indexer connection
- Processes one message at a time

For large workspaces, monitor memory:
```bash
# Check memory usage
ps aux | grep ray
```

Reduce workers if memory becomes constrained:
```yaml
slack_crawler:
  ray_workers: 2  # Use 2 instead of 4
```

### When to Use Ray

**Use Ray when**:
- Processing 1000+ messages
- 4+ CPU cores available
- Sufficient memory (> 4GB)
- Multiple channels to process

**Don't use Ray when**:
- Small workspace (< 100 messages)
- Limited system resources
- Single-channel crawl
- Testing/debugging

## Private vs Public Channel Access

### Access Levels by Scope

Your token's scopes determine what channels you can access:

| Scope | Channel Type | Notes |
|-------|--------------|-------|
| `channels:read` | Public channels | Access all public channels you've joined |
| `groups:read` | Private channels | Access private channels you're a member of |
| `im:read` | Direct messages | Access DMs you've participated in |

### Slack Token Types

| Token Type | Prefix | Channels | Limitations |
|-----------|--------|----------|-------------|
| **User Token** | `xoxp-` | All user has access to | Limited to user's permissions |
| **Bot Token** | `xoxb-` | Limited to channels bot is in | Must invite bot to channels |

**Use user token** for maximum coverage.

### Security Considerations

When using a user token:
- It grants access to all messages the user can see
- Be careful with token distribution
- Rotate tokens periodically
- Store securely (use environment variables)

Never commit tokens to version control.

## Supported Message Types

The crawler indexes:

- **Regular messages**: Text-only messages
- **Messages with attachments**: Bot messages with file attachments
- **Threaded replies**: Full conversation context
- **Edited messages**: Latest version of edited messages
- **Messages with URLs**: Links preserved and de-duplicated

The crawler skips:
- **Empty messages**: No text and no attachments
- **File sharing**: Direct file uploads (metadata only)
- **Reactions**: Emoji reactions not indexed
- **Message edits**: Only latest version indexed

## Troubleshooting

### Authentication Failed

**Error**: `Invalid token` or `Unauthorized`

**Solutions**:
1. Verify token starts with `xoxp-` (user token, not `xoxb-` bot token)
2. Check token hasn't expired:
   ```bash
   curl -H "Authorization: Bearer $SLACK_USER_TOKEN" https://slack.com/api/auth.test
   ```
3. Verify token in environment:
   ```bash
   echo $SLACK_USER_TOKEN
   ```
4. Regenerate token in Slack app settings if expired

### No Channels Found

**Error**: Crawler runs but finds 0 channels

**Solutions**:
1. Verify user is member of channels:
   - Go to Slack workspace
   - Check user is in channels to crawl
2. Verify scopes are correct:
   - `channels:read` for public channels
   - `groups:read` for private channels
3. Check token has correct scopes:
   ```bash
   curl -H "Authorization: Bearer $SLACK_USER_TOKEN" \
     https://slack.com/api/oauth.v2.access
   ```
4. User may not have permission to list all channels

### No Messages Retrieved

**Error**: Channels found but no messages indexed

**Solutions**:
1. Check `days_past` filter:
   - If `days_past: 1`, only today's messages included
   - Try `days_past: 30` to capture more history
2. Verify channels have messages:
   - Go to channel in Slack
   - Check message count
3. Check user permissions in channel
4. Look for rate limiting errors in logs
5. Verify workspace URL matches your Slack domain

### Rate Limit Errors

**Error**: Multiple `429 Too Many Requests` responses

**Solutions**:
1. Reduce `ray_workers`:
   ```yaml
   slack_crawler:
     ray_workers: 2  # Instead of 4
   ```
2. Increase retries:
   ```yaml
   slack_crawler:
     retries: 10
   ```
3. Run during off-peak hours
4. Break crawl into smaller batches (per-channel configs)

### Memory Issues

**Error**: `Out of memory` or process killed

**Solutions**:
1. Disable Ray processing:
   ```yaml
   slack_crawler:
     ray_workers: 0
   ```
2. Reduce `days_past`:
   ```yaml
   slack_crawler:
     days_past: 7  # Smaller time window
   ```
3. Skip high-volume channels:
   ```yaml
   slack_crawler:
     channels_to_skip: [random, general]
   ```
4. Increase system memory or reduce crawler load

### SSL Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:
1. For development/testing with self-signed certs:
   ```bash
   export SSL_NO_VERIFY=true
   bash run.sh config/slack.yaml default
   ```
2. For production, ensure CA certificates are up to date:
   ```bash
   pip install --upgrade certifi
   ```

### Incomplete Message Content

**Error**: Some messages appear empty or truncated

**Solutions**:
1. Check message in Slack UI (might genuinely be empty)
2. Look for errors in logs about specific messages
3. Verify user has permission to view message
4. Try crawling that specific channel separately
5. Check for unusual message formats (embeds-only, deleted content)

## Best Practices

### 1. Use a Dedicated Service Account

Create a separate Slack user for crawling:
1. Create new user in workspace
2. Add to channels to index
3. Create app and generate token for this user
4. Benefits:
   - Easy to disable/revoke
   - Tracks all crawl activity
   - Doesn't tie crawler to personal user account

### 2. Start with Time Filtering

```yaml
slack_crawler:
  days_past: 7  # Start with one week
```

Test before expanding to full history.

### 3. Skip Noise Channels

```yaml
slack_crawler:
  channels_to_skip:
    - random
    - general
    - off-topic
    - announcements
    - social
```

Focus on high-value channels.

### 4. Use Descriptive Workspace URL

```yaml
slack_crawler:
  workspace_url: "https://mycompany.slack.com"
```

Not the default. This ensures message links work correctly.

### 5. Enable Ray for Large Workspaces

```yaml
slack_crawler:
  ray_workers: 4  # Significant speedup for large crawls
```

But monitor memory usage.

### 6. Add Meaningful Metadata

```yaml
metadata:
  source: slack
  workspace: engineering-team
  environment: production
  sync_frequency: daily
```

Helps organize results in Vectara.

### 7. Schedule Regular Syncs

```bash
# Daily crawl at 2 AM
0 2 * * * cd /path && bash run.sh config/slack.yaml default
```

Keeps Vectara index in sync with Slack.

### 8. Monitor Crawl Progress

Enable verbose logging:

```yaml
vectara:
  verbose: true
```

Watch logs during crawl:
```bash
docker logs -f vingest
```

### 9. Test with Subset First

Create separate config for testing:
```yaml
# config/slack-test.yaml
slack_crawler:
  channels_to_skip: [random]  # Only index non-random
  days_past: 1                # Just today
  ray_workers: 0              # Sequential for easier debugging
```

Then expand to production config.

### 10. Document Your Setup

Create a runbook:

```markdown
# Slack Crawler Setup

## Token
- Workspace: mycompany.slack.com
- User: slack-crawler (service account)
- Scopes: channels:read, chat:read, groups:read, users:read

## Channels
- Indexed: engineering, product, design, architecture
- Skipped: random, general, off-topic

## Schedule
- Daily at 2 AM UTC
- Syncs last 30 days of messages

## Files
- Config: config/slack-prod.yaml
- Logs: logs/slack-crawl.log
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/slack-messages.yaml
```

Copy one of the examples below and customize.

### Set Environment Variable

```bash
export SLACK_USER_TOKEN="xoxp-your-token-here"
```

Or add to `.env`:
```
SLACK_USER_TOKEN=xoxp-your-token-here
```

### Run the Crawler

```bash
# Run the crawler
bash run.sh config/slack-messages.yaml default

# Monitor progress
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/slack-messages.yaml default

# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/slack-messages.yaml default
```

Or use GitHub Actions, Jenkins, or other schedulers.

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide
- [Slack API Documentation](https://api.slack.com/) - Official Slack API docs
- [OAuth Scopes](https://api.slack.com/scopes) - Available Slack scopes

## Complete Examples

### Example 1: Simple Daily Sync

```yaml
# config/slack-daily.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-messages

crawling:
  crawler_type: slack

slack_crawler:
  slack_user_token: ${SLACK_USER_TOKEN}
  days_past: 1
  workspace_url: "https://vectara.slack.com"

metadata:
  source: slack
  frequency: daily
```

Save and run:
```bash
bash run.sh config/slack-daily.yaml default
```

### Example 2: Weekly Full Sync with Channel Filtering

```yaml
# config/slack-weekly.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-knowledge-base
  reindex: false

crawling:
  crawler_type: slack

slack_crawler:
  slack_user_token: ${SLACK_USER_TOKEN}
  days_past: 7
  channels_to_skip:
    - random
    - general
    - off-topic
  retries: 5
  workspace_url: "https://vectara.slack.com"

metadata:
  source: slack
  environment: production
  frequency: weekly
```

### Example 3: Large Workspace with Parallel Processing

```yaml
# config/slack-production.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-prod-index
  reindex: false
  verbose: true

crawling:
  crawler_type: slack

slack_crawler:
  slack_user_token: ${SLACK_USER_TOKEN}
  days_past: 30
  channels_to_skip:
    - random
    - general
    - off-topic
    - archived
    - social
  retries: 5
  workspace_url: "https://mycompany.slack.com"
  ray_workers: 4

metadata:
  source: slack
  workspace: engineering
  environment: production
  sync_frequency: daily
  content_types:
    - messages
    - threads
    - user_discussions
```

Run with:
```bash
export SLACK_USER_TOKEN="xoxp-..."
bash run.sh config/slack-production.yaml default
```

### Example 4: Multiple Workspaces

For organizations with multiple Slack workspaces, create separate configs:

```yaml
# config/slack-workspace1.yaml
slack_crawler:
  slack_user_token: ${SLACK_WS1_TOKEN}
  workspace_url: "https://workspace1.slack.com"

# config/slack-workspace2.yaml
slack_crawler:
  slack_user_token: ${SLACK_WS2_TOKEN}
  workspace_url: "https://workspace2.slack.com"
```

Run sequentially:
```bash
bash run.sh config/slack-workspace1.yaml default
bash run.sh config/slack-workspace2.yaml default
```

### Example 5: High-Volume Engineering Channel

```yaml
# config/slack-engineering.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: slack-engineering
  reindex: false

crawling:
  crawler_type: slack

slack_crawler:
  slack_user_token: ${SLACK_USER_TOKEN}
  days_past: 90
  channels_to_skip:
    - random
    - general
    - off-topic
    - marketing-*
    - sales-*
  retries: 5
  workspace_url: "https://vectara.slack.com"
  ray_workers: 4

metadata:
  team: engineering
  source: slack
  environment: production
```

## API Reference

### Slack API Endpoints Used

The crawler uses these Slack Web API methods:

| Method | Purpose | Scopes |
|--------|---------|--------|
| `auth.test` | Verify token validity | (any) |
| `users.list` | Get all users | `users:read` |
| `conversations.list` | Get all channels | `channels:read`, `groups:read` |
| `conversations.history` | Get messages | `channels:read`, `chat:read` |
| `conversations.replies` | Get threaded replies | `channels:read`, `chat:read` |

### Rate Limits

Slack API enforces tier-based rate limiting:

- **Tier 1 (special)**: 180 requests/minute
- **Tier 2 (high)**: 60 requests/minute
- **Tier 3 (normal)**: 20 requests/minute

Different methods may use different tiers. The crawler handles automatic backoff.

### Resources

- [Slack API Reference](https://api.slack.com/methods)
- [Rate Limiting](https://api.slack.com/apis/rate-limits)
- [OAuth Scopes](https://api.slack.com/scopes)
- [Token Types](https://api.slack.com/authentication/token-types)
- [Conversations API](https://api.slack.com/methods?filter=conversations)

## Limitations

### Current Limitations

- **File content**: Attached files are not indexed (metadata only)
- **Rich formatting**: Bold, italic, code formatting lost (plain text only)
- **Custom emojis**: Not indexed
- **Reactions**: Emoji reactions not captured
- **Shared channels**: May have access restrictions

### Not Supported

- Archived workspaces (read-only)
- Crawling messages before token creation date
- Real-time sync (scheduled crawls only)
- Slack Connect channels (cross-workspace)

## FAQ

### Q: Can I use a bot token instead of user token?

A: No, bot tokens have more limited access. User tokens (`xoxp-`) are required for full workspace crawling.

### Q: What if I delete a message after it's indexed?

A: The message remains in your Vectara index. To remove it, you would need to manually delete from Vectara corpus.

### Q: Can I index Slack Connect channels?

A: Currently not fully supported. Shared channels may have limitations.

### Q: How often should I re-crawl?

A: Depends on message volume:
- Active team: Daily or multiple times daily
- Moderate: Every 2-3 days
- Light: Weekly

### Q: What happens with thread-only messages?

A: Threads are indexed as sections within the parent message, creating full conversation context.

### Q: Can I export my indexed messages?

A: Yes, through the Vectara API. See Vectara documentation for export formats.

### Q: How long is my token valid?

A: User tokens don't expire. Revoke in Slack app settings. Bot tokens expire after 12 hours if using refresh tokens.

### Q: Can I crawl private channels?

A: Yes, if the user is a member and has `groups:read` scope.

### Q: What if my workspace is very large (10,000+ messages)?

A: Use these optimization strategies:
1. Enable `ray_workers: 4` for parallel processing
2. Filter by `days_past: 30` to reduce scope
3. Skip high-volume channels in `channels_to_skip`
4. Run during off-peak hours
5. Consider separate crawls for different teams

### Q: Does crawling consume my Slack API quota?

A: Yes, each API call counts against rate limits. Large crawls may temporarily hit rate limits, but the crawler handles automatic backoff.

## Support

For issues with:

- **Slack API**: Check [Slack API documentation](https://api.slack.com/)
- **Vectara integration**: See [Vectara documentation](https://docs.vectara.com)
- **Vectara Ingest**: Visit [GitHub repository](https://github.com/vectara/vectara-ingest)
