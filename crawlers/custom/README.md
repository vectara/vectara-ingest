# Custom Crawlers Directory

This directory is for custom/private crawlers that should not be pushed to GitHub.

## Usage

1. Place your custom crawler files here (e.g., `techdocs_crawler.py`)
2. Reference them in your config using the `crawler_file` parameter:
   ```yaml
   vectara:
     crawler_file: /path/to/your/custom_crawler.py
   ```
3. The `run.sh` script will mount your custom crawler as a Docker volume

## Guidelines

- Custom crawlers in this directory are gitignored by default
- Use this for proprietary, work-in-progress, or client-specific crawlers
- Crawler filename must match the pattern: `{crawler_type}_crawler.py`
- Example: If `crawler_type: techdocs`, file must be named `techdocs_crawler.py`

## Note

This directory exists for organizational purposes. You can place your custom crawlers anywhere on your system - the `crawler_file` config parameter accepts any absolute path.
