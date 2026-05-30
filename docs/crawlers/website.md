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

## Configuration Parameters

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
| `html_processing` | dict | No | `{}` | HTML processing options |
| `html_processing.extract_links` | bool | No | `true` | Extract and preserve links |
| `html_processing.extract_metadata` | bool | No | `true` | Extract metadata tags |
| `html_processing.remove_scripts` | bool | No | `true` | Remove script tags |
| `html_processing.remove_styles` | bool | No | `true` | Remove style tags |
| `css_selectors` | list | No | `[]` | CSS selectors for content extraction |

## Content Extraction

<div class="content-extraction-grid">
  <div class="extraction-card">
    <h3>Automatic Extraction</h3>
    <p>By default, the crawler intelligently extracts main content:</p>

```yaml
vectara:
  remove_boilerplate: true
```

<p><strong>This removes:</strong></p>
<ul>
  <li>Navigation menus</li>
  <li>Sidebars</li>
  <li>Headers and footers</li>
  <li>Ads and promotional content</li>
  <li>Comment sections</li>
</ul>
  </div>

  <div class="extraction-card">
    <h3>Custom CSS Selectors</h3>
    <p>Target specific content areas:</p>

```yaml
website_crawler:
  css_selectors:
    - "article"
    - "main"
    - "div.content"
```

<p><strong>Common selectors:</strong></p>
<ul>
  <li><code>"article"</code> - Article wrapper</li>
  <li><code>"main"</code> - Main content area</li>
  <li><code>"div.content"</code> or <code>"div.main"</code> - Content containers</li>
  <li><code>".documentation"</code> - Documentation container</li>
</ul>
  </div>
</div>

## Getting Started

<div class="info-box-prerequisites">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
  <div>
    <p><strong>Before you begin:</strong></p>
    <ul>
      <li>Set up your Vectara account and create a corpus</li>
      <li>Configure your API credentials (see <a href="../getting-started.md">Quick Start</a>)</li>
    </ul>
  </div>
</div>

<div class="quick-start-card">
  <h3>Quick Start</h3>
  <p>Here's the simplest way to crawl a website:</p>

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: my-website
  remove_boilerplate: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://example.com/sitemap.xml
  pages_source: sitemap

metadata:
  source: website
```

<p><strong>Run:</strong></p>

```bash
bash run.sh config/website.yaml default
```
</div>

<div class="example-references">
  <h3>Need More?</h3>
  <p>See complete examples below for:</p>
  <ul>
    <li><a href="#example-1-basic-auth-scrapy-fast-static-site">Basic Auth + Scrapy (Fast Static Site)</a></li>
    <li><a href="#example-2-saml-playwright-javascript-heavy-site">SAML + Playwright (JavaScript-Heavy Site)</a></li>
    <li><a href="#example-3-multi-domain-documentation-sites">Multi-Domain Documentation Sites</a></li>
    <li><a href="#example-4-large-scale-blog-with-parallel-processing">Large Scale Blog with Parallel Processing</a></li>
  </ul>
</div>

## Metadata Extraction

<div class="content-extraction-grid">
  <div class="extraction-card">
    <h3>Automatic Extraction</h3>
    <p>The crawler automatically extracts and indexes:</p>
    <ul>
      <li><strong>Page Title</strong>: From <code>&lt;title&gt;</code> or <code>&lt;h1&gt;</code> tag</li>
      <li><strong>Meta Description</strong>: From <code>&lt;meta name="description"&gt;</code> tag</li>
      <li><strong>Author</strong>: From meta tags or schema.org data</li>
      <li><strong>Publication Date</strong>: From meta tags or schema.org</li>
      <li><strong>Last Modified</strong>: From HTTP headers or meta tags</li>
      <li><strong>URL</strong>: Source URL of the page</li>
      <li><strong>Source</strong>: Always "website"</li>
    </ul>
  </div>

  <div class="extraction-card">
    <h3>Custom Metadata</h3>
    <p>Add static metadata to all indexed pages:</p>

```yaml
metadata:
  source: website
  category: documentation
  department: engineering
  environment: production
  sync_frequency: daily
  content_type: technical
```

<p>This metadata is attached to every indexed document.</p>
  </div>
</div>

## Performance Optimization

<div class="perf-card">
  <h3>Choose the Right Crawl Method</h3>
  <div class="perf-split">
    <div class="perf-option">
      <p><strong>For speed on static sites:</strong></p>

```yaml
website_crawler:
  crawl_method: scrapy
  ray_workers: 4
```
    </div>
    <div class="perf-option">
      <p><strong>For JavaScript-heavy sites:</strong></p>

```yaml
website_crawler:
  crawl_method: internal
  ray_workers: 0
```
    </div>
  </div>
</div>

<div class="perf-card">
  <h3>Use Sitemaps When Available</h3>
  <div class="perf-split">
    <div class="perf-option">
      <p><strong class="perf-preferred">PREFERRED: Fast and complete</strong></p>

```yaml
website_crawler:
  pages_source: sitemap
  urls:
    - https://example.com/sitemap.xml
```
    </div>
    <div class="perf-option">
      <p><strong class="perf-slower">SLOWER: Recursive discovery</strong></p>

```yaml
website_crawler:
  pages_source: crawl
  max_depth: 5
```
    </div>
  </div>
</div>

<div class="perf-card">
  <h3>Parallel Processing with Ray</h3>

```yaml
website_crawler:
  ray_workers: 0    # Sequential (low memory)
  ray_workers: 4    # 4 parallel workers
  ray_workers: -1   # All CPU cores
```

<p><strong>Recommendations:</strong></p>
<ul>
  <li>Use <code>ray_workers: 0</code> for small sites or limited memory</li>
  <li>Use <code>ray_workers: 4</code> for medium sites with 8GB+ RAM</li>
  <li>Use <code>ray_workers: -1</code> only for large sites with 16GB+ RAM</li>
</ul>
</div>

<div class="perf-card">
  <h3>Rate Limiting</h3>

```yaml
website_crawler:
  num_per_second: 10  # Default
  num_per_second: 20  # Faster (public sites)
  num_per_second: 5   # Slower (rate-limited sites)
```
</div>

<div class="perf-card">
  <h3>URL Filtering</h3>
  <p>Narrow the crawl scope:</p>

```yaml
website_crawler:
  pos_regex:
    - "https://docs\\.example\\.com/en/v2/.*"  # Specific version

  neg_regex:
    - ".*/deprecated/.*"
    - ".*\\.pdf$"
    - ".*/search.*"

  max_pages: 5000  # Safety limit
```
</div>

<div class="perf-card">
  <h3>Query Parameter Handling</h3>
  <p>Deduplicate URLs:</p>

```yaml
website_crawler:
  keep_query_params: false  # Strips ?ref=header, ?utm_source=twitter
```
</div>

## Crawl Reports and Old Content Removal

<div class="report-card">
  <h3>Crawl Reports</h3>
  <p>Generate reports of indexed and removed URLs:</p>

```yaml
website_crawler:
  crawl_report: true
```

<p><strong>Output files:</strong></p>
<ul>
  <li><code>urls_indexed.txt</code> - All URLs successfully indexed</li>
  <li><code>urls_removed.txt</code> - URLs removed from corpus</li>
</ul>

<p><strong>Usage:</strong></p>
<ul>
  <li>Verify correct URLs were crawled</li>
  <li>Audit removed content</li>
  <li>Debug filtering issues</li>
  <li>Track coverage over time</li>
</ul>
</div>

<div class="report-card">
  <h3>Old Content Removal</h3>
  <p>Automatically remove previously indexed URLs no longer in scope:</p>

```yaml
website_crawler:
  remove_old_content: true
  crawl_report: true
```

<p><strong>How it works:</strong></p>
<ol>
  <li>Crawls and discovers current URLs</li>
  <li>Queries Vectara for previously indexed URLs</li>
  <li>Identifies URLs in corpus but not in current crawl</li>
  <li>Deletes those documents from corpus</li>
  <li>Reports removed URLs to <code>urls_removed.txt</code></li>
</ol>

<p><strong>Use cases:</strong></p>
<ul>
  <li>Site restructures</li>
  <li>Deprecated documentation removal</li>
  <li>Keeping index synchronized with live site</li>
  <li>Regular maintenance crawls</li>
</ul>

<div class="warning-box-perf">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>
  <div>
    <p><strong>Warnings</strong></p>
    <ul>
      <li>Irreversibly deletes documents from Vectara</li>
      <li>Test with <code>crawl_report: true</code> before enabling</li>
      <li>Always have a backup plan</li>
    </ul>
  </div>
</div>
</div>

## Troubleshooting

<div class="troubleshoot-card">
  <h3>Pages Not Being Crawled</h3>
  <p><strong>Symptom:</strong> Few or no pages indexed despite large website</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Increase <code>max_depth</code> if too shallow</li>
    <li>Verify URL patterns with regex testing</li>
    <li>Check <code>neg_regex</code> isn't excluding wanted content</li>
    <li>Switch to <code>pages_source: sitemap</code> for reliability</li>
    <li>Enable <code>verbose: true</code> for debugging</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Authentication Failures</h3>
  <p><strong>Symptom:</strong> SAML, Basic Auth, or cookie-based auth failing</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Verify credentials in environment variables</li>
    <li>Test login manually to confirm credentials work</li>
    <li>Check form field names match HTML (inspect source)</li>
    <li>Set correct <code>login_failure_string</code></li>
    <li>Try different <code>crawl_method</code> (internal vs scrapy)</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Memory Issues</h3>
  <p><strong>Symptom:</strong> Process killed, "Out of memory", system unresponsive</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Set <code>ray_workers: 0</code> for sequential processing</li>
    <li>Reduce <code>ray_workers</code> to 2 instead of 4</li>
    <li>Limit scope with <code>max_pages</code> and <code>max_depth</code></li>
    <li>Use <code>crawl_method: scrapy</code> (more memory-efficient)</li>
    <li>Split into multiple smaller crawls</li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Slow Crawling</h3>
  <p><strong>Symptom:</strong> Crawl takes too long to complete</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Increase <code>num_per_second</code> for faster crawling</li>
    <li>Use <code>pages_source: sitemap</code> instead of crawl</li>
    <li>Enable parallel processing with <code>ray_workers: 4</code></li>
    <li>Use <code>crawl_method: scrapy</code> for static sites</li>
    <li>Filter aggressively with <code>pos_regex</code> and <code>neg_regex</code></li>
  </ul>
</div>

<div class="troubleshoot-card">
  <h3>Content Not Extracted</h3>
  <p><strong>Symptom:</strong> URLs indexed but with empty or minimal content</p>
  <p><strong>Solutions:</strong></p>
  <ul>
    <li>Enable <code>remove_boilerplate: true</code></li>
    <li>Specify <code>css_selectors</code> for target content</li>
    <li>Check page source manually (View Source in browser)</li>
    <li>Increase <code>post_load_timeout</code> for JavaScript sites</li>
    <li>Switch to <code>crawl_method: internal</code> for JS-heavy sites</li>
  </ul>
</div>

## Best Practices

<div class="best-practice-grid">
  <div class="best-practice-card">
    <h3>⭕ Start Small and Scale</h3>
    <p>Begin with limited scope to validate</p>

```yaml
website_crawler:
  max_depth: 1
  max_pages: 50
  crawl_report: true
```
  </div>

  <div class="best-practice-card">
    <h3>📄 Prefer Sitemaps</h3>
    <p>Always use sitemaps when available</p>

```yaml
website_crawler:
  pages_source: sitemap
  urls:
    - https://example.com/sitemap.xml
```
  </div>

  <div class="best-practice-card">
    <h3>🔽 Filter Aggressively</h3>
    <p>Narrow the scope</p>

```yaml
website_crawler:
  pos_regex:
    - "https://example\.com/docs/.*"
  neg_regex:
    - ".*/deprecated/.*"
    - ".*\.pdf$"
```
  </div>

  <div class="best-practice-card">
    <h3>⚡ Respect Rate Limits</h3>
    <p>Don't overload servers</p>

```yaml
website_crawler:
  num_per_second: 5
  ray_workers: 0
```
  </div>

  <div class="best-practice-card">
    <h3>⚙️ Add Descriptive Metadata</h3>
    <p>Make content searchable</p>

```yaml
metadata:
  source: website
  site: example.com
  category: documentation
  language: en
```
  </div>

  <div class="best-practice-card">
    <h3>📊 Monitor Crawl Progress</h3>
    <p>Enable verbose logging</p>

```yaml
vectara:
  verbose: true
```
  </div>
</div>

## Complete Examples

### Example 1: Basic Auth + Scrapy (Fast Static Site)

<div class="example-card" markdown="1">

**Use Case:** Crawling a password-protected static documentation site with high performance requirements.

**Best For:** Static HTML sites, fast crawling, basic authentication

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: internal-docs
  remove_boilerplate: true
  verbose: true

crawling:
  crawler_type: website

website_crawler:
  # Starting point
  urls:
    - https://internal.example.com

  # Crawl method: Scrapy for speed on static sites
  pages_source: crawl
  max_depth: 4
  crawl_method: scrapy

  # Basic authentication
  basic_auth:
    username: "${WEBSITE_USERNAME}"
    password: "${WEBSITE_PASSWORD}"

  # URL filtering - only documentation pages
  pos_regex:
    - "https://internal\\.example\\.com/docs/.*"
    - "https://internal\\.example\\.com/guides/.*"
  neg_regex:
    - ".*/admin/.*"
    - ".*/draft/.*"
    - ".*\\.pdf$"

  # Performance settings
  num_per_second: 15
  max_pages: 5000

  # HTML processing
  html_processing:
    extract_links: true
    extract_metadata: true

  # Generate report
  crawl_report: true

metadata:
  source: website
  environment: internal
  category: documentation
  access_level: employees-only
```

**Setup and run:**

```bash
# Create secrets.toml with credentials
cat > secrets.toml <<EOF
WEBSITE_USERNAME = "your-username"
WEBSITE_PASSWORD = "your-password"
EOF

# Run crawler
bash run.sh config/internal-docs.yaml default

# Monitor progress
docker logs -f vingest
```

**What this does:**

- Uses Scrapy for fast crawling of static content
- Authenticates with basic HTTP auth
- Crawls up to 4 levels deep, filtering to docs and guides only
- Rate limited to 15 pages/second to be respectful
- Generates a crawl report showing all indexed URLs

</div>

### Example 2: SAML + Playwright (JavaScript-Heavy Site)

<div class="example-card" markdown="1">

**Use Case:** Crawling an enterprise wiki with SAML SSO that renders content dynamically with JavaScript.

**Best For:** JavaScript-heavy sites, SAML authentication, dynamic content, SPAs

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: enterprise-wiki
  remove_boilerplate: true
  verbose: true

crawling:
  crawler_type: website

website_crawler:
  # Starting point
  urls:
    - https://wiki.enterprise.com

  # Crawl method: Internal (Playwright) for JavaScript rendering
  pages_source: crawl
  max_depth: 3
  crawl_method: internal
  post_load_timeout: 3000  # Wait 3s for JavaScript to execute

  # SAML authentication
  saml_auth:
    login_url: "https://idp.enterprise.com/oauth2/authorize"
    username_field: "email"
    password_field: "password"
    login_failure_string: "Invalid credentials"

  saml_username: "${SAML_USERNAME}"
  saml_password: "${SAML_PASSWORD}"

  # URL filtering - English content only
  pos_regex:
    - "https://wiki\\.enterprise\\.com/en/.*"
    - "https://wiki\\.enterprise\\.com/space/.*"
  neg_regex:
    - ".*/admin/.*"
    - ".*/draft/.*"
    - ".*/personal/.*"
    - ".*\\?.*"  # Skip URLs with query params

  # Custom content extraction
  css_selectors:
    - "article.content"
    - "div.wiki-content"
    - "main#content"

  # Performance settings (slower for JS rendering)
  num_per_second: 3
  max_pages: 2000

  # HTML processing
  html_processing:
    extract_links: true
    extract_metadata: true
    remove_scripts: true
    remove_styles: true

  # Maintenance
  crawl_report: true
  remove_old_content: true

metadata:
  source: website
  platform: confluence
  environment: production
  security_level: confidential
  department: engineering
```

**Setup and run:**

```bash
# Create secrets.toml with SAML credentials
cat > secrets.toml <<EOF
SAML_USERNAME = "user@enterprise.com"
SAML_PASSWORD = "your-secure-password"
EOF

# Run crawler
bash run.sh config/enterprise-wiki.yaml default

# Monitor progress
docker logs -f vingest
```

**What this does:**

- Uses internal crawler (Playwright) to handle JavaScript rendering
- Authenticates via SAML SSO login form
- Waits 3 seconds after page load for dynamic content to render
- Targets specific content areas using CSS selectors
- Rate limited to 3 pages/second (respectful for JS rendering)
- Removes old content that no longer exists on the site

**Pro tips:**

- Increase `post_load_timeout` if content takes longer to load
- Use browser dev tools to identify correct CSS selectors
- Test `login_failure_string` by intentionally using wrong credentials

</div>

### Example 3: Multi-Domain Documentation Sites

<div class="example-card" markdown="1">

**Use Case:** Indexing documentation from multiple related domains/subdomains into a single corpus.

**Best For:** Multi-product documentation, API docs + guides, multi-domain sites

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: unified-docs
  remove_boilerplate: true
  verbose: true

crawling:
  crawler_type: website

website_crawler:
  # Multiple domains and sitemaps
  urls:
    - https://docs.example.com/sitemap.xml
    - https://api.example.com/sitemap.xml
    - https://developers.example.com/sitemap.xml

  # Use sitemaps for reliability
  pages_source: sitemap

  # Aggressive URL filtering across all domains
  pos_regex:
    # Docs site - English only
    - "https://docs\\.example\\.com/en/.*"
    - "https://docs\\.example\\.com/guides/.*"

    # API site - versioned docs only
    - "https://api\\.example\\.com/v[0-9]+/.*"
    - "https://api\\.example\\.com/reference/.*"

    # Developers site - tutorials and samples
    - "https://developers\\.example\\.com/tutorials/.*"
    - "https://developers\\.example\\.com/samples/.*"

  # Exclude across all domains
  neg_regex:
    - ".*\\.pdf$"
    - ".*\\.zip$"
    - ".*/admin/.*"
    - ".*/deprecated/.*"
    - ".*/beta/.*"
    - ".*/internal/.*"
    - ".*/changelog/.*"
    - ".*\\?.*"  # No query parameters

  # Don't keep query params
  keep_query_params: false

  # Performance
  crawl_method: scrapy
  num_per_second: 20
  max_pages: 15000

  # HTML processing
  html_processing:
    extract_links: true
    extract_metadata: true

  # Reports
  crawl_report: true

metadata:
  source: website
  organization: example
  content_types:
    - documentation
    - api-reference
    - tutorials
  language: en
  version: latest
```

**Run:**

```bash
bash run.sh config/multi-domain.yaml default
```

**What this does:**

- Crawls 3 separate domains using their sitemaps
- Applies domain-specific filtering (e.g., versioned API docs only)
- Excludes common unwanted patterns across all domains
- Fast Scrapy crawling at 20 pages/second
- Unified corpus with content from all sources

**Pro tips:**

- Use descriptive metadata to identify source domain
- Test regex patterns individually before combining
- Monitor crawl report to verify filtering is working correctly
- Consider splitting very large multi-domain crawls into separate corpora

</div>

### Example 4: Large Scale Blog with Parallel Processing

<div class="example-card" markdown="1">

**Use Case:** Crawling a large blog site with thousands of articles using parallel processing for speed.

**Best For:** Large content sites, blogs, news sites, high-volume crawling

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: tech-blog
  remove_boilerplate: true
  verbose: true
  reindex: false  # Incremental updates

crawling:
  crawler_type: website

website_crawler:
  # Starting point
  urls:
    - https://blog.techcompany.com

  # Recursive crawl
  pages_source: crawl
  max_depth: 2

  # Target specific content areas with CSS selectors
  css_selectors:
    - "article.post-content"
    - "div.blog-post"
    - "main.article-body"
    - "div.entry-content"

  # Filter blog URLs by date pattern (YYYY/MM/title)
  pos_regex:
    - "https://blog\\.techcompany\\.com/[0-9]{4}/[0-9]{2}/.*"

  # Exclude non-article pages
  neg_regex:
    - ".*/category/.*"
    - ".*/tag/.*"
    - ".*/author/.*"
    - ".*/page/[0-9]+.*"  # Pagination
    - ".*\\?.*"  # Query parameters

  # Parallel processing with Ray
  ray_workers: 4  # Use 4 parallel workers
  num_per_second: 15

  # Handle large scale
  max_pages: 10000

  # Performance tuning
  crawl_method: scrapy  # Fast for static content

  # HTML processing
  html_processing:
    extract_links: true
    extract_metadata: true
    remove_scripts: true
    remove_styles: true

  # Maintenance
  crawl_report: true
  remove_old_content: true  # Clean up deleted articles

metadata:
  source: website
  category: blog
  content_type: articles
  topics:
    - technology
    - engineering
    - product
  language: en
```

**Run:**

```bash
bash run.sh config/tech-blog.yaml default
```

**What this does:**

- Recursive crawl starting from blog homepage
- Uses 4 parallel Ray workers for 4x speed improvement
- Targets article content using multiple CSS selectors
- Filters URLs to match blog date pattern (YYYY/MM/title)
- Excludes category, tag, and pagination pages
- Processes up to 10,000 articles
- Removes articles that have been deleted from the blog

**Performance breakdown:**

- **Sequential (ray_workers: 0):** ~6 hours for 10K pages
- **Parallel (ray_workers: 4):** ~1.5 hours for 10K pages
- At 15 pages/second with 4 workers = 60 effective pages/second

**Pro tips:**

- Start with `max_pages: 100` and `ray_workers: 0` to test CSS selectors
- Increase `ray_workers` based on your machine's CPU cores
- Use `reindex: false` for incremental updates (only new content)
- Monitor memory usage - reduce `ray_workers` if system struggles
- Set `remove_old_content: true` for regular maintenance crawls

</div>

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
