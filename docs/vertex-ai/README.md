# Vertex AI Documentation

This directory contains documentation for using Google Cloud Vertex AI with Vectara ingestion.

## Files

- **VERTEX_AI_SETUP.md** - Complete setup guide for Vertex AI integration

## Overview

Vertex AI integration enables AI-powered table and image summarization during document processing using Google's Gemini models.

## Features

- Table summarization using Gemini models
- Image summarization and analysis
- Cost-effective processing with Gemini Flash
- Service account authentication
- Configurable model selection

## Quick Start

1. Follow [VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md) for setup
2. Create a Google Cloud service account
3. Configure credentials in your config file
4. Enable table/image summarization

## Configuration Example

```yaml
doc_processing:
  summarize_tables: true
  summarize_images: true

table_model_config:
  provider: vertex
  model_name: gemini-1.5-flash-002
  project_id: your-project-id
  location: us-central1
  credentials_file: gcp_service_account.json

image_model_config:
  provider: vertex
  model_name: gemini-1.5-flash-002
  project_id: your-project-id
  location: us-central1
  credentials_file: gcp_service_account.json
```

## Environment Variable

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/gcp_service_account.json"
```

## Support

For issues or questions, see the main vectara-ingest documentation.
