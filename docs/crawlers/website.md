# Website Crawler

The Website crawler indexes content from any website with advanced features including multiple crawl methods (Scrapy or internal), SAML authentication, URL filtering, parallel processing with Ray, and automatic old content removal. It supports sitemap-based crawling, depth-limited recursive crawling, and sophisticated URL pattern matching.

## Overview

<div class="crawler-info-cards">
  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>
      </div>
      <strong>Crawler Type</strong>
    </div>
    <code>website</code>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l4.2 4.2M23 12h-6m-6 0H5m13.2 5.2l-4.2-4.2m0-6l4.2-4.2"></path></svg>
      </div>
      <strong>Crawl Methods</strong>
    </div>
    <p>Scrapy (fast, distributed) or Internal (Playwright-based)</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
      </div>
      <strong>Authentication</strong>
    </div>
    <p>SAML, Basic Auth, Custom Headers</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
      </div>
      <strong>URL Discovery</strong>
    </div>
    <p>Sitemap parsing or recursive crawling</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.35-4.35"></path><line x1="11" y1="8" x2="11" y2="14"></line><line x1="8" y1="11" x2="14" y2="11"></line></svg>
      </div>
      <strong>URL Filtering</strong>
    </div>
    <p>Positive/negative regex patterns</p>
  </div>

  <div class="crawler-info-card">
    <div class="crawler-info-header">
      <div class="crawler-info-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
      </div>
      <strong>Content Extraction</strong>
    </div>
    <p>CSS selectors or automatic boilerplate removal</p>
  </div>
</div>

## How It Works

<div class="use-cases-list">
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>URL Discovery</strong> - Collects URLs either by parsing XML sitemaps or recursively crawling links from starting URLs</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>URL Filtering</strong> - Applies positive and negative regex patterns to filter the URL list</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Authentication</strong> - Handles SAML, Basic Auth, or custom authentication if configured</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Content Fetching</strong> - Retrieves pages using either Scrapy (fast) or Playwright (JavaScript support)</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Content Extraction</strong> - Extracts text using CSS selectors or automatic boilerplate removal</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Indexing</strong> - Sends extracted content to Vectara for indexing</span>
  </div>
  <div class="use-case-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span><strong>Old Content Removal</strong> - Optionally removes previously indexed URLs that are no longer in scope</span>
  </div>
</div>

## Crawl Methods

<div class="crawl-methods-grid">
  <div class="method-card">
    <h3>Scrapy Method</h3>
    <p>Fast, distributed crawling using the Scrapy framework.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  crawl_method: scrapy<br>  ray_workers: 4</code>
    </div>

    <div class="method-section">
      <h4>Best for:</h4>
      <ul>
        <li>Large websites (100+ pages)</li>
        <li>Static HTML content</li>
        <li>Speed-critical applications</li>
        <li>Parallel processing with Ray</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Advantages:</h4>
      <ul>
        <li>Significantly faster than internal crawler</li>
        <li>Built-in distributed crawling support</li>
        <li>Mature, production-tested framework</li>
        <li>Efficient resource usage</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Limitations:</h4>
      <ul>
        <li>JavaScript-rendered content may not be captured</li>
        <li>Less flexible for complex HTML parsing</li>
        <li>Requires Scrapy library installed</li>
      </ul>
    </div>
  </div>

  <div class="method-card">
    <h3>Internal Method</h3>
    <p>Browser-based crawling using Playwright for JavaScript support.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  crawl_method: internal<br>  ray_workers: 0</code>
    </div>

    <div class="method-section">
      <h4>Best for:</h4>
      <ul>
        <li>JavaScript-heavy websites</li>
        <li>Complex authentication flows</li>
        <li>Custom CSS selector extraction</li>
        <li>Small to medium sites (< 1000 pages)</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Advantages:</h4>
      <ul>
        <li>Full JavaScript rendering support</li>
        <li>More flexible content extraction</li>
        <li>Better handling of dynamic content</li>
        <li>Full SAML authentication support</li>
      </ul>
    </div>

    <div class="method-section">
      <h4>Limitations:</h4>
      <ul>
        <li>Slower than Scrapy (browser-based)</li>
        <li>Higher memory usage</li>
        <li>Less efficient for large-scale crawls</li>
      </ul>
    </div>
  </div>
</div>

## Page Discovery Methods

<div class="crawl-methods-grid">
  <div class="method-card">
    <h3>Sitemap Method <span class="recommended-badge">Recommended</span></h3>
    <p>Discovers URLs by parsing XML sitemaps.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  pages_source: sitemap<br>  urls:<br>    - https://example.com/sitemap.xml</code>
    </div>

    <div class="method-section">
      <h4>How it works:</h4>
      <ol>
        <li>Fetches XML sitemap(s) from specified URLs</li>
        <li>Extracts all <code>&lt;loc&gt;</code> elements</li>
        <li>Applies URL filters</li>
        <li>Returns filtered URL list</li>
      </ol>
    </div>

    <div class="method-section">
      <h4>Advantages:</h4>
      <ul>
        <li>Most efficient method</li>
        <li>Complete URL coverage</li>
        <li>No recursive crawling overhead</li>
        <li>Respects site structure</li>
      </ul>
    </div>

    <div class="when-to-use">
      <div class="when-to-use-icon">💡</div>
      <div>
        <h4>When to use</h4>
        <p>Whenever a sitemap is available (check <code>robots.txt</code>)</p>
      </div>
    </div>
  </div>

  <div class="method-card">
    <h3>Crawl Method</h3>
    <p>Discovers URLs by recursively following links.</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  pages_source: crawl<br>  max_depth: 3<br>  urls:<br>    - https://example.com</code>
    </div>

    <div class="method-section">
      <h4>How it works:</h4>
      <ol>
        <li>Starts from initial URLs</li>
        <li>Extracts all links from each page</li>
        <li>Follows links up to <code>max_depth</code></li>
        <li>Applies URL filters</li>
        <li>Returns deduplicated URL list</li>
      </ol>
    </div>

    <div class="method-section">
      <h4>Advantages:</h4>
      <ul>
        <li>Works without sitemap</li>
        <li>Discovers unlisted pages</li>
        <li>Flexible depth control</li>
      </ul>
    </div>

    <div class="when-to-use">
      <div class="when-to-use-icon">💡</div>
      <div>
        <h4>When to use</h4>
        <p>When no sitemap exists or when discovery of dynamic pages is needed</p>
      </div>
    </div>
  </div>
</div>

## URL Filtering

<div class="crawl-methods-grid">
  <div class="method-card">
    <h3>Positive Regex (Include Patterns)</h3>
    <p>Include only URLs matching at least one pattern:</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  pos_regex:<br>    - "https://example\.com/docs/.*"<br>    - "https://example\.com/blog/.*"</code>
    </div>

    <div class="method-section">
      <h4>Common patterns:</h4>
      <ul>
        <li><code>"https://docs\.example\.com/.*"</code> - All docs subdomain pages</li>
        <li><code>".*/api/.*"</code> - Any path containing /api/</li>
        <li><code>".*\.example\.com/en/.*"</code> - English language only</li>
        <li><code>".*/v[0-9]+/.*"</code> - Versioned content</li>
      </ul>
    </div>
  </div>

  <div class="method-card">
    <h3>Negative Regex (Exclude Patterns)</h3>
    <p>Exclude URLs matching any pattern:</p>

    <div class="code-block">
      <span class="code-label">yaml</span>
      <code>website_crawler:<br>  neg_regex:<br>    - ".*\.(pdf|zip|exe)$"<br>    - ".*/admin/.*"<br>    - ".*/login.*"</code>
    </div>

    <div class="method-section">
      <h4>Common patterns:</h4>
      <ul>
        <li><code>".*\.(pdf|doc|xls)$"</code> - Document files</li>
        <li><code>".*/admin/.*"</code> - Admin pages</li>
        <li><code>".*\?.*"</code> - URLs with query parameters</li>
        <li><code>".*/deprecated/.*"</code> - Deprecated content</li>
      </ul>
    </div>
  </div>
</div>

<div class="filter-logic-box">
  <div class="filter-logic-header">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
    <h4>Filter Logic</h4>
  </div>
  <ol>
    <li>Start with all discovered URLs</li>
    <li>Remove URLs matching any <code>neg_regex</code> pattern</li>
    <li>If <code>pos_regex</code> is specified, keep only URLs matching at least one pattern</li>
    <li>Result: Filtered URL list</li>
  </ol>
</div>

## Authentication

<div class="auth-card">
  <h3>SAML Authentication</h3>
  <p>For websites protected by SAML-based single sign-on:</p>

```yaml
website_crawler:
  saml_auth:
    login_url: "https://idp.example.com/login"
    username_field: "username"
    password_field: "password"
    login_failure_string: "Invalid credentials"

  saml_username: "${SAML_USERNAME}"
  saml_password: "${SAML_PASSWORD}"
```

  <div class="method-section">
    <h4>How it works:</h4>
    <ol>
      <li>Navigates to login URL</li>
      <li>Fills in username and password fields</li>
      <li>Submits form</li>
      <li>Verifies login success</li>
      <li>Uses authenticated session for all requests</li>
    </ol>
  </div>

  <div class="method-section">
    <h4>Setting credentials:</h4>

```toml
# secrets.toml
SAML_USERNAME = "user@example.com"
SAML_PASSWORD = "password"
```
  </div>

  <div class="info-box">
    <div class="info-box-header">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
      <strong>Info</strong>
    </div>
    <p>For detailed SAML authentication setup and troubleshooting, see <a href="../authentication/saml">SAML Authentication Guide</a>.</p>
  </div>
</div>

<div class="auth-grid">
  <div class="auth-card-small">
    <h3>Basic Authentication</h3>
    <p>For websites using HTTP Basic Auth:</p>

```yaml
website_crawler:
  basic_auth:
    username: "${WEBSITE_USERNAME}"
    password: "${WEBSITE_PASSWORD}"
```

    <div class="method-section">
      <h4>How it works:</h4>
      <ol>
        <li>Adds Authorization header to all requests</li>
        <li>Encodes credentials in Base64</li>
        <li>Works with standard HTTP 401 challenges</li>
      </ol>
    </div>

    <div class="method-section">
      <h4>Setting credentials:</h4>

```toml
# secrets.toml
WEBSITE_USERNAME = "username"
WEBSITE_PASSWORD = "password"
```
    </div>
  </div>

  <div class="auth-card-small">
    <h3>Custom Headers</h3>
    <p>For websites requiring custom authentication headers:</p>

```yaml
website_crawler:
  custom_headers:
    Authorization: "Bearer ${API_TOKEN}"
    X-API-Key: "${API_KEY}"
```

    <div class="method-section">
      <h4>How it works:</h4>
      <ol>
        <li>Adds specified headers to all requests</li>
        <li>Supports environment variable substitution</li>
        <li>Useful for API tokens, keys, or custom auth</li>
      </ol>
    </div>

    <div class="method-section">
      <h4>Setting credentials:</h4>

```toml
# secrets.toml
API_TOKEN = "your-bearer-token"
API_KEY = "your-api-key"
```
    </div>
  </div>
</div>

## Getting Started

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

### Configuration Parameters

#### Crawler Settings

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
| `crawl_report` | bool | No | `false` | Generate report of indexed URLs |
| `remove_old_content` | bool | No | `false` | Remove previously indexed URLs no longer in crawl list |

#### Authentication Settings

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `saml_auth` | dict | No | - | SAML authentication configuration (login_url, username_field, password_field, login_failure_string) |
| `saml_username` | string | No | - | SAML username (from secrets.toml: `SAML_USERNAME`) |
| `saml_password` | string | No | - | SAML password (from secrets.toml: `SAML_PASSWORD`) |
| `basic_auth` | dict | No | - | Basic authentication configuration (username, password) |
| `basic_auth.username` | string | No | - | Basic auth username (from secrets.toml: `WEBSITE_USERNAME`) |
| `basic_auth.password` | string | No | - | Basic auth password (from secrets.toml: `WEBSITE_PASSWORD`) |
| `custom_headers` | dict | No | `{}` | Custom headers for authentication (e.g., Authorization, X-API-Key) |

#### HTML Processing Settings

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `html_processing` | dict | No | `{}` | HTML processing options (extract_links, extract_metadata) |
| `css_selectors` | list | No | `[]` | CSS selectors for content extraction |

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
