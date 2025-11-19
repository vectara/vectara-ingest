# Website Crawler

The Website crawler indexes content from any website with advanced features including multiple crawl methods (Scrapy or internal), SAML authentication, URL filtering, parallel processing with Ray, and automatic old content removal. It supports sitemap-based crawling, depth-limited recursive crawling, and sophisticated URL pattern matching.

## Overview

- **Crawler Type**: `website`
- **Crawl Methods**: Scrapy (fast, distributed) or Internal (memory-efficient, Playwright-based)
- **Authentication**: SAML, Basic Auth, Custom Headers, or No Authentication
- **Content Extraction**: Intelligent boilerplate removal, CSS selectors, or full page content
- **Parallel Processing**: Ray workers for distributed crawling
- **URL Discovery**: Sitemap parsing or recursive depth-limited crawling
- **URL Filtering**: Positive/negative regex patterns with automatic exclusions
- **Crawl Reports**: Optional reports of indexed and removed URLs
- **Old Content Removal**: Automatic deletion of previously indexed URLs no longer in crawl scope

## Use Cases

- Index company websites and marketing materials
- Crawl product documentation and help sites
- Archive blog content and news articles
- Create searchable knowledge bases from web content
- Index internal enterprise wikis and technical documentation
- Crawl multi-domain properties with consistent filtering
- Monitor and re-crawl sites for content updates

## Getting Started: Basic Website Crawl

### Simplest Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: website-index

crawling:
  crawler_type: website

website_crawler:
  # Website to crawl
  urls:
    - https://example.com

  # How deep to crawl
  max_depth: 3

  # Discover pages from sitemap or by crawling links
  pages_source: sitemap  # or "crawl"
```

### Set Environment Variables

For SAML-protected sites, set credentials:

```bash
export SAML_USERNAME="user@example.com"
export SAML_PASSWORD="password"
```

For basic authentication:

```bash
export WEBSITE_USERNAME="username"
export WEBSITE_PASSWORD="password"
```

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: website-content
  reindex: false

crawling:
  crawler_type: website

website_crawler:
  # List of starting URLs or sitemaps
  urls:
    - https://example.com
    - https://example.com/sitemap.xml

  # Choose how to discover pages
  pages_source: sitemap  # "sitemap" or "crawl"

  # Maximum crawl depth (only for pages_source: crawl)
  max_depth: 3

  # URL patterns to include (regex)
  pos_regex:
    - "https://example\\.com/docs/.*"
    - "https://example\\.com/blog/.*"

  # URL patterns to exclude (regex)
  neg_regex:
    - ".*\\.pdf$"
    - ".*/admin/.*"
    - ".*/login.*"

metadata:
  source: website
  category: documentation
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: website-full
  reindex: false
  verbose: true
  remove_boilerplate: true

crawling:
  crawler_type: website

website_crawler:
  # Starting URLs
  urls:
    - https://docs.example.com
    - https://api.example.com/sitemap.xml

  # Discovery method
  pages_source: crawl
  max_depth: 5

  # URL filtering
  pos_regex:
    - "https://docs\\.example\\.com/.*"
    - "https://api\\.example\\.com/.*"
  neg_regex:
    - ".*/deprecated/.*"
    - ".*/internal/.*"
    - ".*/admin.*"
    - ".*\\.(pdf|zip|exe)$"

  # Query parameter handling
  keep_query_params: false

  # Crawling method (scrapy or internal)
  crawl_method: scrapy

  # Rate limiting
  num_per_second: 10

  # Parallel processing
  ray_workers: 0  # 0=sequential, -1=all CPU cores, N=N workers

  # Page discovery source method
  source: website

  # Performance limits
  max_pages: 5000

  # HTML processing options
  html_processing:
    extract_links: true
    extract_metadata: true

  # SAML authentication (if required)
  saml_auth:
    login_url: "https://idp.example.com/login"
    username_field: "username"
    password_field: "password"
    login_failure_string: "Invalid credentials"

  # CSS selectors for content extraction
  css_selectors:
    - "article.main-content"
    - "div.documentation"
    - "main"

  # Crawl reports
  crawl_report: true

  # Remove old content
  remove_old_content: false

doc_processing:
  doc_parser: unstructured
  process_locally: true

metadata:
  source: website
  environment: production
  sync_frequency: daily
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `urls` | list | Yes | - | Starting URLs or sitemap URLs to crawl |
| `pages_source` | string | No | `sitemap` | How to discover pages: `sitemap` or `crawl` |
| `max_depth` | int | No | `3` | Maximum crawl depth (only for `pages_source: crawl`) |
| `pos_regex` | list | No | `[]` | Regex patterns for URLs to include |
| `neg_regex` | list | No | `[]` | Regex patterns for URLs to exclude |
| `keep_query_params` | bool | No | `false` | Whether to keep query parameters in URLs |
| `crawl_method` | string | No | `internal` | Crawling method: `scrapy` or `internal` |
| `num_per_second` | int | No | `10` | Rate limiting: requests per second |
| `ray_workers` | int | No | `0` | Parallel workers: 0=sequential, -1=all cores, N=N workers |
| `source` | string | No | `website` | Source name for metadata |
| `max_pages` | int | No | `10000` | Maximum number of pages to crawl |
| `html_processing` | dict | No | `{}` | HTML processing options |
| `css_selectors` | list | No | `[]` | CSS selectors for content extraction |
| `saml_auth` | dict | No | - | SAML authentication configuration |
| `crawl_report` | bool | No | `false` | Generate report of indexed URLs |
| `remove_old_content` | bool | No | `false` | Remove previously indexed URLs no longer in crawl list |
| `saml_username` | string | No (with SAML) | - | SAML username (from secrets) |
| `saml_password` | string | No (with SAML) | - | SAML password (from secrets) |

## Crawl Methods Comparison

### Scrapy Method (Fast, Distributed)

Best for: Large websites, distributed crawling, speed-critical applications

```yaml
website_crawler:
  crawl_method: scrapy
  ray_workers: 4  # Can use parallel workers
```

**Advantages**:
- Significantly faster than internal crawler
- Built-in support for distributed crawling
- Better handling of large-scale sites
- Mature, production-tested framework
- Can process SAML-authenticated sites via Playwright

**Disadvantages**:
- Requires Scrapy library installed
- Less flexible for complex HTML parsing
- JavaScript-rendered content may not be captured
- Cannot use custom CSS selectors as effectively

**When to Use**:
- Crawling large documentation sites (100+ pages)
- Speed is critical
- Pages are static HTML (not JavaScript-heavy)
- Using parallel processing with Ray workers

### Internal Method (Memory-Efficient, Flexible)

Best for: Complex sites, JavaScript-heavy content, custom extraction

```yaml
website_crawler:
  crawl_method: internal
  ray_workers: 0  # Sequential processing
```

**Advantages**:
- Uses Playwright for JavaScript rendering
- More flexible content extraction
- Handles complex authentication flows
- Can apply custom CSS selectors
- Better for dynamic content
- SAML authentication fully supported

**Disadvantages**:
- Slower than Scrapy (browser-based)
- Higher memory usage
- Parallel processing with Ray requires more resources
- Limited support for very large crawls (10000+ pages)

**When to Use**:
- Sites with JavaScript-rendered content
- Need custom CSS selector extraction
- SAML/complex authentication required
- Small to medium websites (< 1000 pages)
- Higher content extraction quality needed

## Pages Source Methods

### Sitemap Method (Recommended)

The crawler fetches and parses XML sitemaps to discover URLs:

```yaml
website_crawler:
  pages_source: sitemap
  urls:
    - https://example.com/sitemap.xml
    - https://example.com/sitemap-docs.xml
    - https://example.com/sitemap-blog.xml
```

**How it works**:
1. Fetches XML sitemap(s) from specified URLs
2. Parses `<loc>` elements to extract URLs
3. Applies pos_regex and neg_regex filters
4. Returns unique, filtered URL list

**Advantages**:
- Most efficient method (no recursive crawling needed)
- Exact URL list from site maintainers
- No risk of missing pages
- Respects site structure via sitemap

**Disadvantages**:
- Requires site to have sitemap.xml
- Only finds URLs in sitemap (might miss unlisted pages)
- Must handle multi-level sitemaps manually

**Best Practices**:
- Always use sitemap if available
- Check robots.txt for sitemap.xml location
- Handle paginated sitemaps (sitemap_index.xml)
- Test sitemap parsing before production crawl

### Crawl Method (Discovery-Based)

The crawler recursively discovers URLs by following links:

```yaml
website_crawler:
  pages_source: crawl
  max_depth: 3
  urls:
    - https://example.com
```

**How it works**:
1. Fetches the starting URL
2. Extracts all links from the page
3. Filters by pos_regex and neg_regex
4. Recursively crawls each new URL up to max_depth
5. Deduplicates and returns complete URL list

**Advantages**:
- Works without sitemap
- Discovers dynamically-generated pages
- Can crawl hidden/unlisted pages
- Flexible depth control

**Disadvantages**:
- Much slower than sitemap method
- May discover unintended pages
- Depth limits risk missing pages
- Higher bandwidth usage

**Best Practices**:
- Start with small max_depth (2-3) for testing
- Use positive regex to limit scope
- Use negative regex to exclude admin pages
- Monitor logs for URL explosion
- Set reasonable max_pages limit as safety valve

## URL Filtering with Examples

### Positive Regex (Include Patterns)

Only crawl URLs matching at least one positive pattern:

```yaml
website_crawler:
  pos_regex:
    # Match docs subpath
    - "https://example\\.com/docs/.*"

    # Match blog articles
    - "https://example\\.com/blog/[0-9]{4}/[0-9]{2}/.*"

    # Match knowledge base
    - "https://kb\\.example\\.com/.*"

    # Match pages with /en/ language prefix
    - "https://example\\.com/en/.*"
```

**Examples**:
- `"https://docs\\.example\\.com/.*"` - All docs subdomain pages
- `"^https://.*\\.example\\.com/.*"` - All subdomains
- `".*/api/.*"` - Any path containing /api/
- `".*/v[0-9]+/.*"` - Versioned content paths
- `".*\\.example\\.com/en/.*"` - English language only

### Negative Regex (Exclude Patterns)

Skip URLs matching any negative pattern:

```yaml
website_crawler:
  neg_regex:
    # Exclude PDFs and archives
    - ".*\\.(pdf|zip|exe|dmg)$"

    # Exclude admin areas
    - ".*/admin/.*"
    - ".*/dashboard/.*"

    # Exclude authentication pages
    - ".*/login.*"
    - ".*/logout.*"
    - ".*/signin.*"

    # Exclude deprecated paths
    - ".*/deprecated/.*"
    - ".*/old/.*"
    - ".*/legacy/.*"

    # Exclude search and filters
    - ".*/search.*"
    - ".*\\?.*"  # URLs with query parameters

    # Exclude media files
    - ".*\\.(jpg|png|gif|webp|mp4|webm)$"

    # Exclude user-specific pages
    - ".*/users/.*"
    - ".*/profile/.*"
```

**Common Patterns**:
- `".*\\.(pdf|doc|xls)$"` - Document files
- `.*/admin/.*` - Admin interface
- `.*/account/.*` - User accounts
- `.*/settings/.*` - Settings pages
- `.*=.*` or `.*\\?.*` - URLs with parameters
- `.*\\.jpg$`, `.*\\.png$` - Image files

### Combined Filtering Example

```yaml
website_crawler:
  urls:
    - https://docs.example.com

  # INCLUDE only documentation
  pos_regex:
    - "https://docs\\.example\\.com/en/.*"

  # EXCLUDE everything else
  neg_regex:
    - ".*\\.pdf$"
    - ".*/admin/.*"
    - ".*/staging/.*"
    - ".*\\?.*"
    - ".*/search.*"
    - ".*/media/.*"
    - ".*/assets/.*"
```

**How filtering works**:
1. Start with all discovered URLs
2. Apply neg_regex - remove matching URLs
3. Apply pos_regex - keep only matching URLs (if specified)
4. Result: URLs matching no negative patterns AND (all positive patterns OR no positive patterns specified)

### URL Deduplication

Query parameters are handled based on configuration:

```yaml
website_crawler:
  # Keep query parameters (may create duplicates)
  keep_query_params: true

  # Strip query parameters (default, deduplicates)
  keep_query_params: false
```

**Examples**:
- Keep: `/page?ref=header` and `/page?ref=footer` → 2 URLs
- Strip: `/page?ref=header` and `/page?ref=footer` → 1 URL (`/page`)

## SAML Authentication Setup

For websites protected by SAML-based single sign-on:

### Understanding SAML Flow

1. Client requests protected page
2. Site redirects to IdP (Identity Provider)
3. User logs in at IdP
4. IdP sends SAML assertion back to site
5. Site sets authentication cookies
6. Subsequent requests use cookies

The Website crawler automates this entire flow.

### Configuration

```yaml
website_crawler:
  urls:
    - https://app.example.com

  # Enable SAML authentication
  saml_auth:
    # URL where authentication flow starts
    login_url: "https://app.example.com/login"

    # HTML form field name for username
    username_field: "username"

    # HTML form field name for password
    password_field: "password"

    # String that appears on page if login failed
    login_failure_string: "Invalid username or password"

    # Optional: Extra form data to submit
    extra_form_data:
      mfa_code: "123456"  # If MFA required

  # SAML credentials (from secrets)
  saml_username: "${SAML_USERNAME}"
  saml_password: "${SAML_PASSWORD}"
```

### Setting Credentials

Store SAML credentials securely in `secrets.toml`:

```toml
[default]
api_key = "your-vectara-api-key"
SAML_USERNAME = "user@example.com"
SAML_PASSWORD = "your-password"
```

Or set environment variables:

```bash
export SAML_USERNAME="user@example.com"
export SAML_PASSWORD="your-password"
```

### SAML Authentication Methods

#### Method 1: Internal Crawler with Requests (Basic SAML)

Works for standard form-based SAML:

```yaml
website_crawler:
  crawl_method: internal
  saml_auth:
    login_url: "https://idp.example.com/login"
    username_field: "username"
    password_field: "password"
```

Best for: Simple SAML flows, basic form authentication

#### Method 2: Scrapy with Playwright (Complex SAML)

Uses browser automation for complex flows (Okta, Azure AD):

```yaml
website_crawler:
  crawl_method: scrapy
  saml_auth:
    login_url: "https://okta.example.com/app/example/1234/sign-in"
    username_field: "okta_username"
    password_field: "okta_password"
```

Best for: JavaScript-heavy IdP, MFA, complex flows

**Note**: Playwright-based auth is used automatically when needed with Scrapy method

#### Method 3: Internal Crawler with Playwright (JavaScript-Heavy SAML)

```yaml
website_crawler:
  crawl_method: internal
  saml_auth:
    login_url: "https://azure-ad.example.com/oauth2/v2.0/authorize"
    username_field: "input[name='loginfmt']"
    password_field: "input[name='passwd']"
    login_failure_string: "Invalid credentials"
```

Best for: Complex IdP (Okta, Azure, OneLogin), dynamic forms

### SAML Troubleshooting

**Authentication succeeds but pages show "not authenticated"**:
- SAML cookies may not be transferred to subsequent requests
- Check that cookies are being set and sent
- Verify authentication scope (same domain)

**Form fields not found**:
- Inspect browser dev tools to find correct field names
- Some IdPs use dynamic IDs - use CSS selectors instead
- Check `username_field` and `password_field` values

**Login failure string not working**:
- Verify exact string appears on failure page
- May be case-sensitive or have extra whitespace
- Remove or adjust if needed

**Multi-factor authentication required**:
- Add MFA code to `extra_form_data` if static
- For time-based (TOTP), you'll need to provide current code
- Some MFA flows require manual handling (not supported)

## Content Extraction

### Automatic Extraction (Default)

By default, the crawler extracts main content intelligently:

```yaml
vectara:
  remove_boilerplate: true  # Remove ads, navigation, sidebars
```

This uses heuristics to identify and extract article-like content while removing:
- Navigation menus
- Sidebars and widgets
- Ads and promotional content
- Headers and footers
- Comments sections

### Custom CSS Selectors

Target specific content with CSS selectors:

```yaml
website_crawler:
  css_selectors:
    - "article"           # Use <article> tag
    - "div.content"       # Use div with class "content"
    - "main"              # Use <main> tag
    - "#main-content"     # Use element with id "main-content"
```

**Common Selectors**:
- `"article"` - Article wrapper
- `"main"` - Main content area
- `"div.content"` or `"div.main"` - Content containers
- `"div.post-content"` - Blog post content
- `".documentation"` - Documentation container
- `"#content"` - ID-based selector

**Selector Examples by Site Type**:

Documentation sites:
```yaml
css_selectors:
  - "main"
  - "article"
  - ".content-wrapper"
```

Blog sites:
```yaml
css_selectors:
  - "article.post"
  - "div.post-content"
  - ".entry-content"
```

Product pages:
```yaml
css_selectors:
  - "div.product-description"
  - "div.product-specs"
  - ".product-details"
```

### HTML Processing Options

Control how HTML is processed:

```yaml
website_crawler:
  html_processing:
    extract_links: true          # Extract and preserve links
    extract_metadata: true       # Extract metadata tags
    remove_scripts: true         # Remove script tags
    remove_styles: true          # Remove style tags
```

## Metadata Extraction

The crawler automatically extracts and indexes:

- **Page Title**: From `<title>` or `<h1>` tag
- **Meta Description**: From `<meta name="description">` tag
- **Author**: From meta tags or schema.org data
- **Publication Date**: From meta tags or schema.org
- **Last Modified**: From HTTP headers or meta tags
- **URL**: Source URL of the page
- **Source**: Always "website"
- **Custom Metadata**: From YAML configuration

### Custom Metadata

Add static metadata to all indexed pages:

```yaml
metadata:
  source: website
  category: documentation
  department: engineering
  environment: production
  sync_frequency: daily
  content_type: technical
```

This metadata is attached to every indexed document.

## Performance Optimization

### 1. Choose Correct Crawl Method

For **speed** with static sites:
```yaml
website_crawler:
  crawl_method: scrapy
  ray_workers: 4
```

For **reliability** with complex sites:
```yaml
website_crawler:
  crawl_method: internal
  ray_workers: 0
```

### 2. Rate Limiting

Control request rate to avoid overwhelming servers:

```yaml
website_crawler:
  # Requests per second (default: 10)
  num_per_second: 5  # Slower, more respectful
```

**Recommendations**:
- Public sites: 10-20 requests/second
- Protected sites: 5-10 requests/second
- Rate-limited sites: 1-5 requests/second

### 3. Parallel Processing with Ray

Distribute crawling across CPU cores:

```yaml
website_crawler:
  ray_workers: 0    # Sequential (default, low memory)
  ray_workers: 4    # 4 parallel workers
  ray_workers: -1   # All CPU cores
```

**When to use**:
- Large sites (1000+ pages)
- 4+ CPU cores available
- Sufficient memory (> 4GB)
- Pages fetch quickly

**Memory considerations**:
- Each worker maintains browser/HTTP session
- Ray workers add ~200-300MB each
- Monitor memory usage: `top` or `htop`

### 4. URL Filtering

Reduce scope to crawl only necessary content:

```yaml
website_crawler:
  # GOOD: Narrow scope
  pos_regex:
    - "https://docs\\.example\\.com/en/v[1-2]/.*"
  neg_regex:
    - ".*/deprecated/.*"

  # BAD: Too broad, may crawl too much
  urls:
    - https://example.com  # Crawls entire domain
```

### 5. Depth Limitation

Start with shallow depth and increase as needed:

```yaml
website_crawler:
  pages_source: crawl
  max_depth: 2  # Start here
  max_pages: 500  # Safety limit
```

### 6. Query Parameter Handling

Deduplicate URLs by stripping query parameters:

```yaml
website_crawler:
  keep_query_params: false  # Strip tracking params
```

URLs like `/page?ref=header` and `/page?ref=footer` become single `/page`

### 7. Scheduling

Run crawls during off-peak hours:

```bash
# Daily at 2 AM
0 2 * * * cd /path && bash run.sh config/website.yaml default
```

### 8. Batch Large Sites

Split very large sites into multiple configs:

```yaml
# config/docs-v1.yaml
website_crawler:
  urls:
    - https://docs.example.com/v1

# config/docs-v2.yaml
website_crawler:
  urls:
    - https://docs.example.com/v2
```

Run sequentially or on different schedules.

## Crawl Reports and Old Content Removal

### Generate Crawl Reports

Create reports of indexed and removed URLs:

```yaml
website_crawler:
  crawl_report: true
```

This generates:
- `urls_indexed.txt` - All URLs successfully indexed
- `urls_removed.txt` - URLs removed from corpus

**Output location**: Specified by `vectara.output_dir` (default: `vectara_ingest_output/`)

**Usage**:
- Verify correct URLs were crawled
- Audit removed content
- Track coverage over time
- Debug filtering issues

### Remove Old Content

Automatically delete previously indexed URLs that are no longer in the crawl list:

```yaml
website_crawler:
  remove_old_content: true
  crawl_report: true
```

**How it works**:
1. Crawls and discovers current URLs
2. Queries Vectara for previously indexed URLs
3. Identifies URLs in corpus but not in crawl
4. Deletes those documents from corpus
5. Reports removed URLs to `urls_removed.txt`

**Use Cases**:
- Site restructures, some pages removed
- Deprecated documentation deleted
- Regular maintenance crawls
- Keeping index in sync with live site

**Warnings**:
- Irreversibly deletes documents from Vectara
- Should only enable for sites you control
- Test with `crawl_report: true` before enabling
- Always have a backup/recovery plan

## Troubleshooting

### Pages Not Being Crawled

**Symptom**: Few or no pages indexed despite large website

**Solutions**:

1. **Check `max_depth` setting**:
   ```yaml
   website_crawler:
     max_depth: 5  # Increase if too shallow
   ```

2. **Verify URL patterns**:
   ```bash
   # Test regex patterns
   python -c "import re; print(re.match(r'https://example\.com/docs/.*', 'https://example.com/docs/intro'))"
   ```

3. **Check negative regex excludes**:
   ```yaml
   neg_regex:
     - ".*\\?.*"  # Might exclude paginated content
   ```

4. **Switch to sitemap method**:
   ```yaml
   pages_source: sitemap  # More reliable than crawl
   ```

5. **Enable verbose logging**:
   ```yaml
   vectara:
     verbose: true
   ```

### JavaScript-Heavy Sites

**Symptom**: Content appears as blank or incomplete

**Solution**: Use internal crawler (includes Playwright):

```yaml
website_crawler:
  crawl_method: internal  # Uses Playwright
```

Or increase post-load timeout:

```yaml
vectara:
  post_load_timeout: 10  # Wait 10 seconds after page load
```

### Rate Limiting / Getting Blocked

**Symptom**: HTTP 429, 403, or IP blocking errors

**Solutions**:

1. **Increase delay between requests**:
   ```yaml
   website_crawler:
     num_per_second: 2  # Very slow, respectful
   ```

2. **Use custom user agent**:
   ```yaml
   website_crawler:
     user_agent: "MyBot/1.0 (contact@example.com)"
   ```

3. **Reduce ray_workers**:
   ```yaml
   website_crawler:
     ray_workers: 0  # Sequential instead of parallel
   ```

4. **Run during off-peak**:
   ```bash
   # Schedule for late night
   0 2 * * * bash run.sh config/website.yaml default
   ```

5. **Contact site administrator**:
   - Identify yourself in user agent
   - Request permission to crawl
   - Ask for rate limit guidelines

### SSL Certificate Errors

**Symptom**: `SSL: CERTIFICATE_VERIFY_FAILED` errors

**Solutions**:

1. **For self-signed certificates** (development):
   ```bash
   export SSL_NO_VERIFY=true
   bash run.sh config/website.yaml default
   ```

2. **Update CA certificates**:
   ```bash
   pip install --upgrade certifi
   ```

3. **For corporate proxy/firewall**:
   - Add custom CA certificate to system
   - Contact IT department

### Authentication Failures

**Symptom**: SAML, Basic Auth, or cookie-based auth failing

**Solutions**:

1. **Verify credentials**:
   ```bash
   echo $SAML_USERNAME
   echo $SAML_PASSWORD
   ```

2. **Test login manually**:
   - Manually visit login URL
   - Verify credentials work
   - Check for MFA requirements

3. **Check form field names**:
   ```yaml
   saml_auth:
     username_field: "username"  # Inspect HTML to verify
     password_field: "password"
   ```

4. **Look for failure string**:
   ```yaml
   saml_auth:
     login_failure_string: "Invalid login"  # Site-specific
   ```

5. **Try different crawl method**:
   ```yaml
   crawl_method: internal  # vs scrapy
   ```

### Memory Issues / Crashes

**Symptom**: Process killed, "Out of memory", or system becomes unresponsive

**Solutions**:

1. **Disable parallel processing**:
   ```yaml
   website_crawler:
     ray_workers: 0  # Use sequential
   ```

2. **Reduce ray_workers**:
   ```yaml
   website_crawler:
     ray_workers: 2  # Instead of 4
   ```

3. **Limit crawl scope**:
   ```yaml
   website_crawler:
     max_pages: 1000  # Smaller crawls
     max_depth: 2     # Shallower crawls
   ```

4. **Use Scrapy instead of internal**:
   ```yaml
   website_crawler:
     crawl_method: scrapy  # More memory-efficient
   ```

5. **Split into multiple crawls**:
   Create separate configs for different site sections

### No Content Extracted

**Symptom**: URLs indexed but with empty or minimal content

**Solutions**:

1. **Enable boilerplate removal**:
   ```yaml
   vectara:
     remove_boilerplate: true
   ```

2. **Specify CSS selectors**:
   ```yaml
   website_crawler:
     css_selectors:
       - "article"
       - "main"
   ```

3. **Check page source manually**:
   - Visit page in browser
   - View page source (Ctrl+U)
   - Verify content is in HTML (not JavaScript)

4. **Increase JavaScript rendering time**:
   ```yaml
   vectara:
     post_load_timeout: 10
   ```

## Best Practices

### 1. Start Small and Scale

Begin with a limited crawl to validate configuration:

```yaml
# Test config
website_crawler:
  urls:
    - https://example.com
  max_depth: 1
  max_pages: 50
  crawl_report: true
```

Once validated, expand scope:

```yaml
# Production config
website_crawler:
  max_depth: 3
  max_pages: 5000
```

### 2. Use Sitemaps When Available

```yaml
# PREFER: Sitemap method
website_crawler:
  pages_source: sitemap
  urls:
    - https://example.com/sitemap.xml

# AVOID: Recursive crawling
website_crawler:
  pages_source: crawl
  max_depth: 5  # Slower, less reliable
```

### 3. Filter Aggressively

```yaml
website_crawler:
  pos_regex:
    - "https://example\\.com/docs/.*"  # Only docs

  neg_regex:
    - ".*/deprecated/.*"
    - ".*/admin/.*"
    - ".*\\.pdf$"
    - ".*/media/.*"
```

### 4. Respect Rate Limits

```yaml
website_crawler:
  num_per_second: 5  # Respectful rate
  ray_workers: 0     # Sequential when starting
```

### 5. Preserve Site Owners' Bandwidth

```bash
# Run during off-peak hours
0 2 * * * bash run.sh config/website.yaml default

# Or manually with appropriate delays
```

### 6. Add Descriptive Metadata

```yaml
metadata:
  source: website
  site: example.com
  category: documentation
  language: en
  last_updated: "2024-11-18"
```

### 7. Monitor Crawl Progress

```yaml
vectara:
  verbose: true
```

Watch logs in real-time:

```bash
docker logs -f vingest
```

### 8. Version Your Configurations

```yaml
metadata:
  config_version: "2.0"
  last_modified: "2024-11-18"
  notes: "Added new documentation section"
```

### 9. Test URL Patterns Before Production

```python
import re

# Test your patterns
pos_pattern = re.compile(r'https://docs\.example\.com/.*')
neg_pattern = re.compile(r'.*/deprecated/.*')

test_urls = [
    'https://docs.example.com/intro',           # Should match
    'https://docs.example.com/deprecated/old',  # Should be filtered
    'https://api.example.com/docs',             # Should not match
]

for url in test_urls:
    included = bool(pos_pattern.match(url)) and not neg_pattern.match(url)
    print(f"{url}: {included}")
```

### 10. Backup and Recovery

Before enabling `remove_old_content`:

```bash
# List all indexed documents first
curl -X POST https://api.vectara.io/v1/list-docs \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"corpus_key": "your-corpus"}'
```

Then enable with confidence:

```yaml
website_crawler:
  remove_old_content: true
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/website-docs.yaml
```

### Set Credentials (If Required)

```bash
# For SAML
export SAML_USERNAME="user@example.com"
export SAML_PASSWORD="your-password"

# For Basic Auth
export WEBSITE_USERNAME="username"
export WEBSITE_PASSWORD="password"
```

### Run the Crawler

```bash
# Run once
bash run.sh config/website-docs.yaml default

# Monitor progress
docker logs -f vingest
```

### Schedule Regular Crawls

Using cron:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/website.yaml default

# Multiple times per day
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/website.yaml default
```

Or use GitHub Actions, Jenkins, or other schedulers.

## Complete Examples

### Example 1: Simple Documentation Site (Sitemap)

```yaml
# config/docs-simple.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: docs-index
  remove_boilerplate: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://docs.example.com/sitemap.xml
  pages_source: sitemap
  pos_regex:
    - "https://docs\\.example\\.com/en/.*"
  neg_regex:
    - ".*/api/.*"
    - ".*\\.pdf$"

metadata:
  source: website
  category: documentation
```

Run:
```bash
bash run.sh config/docs-simple.yaml default
```

### Example 2: Blog with Recursive Crawling

```yaml
# config/blog-crawl.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: blog-articles
  remove_boilerplate: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://blog.example.com
  pages_source: crawl
  max_depth: 2
  pos_regex:
    - "https://blog\\.example\\.com/[0-9]{4}/[0-9]{2}/.*"
  neg_regex:
    - ".*/search.*"
    - ".*/category/.*"
    - ".*\\?.*"
  css_selectors:
    - "article.post-content"
  ray_workers: 2

metadata:
  source: website
  category: blog
  content_type: articles
```

Run:
```bash
bash run.sh config/blog-crawl.yaml default
```

### Example 3: SAML-Protected Enterprise Documentation

```yaml
# config/internal-docs-saml.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: internal-docs
  remove_boilerplate: true
  verbose: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://internal-wiki.example.com
  pages_source: crawl
  max_depth: 3
  max_pages: 1000

  # SAML authentication
  saml_auth:
    login_url: "https://idp.example.com/oauth2/authorize"
    username_field: "username"
    password_field: "password"
    login_failure_string: "Invalid credentials"

  saml_username: "${SAML_USERNAME}"
  saml_password: "${SAML_PASSWORD}"

  # Filtering
  pos_regex:
    - "https://internal-wiki\\.example\\.com/en/.*"
  neg_regex:
    - ".*/admin/.*"
    - ".*/draft/.*"

  crawl_method: internal
  num_per_second: 5

metadata:
  source: website
  environment: internal
  security_level: confidential
```

Set credentials:
```bash
export SAML_USERNAME="your.email@example.com"
export SAML_PASSWORD="your-password"
```

Run:
```bash
bash run.sh config/internal-docs-saml.yaml default
```

### Example 4: Large Site with Scrapy and Ray

```yaml
# config/large-site-scrapy.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: large-site-index
  reindex: false
  verbose: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://example.com/sitemap.xml
  pages_source: sitemap

  # Fast crawling with Scrapy
  crawl_method: scrapy
  ray_workers: 4
  num_per_second: 20

  # Aggressive filtering
  pos_regex:
    - "https://example\\.com/docs/.*"
    - "https://example\\.com/guide/.*"
  neg_regex:
    - ".*/deprecated/.*"
    - ".*/internal/.*"
    - ".*\\.(pdf|zip)$"
    - ".*/admin/.*"
    - ".*/search.*"

  # Reports and maintenance
  crawl_report: true
  remove_old_content: true
  max_pages: 10000

metadata:
  source: website
  site: example.com
  sync_frequency: daily
  content_types:
    - documentation
    - guides
    - tutorials
```

Run:
```bash
bash run.sh config/large-site-scrapy.yaml default
```

### Example 5: Multi-Section Site with Custom Selectors

```yaml
# config/complex-site.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: complex-index
  remove_boilerplate: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://help.example.com/sitemap.xml
    - https://developers.example.com/sitemap.xml
  pages_source: sitemap

  # Extract specific content
  css_selectors:
    - "article"
    - "main"
    - ".content"
    - "#documentation"

  # Filter by section
  pos_regex:
    - "https://help\\.example\\.com/en/.*"
    - "https://developers\\.example\\.com/api/.*"
  neg_regex:
    - ".*/beta/.*"
    - ".*/internal/.*"
    - ".*/search.*"

  crawl_method: internal
  ray_workers: 0
  num_per_second: 10

  html_processing:
    extract_metadata: true
    extract_links: true

metadata:
  source: website
  sections:
    - help
    - developer
  language: en
```

Run:
```bash
bash run.sh config/complex-site.yaml default
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide
- [Advanced: Custom Crawlers](../advanced/custom-crawler.md) - Building custom crawlers

## Additional Resources

- [Scrapy Documentation](https://docs.scrapy.org/) - Details on Scrapy crawler framework
- [Playwright Documentation](https://playwright.dev/) - JavaScript rendering automation
- [Regular Expressions Guide](https://www.regular-expressions.info/) - Regex pattern reference
- [SAML Specification](https://en.wikipedia.org/wiki/SAML_2.0) - SAML 2.0 overview
