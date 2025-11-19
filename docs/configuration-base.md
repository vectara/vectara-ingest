# Base Configuration Reference

Every vectara-ingest crawler configuration includes three main sections: **Vectara settings**, **Document processing settings**, and **Crawler-specific settings**. This guide covers the common configuration that applies to all crawlers.

## Configuration File Structure

```yaml
# Vectara platform configuration (common to all crawlers)
vectara:
  # ... vectara settings ...

# Document processing configuration (common to all crawlers)
doc_processing:
  # ... processing settings ...

# Crawler specification (required)
crawling:
  crawler_type: <crawler_name>

# Crawler-specific configuration
<crawler_name>_crawler:
  # ... crawler-specific settings ...

# Optional: Static metadata for all documents
metadata:
  # ... custom metadata ...
```

---

## Vectara Configuration

These settings control how vectara-ingest connects to Vectara and processes documents.

### Connection Settings

```yaml
vectara:
  # Vectara API endpoint
  endpoint: api.vectara.io

  # OAuth endpoint for authentication (used with create_corpus)
  auth_url: auth.vectara.io

  # Your corpus key (required)
  corpus_key: my-corpus-key
```

### SSL/TLS Configuration

```yaml
vectara:
  # SSL verification options:
  # - true: Default SSL verification (default)
  # - false: Disable SSL verification (not recommended for production)
  # - /path/to/cert: Custom CA certificate file
  ssl_verify: true
```

**Example with custom certificate:**
```yaml
vectara:
  ssl_verify: /home/vectara/env/ca.pem
```

### Indexing Behavior

```yaml
vectara:
  # Reindex existing documents if they already exist
  reindex: false

  # Create the corpus if it doesn't exist
  # Requires personal API key in secrets.toml
  create_corpus: false
```

### Chunking Strategy

Vectara can chunk documents using different strategies:

```yaml
vectara:
  # Chunking strategy: "sentence" or "fixed"
  chunking_strategy: sentence

  # Chunk size in characters (only for "fixed" strategy)
  chunk_size: 512
```

**Chunking strategies:**
- `sentence`: Intelligent sentence-based chunking (recommended)
- `fixed`: Fixed-size character chunks

### Content Processing

```yaml
vectara:
  # Remove code blocks from HTML content
  remove_code: true

  # Remove boilerplate content (ads, navigation, footers)
  # Uses Goose3 and justext algorithms
  remove_boilerplate: false

  # Mask personally identifiable information (PII)
  # Uses Microsoft Presidio (English only)
  mask_pii: false

  # Custom user agent for web crawling
  user_agent: "vectara-crawler"
```

### Timeouts

```yaml
vectara:
  # URL crawling timeout in seconds
  timeout: 90

  # Additional timeout after page load for AJAX/animations
  post_load_timeout: 5
```

### Storage & Output

```yaml
vectara:
  # Store local copies of all indexed documents
  # Saved to ~/tmp/mount/indexed_docs_XXX
  store_docs: false

  # Directory for output files, reports, and temp files
  # Path is relative when running locally, /home/vectara/<dir>/ in Docker
  output_dir: vectara_ingest_output
```

### Debugging

```yaml
vectara:
  # Enable verbose logging
  verbose: false
```

---

## Document Processing Configuration

Advanced document processing features including table extraction, image summarization, and contextual chunking.

### Model Configuration

#### Simple Configuration (Legacy)

```yaml
doc_processing:
  # Provider: "openai" or "anthropic"
  model: openai

  # Model name
  model_name: "gpt-4o"
```

#### Advanced Configuration (Recommended)

Use different models for text and vision processing:

```yaml
doc_processing:
  model_config:
    # Text processing (tables, contextual chunks, metadata extraction)
    text:
      provider: openai
      base_url: https://api.openai.com/v1
      model_name: "gpt-4o"

    # Vision processing (image summarization)
    vision:
      provider: anthropic
      base_url: https://api.anthropic.com
      model_name: "claude-3-opus-20240229"
```

#### Private Model Endpoints

```yaml
doc_processing:
  model_config:
    text:
      provider: private
      base_url: "http://host.docker.internal:5000/v1"
      model_name: "custom-model"
```

!!! note "Private API Keys"
    Add `PRIVATE_API_KEY` to your `secrets.toml` under the `[general]` profile.

### Document Parsers

Vectara-ingest supports multiple document parsers:

```yaml
doc_processing:
  # Parser: "unstructured", "llama_parse", "docupanda", or "docling"
  doc_parser: docling
```

**Parser options:**
- `unstructured`: Unstructured.io parser (default)
- `llama_parse`: LlamaIndex cloud parser (requires `LLAMA_CLOUD_API_KEY`)
- `docupanda`: DocuPanda parser (requires `DOCUPANDA_API_KEY`)
- `docling`: IBM Docling parser (recommended)

#### Unstructured Parser Configuration

```yaml
doc_processing:
  doc_parser: unstructured

  unstructured_config:
    # Chunking strategy: "basic", "by_title", or "none"
    chunking_strategy: by_title

    # Chunk size for basic chunking
    chunk_size: 1024
```

#### Docling Parser Configuration

```yaml
doc_processing:
  doc_parser: docling

  docling_config:
    # Chunking strategy: "hierarchical", "hybrid", or "none"
    chunking_strategy: hybrid

    # Image resolution scale (1.0 = 72 DPI, 2.0 = 144 DPI)
    image_scale: 1.0

    # Chunk size for hybrid chunking
    chunk_size: 1024
```

### Table Processing

Extract and summarize tables from documents:

```yaml
doc_processing:
  # Extract and summarize tables (requires OpenAI or Anthropic API key)
  parse_tables: false

  # Use GMFT (Graph-based Multi-modal Fusion Transformer) for table extraction
  # Only works with PDF files
  enable_gmft: true
```

!!! warning "API Key Required"
    Table summarization requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in the `[general]` profile of `secrets.toml`.

### Image Processing

Process images with AI vision models:

```yaml
doc_processing:
  # Summarize images using GPT-4o Vision or Claude (requires API key)
  summarize_images: false

  # Include image binary data alongside summaries
  # Requires summarize_images: true
  add_image_bytes: false

  # Index images inline within document flow (true)
  # or as separate documents (false)
  inline_images: true
```

### OCR Configuration

Enable OCR for scanned documents:

```yaml
doc_processing:
  # Enable OCR (Docling parser only)
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

#### Core Indexing

```yaml
doc_processing:
  # Preserve chunks from document parsers
  # Automatically enabled when parser chunking is enabled
  use_core_indexing: false
```

#### Contextual Chunking

```yaml
doc_processing:
  # Add contextual information to chunks (PDF only)
  # Requires OpenAI or Anthropic API key
  contextual_chunking: false
```

#### Metadata Extraction

Extract custom metadata using LLMs:

```yaml
doc_processing:
  # Define metadata fields to extract
  extract_metadata:
    'num_pages': 'number of pages in this document'
    'date': 'date of this document'
    'author': 'author of this document'
    'summary': 'brief summary of the document'
```

---

## Crawler Configuration

Specify which crawler to use:

```yaml
crawling:
  # Crawler type (required)
  # Options: website, rss, notion, jira, confluence, slack, github,
  #          gdrive, docs, folder, s3, database, and more
  crawler_type: website
```

Each crawler has its own configuration section. See individual crawler documentation for details.

---

## Static Metadata

Add custom metadata to all indexed documents:

```yaml
metadata:
  # Single values
  project: documentation
  department: engineering
  version: "2.0"

  # Array values
  groups:
    - team-a
    - team-b
    - team-c

  # Any custom fields
  environment: production
  indexed_by: vectara-ingest
```

This metadata is merged with crawler-specific metadata. If conflicts occur, crawler metadata takes precedence.

---

## Complete Example

Here's a complete configuration example with all common settings:

```yaml
# Vectara platform configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: my-documentation
  reindex: false
  create_corpus: false

  # Chunking
  chunking_strategy: sentence

  # Content processing
  remove_code: true
  remove_boilerplate: false
  mask_pii: false

  # Timeouts
  timeout: 90
  post_load_timeout: 5

  # Output
  verbose: true
  store_docs: false
  output_dir: vectara_ingest_output

# Document processing configuration
doc_processing:
  # Model configuration
  model: openai
  model_name: gpt-4o

  # Document parser
  doc_parser: docling
  docling_config:
    chunking_strategy: hybrid
    image_scale: 1.0
    chunk_size: 1024

  # Features
  parse_tables: true
  enable_gmft: true
  summarize_images: true
  add_image_bytes: false
  inline_images: true
  do_ocr: true
  contextual_chunking: false

  # Metadata extraction
  extract_metadata:
    'date': 'publication date'
    'author': 'author name'

# Crawler specification
crawling:
  crawler_type: website

# Crawler-specific configuration
website_crawler:
  urls:
    - https://docs.example.com
  pages_source: sitemap
  pos_regex:
    - "https://docs\\.example\\.com/.*"
  num_per_second: 10

# Static metadata
metadata:
  project: product-docs
  version: "v2.0"
  environment: production
```

---

## Environment Variables

Additional environment variables can be injected via `.run-env`:

```bash
# .run-env
HF_ENDPOINT="http://localhost:9000"
CUSTOM_VAR="value"
```

---

## Secrets Management

Sensitive values like API keys should be stored in `secrets.toml`:

```toml
# secrets.toml

# LLM API keys for advanced features
[general]
OPENAI_API_KEY = "sk-..."
ANTHROPIC_API_KEY = "sk-ant-..."

# Vectara and crawler credentials
[default]
api_key = "your-vectara-api-key"
NOTION_API_KEY = "secret_..."
JIRA_USERNAME = "user@example.com"
JIRA_PASSWORD = "api-token"
```

Reference these in your YAML config:

```yaml
notion_crawler:
  notion_api_key: "${NOTION_API_KEY}"
```

See [Secrets Management](secrets-management.md) for details.

---

## Next Steps

- **Crawler-Specific Configs**: See individual [crawler documentation](crawlers/index.md)
- **Advanced Features**: Learn about [table extraction](features/table-extraction.md), [image processing](features/image-processing.md)
- **Deployment**: Check [deployment guides](deployment/docker.md)

---

## Configuration Tips

### Start Simple

Begin with minimal configuration:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: my-corpus

crawling:
  crawler_type: rss

rss_crawler:
  rss_pages: ["https://example.com/feed.xml"]
  days_past: 30
  delay: 1
  source: news
```

### Enable Features Incrementally

Add advanced features one at a time:

1. Start with basic crawling
2. Enable table extraction if needed
3. Add image summarization for visual content
4. Enable contextual chunking for better retrieval
5. Add custom metadata extraction

### Test with Verbose Mode

Always test new configurations with verbose logging:

```yaml
vectara:
  verbose: true
```

### Monitor Resource Usage

Advanced features require more resources:
- **Table summarization**: LLM API calls
- **Image processing**: Vision model API calls
- **OCR**: CPU/GPU intensive
- **Large files**: More memory

Adjust Docker resources accordingly (recommend 4-8GB RAM).
