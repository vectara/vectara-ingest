# Configuration Reference

Complete reference for configuring vectara-ingest crawlers.

## Configuration File Structure

Every vectara-ingest job is controlled by a YAML configuration file with three main sections:

1. **`vectara`**: Vectara platform and processing settings
2. **`crawling`**: Crawler type specification
3. **`<crawler>_crawler`**: Crawler-specific parameters

## Vectara Configuration

### Basic Settings

```yaml
vectara:
  # Vectara API endpoint
  endpoint: api.vectara.io

  # OAuth endpoint for authentication
  auth_url: auth.vectara.io

  # Your corpus key
  corpus_key: my-corpus

  # Reindex existing documents
  reindex: false

  # Create corpus if it doesn't exist
  create_corpus: false

  # Enable verbose logging
  verbose: false
```

### SSL Configuration

```yaml
vectara:
  # SSL verification options:
  # - true: default SSL verification (default)
  # - false: disable SSL verification (not recommended)
  # - path: custom CA certificate file
  ssl_verify: true
  # ssl_verify: /home/vectara/env/ca.pem
```

### Chunking Strategy

```yaml
vectara:
  # Chunking strategy: sentence or fixed
  chunking_strategy: sentence

  # Chunk size (for fixed strategy)
  chunk_size: 512
```

### Content Processing

```yaml
vectara:
  # Remove code blocks from HTML
  remove_code: true

  # Remove boilerplate content (ads, navigation)
  remove_boilerplate: false

  # Mask personally identifiable information
  mask_pii: false

  # Custom user agent for web crawling
  user_agent: "vectara-crawler"
```

### Timeouts

```yaml
vectara:
  # URL crawling timeout (seconds)
  timeout: 90

  # Wait time after page load for AJAX/animations
  post_load_timeout: 5
```

### Storage Options

```yaml
vectara:
  # Store local copies of indexed documents
  store_docs: false

  # Output directory for reports and temp files
  output_dir: vectara_ingest_output
```

## Document Processing Configuration

### Model Configuration

```yaml
doc_processing:
  # Legacy: single model for all processing
  model: openai
  model_name: 'gpt-4o'

  # New: separate models for text and vision
  model_config:
    text:
      provider: openai
      base_url: https://api.openai.com/v1
      model_name: "gpt-4o"
    vision:
      provider: anthropic
      base_url: https://api.anthropic.com
      model_name: "claude-3-opus-20240229"
```

### Document Parsers

```yaml
doc_processing:
  # Parser: unstructured, llama_parse, docupanda, or docling
  doc_parser: docling

  # Unstructured parser configuration
  unstructured_config:
    chunking_strategy: by_title  # basic, by_title, or none
    chunk_size: 1024

  # Docling parser configuration
  docling_config:
    chunking_strategy: hybrid  # hierarchical, hybrid, or none
    image_scale: 1.0  # 2.0 for higher resolution
    chunk_size: 1024
```

### Table Processing

```yaml
doc_processing:
  # Extract and summarize tables
  parse_tables: false

  # Use GMFT for table extraction (PDF only)
  enable_gmft: true
```

### Image Processing

```yaml
doc_processing:
  # Summarize images using GPT-4o Vision
  summarize_images: false

  # Include image binary data
  add_image_bytes: false

  # Index images inline or as separate documents
  inline_images: true
```

### OCR Configuration

```yaml
doc_processing:
  # Enable OCR for scanned documents
  do_ocr: true

  # EasyOCR configuration
  easy_ocr_config:
    download_enabled: true
    use_gpu: false
    lang: ['en', 'fr', 'de']
    confidence_threshold: 0.5
    force_full_page_ocr: false
```

### Advanced Features

```yaml
doc_processing:
  # Enable contextual chunking
  contextual_chunking: false

  # Use core indexing (preserve parser chunks)
  use_core_indexing: false

  # Extract custom metadata using LLM
  extract_metadata:
    'num_pages': 'number of pages in this document'
    'date': 'date of this document'
    'author': 'author of this document'
```

## Crawler Configuration

### Specifying the Crawler

```yaml
crawling:
  crawler_type: website  # or rss, notion, jira, etc.
```

### Crawler-Specific Settings

Each crawler has its own configuration section:

```yaml
website_crawler:
  urls:
    - https://example.com
  max_depth: 3

rss_crawler:
  source: my-source
  rss_pages:
    - https://example.com/feed.xml
  days_past: 30

notion_crawler:
  source: notion
  # Uses NOTION_API_KEY from secrets.toml
```

See individual [crawler documentation](crawlers/index.md) for specific options.

## Metadata Configuration

Add static metadata to all documents:

```yaml
metadata:
  project: documentation
  department: engineering
  groups:
    - team-a
    - team-b
```

## Complete Example

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: my-docs
  reindex: false
  verbose: true
  chunking_strategy: sentence
  remove_code: true
  remove_boilerplate: false
  timeout: 90

doc_processing:
  model: openai
  model_name: gpt-4o
  doc_parser: docling
  parse_tables: true
  summarize_images: true
  do_ocr: true

crawling:
  crawler_type: website

website_crawler:
  urls:
    - https://docs.example.com
  max_depth: 5
  url_regex:
    - "https://docs\\.example\\.com/.*"

metadata:
  source: documentation
  version: "2.0"
```

## Environment Variables

Additional environment variables can be set in `.run-env`:

```bash
HF_ENDPOINT="http://localhost:9000"
CUSTOM_VAR="value"
```

## Next Steps

- **Secrets Management**: Learn about [managing API keys](secrets-management.md)
- **Crawlers**: Explore [available crawlers](crawlers/index.md)
- **Features**: Discover [advanced features](features/document-processing.md)
