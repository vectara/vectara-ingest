# Getting Started

This tutorial will guide you through your first data ingestion job with vectara-ingest. We'll crawl content from [Paul Graham's website](http://www.paulgraham.com/index.html) using the RSS crawler and ingest it into Vectara.

---

<div class="learning-objectives">
  <div class="learning-header">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>
    <h2>What You'll Learn</h2>
  </div>
  <ul>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>How to configure a crawler</span>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>How to set up authentication</span>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>How to run an ingestion job</span>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>How to verify the ingestion and query your data</span>
    </li>
  </ul>
</div>

---

<div class="prerequisites-card">
  <h2>Prerequisites</h2>
  <p>Before starting, make sure you have:</p>
  <ul class="prerequisites-list">
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-success"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>Completed the <a href="installation.md">Installation</a></span>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-success"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>A Vectara corpus with an API key</span>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-success"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
      <span>Docker installed and running</span>
    </li>
  </ul>
</div>

---

<div class="step-section">
  <div class="step-header">
    <div class="step-number">1</div>
    <h2>Set Up Your Secrets</h2>
  </div>
  <div class="step-content">
    <p>First, configure your Vectara API credentials:</p>

    <pre><code class="language-bash"># Copy the example secrets file
cp secrets.example.toml secrets.toml</code></pre>

    <p>Edit <code>secrets.toml</code> and add your Vectara API key:</p>

    <pre><code class="language-toml">[default]
api_key = "zwt_your_vectara_api_key_here"</code></pre>

    <div class="info-box">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="info-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      <div>
        <p class="box-title">Getting Your API Key</p>
        <p>To retrieve your API key from the Vectara console:</p>
        <ol>
          <li>Log in to <a href="https://console.vectara.com">console.vectara.com</a></li>
          <li>Navigate to your corpus</li>
          <li>Click <strong>Access Control</strong> or the <strong>Authorization</strong> tab</li>
          <li>Copy your personal API key or create a query+index API key</li>
        </ol>
      </div>
    </div>
  </div>
</div>

---

<div class="step-section">
  <div class="step-header">
    <div class="step-number">2</div>
    <h2>Get Your Corpus Key</h2>
  </div>
  <div class="step-content">
    <p>You'll need your corpus key for the configuration:</p>
    <ol class="simple-list">
      <li>In the Vectara console, click on your corpus name</li>
      <li>Your corpus key appears at the top of the screen</li>
      <li>Copy this key for the next step</li>
    </ol>
  </div>
</div>

---

<div class="step-section">
  <div class="step-header">
    <div class="step-number">3</div>
    <h2>Create Your Configuration</h2>
  </div>
  <div class="step-content">
    <p>Create a new configuration file for the Paul Graham RSS crawler:</p>

    <pre><code class="language-bash"># Copy an example config
cp config/news-bbc.yaml config/pg-rss.yaml</code></pre>

    <p>Edit <code>config/pg-rss.yaml</code>:</p>

    <pre><code class="language-yaml">vectara:
  # Vectara platform endpoint
  endpoint: api.vectara.io

  # Your corpus key
  corpus_key: your-corpus-key-here

  # Indexing settings
  reindex: false
  verbose: true

# Crawler configuration
crawling:
  crawler_type: rss

rss_crawler:
  # Source identifier
  source: pg

  # RSS feed URL
  rss_pages:
    - "http://www.aaronsw.com/2002/feeds/pgessays.rss"

  # How many days back to crawl
  days_past: 365</code></pre>

    <div class="warning-box">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="warning-icon"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      <div>
        <p class="box-title">Replace Values</p>
        <p>Make sure to replace <code>your-corpus-key-here</code> with your actual corpus key from Step 2.</p>
      </div>
    </div>
  </div>
</div>

---

<div class="step-section">
  <div class="step-header">
    <div class="step-number">4</div>
    <h2>Run the Crawler</h2>
  </div>
  <div class="step-content">
    <p>Now you're ready to run your first ingestion job!</p>

    <pre><code class="language-bash">bash run.sh config/pg-rss.yaml default</code></pre>

    <p>This command will:</p>
    <ol class="simple-list">
      <li>Build a Docker container (first time only - this may take a few minutes)</li>
      <li>Start the crawler with your configuration</li>
      <li>Begin ingesting content into your Vectara corpus</li>
    </ol>

    <div class="info-box">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="info-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      <div>
        <p class="box-title">First Run</p>
        <p>The first time you run this command, Docker needs to build the container image. This involves downloading dependencies and can take 5-10 minutes. Subsequent runs will be much faster.</p>
      </div>
    </div>

    <h3 class="monitor-heading">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
      Monitor Progress
    </h3>

    <p>In a new terminal, watch the crawler logs:</p>

    <pre><code class="language-bash">docker logs -f vingest</code></pre>

    <p>You should see output like:</p>

    <pre><code class="language-text">INFO: Starting RSS crawler for source: pg
INFO: Found 42 items in RSS feed
INFO: Processing: What You Can't Say
INFO: Indexed document: what-you-cant-say
INFO: Processing: Hackers and Painters
INFO: Indexed document: hackers-and-painters
...</code></pre>

    <p>Press <code>Ctrl+C</code> to stop following the logs (the crawler will continue running).</p>
  </div>
</div>

---

<div class="step-section">
  <div class="step-header">
    <div class="step-number">5</div>
    <h2>Query Your Data</h2>
  </div>
  <div class="step-content">
    <p>While the crawler is running, you can start querying your corpus!</p>

    <h3>Using the Vectara Console</h3>

    <ol class="simple-list">
      <li>Go to <a href="https://console.vectara.com">console.vectara.com</a></li>
      <li>Click <strong>Data → Your Corpus Name</strong></li>
      <li>Click the <strong>Query</strong> tab</li>
      <li>Try some queries:
        <ul>
          <li>"What is a maker schedule?"</li>
          <li>"How to start a startup"</li>
          <li>"What makes a good programming language?"</li>
        </ul>
      </li>
    </ol>

    <h3>Using the API</h3>

    <p>You can also query via the Vectara API:</p>

    <pre><code class="language-python">import requests

query = "What is a maker schedule?"
corpus_key = "your-corpus-key"
api_key = "your-api-key"

response = requests.post(
    "https://api.vectara.io/v2/query",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "query": query,
        "corpus_key": corpus_key,
        "limit": 10
    }
)

print(response.json())</code></pre>
  </div>
</div>

---

<div class="understanding-section">
  <h2>Understanding What Happened</h2>
  <p>Let's break down what the crawler did:</p>

  <div class="process-steps">
    <div class="process-step">
      <div class="process-number">1</div>
      <div class="process-content">
        <h4>Connected to RSS Feed</h4>
        <p>The crawler fetched the Paul Graham RSS feed</p>
      </div>
    </div>

    <div class="process-step">
      <div class="process-number">2</div>
      <div class="process-content">
        <h4>Filtered by Date</h4>
        <p>Only articles from the last 365 days were selected</p>
      </div>
    </div>

    <div class="process-step">
      <div class="process-number">3</div>
      <div class="process-content">
        <h4>Extracted Content</h4>
        <p>For each article, the crawler visited the URL and extracted the text</p>
      </div>
    </div>

    <div class="process-step">
      <div class="process-number">4</div>
      <div class="process-content">
        <h4>Indexed to Vectara</h4>
        <p>Each article was sent to your Vectara corpus as a document</p>
      </div>
    </div>

    <div class="process-step">
      <div class="process-number">5</div>
      <div class="process-content">
        <h4>Made Searchable</h4>
        <p>Vectara automatically made all content searchable with semantic search</p>
      </div>
    </div>
  </div>
</div>

---

## Next Steps

Congratulations! You've successfully completed your first ingestion job. Here's what to explore next:

<div class="next-steps-section">
  <h3>
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
    Try Different Crawlers
  </h3>

  <div class="crawler-options">
    <a href="crawlers/website.md" class="crawler-card">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>
      <div>
        <h4>Website Crawler</h4>
        <p>Crawl an entire website</p>
      </div>
    </a>

    <a href="crawlers/notion.md" class="crawler-card">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>
      <div>
        <h4>Notion</h4>
        <p>Import your Notion workspace</p>
      </div>
    </a>

    <a href="crawlers/jira.md" class="crawler-card">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
      <div>
        <h4>Jira</h4>
        <p>Index your Jira tickets</p>
      </div>
    </a>

    <a href="crawlers/github.md" class="crawler-card crawler-card-highlight">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/><path d="M9 18c-4.51 2-5-2-7-2"/></svg>
      <div>
        <h4>GitHub</h4>
        <p>Crawl GitHub repositories</p>
      </div>
    </a>
  </div>

  <h3>
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
    Explore Advanced Features
  </h3>

  <ul class="feature-links">
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 11-6 6v3h3l6-6"/><path d="m22 12-4.7 4.7a1 1 0 0 1-1.4 0l-2.6-2.6a1 1 0 0 1 0-1.4L18 8"/><path d="m2 2 20 20"/></svg>
      <a href="features/table-extraction.md">Table Extraction: Automatically extract and summarize tables</a>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 8 6 4-6 4z"/></svg>
      <a href="features/image-processing.md">Image Processing: Use GPT-4o Vision to process images</a>
    </li>
    <li>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>
      <a href="features/chunking-strategies.md">Chunking Strategies: Optimize how documents are split</a>
    </li>
  </ul>
</div>

---

## Common Issues

<div class="issues-section">
  <div class="issue-card">
    <h4>Docker Not Running</h4>
    <p class="error-label"><strong>Error:</strong> <code>Cannot connect to the Docker daemon</code></p>
    <p><strong>Solution:</strong> Make sure Docker Desktop is running:</p>
    <pre><code class="language-bash">docker ps</code></pre>
  </div>

  <div class="issue-card">
    <h4>Invalid API Key</h4>
    <p class="error-label"><strong>Error:</strong> <code>Authentication failed</code></p>
    <p><strong>Solution:</strong> Verify your API key in secrets.toml, ensure the key has indexing permissions, and check you're using the correct profile name (default)</p>
  </div>

  <div class="issue-card">
    <h4>Corpus Not Found</h4>
    <p class="error-label"><strong>Error:</strong> <code>Corpus not found</code></p>
    <p><strong>Solution:</strong> Double-check your corpus key in the config file and verify the corpus exists in your Vectara account</p>
  </div>
</div>

---

## Getting Help

Need assistance? Here are your resources:

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

---

<p class="footer-text"><strong>Ready for more?</strong> Explore the <a href="configuration.md">Configuration Guide</a> to learn about all available options, or check out the <a href="crawlers/index.md">Crawlers Overview</a> to see what else you can ingest.</p>
