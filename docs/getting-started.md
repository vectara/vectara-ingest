# Getting Started

This tutorial will guide you through your first data ingestion job with vectara-ingest. We'll crawl content from [Paul Graham's website](http://www.paulgraham.com/index.html) using the RSS crawler and ingest it into Vectara.

## What You'll Learn

- How to configure a crawler
- How to set up authentication
- How to run an ingestion job
- How to verify the ingestion and query your data

## Prerequisites

Before starting, make sure you have:

- ✅ Completed the [Installation](installation.md)
- ✅ A Vectara corpus with an API key
- ✅ Docker installed and running

## Step 1: Set Up Your Secrets

First, configure your Vectara API credentials:

```bash
# Copy the example secrets file
cp secrets.example.toml secrets.toml
```

Edit `secrets.toml` and add your Vectara API key:

```toml
[default]
api_key = "zwt_your_vectara_api_key_here"
```

!!! tip "Getting Your API Key"
    To retrieve your API key from the Vectara console:

    1. Log in to [console.vectara.com](https://console.vectara.com)
    2. Navigate to your corpus
    3. Click **Access Control** or the **Authorization** tab
    4. Copy your personal API key or create a query+index API key

## Step 2: Get Your Corpus Key

You'll need your corpus key for the configuration:

1. In the Vectara console, click on your corpus name
2. Your corpus key appears at the top of the screen
3. Copy this key for the next step

## Step 3: Create Your Configuration

Create a new configuration file for the Paul Graham RSS crawler:

```bash
# Copy an example config
cp config/news-bbc.yaml config/pg-rss.yaml
```

Edit `config/pg-rss.yaml`:

```yaml
vectara:
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
  days_past: 365
```

!!! warning "Replace Values"
    Make sure to replace `your-corpus-key-here` with your actual corpus key from Step 2.

## Step 4: Run the Crawler

Now you're ready to run your first ingestion job!

```bash
bash run.sh config/pg-rss.yaml default
```

This command will:

1. Build a Docker container (first time only - this may take a few minutes)
2. Start the crawler with your configuration
3. Begin ingesting content into your Vectara corpus

!!! info "First Run"
    The first time you run this command, Docker needs to build the container image. This involves downloading dependencies and can take 5-10 minutes. Subsequent runs will be much faster.

### Monitor Progress

In a new terminal, watch the crawler logs:

```bash
docker logs -f vingest
```

You should see output like:

```
INFO: Starting RSS crawler for source: pg
INFO: Found 42 items in RSS feed
INFO: Processing: What You Can't Say
INFO: Indexed document: what-you-cant-say
INFO: Processing: Hackers and Painters
INFO: Indexed document: hackers-and-painters
...
```

Press `Ctrl+C` to stop following the logs (the crawler will continue running).

## Step 5: Query Your Data

While the crawler is running, you can start querying your corpus!

### Using the Vectara Console

1. Go to [console.vectara.com](https://console.vectara.com)
2. Click **Data** → **Your Corpus Name**
3. Click the **Query** tab
4. Try some queries:
   - "What is a maker schedule?"
   - "How to start a startup"
   - "What makes a good programming language?"

### Using the API

You can also query via the Vectara API:

```python
import requests

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

print(response.json())
```

## Understanding What Happened

Let's break down what the crawler did:

1. **Connected to RSS Feed**: The crawler fetched the Paul Graham RSS feed
2. **Filtered by Date**: Only articles from the last 365 days were selected
3. **Extracted Content**: For each article, the crawler visited the URL and extracted the text
4. **Indexed to Vectara**: Each article was sent to your Vectara corpus as a document
5. **Made Searchable**: Vectara automatically made all content searchable with semantic search

## Next Steps

Congratulations! You've successfully completed your first ingestion job. Here's what to explore next:

### Try Different Crawlers

- **Website Crawler**: Crawl an entire website - [Website Crawler Guide](crawlers/website.md)
- **Notion**: Import your Notion workspace - [Notion Crawler Guide](crawlers/notion.md)
- **Jira**: Index your Jira tickets - [Jira Crawler Guide](crawlers/jira.md)
- **GitHub**: Crawl GitHub repositories - [GitHub Crawler Guide](crawlers/github.md)

### Explore Advanced Features

- **Table Extraction**: Automatically extract and summarize tables - [Table Extraction](features/table-extraction.md)
- **Image Processing**: Use GPT-4o Vision to process images - [Image Processing](features/image-processing.md)
- **Chunking Strategies**: Optimize how documents are split - [Chunking Strategies](features/chunking-strategies.md)

### Deploy to Production

- **Cloud Deployment**: Deploy on Render or AWS - [Deployment Guide](deployment/render.md)
- **Scheduled Jobs**: Set up recurring crawls - [Docker Deployment](deployment/docker.md)

### Build Custom Crawlers

- **Custom Crawler**: Build your own crawler for unique data sources - [Custom Crawler Guide](advanced/custom-crawler.md)

## Common Issues

### Docker Not Running

**Error**: `Cannot connect to the Docker daemon`

**Solution**: Make sure Docker Desktop is running:
```bash
docker ps
```

### Invalid API Key

**Error**: `Authentication failed`

**Solution**:
- Verify your API key in `secrets.toml`
- Ensure the key has indexing permissions
- Check you're using the correct profile name (`default`)

### Corpus Not Found

**Error**: `Corpus not found`

**Solution**:
- Double-check your corpus key in the config file
- Verify the corpus exists in your Vectara account

### RSS Feed Issues

**Error**: `Failed to fetch RSS feed`

**Solution**:
- Verify the RSS URL is accessible
- Check your internet connection
- Try a different RSS feed to test

## Configuration Quick Reference

Here's a template for quick reference:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: YOUR_CORPUS_KEY
  reindex: false
  verbose: true

crawling:
  crawler_type: rss

rss_crawler:
  source: SOURCE_NAME
  rss_pages:
    - "RSS_FEED_URL"
  days_past: 365
```

## Getting Help

Need help? Here are your resources:

- **Documentation**: Browse the [full documentation](index.md)
- **Discord**: Join our [Discord community](https://discord.com/invite/GFb8gMz6UH)
- **GitHub Issues**: [Report bugs or ask questions](https://github.com/vectara/vectara-ingest/issues)
- **Vectara Docs**: Check the [Vectara platform documentation](https://docs.vectara.com)

---

**Ready for more?** Explore the [Configuration Guide](configuration.md) to learn about all available options, or check out the [Crawlers Overview](crawlers/index.md) to see what else you can ingest.
