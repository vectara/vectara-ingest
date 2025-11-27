# Documentation Crawler

The Documentation crawler is a specialized crawler designed for modern documentation sites built with popular documentation frameworks like Docusaurus, ReadTheDocs, MkDocs, GitBook, Sphinx, and more. It's optimized for crawling hierarchical documentation structures with intelligent URL filtering, pattern-based discovery, and content extraction.

## Use Cases

- Index Docusaurus documentation sites
- Crawl ReadTheDocs hosted documentation
- Ingest MkDocs generated documentation
- Archive GitBook knowledge bases
- Index Sphinx-generated documentation
- Create searchable documentation knowledge bases
- Maintain documentation in sync with source repositories
- Extract and index API reference documentation

## Key Features

- **Pattern-Based URL Filtering**: Include/exclude URLs using regex patterns optimized for documentation structures
- **Multi-Crawl Methods**: Choose between internal crawling or Scrapy-based crawling for complex sites
- **HTML Processing**: Customize how HTML content is processed and extracted
- **Scrape Methods**: Support for different JavaScript rendering approaches
- **Crawl Reports**: Generate detailed reports of indexed and removed URLs
- **Incremental Updates**: Remove outdated content not found in current crawl
- **Rate Limiting**: Configurable request throttling to respect server resources
- **SSL Flexibility**: Support for custom certificates and SSL verification options
- **Ray Parallelization**: Distribute crawling and indexing across multiple cores

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: your-corpus-key
  reindex: false

crawling:
  crawler_type: docs

docs_crawler:
  # Documentation framework name
  docs_system: docusaurus

  # Base URL to start crawling
  base_urls:
    - https://docs.example.com

  # URL patterns to include (regex)
  pos_regex:
    - "https://docs\\.example\\.com/.*"

  # URL patterns to exclude (regex)
  neg_regex:
    - ".*\\.pdf$"
    - ".*/api/.*"
```

### Advanced Configuration

```yaml
docs_crawler:
  docs_system: docusaurus

  base_urls:
    - https://docs.example.com

  # Crawl method: internal or scrapy
  crawl_method: internal  # default: internal

  # Maximum crawl depth for URL discovery
  max_depth: 3

  # URL filtering patterns
  pos_regex:
    - "https://docs\\.example\\.com/docs/.*"
    - "https://docs\\.example\\.com/api/.*"

  neg_regex:
    - ".*\\.pdf$"
    - ".*/admin/.*"
    - ".*\\.mp4$"

  # File extensions to ignore
  extensions_to_ignore:
    - .pdf
    - .zip
    - .tar.gz
    - .exe

  # HTML processing options
  html_processing:
    remove_code: false
    remove_scripts: true
    remove_styles: true

  # JavaScript rendering scrape method
  scrape_method: beautiful_soup  # or playwright, selenium, etc.

  # Rate limiting (requests per second)
  num_per_second: 10

  # Generate crawl report
  crawl_report: true

  # Remove old content not found in new crawl
  remove_old_content: false

  # SSL Certificate configuration
  disable_ssl_verification: false
  ca_bundle_path: /path/to/ca-bundle.crt

  # Ray-based parallel processing
  ray_workers: 0  # -1: use all cores, 0: no parallelization, N: use N cores
```

## Documentation Framework Examples

### Docusaurus

Docusaurus generates clean, SEO-friendly documentation sites with well-structured URLs.

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: docs-corpus
  remove_code: true

crawling:
  crawler_type: docs

docs_crawler:
  docs_system: docusaurus

  base_urls:
    - https://docusaurus.io

  pos_regex:
    - "https://docusaurus\\.io/docs/.*"
    - "https://docusaurus\\.io/blog/.*"

  neg_regex:
    - ".*\\.pdf$"

  num_per_second: 10
  crawl_report: true
```

### ReadTheDocs

ReadTheDocs hosts documentation with version management. The crawler can index specific versions.

```yaml
docs_crawler:
  docs_system: readthedocs

  base_urls:
    - https://myproject.readthedocs.io/en/stable/

  pos_regex:
    - "https://myproject\\.readthedocs\\.io/en/stable/.*"

  neg_regex:
    - ".*/search\\.html$"
    - ".*/genindex\\.html$"
    - ".*/py-modindex\\.html$"

  max_depth: 4
  num_per_second: 5  # ReadTheDocs may rate limit
```

### MkDocs

MkDocs creates lightweight documentation sites with a clean structure.

```yaml
docs_crawler:
  docs_system: mkdocs

  base_urls:
    - https://docs.example.com

  pos_regex:
    - "https://docs\\.example\\.com/.*"

  neg_regex:
    - ".*/sitemap\\.xml.*"
    - ".*/search\\.html$"

  num_per_second: 10
```

### GitBook

GitBook provides a platform for publishing documentation with search and versioning.

```yaml
docs_crawler:
  docs_system: gitbook

  base_urls:
    - https://docs.example.com

  pos_regex:
    - "https://docs\\.example\\.com/.*"

  neg_regex:
    - ".*api\\.example\\.com.*"  # Exclude external API docs
    - ".*/settings/.*"
    - ".*/pricing/.*"

  num_per_second: 8
  crawl_report: true
```

### Sphinx

Sphinx is widely used for Python and technical documentation.

```yaml
docs_crawler:
  docs_system: sphinx

  base_urls:
    - https://docs.example.com

  pos_regex:
    - "https://docs\\.example\\.com/.*"

  neg_regex:
    - ".*/genindex\\.html$"
    - ".*/search\\.html$"
    - ".*/py-modindex\\.html$"
    - ".*/modindex\\.html$"

  max_depth: 5
  num_per_second: 10
```

### OpenAPI/Swagger Documentation

For API documentation generated from OpenAPI specs:

```yaml
docs_crawler:
  docs_system: swagger

  base_urls:
    - https://api-docs.example.com

  pos_regex:
    - "https://api-docs\\.example\\.com/.*"

  neg_regex:
    - ".*/swagger-ui\\.html$"
    - ".*/v2/api-docs.*"
    - ".*/v3/api-docs.*"

  html_processing:
    remove_scripts: true
    remove_styles: true

  crawl_report: true
```

## Crawl Methods

### Internal Crawl Method

Uses built-in URL discovery and crawling. Fast and reliable for most documentation sites.

```yaml
docs_crawler:
  crawl_method: internal  # default
  max_depth: 3
```

**Advantages**:
- No additional dependencies
- Faster crawling
- Lower memory usage
- Works reliably for static documentation

**Disadvantages**:
- May miss dynamically generated content
- Limited to HTTP link discovery

### Scrapy Crawl Method

Uses Scrapy for more advanced crawling with better handling of complex structures.

```yaml
docs_crawler:
  crawl_method: scrapy
  max_depth: 3
```

**Advantages**:
- Better handling of complex URL structures
- More robust error handling
- Advanced filtering capabilities
- Ideal for large documentation sites

**Disadvantages**:
- Requires Scrapy installation
- Higher memory usage
- Slightly slower for simple sites

## Scrape Methods

The crawler supports different JavaScript rendering approaches for extracting content:

```yaml
docs_crawler:
  scrape_method: beautiful_soup  # Default: static HTML parsing
  # Alternative options:
  # - playwright: Browser-based rendering
  # - selenium: Selenium WebDriver rendering
  # - requests: Simple requests library
```

## Content Extraction

### HTML Processing

Control how HTML content is extracted and cleaned:

```yaml
docs_crawler:
  html_processing:
    remove_code: false          # Keep code blocks
    remove_scripts: true        # Remove script tags
    remove_styles: true         # Remove style tags
    remove_navigation: true     # Remove nav elements
    extract_tables: true        # Extract table content
```

### Intelligent Content Selection

The crawler automatically identifies and extracts main content, skipping:
- Navigation menus
- Sidebars
- Footers
- Ads and tracking code
- Comments sections

## URL Filtering and Pattern Matching

### Include Patterns (Positive Regex)

Define which URLs to include in the crawl:

```yaml
docs_crawler:
  pos_regex:
    # Include docs and API reference
    - "https://docs\\.example\\.com/docs/.*"
    - "https://docs\\.example\\.com/api/.*"
    - "https://docs\\.example\\.com/guides/.*"
```

### Exclude Patterns (Negative Regex)

Define which URLs to skip:

```yaml
docs_crawler:
  neg_regex:
    # Exclude binary files
    - ".*\\.pdf$"
    - ".*\\.zip$"
    - ".*\\.tar\\.gz$"

    # Exclude admin and search pages
    - ".*/admin/.*"
    - ".*/search.*"

    # Exclude version history
    - ".*/history.*"
    - ".*/changelog.*"
```

### File Extensions to Ignore

Skip specific file types:

```yaml
docs_crawler:
  extensions_to_ignore:
    - .pdf
    - .zip
    - .exe
    - .dmg
    - .tar.gz
    - .mp4
    - .mp3
    - .wav
    - .png
    - .jpg
    - .jpeg
    - .gif
    - .svg
```

## Rate Limiting and Performance

### Request Rate Limiting

Control the crawling speed to respect server resources:

```yaml
docs_crawler:
  num_per_second: 10  # Default: 10 requests/second
```

### Distributed Processing with Ray

Parallelize crawling and indexing across multiple CPU cores:

```yaml
docs_crawler:
  ray_workers: -1   # Use all available CPU cores
  # or
  ray_workers: 4    # Use 4 cores specifically
  # or
  ray_workers: 0    # No parallelization (default)
```

When using Ray workers:
- Each worker processes URLs independently
- Automatic resource cleanup
- Better throughput for large sites
- Ensure sufficient memory for multiple workers

### Performance Tuning Example

For a large documentation site with thousands of pages:

```yaml
docs_crawler:
  crawl_method: scrapy    # More robust for large sites
  max_depth: 4
  num_per_second: 5       # Conservative rate limit
  ray_workers: 4          # Distribute across 4 cores
  crawl_report: true
```

## Crawl Reports

Generate detailed reports of the crawl process:

```yaml
docs_crawler:
  crawl_report: true
```

This creates two files in the output directory:

- **urls_indexed.txt**: List of all successfully indexed URLs
- **urls_removed.txt**: List of URLs removed from corpus (if `remove_old_content: true`)

### Using Crawl Reports

```bash
# View indexed URLs
cat vectara_ingest_output/urls_indexed.txt

# Verify coverage
wc -l vectara_ingest_output/urls_indexed.txt

# Check for removed content
cat vectara_ingest_output/urls_removed.txt
```

## Content Management

### Incremental Updates

Remove old content not found in the current crawl:

```yaml
docs_crawler:
  remove_old_content: true
  crawl_report: true
```

This is useful when:
- Documentation pages are deleted
- URLs are reorganized
- Keeping the corpus in sync with the live documentation
- Maintaining a clean index without stale pages

### Full Reindex

To do a full reindex without removing old content:

```yaml
docs_crawler:
  remove_old_content: false

vectara:
  reindex: true  # Full corpus reindex
```

## SSL and Certificate Configuration

### Default Behavior

By default, SSL certificates are verified:

```yaml
docs_crawler:
  disable_ssl_verification: false
```

### Custom Certificates

For documentation sites with internal CAs:

```yaml
docs_crawler:
  disable_ssl_verification: false
  ca_bundle_path: /path/to/ca-bundle.crt
```

### Disable SSL Verification

For self-signed certificates (not recommended for production):

```yaml
docs_crawler:
  disable_ssl_verification: true
```

## Authentication

### Basic Authentication

For password-protected documentation:

Add to `secrets.toml`:

```toml
[default]
api_key = "your-vectara-api-key"
DOCS_USERNAME = "user@example.com"
DOCS_PASSWORD = "your-password"
```

Configure in YAML:

```yaml
docs_crawler:
  auth_type: basic
```

### Custom Headers

For API key or token authentication:

```yaml
docs_crawler:
  custom_headers:
    Authorization: "Bearer YOUR_TOKEN"
    X-API-Key: "YOUR_API_KEY"
```

## Metadata Extraction

The crawler automatically extracts and preserves:

- Page title
- URL
- Meta description
- Documentation framework (docs_system)
- Last crawl timestamp
- Breadcrumb path (when available)

### Custom Metadata

Add static metadata to all indexed documents:

```yaml
metadata:
  doc_type: internal
  version: latest
  framework: docusaurus
  team: documentation
```

## Real-World Configuration Examples

### Production Documentation Site

Complete configuration for indexing a production documentation site:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: main-docs
  reindex: false
  remove_code: false
  verbose: false

crawling:
  crawler_type: docs

docs_crawler:
  docs_system: docusaurus
  base_urls:
    - https://docs.example.com

  pos_regex:
    - "https://docs\\.example\\.com/docs/.*"
    - "https://docs\\.example\\.com/api/.*"

  neg_regex:
    - ".*/admin/.*"
    - ".*/search.*"
    - ".*\\.pdf$"

  max_depth: 4
  num_per_second: 10
  crawl_method: internal
  crawl_report: true
  remove_old_content: true
  ray_workers: 4

metadata:
  doc_type: official
  source: docusaurus
  environment: production
```

### Large Multi-Version Documentation

For documentation sites with multiple versions:

```yaml
docs_crawler:
  docs_system: readthedocs
  base_urls:
    - https://myproject.readthedocs.io/en/stable/

  pos_regex:
    - "https://myproject\\.readthedocs\\.io/en/stable/.*"

  neg_regex:
    - ".*/search.*"
    - ".*/genindex.*"
    - ".*/modindex.*"

  max_depth: 5
  num_per_second: 5
  crawl_method: scrapy
  crawl_report: true
  ray_workers: 2
```

### Internal Documentation with Authentication

For internal documentation behind authentication:

```yaml
docs_crawler:
  docs_system: docusaurus
  base_urls:
    - https://internal-docs.company.com

  pos_regex:
    - "https://internal-docs\\.company\\.com/.*"

  custom_headers:
    Authorization: "Bearer $(DOCS_API_TOKEN)"

  disable_ssl_verification: false
  ca_bundle_path: /etc/ssl/certs/company-ca.crt

  num_per_second: 5
  crawl_report: true
```

### API Documentation

For API reference documentation sites:

```yaml
docs_crawler:
  docs_system: swagger
  base_urls:
    - https://api-docs.example.com

  pos_regex:
    - "https://api-docs\\.example\\.com/.*"

  neg_regex:
    - ".*swagger-ui.*"
    - ".*/download/.*"

  html_processing:
    remove_scripts: true
    remove_styles: true
    extract_tables: true

  crawl_report: true
```

## Troubleshooting

### Pages Not Being Indexed

**Issue**: Expecting more pages but fewer are indexed

**Solutions**:

1. Check URL patterns:
   ```bash
   # Verify positive regex matches your URLs
   echo "https://docs.example.com/guides/intro" | grep -E "https://docs\.example\.com/docs/.*"
   ```

2. Increase max_depth:
   ```yaml
   docs_crawler:
     max_depth: 5  # Try deeper crawling
   ```

3. Add missing paths to pos_regex:
   ```yaml
   docs_crawler:
     pos_regex:
       - "https://docs\\.example\\.com/docs/.*"
       - "https://docs\\.example\\.com/guides/.*"  # Add missing path
   ```

4. Check logs:
   ```bash
   docker logs -f vingest | grep "Found.*urls"
   ```

### JavaScript-Rendered Content

**Issue**: Content not extracted from JavaScript-heavy documentation sites

**Solution**: Use Playwright or Selenium for rendering:

```yaml
docs_crawler:
  scrape_method: playwright
  num_per_second: 5  # Reduce rate due to rendering overhead
```

### Rate Limiting and 429 Errors

**Issue**: Getting blocked with HTTP 429 Too Many Requests

**Solutions**:

1. Reduce request rate:
   ```yaml
   docs_crawler:
     num_per_second: 2
   ```

2. Reduce parallel workers:
   ```yaml
   docs_crawler:
     ray_workers: 1
   ```

3. Add request delay:
   ```yaml
   docs_crawler:
     num_per_second: 1
   ```

### SSL Certificate Errors

**Issue**: Certificate verification failed

**Solutions**:

1. For self-signed certificates:
   ```yaml
   docs_crawler:
     disable_ssl_verification: true
   ```

2. For custom CA certificates:
   ```yaml
   docs_crawler:
     ca_bundle_path: /path/to/ca-bundle.crt
   ```

### Memory Issues with Ray Workers

**Issue**: Out of memory errors when using Ray parallelization

**Solutions**:

1. Reduce worker count:
   ```yaml
   docs_crawler:
     ray_workers: 2  # Use fewer cores
   ```

2. Increase Docker memory:
   ```bash
   docker run -m 8g vectara-ingest
   ```

3. Reduce batch processing:
   ```yaml
   docs_crawler:
     num_per_second: 5
   ```

### Incomplete Crawl Reports

**Issue**: Crawl report files are empty or missing

**Solutions**:

1. Enable crawl reports:
   ```yaml
   docs_crawler:
     crawl_report: true
   ```

2. Check output directory:
   ```bash
   ls -la vectara_ingest_output/
   ```

3. Ensure write permissions to output directory

## Best Practices

1. **Start with Conservative Settings**: Begin with lower `max_depth` and `num_per_second` values
2. **Use URL Patterns**: Leverage positive and negative regex patterns for precise control
3. **Test on Sample**: Verify configuration on a small section first
4. **Monitor Progress**: Check logs and use `crawl_report: true` for visibility
5. **Respect Server Limits**: Use appropriate `num_per_second` settings
6. **Verify Content Extraction**: Manually check a few indexed documents
7. **Use Version Control**: Keep documentation configurations in version control
8. **Schedule Regular Updates**: Use cron or similar tools for incremental updates
9. **Backup Corpus**: Before using `remove_old_content: true` on production
10. **Test URL Patterns**: Verify regex patterns before full crawl

## Running the Crawler

### Basic Execution

```bash
# Create your configuration
vim config/docs-crawler.yaml

# Run the crawler
bash run.sh config/docs-crawler.yaml default

# Monitor progress
docker logs -f vingest
```

### Full Example Workflow

```bash
# 1. Create config for Docusaurus documentation
cat > config/docusaurus-docs.yaml << 'EOF'
vectara:
  endpoint: api.vectara.io
  corpus_key: my-docs
  reindex: false

crawling:
  crawler_type: docs

docs_crawler:
  docs_system: docusaurus
  base_urls:
    - https://docs.example.com
  pos_regex:
    - "https://docs\\.example\\.com/docs/.*"
  neg_regex:
    - ".*\\.pdf$"
  crawl_report: true
EOF

# 2. Run the crawler
bash run.sh config/docusaurus-docs.yaml default

# 3. Monitor logs
docker logs -f vingest

# 4. Review results
docker exec vingest cat /home/vectara/vectara_ingest_output/urls_indexed.txt | head -20
```

## Performance Benchmarks

Typical performance on modern documentation sites:

| Framework | Typical Pages | Crawl Time | Settings |
|-----------|---------------|-----------|----------|
| Docusaurus | 100-500 | 2-5 min | num_per_second: 10, ray_workers: 2 |
| ReadTheDocs | 500-2000 | 10-30 min | num_per_second: 5, ray_workers: 4 |
| MkDocs | 50-300 | 1-3 min | num_per_second: 10, ray_workers: 2 |
| GitBook | 100-1000 | 5-15 min | num_per_second: 8, ray_workers: 2 |
| Sphinx | 200-1500 | 5-20 min | num_per_second: 10, ray_workers: 4 |

## Next Steps

- Learn about [Document Processing](../features/document-processing.md)
- Explore [Table Extraction](../features/table-extraction.md)
- Check out [Custom Crawlers](../advanced/custom-crawler.md)
- Review [Deployment Options](../deployment/docker.md)
- Visit the [Troubleshooting Guide](../deployment/troubleshooting.md)

## Resources

- [Crawlers Overview](index.md)
- [Configuration Reference](../configuration.md)
- [Advanced Configuration](../advanced/)
