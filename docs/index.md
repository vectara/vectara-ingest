<h1 class="hero-title">Welcome to Vectara Ingest</h1>

<div class="badges">
  <a href="https://opensource.org/licenses/Apache-2.0"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://github.com/vectara/vectara-ingest/graphs/commit-activity"><img src="https://img.shields.io/badge/Maintained%3F-yes-green.svg" alt="Maintained"></a>
  <img src="https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue" alt="Python Versions">
</div>

<p class="subtitle">A powerful Python package for ingesting content from various sources into Vectara. Simple, fast, and reliable data ingestion made easy.</p>

<div class="button-group">
  <a href="getting-started.md" class="md-button md-button--primary">
    Get Started
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="button-icon"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
  </a>
  <a href="https://github.com/vectara/vectara-ingest" class="md-button md-button--outline">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="button-icon"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>
    View on GitHub
  </a>
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
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"></path></svg>
      30+ Pre-built Crawlers
    </h3>
    <p>Ready-to-use crawlers for web scraping, APIs, databases, and more. Each crawler handles the specific requirements of its data source.</p>
  </div>

  <div class="feature-card-clean">
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
      Intelligent Crawling
    </h3>
    <p>Respect robots.txt, handle rate limiting automatically, and follow sitemap guidelines for efficient web crawling.</p>
  </div>

  <div class="feature-card-clean">
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>
      Smart Processing
    </h3>
    <p>Built-in text extraction, cleaning, and transformation with support for custom processing pipelines and filters.</p>
  </div>

  <div class="feature-card-clean">
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 17 2 2 4-4"></path><path d="m3 7 2 2 4-4"></path><path d="M13 6h8"></path><path d="M13 12h8"></path><path d="M13 18h8"></path></svg>
      Reliable Execution
    </h3>
    <p>Automatic retry mechanisms, graceful error handling, and comprehensive logging ensure robust data ingestion.</p>
  </div>

  <div class="feature-card-clean">
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>
      Flexible Deployment
    </h3>
    <p>Run as CLI, as a library, or schedule via cron. Supports both one-time and incremental ingestion workflows.</p>
  </div>

  <div class="feature-card-clean">
    <h3>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      Extensible Architecture
    </h3>
    <p>Easy to extend with custom crawlers, processors, and transformers. Plugin architecture supports third-party extensions.</p>
  </div>
</div>

---

## Supported Data Sources

<div class="source-grid-clean">
  <div class="source-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path><path d="M12 22V12"></path><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"></path><path d="m7.5 4.27 9 5.15"></path></svg>
      Knowledge Bases
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

<div class="architecture-card">
  <div class="architecture-code">
    <pre><code>vectara_ingest/
├── core/         # Core ingestion logic
├── crawlers/     # Source-specific crawlers
├── processors/   # Data transformation
└── utils/        # Shared utilities</code></pre>
    <p>Learn more in our <a href="advanced/custom-crawler.md">Architecture Guide</a>.</p>
  </div>
</div>

---

## Documentation Overview

<div class="doc-grid-clean">
  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>
      Getting Started
    </h4>
    <p>Installation, quick start, and configuration guides</p>
  </div>

  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/></svg>
      Authentication
    </h4>
    <p>OAuth, API keys, service accounts, and SAML setup</p>
  </div>

  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
      Crawlers
    </h4>
    <p>30+ pre-built crawlers for various data sources</p>
  </div>

  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
      Features
    </h4>
    <p>Document processing, chunking, and metadata extraction</p>
  </div>

  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      Deployment
    </h4>
    <p>Docker, cloud deployment, and troubleshooting</p>
  </div>

  <div class="doc-card-clean">
    <h4>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="doc-icon"><circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><line x1="6" x2="6" y1="9" y2="21"></line></svg>
      Advanced
    </h4>
    <p>Custom crawlers, SAML auth, and API reference</p>
  </div>
</div>

---

## Community & Support

<div class="community-card">
  <div class="community-grid-clean">
    <div class="community-item">
      <div class="community-icon-text">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="community-icon"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <div>
          <h4>GitHub</h4>
          <p><a href="https://github.com/vectara/vectara-ingest">github.com/vectara/vectara-ingest</a></p>
        </div>
      </div>
    </div>

    <div class="community-item">
      <div class="community-icon-text">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="community-icon"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <div>
          <h4>Documentation</h4>
          <p><a href="https://docs.vectara.com">docs.vectara.com</a></p>
        </div>
      </div>
    </div>

    <div class="community-item">
      <div class="community-icon-text">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="community-icon"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <div>
          <h4>Community Forum</h4>
          <p><a href="https://discuss.vectara.com">discuss.vectara.com</a></p>
        </div>
      </div>
    </div>

    <div class="community-item">
      <div class="community-icon-text">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="community-icon"><path d="M22 4s-.7 2.1-2 3.4c1.6 10-9.4 17.3-18 11.6 2.2.1 4.4-.6 6-2C3 15.5.5 9.6 3 5c2.2 2.6 5.6 4.1 9 4-.9-4.2 4-6.6 7-3.8 1.1 0 3-1.2 3-1.2z"/></svg>
        <div>
          <h4>Twitter</h4>
          <p><a href="https://twitter.com/vectara">@vectara</a></p>
        </div>
      </div>
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

## Author

<div class="content-card" markdown="1">

Made with ❤️ by [Vectara](https://www.vectara.com). For questions or commercial support inquiries, reach out to support@vectara.com.

</div>
