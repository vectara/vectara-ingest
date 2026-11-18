# Custom Crawler Setup Guide

This guide explains how to use custom or private crawler files with vectara-ingest without committing them to the repository.

## Overview

The `crawler_file` configuration option allows you to specify a custom crawler file that will be automatically copied to the `crawlers/` directory before the Docker image is built. This is useful for:

- Private crawlers that should not be committed to version control
- Organization-specific crawlers
- Testing new crawlers without modifying the repository

## Setup Instructions

### Step 1: Create Your Custom Crawler

Create your custom crawler Python file anywhere on your system. The crawler should follow the standard vectara-ingest crawler structure.

Example: `/home/myuser/my_custom_crawler.py`

```python
from core.crawler import Crawler

class MyCustomCrawler(Crawler):
    def __init__(self, cfg, endpoint, corpus_key, api_key):
        super().__init__(cfg, endpoint, corpus_key, api_key)
        # Your initialization code

    def crawl(self):
        # Your crawling logic
        pass
```

### Step 2: Add crawler_file to Your Configuration

In your configuration YAML file, add the `crawler_file` parameter under the `vectara` section:

```yaml
vectara:
  corpus_key: my_corpus
  reindex: true
  create_corpus: false

  # Path to your custom crawler file
  crawler_file: /home/myuser/my_custom_crawler.py

crawling:
  # The crawler_type should match your crawler's naming convention
  # For my_custom_crawler.py, use: my_custom
  crawler_type: my_custom

my_custom_crawler:
  # Your crawler-specific configuration
  # ...
```

### Step 3: Run the Ingest Script

Run the ingest script as usual:

```bash
sh run.sh config/my-config.yaml default
```

The `run.sh` script will:
1. Read the `crawler_file` path from your configuration
2. Verify the file exists
3. Copy it to the `crawlers/` directory
4. Build the Docker image with your custom crawler included
5. Run the crawler

## Configuration Details

### crawler_file Parameter

- **Location**: Under the `vectara` section in your config YAML
- **Type**: String (absolute or relative path to Python file)
- **Required**: No (only needed if using a custom crawler)
- **Example**: `crawler_file: /path/to/my_crawler.py`

### Naming Convention

The `crawler_type` should match the crawler class name pattern:

- If your file is `my_custom_crawler.py` with class `MyCustomCrawler`
- Use `crawler_type: my_custom`
- Add configuration section named `my_custom_crawler`

## Error Handling

If the custom crawler file is not found, the script will exit with an error:

```
Error: Custom crawler file not found at '/path/to/crawler.py'
```

Make sure:
- The file path is correct
- The file exists and is readable
- You have proper permissions to access the file

## Git and Version Control

Custom crawler files copied to the `crawlers/` directory are automatically excluded from git commits through patterns in `.gitignore`:

- `crawlers/*_custom_crawler.py`
- `crawlers/custom_*.py`

To ensure your custom crawler is not accidentally committed:
1. Name your crawler file with `custom` prefix or suffix
2. Or keep it outside the repository and only reference it via `crawler_file`

## Example Configuration

Complete example for a custom crawler:

```yaml
vectara:
  corpus_key: proprietary_data
  reindex: true
  create_corpus: false
  crawler_file: /home/user/proprietary_crawler.py

crawling:
  crawler_type: proprietary

proprietary_crawler:
  # Your custom crawler configuration
  api_endpoint: https://internal.company.com/api
  batch_size: 100
```

## Troubleshooting

**Issue**: Script exits with "Custom crawler file not found"
- **Solution**: Verify the file path is correct and the file exists

**Issue**: Crawler not being recognized
- **Solution**: Ensure `crawler_type` matches your crawler class naming convention

**Issue**: Custom crawler appears in git status
- **Solution**: Rename the file to include `custom` in the filename or add it to `.gitignore`
