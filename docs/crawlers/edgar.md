# EDGAR Crawler

The EDGAR crawler indexes financial documents from the U.S. Securities and Exchange Commission (SEC), including 10-K annual reports, 10-Q quarterly reports, 8-K current reports, and DEF 14A proxy statements. It supports multi-company crawling, date filtering, parallel processing with Ray, and automatic filing type selection.

## Overview

- **Crawler Type**: `edgar`
- **Data Source**: SEC EDGAR (Electronic Data Gathering, Organization, and Retrieval)
- **Supported Filing Types**: 10-K, 10-Q, 8-K, DEF 14A, and other SEC forms
- **Authentication**: None required (public SEC data)
- **Company Support**: Multiple ticker symbols per crawl
- **Date Filtering**: Configurable date range for filings
- **Document Format**: HTML and text extraction from SEC filings
- **Parallel Processing**: Ray workers supported for multi-company crawls
- **Automatic Parsing**: SEC filing downloader handles document retrieval and parsing
- **Metadata Extraction**: Company name, ticker, filing date, filing type

## Use Cases

- Build financial knowledge bases for investment research
- Create searchable archives of SEC filings
- Index company financial disclosures and risk factors
- Analyze management discussion and analysis (MD&A) sections
- Build RAG systems for financial analysis
- Track company financial history over time
- Index competitor financial information
- Create searchable regulatory compliance documentation

## Getting Started

### No Authentication Required

EDGAR data is publicly available from the SEC. No API key or authentication is needed.

### Finding Company Tickers

Identify companies you want to include:

1. Go to [SEC.gov EDGAR Search](https://www.sec.gov/cgi-bin/browse-edgar)
2. Search for company by name
3. Copy the ticker symbol (e.g., AAPL, MSFT, GOOG)
4. Or find a list of tickers from:
   - [NASDAQ listed companies](https://www.nasdaq.com/market-activity/stocks)
   - [NYSE listed companies](https://www.nyse.com)
   - Financial data providers (Yahoo Finance, etc.)

### Determining Date Range

Choose the date range for filings:

```yaml
edgar_crawler:
  start_date: "2020-01-01"  # First filing date to include
  end_date: "2024-12-31"    # Last filing date to include
```

Dates should span the period when filings were actually published to EDGAR.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: edgar-filings

crawling:
  crawler_type: edgar

edgar_crawler:
  # Company ticker symbols
  tickers: ["AAPL", "MSFT", "GOOG"]

  # Date range for filings (YYYY-MM-DD format)
  start_date: "2020-01-01"
  end_date: "2024-12-31"

  # Filing types to include (optional, defaults shown)
  filing_types: ["10-K", "10-Q", "8-K", "DEF 14A"]
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: edgar-knowledge-base
  reindex: true
  verbose: true
  create_corpus: true

crawling:
  crawler_type: edgar

edgar_crawler:
  # Multiple companies
  tickers:
    - "AAPL"
    - "MSFT"
    - "GOOG"
    - "NVDA"
    - "TSLA"
    - "JPM"
    - "JNJ"

  # 5-year date range
  start_date: "2019-01-01"
  end_date: "2024-12-31"

  # Specific filing types
  filing_types: ["10-K", "10-Q", "8-K"]

  # Parallel processing with Ray
  ray_workers: 4  # 0 = sequential, -1 = all CPUs, N = N workers

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  source: sec-edgar
  content_type: financial_filings
  update_frequency: quarterly
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `tickers` | list | Yes | - | List of company ticker symbols (uppercase) |
| `start_date` | string | Yes | - | First filing date to include (YYYY-MM-DD) |
| `end_date` | string | Yes | - | Last filing date to include (YYYY-MM-DD) |
| `filing_types` | list | No | `["10-K", "10-Q", "8-K", "DEF 14A"]` | SEC filing types to retrieve |
| `ray_workers` | int | No | `0` | Number of Ray workers (0=sequential, -1=all CPUs) |

## Supported Filing Types

### Primary Document Types

| Filing Type | Description | Frequency | Content |
|-------------|-------------|-----------|---------|
| **10-K** | Annual Report | Annually | Comprehensive financial statements, MD&A, risk factors |
| **10-Q** | Quarterly Report | Quarterly | Interim financial statements, MD&A for quarter |
| **8-K** | Current Report | As needed | Material events and changes |
| **DEF 14A** | Proxy Statement | Annually (before AGM) | Executive compensation, governance, shareholder info |

### Additional Filing Types Available

```yaml
filing_types:
  - "20-F"      # Annual report for foreign private issuers
  - "424B5"     # Prospectus (for IPOs and offerings)
  - "SC 13D/A"  # Schedule 13D Amendment
  - "4"         # Form 4 - Insider trading
  - "S-1"       # Registration statement
```

## How It Works

### Filing Retrieval Process

```
1. Initialize SEC Downloader
   └─ Uses unofficial SEC ticker lookup
        ↓
2. For Each Ticker
   ├─ Convert ticker to CIK (Central Index Key)
   ├─ Query SEC for specified filing types
   ├─ Filter by date range
   │  └─ Keep only filings between start_date and end_date
   ├─ Download each filing
   └─ Convert to HTML/text format
        ↓
3. Index Each Filing
   ├─ Extract metadata (ticker, date, type, company)
   ├─ Parse HTML/text content
   └─ Send to Vectara for indexing
        ↓
4. Report Statistics
   └─ Log number of filings indexed per company
```

### Filing Metadata Extraction

Each indexed filing includes:

- **Title**: Filing type, company name, and date
- **Ticker**: Company stock symbol
- **Company Name**: Full legal company name
- **Filing Type**: 10-K, 10-Q, 8-K, etc.
- **Report Date**: Date covered by the filing
- **Filing Year**: Year extracted from report date
- **Document URL**: Direct link to SEC filing
- **Source**: Always "edgar"

### Content Processing

1. **Download**: Files retrieved from SEC.gov
2. **Extract**: HTML documents parsed for text content
3. **Clean**: Boilerplate and formatting removed
4. **Chunk**: Content split for optimal indexing
5. **Index**: Chunks sent to Vectara with metadata

## Date Filtering

### Date Range Behavior

- **start_date**: First filing to include (based on report date)
- **end_date**: Last filing to include (based on report date)
- **Inclusive**: Both start and end dates are included
- **No filtering**: Filings published on exact dates are included

### Example Date Ranges

```yaml
# Last 5 calendar years
start_date: "2020-01-01"
end_date: "2024-12-31"

# Last 3 years from today
# Adjust based on current date

# Recent 10-K filings (usually Jan-March for CY)
start_date: "2024-01-01"
end_date: "2024-12-31"

# Specific period (e.g., 2008 financial crisis)
start_date: "2008-01-01"
end_date: "2008-12-31"
```

### Finding Correct Dates

Before setting your date range:

1. Go to SEC.gov EDGAR Search
2. Search for a company ticker
3. Note the dates when filings were published
4. Adjust your `start_date` and `end_date` accordingly

## Parallel Processing with Ray

Enable multi-core processing for large crawls:

```yaml
edgar_crawler:
  ray_workers: 4
```

### Ray Configuration

| Setting | Behavior | Use Case |
|---------|----------|----------|
| `ray_workers: 0` | Sequential processing (default) | Testing, small crawls |
| `ray_workers: 1` | Single Ray worker | Debugging |
| `ray_workers: 4` | 4 parallel workers | 5-10 companies |
| `ray_workers: 8` | 8 parallel workers | 10-50 companies |
| `ray_workers: -1` | Use all CPU cores | Large crawls (50+ companies) |

### Performance Tuning

- **Few companies** (< 3): Use sequential (`ray_workers: 0`)
- **Medium crawl** (3-10): Use 4 workers
- **Large crawl** (10+): Use 8 workers or all cores

## Troubleshooting

### No Filings Found

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Verify ticker symbols are correct (uppercase):
   ```yaml
   tickers: ["AAPL", "MSFT"]  # Correct
   tickers: ["aapl", "msft"]  # Wrong
   ```
2. Check date range - are filings actually from that period?
   ```bash
   # Search manually on SEC.gov to verify dates
   ```
3. Verify filing types are available for that company:
   ```yaml
   # Try with default filing types first
   filing_types: ["10-K", "10-Q"]
   ```
4. Check network connectivity to SEC.gov

### Invalid Ticker

**Error**: `Ticker not found` or `CIK lookup failed`

**Solutions**:
1. Verify ticker is a real stock symbol
2. Use the [SEC EDGAR search](https://www.sec.gov/cgi-bin/browse-edgar) to verify
3. Some tickers might be delisted - use historical ticker symbols if needed
4. Private companies won't have SEC filings
5. Foreign companies may file as ADRs or use 20-F instead of 10-K

### Partial Data

**Error**: Only some companies are indexed

**Solutions**:
1. Check individual tickers manually on SEC.gov
2. Some companies may not have filed in your date range
3. Review logs for specific errors:
   ```bash
   docker logs -f vingest | grep -i "error"
   ```
4. Verify date range covers the companies' filing history

### Memory Issues

**Error**: Out of memory or process killed

**Solutions**:
1. Reduce the number of Ray workers:
   ```yaml
   ray_workers: 1  # or 0 for sequential
   ```
2. Crawl fewer companies at once:
   ```yaml
   tickers: ["AAPL", "MSFT"]  # Start small
   ```
3. Use a narrower date range:
   ```yaml
   start_date: "2023-01-01"  # More recent
   end_date: "2023-12-31"
   ```
4. Increase Docker memory if containerized

### Network Errors

**Error**: `Connection timeout` or `Connection refused`

**Solutions**:
1. Check network connectivity to SEC.gov
2. SEC website may have rate limiting - retry after a delay
3. Use a smaller batch of companies
4. Try again during off-peak hours

### SSL Certificate Errors

**Error**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solutions**:
1. Update your CA certificate bundle:
   ```bash
   pip install --upgrade certifi
   ```
2. For development only (not production):
   ```yaml
   edgar_crawler:
     ssl_verify: false
   ```

## Best Practices

### 1. Start with a Single Company

Test configuration with one company first:

```yaml
edgar_crawler:
  tickers: ["AAPL"]
  start_date: "2023-01-01"
  end_date: "2023-12-31"
```

After successful run, expand to more companies.

### 2. Use Recent Date Ranges

For initial crawls, use recent years:

```yaml
# Good: 1-2 years of recent data
start_date: "2023-01-01"
end_date: "2024-12-31"

# Large: 10+ years might be too much initially
start_date: "2014-01-01"
end_date: "2024-12-31"
```

### 3. Filter by Relevant Filing Types

Not all companies file all types. Use only what you need:

```yaml
# For standard financial analysis
filing_types: ["10-K", "10-Q"]

# For complete picture
filing_types: ["10-K", "10-Q", "8-K"]

# For executive compensation details
filing_types: ["DEF 14A"]
```

### 4. Document Your Configuration

```yaml
metadata:
  source: sec-edgar
  version: "1.0"
  created_date: "2024-11-18"
  notes: "Tech company financials - FAANG subset"
  companies: "Apple, Microsoft, Google, Amazon, Meta"
  coverage_period: "2020-2024"
```

### 5. Schedule Regular Updates

Update filings periodically:

```bash
# Monthly crawl for new filings
0 1 1 * * cd /path/to/vectara-ingest && bash run.sh config/edgar-quarterly.yaml default

# Or quarterly
0 1 1 1,4,7,10 * cd /path/to/vectara-ingest && bash run.sh config/edgar-quarterly.yaml default
```

### 6. Use Incremental Indexing

After initial full crawl, only fetch recent filings:

```yaml
vectara:
  reindex: false  # Don't delete old documents

edgar_crawler:
  # Only recent year
  start_date: "2024-01-01"
  end_date: "2024-12-31"
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/edgar-companies.yaml
```

Enter your configuration (see examples below).

### Run the Crawler

```bash
# Run the crawler
bash run.sh config/edgar-companies.yaml default

# Monitor progress
docker logs -f vingest
```

### Examples

#### Example 1: Single Large-Cap Company

```yaml
vectara:
  corpus_key: edgar-apple

crawling:
  crawler_type: edgar

edgar_crawler:
  tickers: ["AAPL"]
  start_date: "2020-01-01"
  end_date: "2024-12-31"
  filing_types: ["10-K", "10-Q", "8-K"]

metadata:
  company: Apple Inc.
  ticker: AAPL
  years: "2020-2024"
```

Save as `config/edgar-apple.yaml`:

```bash
bash run.sh config/edgar-apple.yaml default
```

#### Example 2: Tech Sector Companies

```yaml
vectara:
  corpus_key: edgar-tech

crawling:
  crawler_type: edgar

edgar_crawler:
  tickers:
    - "AAPL"
    - "MSFT"
    - "GOOG"
    - "NVDA"
    - "META"

  start_date: "2022-01-01"
  end_date: "2024-12-31"
  filing_types: ["10-K", "10-Q"]
  ray_workers: 4

metadata:
  sector: Technology
  focus: "Large-cap tech companies"
```

Save as `config/edgar-tech.yaml`:

```bash
bash run.sh config/edgar-tech.yaml default
```

#### Example 3: Broad Multi-Sector Crawl

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: edgar-market
  reindex: true
  verbose: true

crawling:
  crawler_type: edgar

edgar_crawler:
  tickers:
    - "AAPL"
    - "MSFT"
    - "JPM"
    - "JNJ"
    - "PG"
    - "XOM"
    - "UNH"

  start_date: "2020-01-01"
  end_date: "2024-12-31"
  filing_types: ["10-K", "10-Q", "8-K", "DEF 14A"]
  ray_workers: -1  # Use all CPU cores

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  market: "US Market"
  coverage: "Multi-sector S&P 500 subset"
  update_frequency: "quarterly"
```

#### Example 4: Historical Analysis

```yaml
vectara:
  corpus_key: edgar-historical

crawling:
  crawler_type: edgar

edgar_crawler:
  # Single company - historical analysis
  tickers: ["MSFT"]

  # Decade-long historical period
  start_date: "2014-01-01"
  end_date: "2024-12-31"

  # All filing types for comprehensive view
  filing_types: ["10-K", "10-Q", "8-K"]

  ray_workers: 1  # Single worker for stability

metadata:
  analysis_type: historical
  company: Microsoft Corporation
  period: "Decade view 2014-2024"
```

## Data Structure

### Document Title Format

```
TICKER-YYYY-MM-DD-FILING_TYPE
Example: AAPL-2024-02-15-10-K
```

### Typical Filing Content

**10-K (Annual Report)**:
- Business overview and segments
- Risk factors
- Financial statements (balance sheet, income statement, cash flow)
- Management discussion and analysis (MD&A)
- Executive compensation
- Related party transactions

**10-Q (Quarterly Report)**:
- Interim financial statements
- Quarterly MD&A
- Changes in internal controls
- Legal proceedings updates

**8-K (Current Report)**:
- Material events
- Executive changes
- Acquisitions/dispositions
- Bankruptcy or receivership
- Other material changes

**DEF 14A (Proxy Statement)**:
- Executive compensation details
- Board director information
- Corporate governance
- Shareholder voting matters

## Performance Considerations

### Network I/O

SEC filing downloads can be large. Typical performance:

- Single company (10-K only): 1-5 minutes
- Single company (10-K + 10-Q): 5-15 minutes
- 5 companies (all types): 15-45 minutes

### Storage Requirements

Estimate storage based on companies and date range:

- Single year of filings: ~50-100 MB per company
- 5 years of filings: ~250-500 MB per company
- 10 companies, 5 years: ~2.5-5 GB

### Memory Usage

- Sequential processing: ~500 MB - 1 GB
- Ray workers: ~2-3 GB per worker (4 workers = 8-12 GB)

### Optimization Tips

1. Use sequential processing for initial testing
2. Filter by filing types needed only
3. Use focused date ranges
4. Run during off-peak hours
5. Monitor memory usage and adjust worker count

## API Reference

### SEC EDGAR Resources

- [SEC EDGAR Search](https://www.sec.gov/cgi-bin/browse-edgar)
- [SEC EDGAR FTP Archive](https://www.sec.gov/edgar.shtml)
- [CIK Lookup Tool](https://www.sec.gov/cgi-bin/browse-edgar?company=&CIK=&type=&dateb=&owner=exclude&count=100&search_text=)

### Filing Type Reference

For complete list of SEC form types:
- [SEC Form Types Guide](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=&type=&dateb=&owner=exclude&count=100)

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide
- [SEC EDGAR Documentation](https://www.sec.gov/edgar.shtml)

## Monitoring and Logging

### Enable Verbose Logging

```yaml
vectara:
  verbose: true
```

### Watch Crawler Progress

```bash
docker logs -f vingest | tail -50
```

### Parse Log Output

```bash
# Show indexed filings
docker logs -f vingest | grep "Indexing succeeded"

# Show errors
docker logs -f vingest | grep "Error"

# Count filings per company
docker logs -f vingest | grep "downloaded"
```

## Support

For issues:

1. Check [SEC EDGAR website](https://www.sec.gov)
2. Verify ticker symbols are correct
3. Confirm date range contains actual filings
4. Check [Troubleshooting Guide](../deployment/troubleshooting.md)
5. Open [GitHub issue](https://github.com/vectara/vectara-ingest/issues)
