# Configuration Reference

<p class="subtitle">Comprehensive reference for all configuration options in vectara-ingest. Learn how to configure Vectara connections, document processing, and crawler settings.</p>

---

## Overview

Every vectara-ingest crawler configuration includes three main sections: **Vectara settings**, **Document processing settings**, and **Crawler-specific settings**. This guide covers the configuration that applies to all crawlers.

<div class="config-structure">
  <h3>Configuration File Structure</h3>
  <pre><code class="language-yaml"># Vectara platform configuration
vectara:
  # ... vectara settings ...

# Document processing configuration
doc_processing:
  # ... processing settings ...

# Crawler specification (required)
crawling:
  crawler_type: &lt;crawler_name&gt;

# Crawler-specific configuration
&lt;crawler_name&gt;_crawler:
  # ... crawler-specific settings ...

# Optional: Static metadata for all documents
metadata:
  # ... custom metadata ...</code></pre>
</div>

---

## Vectara Configuration

These settings control how vectara-ingest connects to Vectara and processes documents.

### Connection Settings

Configure your Vectara API connection:

```yaml
vectara:
  # Vectara API endpoint
  endpoint: api.vectara.io

  # OAuth endpoint for authentication (used with create_corpus)
  auth_url: auth.vectara.io

  # Your corpus key (required)
  corpus_key: my-corpus-key
```

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Required Configuration</p>
    <p>The <code>corpus_key</code> is required for all crawlers. Get your corpus key from the Vectara console.</p>
  </div>
</div>

### SSL/TLS Configuration

Control SSL certificate verification:

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

Control how documents are indexed:

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

**Available strategies:**

<div class="option-list">
  <div class="option-item">
    <span class="option-name">sentence</span>
    <span class="option-description">Intelligent sentence-based chunking (recommended)</span>
  </div>
  <div class="option-item">
    <span class="option-name">fixed</span>
    <span class="option-description">Fixed-size character chunks</span>
  </div>
</div>

### Content Processing

Configure content extraction and cleaning:

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

Configure timeout settings for web crawling:

```yaml
vectara:
  # URL crawling timeout in seconds
  timeout: 90

  # Additional timeout after page load for AJAX/animations
  post_load_timeout: 5
```

### Storage & Output

Configure where to store documents and logs:

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

Enable verbose logging for troubleshooting:

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

Basic model configuration for all processing tasks:

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

Use custom or self-hosted model endpoints:

```yaml
doc_processing:
  model_config:
    text:
      provider: private
      base_url: "http://host.docker.internal:5000/v1"
      model_name: "custom-model"
```

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Private API Keys</p>
    <p>Add <code>PRIVATE_API_KEY</code> to your <code>secrets.toml</code> under the <code>[general]</code> profile.</p>
  </div>
</div>

### Document Parsers

Vectara-ingest supports multiple document parsers:

```yaml
doc_processing:
  # Parser: "unstructured", "llama_parse", "docupanda", or "docling"
  doc_parser: docling
```

**Available parsers:**

<div class="option-list">
  <div class="option-item">
    <span class="option-name">unstructured</span>
    <span class="option-description">Unstructured.io parser (default)</span>
  </div>
  <div class="option-item">
    <span class="option-name">llama_parse</span>
    <span class="option-description">LlamaIndex cloud parser (requires <code>LLAMA_CLOUD_API_KEY</code>)</span>
  </div>
  <div class="option-item">
    <span class="option-name">docupanda</span>
    <span class="option-description">DocuPanda parser (requires <code>DOCUPANDA_API_KEY</code>)</span>
  </div>
  <div class="option-item">
    <span class="option-name">docling</span>
    <span class="option-description">IBM Docling parser (recommended)</span>
  </div>
</div>

#### Unstructured Parser Configuration

Configure the Unstructured.io parser:

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

Configure the IBM Docling parser (recommended):

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

<div class="warning-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">API Key Required</p>
    <p>Table summarization requires <code>OPENAI_API_KEY</code> or <code>ANTHROPIC_API_KEY</code> in the <code>[general]</code> profile of <code>secrets.toml</code>.</p>
  </div>
</div>

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

Preserve chunks from document parsers:

```yaml
doc_processing:
  # Preserve chunks from document parsers
  # Automatically enabled when parser chunking is enabled
  use_core_indexing: false
```

#### Contextual Chunking

Add contextual information to chunks for better retrieval:

```yaml
doc_processing:
  # Add contextual information to chunks (PDF only)
  # Requires OpenAI or Anthropic API key
  contextual_chunking: false
```

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Learn More</p>
    <p>See our <a href="../features/contextual-chunking.md">Contextual Chunking Guide</a> for details on how this improves retrieval accuracy.</p>
  </div>
</div>

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

Each crawler has its own configuration section. See individual [crawler documentation](crawlers/index.md) for details.

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

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Metadata Precedence</p>
    <p>Static metadata is merged with crawler-specific metadata. If conflicts occur, crawler metadata takes precedence.</p>
  </div>
</div>

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

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Environment File Location</p>
    <p>Place the <code>.run-env</code> file in the root directory of your vectara-ingest installation.</p>
  </div>
</div>

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

Reference these in your YAML config using environment variable syntax:

```yaml
notion_crawler:
  notion_api_key: "${NOTION_API_KEY}"
```

<div class="warning-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Security Warning</p>
    <p>Never commit <code>secrets.toml</code> to version control. Add it to your <code>.gitignore</code> file.</p>
  </div>
</div>

See [Secrets Management](secrets-management.md) for complete details.

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

- **Table summarization:** LLM API calls
- **Image processing:** Vision model API calls
- **OCR:** CPU/GPU intensive
- **Large files:** More memory

Adjust Docker resources accordingly (recommend 4-8GB RAM).

---

## Next Steps

<div class="next-steps-grid">
  <a href="../crawlers/index.md" class="next-step-card">
    <h3>Explore Crawlers →</h3>
    <p>Learn about all 30+ available crawlers and their specific configurations</p>
  </a>

  <a href="../features/table-extraction.md" class="next-step-card">
    <h3>Advanced Features →</h3>
    <p>Discover table extraction, image processing, and contextual chunking</p>
  </a>
</div>

---

## Getting Help

Need assistance with configuration? Here are your resources:

<div class="help-grid">
  <a href="https://github.com/vectara/vectara-ingest/issues" target="_blank" class="help-card">
    <h4>GitHub Issues</h4>
    <p>Report bugs or ask questions</p>
  </a>

  <a href="https://discord.gg/GFb8gMz6UH" target="_blank" class="help-card">
    <h4>Discord Community</h4>
    <p>Chat with other users</p>
  </a>

  <a href="https://docs.vectara.com" target="_blank" class="help-card">
    <h4>Vectara Docs</h4>
    <p>Platform documentation</p>
  </a>
</div>
