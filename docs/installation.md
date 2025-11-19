# Installation

<p class="subtitle">Get vectara-ingest up and running on your system. Choose between Docker (recommended) or local installation.</p>

---

## Prerequisites

Before installing vectara-ingest, ensure you have:

<div class="prerequisites-list">
  <div class="prerequisite-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span>A Vectara account (<a href="https://console.vectara.com/signup">sign up for free</a>)</span>
  </div>
  <div class="prerequisite-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span>Git installed on your system</span>
  </div>
  <div class="prerequisite-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="check-icon"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
    <span>Either Docker (recommended) or Python 3.8+ with pip</span>
  </div>
</div>

---

## Method 1: Using Docker <span class="recommended-badge">Recommended</span>

Docker is the easiest way to run vectara-ingest without managing Python dependencies.

### Step 1: Install Docker

If you don't have Docker installed:

- **Mac:** Download [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)
- **Windows:** Download [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- **Linux:** Follow the [Docker Engine installation guide](https://docs.docker.com/engine/install/)

### Step 2: Clone the Repository

```bash
git clone https://github.com/vectara/vectara-ingest.git
cd vectara-ingest
```

### Step 3: Build the Docker Image

```bash
docker build -t vectara-ingest .
```

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">First Build Takes Time</p>
    <p>The initial build downloads and installs all dependencies. This typically takes 5-10 minutes depending on your internet connection.</p>
  </div>
</div>

### Step 4: Run a Test Crawl

Test your installation with a sample configuration:

```bash
bash run.sh config/news-bbc.yaml default
```

---

## Method 2: Local Installation

Install vectara-ingest directly on your system using Python.

### Step 1: Clone the Repository

```bash
git clone https://github.com/vectara/vectara-ingest.git
cd vectara-ingest
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv

source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Run a Test Crawl

```bash
python3 main.py config/news-bbc.yaml default
```

<div class="warning-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Platform-Specific Dependencies</p>
    <p>Some crawlers (like Playwright for web scraping) may require additional system libraries. Check the specific crawler documentation if you encounter issues.</p>
  </div>
</div>

---

## Verify Installation

To verify your installation is working correctly:

<div class="verification-list">
  <div class="verification-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="terminal-icon"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
    <div class="verification-content">
      <p class="verification-title">Check Docker is Running</p>
      <pre><code class="language-bash">docker ps</code></pre>
    </div>
  </div>

  <div class="verification-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="terminal-icon"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
    <div class="verification-content">
      <p class="verification-title">List Available Configurations</p>
      <pre><code class="language-bash">ls config/</code></pre>
    </div>
  </div>

  <div class="verification-item">
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="terminal-icon"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
    <div class="verification-content">
      <p class="verification-title">View Help Information</p>
      <pre><code class="language-bash">docker run vectara-ingest --help</code></pre>
    </div>
  </div>
</div>

---

## Configuration Files

After installation, you'll work with two main types of files:

<div class="config-grid">
  <div class="config-card">
    <div class="config-header">
      <div class="config-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
      </div>
      <h3>secrets.toml</h3>
    </div>
    <p>Stores your Vectara API credentials and other sensitive information. Never commit this file to version control.</p>
    <pre><code class="language-toml">[default]
api_key = "zwt_your_api_key"</code></pre>
  </div>

  <div class="config-card">
    <div class="config-header">
      <div class="config-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
      </div>
      <h3>config/*.yaml</h3>
    </div>
    <p>Configuration files that define what to crawl and how to ingest it. Each file represents one crawler job.</p>
    <pre><code class="language-yaml">vectara:
  corpus_key: your-key

crawling:
  crawler_type: rss</code></pre>
  </div>
</div>

---

## Next Steps

Now that you have vectara-ingest installed, here's what to do next:

<div class="next-steps-grid">
  <a href="getting-started.md" class="next-step-card">
    <h3>Quick Start Guide →</h3>
    <p>Follow a step-by-step tutorial to run your first ingestion job</p>
  </a>

  <a href="crawlers/index.md" class="next-step-card">
    <h3>Explore Crawlers →</h3>
    <p>Learn about all available crawler types and their capabilities</p>
  </a>
</div>

---

## Troubleshooting

<div class="troubleshooting-section">
  <div class="troubleshooting-card">
    <h4>Docker Build Fails</h4>
    <p>If the Docker build fails, try:</p>
    <ul>
      <li>Ensure Docker Desktop is running</li>
      <li>Check your internet connection</li>
      <li>Try <code>docker system prune</code> to clear cache</li>
    </ul>
  </div>

  <div class="troubleshooting-card">
    <h4>Permission Denied Errors</h4>
    <p>On Linux, you may need to run Docker commands with sudo or add your user to the docker group:</p>
    <pre><code class="language-bash">sudo usermod -aG docker $USER</code></pre>
  </div>

  <div class="troubleshooting-card">
    <h4>Python Version Issues</h4>
    <p>Vectara-ingest requires Python 3.8 or higher. Check your version with <code>python3 --version</code></p>
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
