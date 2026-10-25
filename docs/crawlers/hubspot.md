# HubSpot CRM Crawler

The HubSpot CRM crawler indexes customer relationship management data from HubSpot, including deals, companies, contacts, tickets, and email engagements. It supports hierarchical data relationships, date filtering, PII masking, and parallel processing with Ray.

## Overview

- **Crawler Type**: `hubspot`
- **Authentication**: API key-based
- **Data Objects**: Deals, Companies, Contacts, Tickets, Engagements (emails, calls, tasks, meetings)
- **Relationship Support**: Automatic association fetching and hierarchical linking
- **Operating Modes**:
  - `crm` - Full CRM data crawling (default)
  - `emails` - Email-only lightweight mode
- **Date Filtering**: Optional start and end date filters (YYYY-MM-DD format)
- **PII Protection**: Automatic masking of sensitive engagement content
- **Parallel Processing**: Ray workers supported for large instances
- **Performance**: Optimized for instances with thousands of records

## Use Cases

- Build RAG systems from customer relationship data
- Create searchable knowledge bases from deal information
- Index customer interaction history and engagements
- Archive and search customer communications
- Analyze customer lifecycle and engagement patterns
- Preserve customer context for support and sales teams
- Index company information and relationships
- Track deal progression and sales activities

## Getting Started: API Authentication

### Generate Your HubSpot API Key

1. Log in to your [HubSpot portal](https://app.hubspot.com)
2. Click the **settings icon** (gear) in the top-right corner
3. In the left sidebar, select **Integrations** > **Private apps**
4. Click **Create private app** button
5. Enter an app name (e.g., "Vectara Ingest")
6. Go to the **Scopes** tab and select:
   - **CRM** > **Deals**: Read
   - **CRM** > **Companies**: Read
   - **CRM** > **Contacts**: Read
   - **CRM** > **Tickets**: Read
   - **CRM** > **Engagements**: Read
   - **Engagements** > **Engagements**: Read (for email access)
7. Click **Create app**
8. Go to the **Auth** tab and copy the **Private app token** (starts with `pat-`)

Your credentials are:
- **API Key**: The private app token you just created
- **Customer ID**: Found in your HubSpot account settings (Settings > Data Management > Objects > Contacts)

### Setting Environment Variables

Store your credentials securely as environment variables:

```bash
export HUBSPOT_API_KEY="pat-your-private-app-token"
export HUBSPOT_CUSTOMER_ID="your-customer-id"
```

Or add to your `secrets.toml`:

```toml
[default]
HUBSPOT_API_KEY = "pat-your-private-app-token"
HUBSPOT_CUSTOMER_ID = "your-customer-id"
```

## Configuration

### Basic Configuration (CRM Mode)

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hubspot-crm

crawling:
  crawler_type: hubspot

hubspot_crawler:
  # API credentials (read from environment)
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"

  # Operating mode
  mode: crm  # or 'emails' for email-only mode
```

### Basic Configuration (Email Mode)

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hubspot-emails

crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"

  # Email-only mode for lightweight ingestion
  mode: emails
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hubspot-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: hubspot

hubspot_crawler:
  # API credentials
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"

  # Operating mode with parallel processing
  mode: crm
  ray_workers: 4  # Use 4 workers for parallel processing

  # Date filtering (optional)
  start_date: "2024-01-01"  # Only crawl data from this date (YYYY-MM-DD)
  end_date: "2024-12-31"    # Only crawl data until this date (YYYY-MM-DD)

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  source: hubspot
  environment: production
  sync_frequency: daily
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `hubspot_api_key` | string | Yes | - | HubSpot private app token (starts with `pat-`) |
| `hubspot_customer_id` | string | Yes | - | Your HubSpot customer/portal ID |
| `mode` | string | No | `crm` | Operating mode: `crm` (full) or `emails` (lightweight) |
| `ray_workers` | int | No | `0` | Number of Ray workers (0=sequential, -1=all CPUs, N=N workers) |
| `start_date` | string | No | - | Filter data from this date (YYYY-MM-DD format, optional) |
| `end_date` | string | No | - | Filter data until this date (YYYY-MM-DD format, optional) |

## Operating Modes

### CRM Mode (Full Data Crawling)

Full CRM data extraction with all object types and relationships:

```yaml
hubspot_crawler:
  mode: crm
  ray_workers: 4
```

**Indexes**:
1. **Deals** - Sales opportunities with deal stages, amounts, and close dates
2. **Companies** - Organization information and metadata
3. **Contacts** - Individual contact records and details
4. **Tickets** - Support tickets and issues
5. **Engagements** - All interaction types (emails, calls, tasks, meetings)

**Process**:
1. Fetches all deals and extracts company/contact relationships
2. Fetches company and contact records referenced by deals
3. Indexes companies with deal associations
4. Indexes contacts with deal associations
5. Indexes all deals with enriched context
6. Indexes support tickets
7. Indexes all engagement records (emails, calls, tasks, meetings)

### Email Mode (Lightweight)

Email-only crawling for focused engagement indexing:

```yaml
hubspot_crawler:
  mode: emails
  ray_workers: 0  # Sequential processing recommended
```

**Behavior**:
- Skips companies, contacts, deals, and tickets
- Caches company/contact data for email context
- Extracts and indexes only email engagement records
- Applies automatic PII masking to email content
- Lightweight memory footprint suitable for large instances

## How It Works

### CRM Mode Data Flow

```
1. Fetch Deals
   ├─ Extract company IDs
   └─ Extract contact IDs
        ↓
2. Fetch Related Companies
   └─ Cache for context
        ↓
3. Fetch Related Contacts
   └─ Cache for context
        ↓
4. Index Deals (enriched with company/contact data)
        ↓
5. Index Tickets
        ↓
6. Index Engagements (emails, calls, tasks, meetings)
```

### Data Extraction

#### Deals
- Deal name, amount, stage, and pipeline
- Close date and forecast probability
- Deal type and next steps
- Owner information
- Associated companies and contacts

#### Companies
- Company name, domain, and website
- Industry and revenue information
- Employee count and location (city, state, country)
- Lifecycle stage
- Owner and creation metadata
- Associated contacts and deals

#### Contacts
- First name, last name, email, and phone
- Job title and company
- Lead status and lifecycle stage
- Owner information
- Creation and activity dates
- Associated companies and deals

#### Tickets
- Ticket subject and description
- Priority and status
- Assigned agent
- Customer information
- Creation and resolution dates

#### Engagements
- Email subject and body (with PII masking)
- Call transcripts and summaries
- Task details and status
- Meeting notes and attendees
- Timestamp and owner information

### Metadata Captured

The crawler automatically indexes:

- **Deal Information**: Deal name, amount, stage, pipeline, close date
- **Company Details**: Name, industry, revenue, employees, lifecycle stage
- **Contact Details**: Name, email, phone, job title, company
- **Engagement Type**: Email, call, task, meeting
- **Relationships**: Deal ↔ Company, Deal ↔ Contact, Contact ↔ Company
- **Timestamps**: Creation, update, and last activity dates
- **Owner**: HubSpot user assigned to record
- **Source**: Always "hubspot"

## Date Filtering

### Using Date Ranges

Filter indexed data to a specific date range:

```yaml
hubspot_crawler:
  start_date: "2024-01-01"
  end_date: "2024-12-31"
```

Behavior:
- Records created after `start_date` are included
- Records created before `end_date` are included
- Records without dates are included
- Date range is applied to all object types
- Supports ISO 8601 format (with or without time)

### Examples

```yaml
# Last 90 days
start_date: "2024-08-20"

# Specific year
start_date: "2024-01-01"
end_date: "2024-12-31"

# Specific quarter
start_date: "2024-07-01"
end_date: "2024-09-30"

# All data (no filtering)
# Simply omit start_date and end_date
```

## PII Masking

Email engagements are automatically processed with PII (Personally Identifiable Information) masking:

- Email addresses are masked
- Phone numbers are masked
- Personal names are masked
- Credit card numbers are masked
- Social security numbers are masked

This protection is automatically applied in both CRM and email modes.

## Ray Parallel Processing

Enable parallel processing for large instances:

```yaml
hubspot_crawler:
  ray_workers: 4  # Use 4 concurrent workers
```

### Ray Worker Configuration

| Setting | Behavior |
|---------|----------|
| `ray_workers: 0` | Sequential processing (default, good for testing) |
| `ray_workers: 1` | Single Ray worker |
| `ray_workers: 4` | 4 parallel workers |
| `ray_workers: -1` | Use all available CPU cores |

### Performance Tips

- For instances with < 1000 records: Use sequential (`ray_workers: 0`)
- For instances with 1000-10000 records: Use 2-4 workers
- For instances with > 10000 records: Use 4-8 workers or `-1` for all cores
- Email mode typically doesn't need parallel processing

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized` or `Invalid API key`

**Solutions**:
1. Verify the API key starts with `pat-`
2. Check the token hasn't expired (private apps expire after a period)
3. Verify required scopes are enabled (CRM: Deals, Companies, Contacts, Tickets, Engagements)
4. Confirm environment variables are set:
   ```bash
   echo $HUBSPOT_API_KEY
   echo $HUBSPOT_CUSTOMER_ID
   ```
5. Generate a new private app if issues persist

### No Data Indexed

**Error**: Crawler runs but indexes 0 records

**Solutions**:
1. Verify you have data in your HubSpot account
2. Check that the account has permission to access data
3. Try with date filtering disabled:
   ```yaml
   # Remove start_date and end_date if present
   ```
4. Check logs for specific errors:
   ```bash
   docker logs -f vingest | grep -i error
   ```
5. Test API connection manually:
   ```bash
   curl -H "Authorization: Bearer $HUBSPOT_API_KEY" \
     https://api.hubapi.com/crm/v3/objects/deals
   ```

### Rate Limiting

**Error**: `429 Too Many Requests` or `Rate limit exceeded`

**Solutions**:
1. Reduce the number of Ray workers:
   ```yaml
   ray_workers: 1  # or 0 for sequential
   ```
2. HubSpot has rate limits based on subscription tier
3. Run crawls during off-peak hours
4. Implement longer delays between crawls if running multiple instances

### Missing Relationships

**Issue**: Deals show but related companies/contacts are missing

**Solutions**:
1. This is normal - only companies/contacts involved in deals are fetched
2. Verify the association exists in HubSpot
3. Check that company/contact records haven't been deleted
4. Run with `verbose: true` to see detailed logs

### Email Mode Issues

**Issue**: No emails are being indexed

**Solutions**:
1. Verify you have email engagements in HubSpot
2. Check scopes include **Engagements** > **Engagements**: Read
3. Ensure the private app has access to engagement data
4. Try CRM mode instead:
   ```yaml
   mode: crm
   ```

### Memory Issues

**Error**: Out of memory or process killed

**Solutions**:
1. Use sequential mode instead of Ray:
   ```yaml
   ray_workers: 0
   ```
2. Add date filtering to limit data:
   ```yaml
   start_date: "2024-01-01"
   end_date: "2024-12-31"
   ```
3. Try email-only mode:
   ```yaml
   mode: emails
   ```
4. Increase Docker memory allocation if running containerized

## Best Practices

### 1. Start Small

Test with a limited date range first:

```yaml
hubspot_crawler:
  start_date: "2024-09-01"
  end_date: "2024-09-30"
```

Then expand to full data:

```yaml
# Remove date filters for full crawl
```

### 2. Use Appropriate Mode

- **CRM mode** for: Complete customer views, sales analytics, full relationship context
- **Email mode** for: Communication archives, lightweight engagement indexing, email search

### 3. Document Configuration

```yaml
metadata:
  version: "1.0"
  created_date: "2024-11-18"
  notes: "Full HubSpot CRM sync including deals, companies, contacts"
  data_source: "HubSpot production"
```

### 4. Schedule Regular Syncs

Use cron for periodic updates:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/hubspot-crm.yaml default
```

### 5. Monitor Indexing

Watch crawl statistics for anomalies:

```bash
# Monitor in real-time
docker logs -f vingest | grep -E "indexed|error|statistics"
```

### 6. Version Configuration Changes

Track configuration versions and changes:

```yaml
metadata:
  version: "1.0"
  updated: "2024-11-18"
  changes: "Added date filtering to recent year only"
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/hubspot-crm.yaml
```

Enter your configuration (see examples above).

### Set Environment Variables

```bash
export HUBSPOT_API_KEY="pat-your-token"
export HUBSPOT_CUSTOMER_ID="your-customer-id"
```

### Run the Crawler

```bash
# Full CRM crawl
bash run.sh config/hubspot-crm.yaml default

# Monitor progress
docker logs -f vingest
```

### Examples

#### Example 1: Full CRM Crawl with Parallel Processing

```yaml
vectara:
  corpus_key: hubspot-crm
  reindex: true

crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"
  mode: crm
  ray_workers: 4

metadata:
  sync_type: full_crm
  frequency: daily
```

Save as `config/hubspot-full.yaml`:

```bash
bash run.sh config/hubspot-full.yaml default
```

#### Example 2: Email-Only Mode (Lightweight)

```yaml
vectara:
  corpus_key: hubspot-emails

crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"
  mode: emails

metadata:
  content_type: email_engagements
```

Save as `config/hubspot-emails.yaml`:

```bash
bash run.sh config/hubspot-emails.yaml default
```

#### Example 3: Recent Data Only with Date Filter

```yaml
vectara:
  corpus_key: hubspot-recent
  reindex: false

crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"
  mode: crm
  start_date: "2024-01-01"
  end_date: "2024-12-31"
  ray_workers: 2

metadata:
  data_period: "2024"
  update_frequency: "weekly"
```

#### Example 4: Large Instance Production Setup

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hubspot-prod-kb
  reindex: false
  verbose: true

crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_api_key: "${HUBSPOT_API_KEY}"
  hubspot_customer_id: "${HUBSPOT_CUSTOMER_ID}"
  mode: crm
  ray_workers: -1  # Use all CPU cores
  start_date: "2023-01-01"

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  environment: production
  source: hubspot_crm
  sync_schedule: daily_2am
  content_types:
    - deals
    - companies
    - contacts
    - engagements
```

## API Reference

### Supported API Scopes

For the private app, enable these scopes:

- **CRM** > **Deals**: Read
- **CRM** > **Companies**: Read
- **CRM** > **Contacts**: Read
- **CRM** > **Tickets**: Read
- **CRM** > **Engagements**: Read
- **Engagements** > **Engagements**: Read

### Rate Limits

HubSpot rate limits vary by subscription tier:

- **Free Plan**: 10 requests/second
- **Paid Plans**: 100 requests/second
- Check your account for specific limits

### Data Limits

- Maximum records per request: 100
- Maximum associations per record: Unlimited (fetched in batches)
- Ray workers recommended: 1-8 depending on instance size

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide
- [HubSpot API Documentation](https://developers.hubspot.com/docs/api/overview)

## Monitoring and Logging

### Enable Verbose Logging

```yaml
vectara:
  verbose: true
```

### Check Indexing Statistics

The crawler logs final statistics:

```
FINAL CRAWL STATISTICS:
  Deals indexed: 245
  Companies indexed: 180
  Contacts indexed: 512
  Tickets indexed: 67
  Engagements indexed: 3421
  Items filtered by date: 156
  Total errors: 2
```

### Real-Time Monitoring

```bash
# Watch crawler progress
docker logs -f vingest | tail -50

# Search for specific object type
docker logs -f vingest | grep "Deals indexed"

# Find errors
docker logs -f vingest | grep -i "error"
```

## Support and Troubleshooting

For issues or questions:

1. Check the [Troubleshooting Guide](../deployment/troubleshooting.md)
2. Review HubSpot API documentation for data structure questions
3. Verify private app permissions in HubSpot settings
4. Check Docker resource allocation if experiencing performance issues
5. Open an issue on [GitHub](https://github.com/vectara/vectara-ingest/issues)
