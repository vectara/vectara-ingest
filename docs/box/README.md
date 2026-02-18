# Box Crawler Documentation

This directory contains documentation for the Box crawler integration with Vectara.

## Files

- **BOX_SETUP.md** - Complete setup guide for Box crawler
- **BOX_CREDENTIALS_README.md** - How to obtain and configure Box credentials
- **BOX_CLIENT_INSTRUCTIONS.txt** - Step-by-step client instructions
- **BOX_INGESTION_GUIDE.md** - Guide for running Box ingestion
- **BOX_REPORT_USAGE.md** - How to generate and use Box structure reports

## Quick Start

1. Follow [BOX_SETUP.md](BOX_SETUP.md) for initial setup
2. Configure credentials using [BOX_CREDENTIALS_README.md](BOX_CREDENTIALS_README.md)
3. Run ingestion following [BOX_INGESTION_GUIDE.md](BOX_INGESTION_GUIDE.md)

## Features

- JWT and OAuth 2.0 authentication
- As-user authentication for enterprise-wide access
- File extension filtering (include/exclude lists)
- Recursive folder traversal
- Structure report generation
- Graceful error handling with inspection folder

## Configuration Example

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: box_config.json
  folder_ids:
    - "323805611740"
  exclude_extensions: ['.csv', '.xlsx', '.xls', '.tsv']
  skip_indexing: false
  generate_report: false
```

## Support

For issues or questions, see the main vectara-ingest documentation.
