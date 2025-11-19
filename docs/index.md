# Welcome to Vectara Ingest

<div class="badges">
  <span class="badge">v2.0.0</span>
  <span class="badge">Python</span>
  <span class="badge">Apache 2.0</span>
</div>

<p class="subtitle">A powerful Python package for ingesting content from various sources into Vectara. Simple, fast, and reliable data ingestion made easy.</p>

<div class="button-group">
  <a href="getting-started.md" class="md-button md-button--primary">Get Started →</a>
  <a href="https://github.com/vectara/vectara-ingest" class="md-button">📋 View on GitHub</a>
</div>

---

## About Vectara Ingest

<div class="content-card" markdown="1">

**Vectara Ingest** is an open-source Python library designed to make it easy to ingest data from various sources into Vectara. The library provides a simple interface to crawl and process content, transforming it into a format suitable for indexing.

Whether you're working with websites, APIs, databases, or file systems, Vectara Ingest provides pre-built crawlers and an extensible architecture that lets you quickly get your data into Vectara with minimal setup. With support for 30+ data sources and counting, you can ingest content from almost anywhere with just a few lines of code.

</div>

---

## Key Features

<div class="feature-grid-clean">
  <div class="feature-card-clean">
    <h3>30+ Pre-built Crawlers</h3>
    <p>Ready-to-use crawlers for web scraping, APIs, databases, and more. Each crawler handles the specific requirements of its data source.</p>
  </div>

  <div class="feature-card-clean">
    <h3>Intelligent Crawling</h3>
    <p>Respect robots.txt, handle rate limiting automatically, and follow sitemap guidelines for efficient web crawling.</p>
  </div>

  <div class="feature-card-clean">
    <h3>Smart Processing</h3>
    <p>Built-in text extraction, cleaning, and transformation with support for custom processing pipelines and filters.</p>
  </div>

  <div class="feature-card-clean">
    <h3>Reliable Execution</h3>
    <p>Automatic retry mechanisms, graceful error handling, and comprehensive logging ensure robust data ingestion.</p>
  </div>

  <div class="feature-card-clean">
    <h3>Flexible Deployment</h3>
    <p>Run as CLI, as a library, or schedule via cron. Supports both one-time and incremental ingestion workflows.</p>
  </div>

  <div class="feature-card-clean">
    <h3>Extensible Architecture</h3>
    <p>Easy to extend with custom crawlers, processors, and transformers. Plugin architecture supports third-party extensions.</p>
  </div>
</div>

---

## Supported Data Sources

<div class="source-grid-clean">
  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Content Management & Documentation
    </h4>
    <ul>
      <li>Docusaurus 2.x</li>
      <li>Docusaurus (legacy)</li>
      <li>Notion</li>
      <li>MediaWiki</li>
      <li>Confluence 1.x, 2.x, 3.x, Cloud</li>
    </ul>
  </div>

  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Communication & Collaboration
    </h4>
    <ul>
      <li>Slack</li>
      <li>Discord/Revolt</li>
    </ul>
  </div>

  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Project Management & Dev
    </h4>
    <ul>
      <li>Jira</li>
      <li>GitHub (repositories)</li>
      <li>Linear/Plane</li>
    </ul>
  </div>

  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      File Storage
    </h4>
    <ul>
      <li>Google Drive</li>
      <li>Amazon S3</li>
      <li>FTP/SFTP</li>
      <li>SMB Files</li>
    </ul>
  </div>

  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Data & Research
    </h4>
    <ul>
      <li>Edgar.sec (USA)</li>
      <li>SEC.gov</li>
      <li>Hugging Face (datasets)</li>
      <li>arXiv (via Kaggle)</li>
      <li>PubMed Central</li>
    </ul>
  </div>

  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Miscellaneous
    </h4>
    <ul>
      <li>RSS/Atom Feeds</li>
      <li>Twitter/X</li>
      <li>Hacker News</li>
      <li>YouTube</li>
    </ul>
  </div>
</div>

---

## Quick Start

<div class="content-card" markdown="1">

### 1. Install Dependencies

```bash
git clone https://github.com/vectara/vectara-ingest.git
cd vectara-ingest
poetry install
```

### 2. Set Up Authentication

Create a `secrets.toml` file with your Vectara credentials:

```toml
[default]
VECTARA_CORPUS_KEY = "your-corpus-key"
VECTARA_API_KEY = "your-api-key"
```

### 3. Create a Configuration File

Create `config/example.yaml`:

```yaml
vectara:
  corpus_key: !ENV ${VECTARA_CORPUS_KEY}
  api_key: !ENV ${VECTARA_API_KEY}

website_crawler:
  urls:
    - https://docs.example.com
  scrape_method: scrapy
  max_depth: 3
```

### 4. Run Your First Crawl

```bash
bash run.sh config/example.yaml default
```

For a detailed tutorial, see the [Getting Started Guide](getting-started.md).

</div>

---

## Architecture

<div class="architecture-card" markdown="1">

<div class="architecture-grid" markdown="1">

<div class="architecture-code" markdown="1">

```
vectara_ingest/
├── core/         # Core ingestion logic
├── crawlers/     # Source-specific crawlers
├── processors/   # Data transformation
└── utils/        # Shared utilities
```

</div>

</div>

<div class="architecture-link" markdown="1">

Learn more about the architecture in our [Architecture Guide](advanced/custom-crawler.md).

</div>

</div>

---

## Documentation Overview

<div class="doc-grid-clean">
  <div class="doc-card-clean">
    <h4>🚀 Getting Started</h4>
    <p>Installation, quick start, and configuration guides</p>
  </div>

  <div class="doc-card-clean">
    <h4>🔐 Authentication</h4>
    <p>OAuth, API keys, service accounts, and SAML setup</p>
  </div>

  <div class="doc-card-clean">
    <h4>🔍 Crawlers</h4>
    <p>30+ pre-built crawlers for various data sources</p>
  </div>

  <div class="doc-card-clean">
    <h4>✨ Features</h4>
    <p>Document processing, chunking, and metadata extraction</p>
  </div>

  <div class="doc-card-clean">
    <h4>🚀 Deployment</h4>
    <p>Docker, cloud deployment, and troubleshooting</p>
  </div>

  <div class="doc-card-clean">
    <h4>🛠️ Advanced</h4>
    <p>Custom crawlers, SAML auth, and API reference</p>
  </div>
</div>

---

## Community & Support

<div class="community-card" markdown="1">

<div class="community-grid-clean" markdown="1">
  <div>
    <h4>💬 GitHub</h4>
    <p><a href="https://github.com/vectara/vectara-ingest">github.com/vectara/vectara-ingest</a></p>
  </div>

  <div>
    <h4>📖 Community Forum</h4>
    <p><a href="https://discuss.vectara.com">discuss.vectara.com</a></p>
  </div>

  <div>
    <h4>📘 Documentation</h4>
    <p><a href="https://docs.vectara.com">docs.vectara.com</a></p>
  </div>

  <div>
    <h4>🐦 Twitter</h4>
    <p><a href="https://twitter.com/vectara">@vectara</a></p>
  </div>
</div>

</div>

---

## Contributing

<div class="content-card" markdown="1">

We welcome contributions! Whether it's bug fixes, new crawlers, documentation improvements, or feature requests, we're happy to work with you. Please see our [Contributing Guide](contributing.md) for details.

<a href="contributing.md" class="md-button">📝 Contribution Guidelines</a>

</div>

---

## License

<div class="content-card" markdown="1">

Vectara Ingest is released under the [Apache 2.0 License](https://opensource.org/licenses/Apache-2.0).

Made with ❤️ by Vectara. For questions or commercial support inquiries, reach out to support@vectara.com.

</div>
