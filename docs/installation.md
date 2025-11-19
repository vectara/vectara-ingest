# Installation

This guide covers the different ways to install and set up vectara-ingest.

## Prerequisites

Before installing vectara-ingest, ensure you have:

- **Vectara Account**: Sign up for a [free Vectara account](https://console.vectara.com/signup)
- **Vectara Corpus**: Create a corpus with an [API key](https://docs.vectara.com/docs/api-keys) that has indexing permissions
- **Python 3.8+**: [Download Python](https://www.python.org/downloads/) if you don't have it
- **Docker**: [Install Docker](https://docs.docker.com/engine/install/) for containerized execution (recommended)

## Installation Methods

Vectara-ingest can be used in three ways:

1. **Docker Container** (Recommended)
2. **Conda Package**
3. **Python Package**

### Method 1: Docker Container (Recommended)

Docker provides the easiest and most consistent way to run vectara-ingest across different platforms.

#### Linux & macOS

```bash
# Clone the repository
git clone https://github.com/vectara/vectara-ingest.git
cd vectara-ingest

# Make the run script executable (Linux only)
chmod +x run.sh

# Set up your secrets file
cp secrets.example.toml secrets.toml
# Edit secrets.toml with your API key
```

#### Windows

1. Open Windows PowerShell and update WSL:
   ```powershell
   wsl --update
   ```

2. Install Ubuntu on WSL:
   ```powershell
   wsl --install ubuntu-20.04
   ```

3. Open your Linux terminal and clone the repository:
   ```bash
   git clone https://github.com/vectara/vectara-ingest.git
   cd vectara-ingest
   ```

4. Set up your secrets file:
   ```bash
   cp secrets.example.toml secrets.toml
   # Edit secrets.toml with your API key
   ```

!!! warning "Windows Users"
    Always run vectara-ingest commands from within the WSL 2 Linux environment, not from Windows PowerShell.

### Method 2: Conda Package

Install vectara-ingest as a conda package for CLI usage:

```bash
# Install from conda
conda install -c vectara vectara-ingest

# Or create a new environment
conda create -n vectara python=3.10
conda activate vectara
conda install -c vectara vectara-ingest
```

For detailed conda usage, see [conda/README.md](https://github.com/vectara/vectara-ingest/blob/main/conda/README.md).

### Method 3: Python Package

Install vectara-ingest as a Python package to use in your own code:

```bash
# Install with pip
pip install vectara-ingest

# Or install from source
git clone https://github.com/vectara/vectara-ingest.git
cd vectara-ingest
pip install -e .
```

Then import in your Python code:

```python
from core.indexer import Indexer
from crawlers.website_crawler import WebsiteCrawler

# Your code here
```

## Verifying Installation

### Docker Installation

Verify Docker is running:

```bash
docker --version
docker ps
```

### Python/Conda Installation

Verify the installation:

```bash
python -c "import vectara_ingest; print('Installation successful!')"
```

## Setting Up API Keys

### 1. Vectara API Key

1. Log in to the [Vectara Console](https://console.vectara.com)
2. Navigate to your corpus
3. Click **Access Control** or the **Authorization** tab
4. Copy your API key (use a personal API key or a query+write API key)

### 2. Create secrets.toml

Create a `secrets.toml` file in your project root:

```bash
cp secrets.example.toml secrets.toml
```

Edit `secrets.toml`:

```toml
[general]
OPENAI_API_KEY = "sk-..."          # Required for table/image summarization
ANTHROPIC_API_KEY = "sk-ant-..."   # Alternative to OpenAI

[default]
api_key = "your-vectara-api-key"

# Additional profiles for different projects
[production]
api_key = "your-production-api-key"

[staging]
api_key = "your-staging-api-key"
```

!!! tip "Profile Management"
    Use different profiles in `secrets.toml` to manage multiple Vectara corpora or environments.

### 3. Crawler-Specific Keys

Many crawlers require additional API keys. Add them to your `secrets.toml`:

```toml
[default]
api_key = "your-vectara-api-key"

# Notion
NOTION_API_KEY = "secret_..."

# Jira
JIRA_USERNAME = "your-email@company.com"
JIRA_PASSWORD = "your-jira-api-token"

# GitHub
GITHUB_TOKEN = "ghp_..."

# Google Drive
# (requires separate OAuth setup - see gdrive-oauth-setup.md)

# Slack
SLACK_TOKEN = "xoxb-..."

# ServiceNow
SERVICENOW_USERNAME = "admin"
SERVICENOW_PASSWORD = "password"
```

!!! warning "Security"
    Never commit `secrets.toml` to version control. It's included in `.gitignore` by default.

## Optional Dependencies

### For Advanced Features

Some features require additional API keys:

#### Table Summarization
Requires OpenAI or Anthropic API key in the `[general]` profile:

```toml
[general]
OPENAI_API_KEY = "sk-..."
```

#### Image Summarization
Requires OpenAI (GPT-4o) or Anthropic API key:

```toml
[general]
OPENAI_API_KEY = "sk-..."
```

#### LlamaParse Document Parser
```toml
[general]
LLAMA_CLOUD_API_KEY = "llx-..."
```

#### DocuPanda Document Parser
```toml
[general]
DOCUPANDA_API_KEY = "your-key"
```

## Custom CA Certificates

If you're using Vectara in your datacenter with internal certificate authorities:

1. Create an `ssl` directory in the project root
2. Add your `.crt` certificate files to the `ssl` directory
3. Update your crawler config:

```yaml
vectara:
  ssl_verify: /home/vectara/env/ca.pem
```

The Docker container automatically installs certificates from the `ssl` directory.

## HTTP Proxy Configuration

If you're behind a corporate proxy, set environment variables:

```bash
export http_proxy="http://proxy.company.com:8080"
export https_proxy="http://proxy.company.com:8080"
export no_proxy="localhost,127.0.0.1"
```

These variables are automatically used during Docker build.

## Additional Environment Variables

Create a `.run-env` file to inject custom environment variables:

```bash
HF_ENDPOINT="http://localhost:9000"
CUSTOM_VAR="value"
```

## Next Steps

- **First Time User?** Follow the [Getting Started Guide](getting-started.md) for a complete tutorial
- **Configure a Crawler**: See [Configuration Reference](configuration.md)
- **Explore Crawlers**: Browse [available crawlers](crawlers/index.md)
- **Deploy to Production**: Check [Deployment Options](deployment/docker.md)

## Troubleshooting

### Docker Issues

**Problem**: Docker build fails with "out of memory"

**Solution**: Increase Docker memory allocation in Docker Desktop settings (recommend at least 4GB)

---

**Problem**: Permission denied on `run.sh`

**Solution**:
```bash
chmod +x run.sh
```

### Python Issues

**Problem**: Import errors when using as Python package

**Solution**: Ensure you've installed all dependencies:
```bash
pip install -r requirements.txt
```

### API Key Issues

**Problem**: Authentication failed

**Solution**:
- Verify your API key has indexing permissions
- Check that the API key is in the correct `secrets.toml` profile
- Ensure the profile name matches what you're passing to `run.sh`

For more troubleshooting help, see [Deployment Troubleshooting](deployment/troubleshooting.md).
