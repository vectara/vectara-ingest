# Financial Modeling Prep (FMP) Crawler

The Financial Modeling Prep (FMP) crawler indexes financial data and earnings call transcripts from the financialmodelingprep.com API. It supports multiple companies, year ranges, selective indexing of 10-K filings and earnings call transcripts, and automatic company profile retrieval.

## Overview

- **Crawler Type**: `fmp`
- **Data Source**: Financial Modeling Prep API (financialmodelingprep.com)
- **Authentication**: API key-based (free or paid plans available)
- **Data Types**:
  - 10-K annual financial reports (structured JSON)
  - Earnings call transcripts
  - Company profiles
- **Company Support**: Multiple ticker symbols
- **Date Range**: Configurable year range for historical data
- **Selective Indexing**: Choose to index 10-Ks, transcripts, or both
- **Document Format**: Structured financial data and text transcripts
- **Metadata**: Company name, ticker, year, filing type, quarter information

## Use Cases

- Build financial knowledge bases with structured financial data
- Create searchable earnings call transcript archives
- Index company financial statements in structured format
- Build RAG systems for financial analysis and Q&A
- Track company financial performance over multiple years
- Analyze management commentary from earnings calls
- Create searchable financial ratio and metric databases
- Build investment research knowledge bases

## Getting Started: API Authentication

### Create a Financial Modeling Prep Account

1. Go to [Financial Modeling Prep](https://financialmodelingprep.com/)
2. Click **Sign Up** to create a free or paid account
3. Verify your email address
4. Log in to your account
5. Go to your **Dashboard** > **API** section
6. Copy your **API Key** (visible on the dashboard)

### API Key Setup

Free tier includes:
- 250 API calls per day
- Last 5 years of data
- Essential financial endpoints

Paid tiers include:
- Higher request limits (up to 300,000/month)
- More data endpoints
- Extended historical data
- Priority support

### Setting Environment Variables

Store your API key securely:

```bash
export FMP_API_KEY="your-api-key-here"
```

Or add to `secrets.toml`:

```toml
[default]
FMP_API_KEY = "your-api-key-here"
```

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: fmp-financials

crawling:
  crawler_type: fmp

fmp_crawler:
  # API key from environment
  fmp_api_key: "${FMP_API_KEY}"

  # Company ticker symbols
  tickers: ["AAPL", "MSFT", "GOOG"]

  # Year range for data
  start_year: 2020
  end_year: 2024

  # Data types to index (optional)
  index_10k: true                 # Index 10-K structured financial data
  index_call_transcripts: true    # Index earnings call transcripts
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: fmp-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"

  # Multiple companies
  tickers:
    - "AAPL"
    - "MSFT"
    - "GOOG"
    - "NVDA"
    - "TSLA"
    - "JPM"
    - "JNJ"

  # Multi-year range
  start_year: 2015
  end_year: 2024

  # Data type selection
  index_10k: true
  index_call_transcripts: true

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  source: financial-modeling-prep
  content_types:
    - financial_reports
    - earnings_transcripts
  update_frequency: quarterly
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `fmp_api_key` | string | Yes | - | FMP API key from your account |
| `tickers` | list | Yes | - | List of company ticker symbols |
| `start_year` | int | Yes | - | First year to include (e.g., 2020) |
| `end_year` | int | Yes | - | Last year to include (e.g., 2024) |
| `index_10k` | bool | No | `false` | Whether to index 10-K financial reports |
| `index_call_transcripts` | bool | No | `true` | Whether to index earnings call transcripts |

## Data Types

### 10-K Financial Reports

Structured JSON financial data including:

**Financial Statements**:
- Balance Sheet (assets, liabilities, equity)
- Income Statement (revenue, expenses, net income)
- Cash Flow Statement (operating, investing, financing)
- Ratios and metrics (profitability, liquidity, solvency)

**Sections Indexed**:
- Income statement data
- Balance sheet line items
- Cash flow statement items
- Financial ratios
- Key metrics and calculations

**Metadata**:
- Company name and ticker
- Fiscal year
- Filing type (10-K)
- Report URL

### Earnings Call Transcripts

**Content**:
- Management prepared remarks
- Question and answer session
- Company guidance and outlook
- Analyst questions and discussion

**Structure**:
- Full transcript text
- Speaker attribution (management vs. analysts)
- Time markers for quarters and years
- Company name and ticker

**Metadata**:
- Company name and ticker
- Quarter and year
- Transcript URL
- Filing type (transcript)

## How It Works

### 10-K Indexing Process

```
1. For Each Ticker
   ├─ Get company profile (name)
   ├─ For Each Year in Range
   │  ├─ Query FMP API: GET /api/v3/sec_filings/{ticker}?type=10-K
   │  ├─ Find 10-K for fiscal year
   │  ├─ Query FMP API: GET /api/v4/financial-reports-json
   │  ├─ Parse JSON financial data
   │  └─ Extract text sections with substantial content
   │
   └─ Index Document
      ├─ Title: "10-K for {company} from {year}"
      ├─ Sections: Financial statement line items
      └─ Metadata: Ticker, year, company name, URL
```

### Earnings Call Transcript Indexing

```
1. For Each Ticker
   ├─ Get company profile
   ├─ For Each Year
   │  └─ For Each Quarter (1-4)
   │     ├─ Query FMP API: GET /api/v3/earning_call_transcript
   │     ├─ Filter by quarter and year
   │     ├─ Extract transcript content
   │     └─ Create document
   │
   └─ Index Document
      ├─ Title: "Earnings call {company} Q{quarter} {year}"
      ├─ Content: Full transcript text
      └─ Metadata: Ticker, quarter, year, URL
```

### Company Profile Retrieval

For each ticker, the crawler:

1. Queries FMP API for company profile
2. Extracts company name (used in document titles)
3. Verifies company exists in FMP database
4. Continues if profile found, skips if not

## Metadata Captured

### 10-K Documents

Each 10-K document includes:

- **Title**: "10-K for {Company} from {Year}"
- **Company Name**: Full legal company name
- **Ticker**: Stock symbol
- **Year**: Fiscal year covered
- **Filing Type**: "10-K" (or "filing")
- **Source**: "edgar" (original data source)
- **URL**: Direct link to SEC filing
- **Sections**: Each financial statement line item becomes a searchable section

### Earnings Call Transcripts

Each transcript document includes:

- **Title**: "Earnings call transcript for {Company}, quarter {Q} of {year}"
- **Company Name**: Full legal company name
- **Ticker**: Stock symbol (used as source metadata)
- **Year**: Calendar year
- **Quarter**: Quarter number (1-4)
- **Type**: "transcript"
- **Source**: Stock ticker symbol (lowercase)
- **URL**: Link to FMP transcript
- **Content**: Full transcript text in single section

## API Rate Limiting

### Free Tier

- 250 API calls per day
- ~1 request per 350 seconds (roughly)
- Recommended: 1-2 companies per crawl

### Paid Tiers

- Depends on subscription level
- Typically 300 - 1,000,000+ requests per month
- Check your [FMP account dashboard](https://financialmodelingprep.com/dashboard) for limits

### Handling Rate Limits

The crawler automatically handles API responses:

```yaml
fmp_crawler:
  tickers: ["AAPL"]  # Start small to avoid rate limits
  start_year: 2024   # Recent years only
  end_year: 2024
```

If you hit rate limits:

1. Reduce number of tickers
2. Narrow year range
3. Run separate crawls at different times
4. Consider upgrading to paid tier for high-volume crawls

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized` or `Invalid API key`

**Solutions**:
1. Verify API key is correct (copy from FMP dashboard)
2. Check environment variable is set:
   ```bash
   echo $FMP_API_KEY
   ```
3. Verify account is active (check FMP login)
4. Free tier might have expired - check account dashboard
5. Generate new API key if needed

### No Data Indexed

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Verify tickers are valid (use [FMP Search](https://financialmodelingprep.com/))
2. Check that companies have 10-Ks or transcripts in the year range
3. Verify both `index_10k` and `index_call_transcripts` aren't both false:
   ```yaml
   index_10k: true
   index_call_transcripts: true
   ```
4. Try with a single company first:
   ```yaml
   tickers: ["AAPL"]
   ```
5. Check logs for API errors:
   ```bash
   docker logs -f vingest | grep -i "error"
   ```

### Rate Limited

**Error**: `429 Too Many Requests` or `Rate limit exceeded`

**Solutions**:
1. Reduce the scope:
   ```yaml
   tickers: ["AAPL"]          # Single company
   start_year: 2024
   end_year: 2024             # Single year
   ```
2. Wait before next crawl (rate limits reset daily for free tier)
3. Upgrade to paid tier for higher limits
4. Disable one data type:
   ```yaml
   index_10k: true
   index_call_transcripts: false  # Skip transcripts
   ```

### Partial Data

**Issue**: Some years or companies missing

**Solutions**:
1. Not all companies have data for all years
2. Smaller companies might not have transcripts
3. Check FMP directly to verify data availability
4. Try expanding the year range:
   ```yaml
   start_year: 2010  # Further back
   end_year: 2024
   ```

### Empty Financial Sections

**Issue**: 10-K indexed but with empty sections

**Solutions**:
1. This is normal - crawler filters out very small data values
2. Minimum requirement: 50 characters per value
3. Check actual FMP data for that company/year
4. Some companies might have incomplete data

### API Errors

**Error**: `Connection error` or `Timeout`

**Solutions**:
1. Check network connectivity
2. FMP service might be down - try later
3. Request might be too large - reduce scope
4. Increase timeout if available:
   ```yaml
   api_timeout: 60  # 60 seconds
   ```

## Best Practices

### 1. Start Small

Test with a single company and recent year:

```yaml
fmp_crawler:
  tickers: ["AAPL"]
  start_year: 2024
  end_year: 2024
  index_10k: true
  index_call_transcripts: true
```

After success, expand scope.

### 2. Respect API Limits

For free tier:

```yaml
# Good: 1 company per crawl
tickers: ["AAPL"]

# Consider: 2-3 companies max
tickers: ["AAPL", "MSFT", "GOOG"]

# Avoid: Too many companies for free tier
tickers: [50 companies]  # Would hit rate limits
```

### 3. Use Selective Indexing

Index only what you need:

```yaml
# Financial data only (faster)
index_10k: true
index_call_transcripts: false

# Transcripts only (lighter data)
index_10k: false
index_call_transcripts: true

# Both for comprehensive knowledge base
index_10k: true
index_call_transcripts: true
```

### 4. Schedule Crawls During Off-Hours

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && \
  bash run.sh config/fmp-daily.yaml default

# Run monthly
0 2 1 * * cd /path/to/vectara-ingest && \
  bash run.sh config/fmp-monthly.yaml default
```

### 5. Document Configuration

```yaml
metadata:
  source: financial-modeling-prep
  version: "1.0"
  created: "2024-11-18"
  notes: "FAANG companies financial data"
  data_scope: "2020-2024"
  includes: ["10-K reports", "Earnings call transcripts"]
```

### 6. Monitor API Usage

Check FMP dashboard periodically:

1. Log in to [FMP account](https://financialmodelingprep.com/dashboard)
2. Check API call usage
3. Track remaining calls for the day/month
4. Plan crawls around limits

## Running the Crawler

### Create Your Configuration

```bash
vim config/fmp-financials.yaml
```

### Set Environment Variable

```bash
export FMP_API_KEY="your-api-key-here"
```

### Run the Crawler

```bash
bash run.sh config/fmp-financials.yaml default
```

### Monitor Progress

```bash
docker logs -f vingest
```

## Examples

### Example 1: Single Company - Recent Data

```yaml
vectara:
  corpus_key: fmp-apple

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"
  tickers: ["AAPL"]
  start_year: 2024
  end_year: 2024
  index_10k: true
  index_call_transcripts: true

metadata:
  company: Apple Inc.
  period: "2024"
```

### Example 2: Tech Sector - Multi-Year

```yaml
vectara:
  corpus_key: fmp-tech-financials

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"
  tickers:
    - "AAPL"
    - "MSFT"
    - "GOOG"
    - "NVDA"
  start_year: 2022
  end_year: 2024
  index_10k: true
  index_call_transcripts: true

metadata:
  sector: technology
  focus: "Large-cap tech financial data"
  years: "2022-2024"
```

### Example 3: Transcripts Only - Multi-Company

```yaml
vectara:
  corpus_key: fmp-earnings-calls

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"
  tickers:
    - "AAPL"
    - "MSFT"
    - "JPM"
    - "JNJ"
    - "PG"
  start_year: 2020
  end_year: 2024
  index_10k: false               # Skip financial reports
  index_call_transcripts: true   # Focus on transcripts

metadata:
  content_type: earnings_transcripts
  focus: "Management commentary and guidance"
```

### Example 4: 10-K Reports Only - Historical

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: fmp-financials-history
  reindex: true
  verbose: true

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"
  tickers:
    - "MSFT"
    - "AAPL"
  start_year: 2015
  end_year: 2024
  index_10k: true                # Full financial history
  index_call_transcripts: false  # Skip transcripts

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  analysis: historical_financials
  period: "10-year view"
  data_source: "FMP + SEC EDGAR"
```

### Example 5: Broad Multi-Sector

```yaml
vectara:
  corpus_key: fmp-market-data

crawling:
  crawler_type: fmp

fmp_crawler:
  fmp_api_key: "${FMP_API_KEY}"
  tickers:
    - "AAPL"
    - "MSFT"
    - "JPM"
    - "JNJ"
    - "XOM"
    - "UNH"
    - "PG"
    - "KO"
  start_year: 2020
  end_year: 2024
  index_10k: true
  index_call_transcripts: true

metadata:
  market: "Multi-sector S&P 500 subset"
  types: ["Financial Reports", "Earnings Transcripts"]
  frequency: "quarterly_update"
```

## Data Format and Structure

### 10-K Document Example

```
Document ID: 10-K-Apple Inc.-2024
Title: 10-K for Apple Inc. from 2024
Metadata:
  - company_name: "Apple Inc."
  - ticker: "AAPL"
  - year: 2024
  - type: "10-K"
  - source: "edgar"
  - filing_type: "10-K"

Sections:
  - Title: "Revenue"
    Text: "Products Revenue: 195,899 | Services Revenue: 85,156 | ..."
  - Title: "Operating Expenses"
    Text: "Research and Development: 29,915 | Sales and Marketing: 21,514 | ..."
  - Title: "Net Income"
    Text: "93,736 | ..."
```

### Earnings Call Transcript Example

```
Document ID: transcript-Apple Inc.-2024-4
Title: Earnings call transcript for Apple Inc., quarter 4 of 2024
Metadata:
  - company_name: "Apple Inc."
  - ticker: "aapl"
  - year: 2024
  - quarter: 4
  - type: "transcript"
  - url: "https://financialmodelingprep.com/..."

Sections:
  - Text: "Good afternoon, and thank you for joining us.
          I'm Tim Cook, CEO of Apple. I'm pleased to report that we
          delivered record revenue in Q4 2024, driven by strong performance
          in our services business..."
```

## Performance Considerations

### API Request Overhead

- Company profile lookup: 1 request per ticker
- 10-K lookup: 1 request per ticker
- 10-K detailed data: 1 request per year (if indexed)
- Transcript lookup: 1 request per quarter per year

**Example**: 3 companies, 2024 only, both data types:
- 3 profile lookups
- 3 10-K lookups
- 3 10-K data requests
- 3 × 4 quarters = 12 transcript requests
- **Total: ~21 API calls**

### Optimization Tips

1. **Limit year range**: Fewer years = fewer API calls
2. **Fewer tickers**: Start with 1-2, expand later
3. **Choose data types**: Index only what you need
4. **Batch crawls**: Multiple separate runs better than one large run
5. **Free tier strategy**: Crawl 1 company per day to spread API usage

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide
- [Financial Modeling Prep API Docs](https://financialmodelingprep.com/developer/docs/)

## API Reference

### FMP Endpoints Used

- `GET /api/v3/profile/{ticker}` - Company profile (name, industry, etc.)
- `GET /api/v3/sec_filings/{ticker}?type=10-K` - 10-K filing metadata
- `GET /api/v4/financial-reports-json` - Structured 10-K financial data
- `GET /api/v3/earning_call_transcript/{ticker}` - Earnings call transcripts

### FMP Resources

- [FMP Home](https://financialmodelingprep.com/)
- [FMP API Documentation](https://financialmodelingprep.com/developer/docs/)
- [FMP Dashboard](https://financialmodelingprep.com/dashboard)
- [FMP Support](https://financialmodelingprep.com/contact)

## Support

For issues:

1. Verify API key and account status on FMP dashboard
2. Check FMP API documentation
3. Confirm ticker symbols are valid
4. Review [Troubleshooting Guide](../deployment/troubleshooting.md)
5. Open [GitHub issue](https://github.com/vectara/vectara-ingest/issues)
