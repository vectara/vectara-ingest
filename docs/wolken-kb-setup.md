# Wolken KB Crawler Setup Guide

This guide explains how to set up the Wolken KB crawler to index Knowledge Base articles from [Wolken ServiceDesk](https://www.wolkensoftware.com/) into Vectara.

## Overview

The Wolken KB crawler uses the [public Wolken Knowledge Base REST API](https://developer-beta.wolkensoftware.com/kb/docs.html) to fetch and index KB articles. It:

1. Authenticates using OAuth2 refresh token flow
2. Fetches all KB categories
3. For each category, fetches all articles (with pagination)
4. For each article, fetches the full details (introduction, cause, resolution, etc.)
5. Indexes each article as a structured document in Vectara

## Prerequisites

You need the following from your Wolken ServiceDesk instance:

| Credential | Description |
|---|---|
| **API Endpoint** | Base URL for your instance (e.g. `https://api-mycompany.wolkenservicedesk.com`) |
| **Domain** | Your Wolken tenant domain name |
| **Client ID** | OAuth client ID associated with the service account |
| **Service Account** | Service account email for API access |
| **Auth Code** | Basic authentication code for the token endpoint (e.g. `Basic dXNlcjpwYXNz`) |
| **Refresh Token** | OAuth refresh token for obtaining access tokens |

Contact your Wolken administrator to obtain these credentials.

## Configuration

### 1. Create the config file

Create a YAML config file (e.g. `config/wolken-kb.yaml`):

```yaml
vectara:
  corpus_key: wolken-kb
  reindex: false
  create_corpus: true

crawling:
  crawler_type: wolken

wolken_crawler:
  # API endpoint for your Wolken instance
  api_endpoint: "https://api-mycompany.wolkenservicedesk.com"
  # Domain name
  domain: "mycompany"
  # OAuth client ID
  client_id: "your-client-id"
  # Service account email
  service_account: "service@mycompany.com"
  # Basic auth code for token endpoint
  auth_code: "Basic ..."
  # Refresh token
  refresh_token: "your-refresh-token"

  # Number of items per API page (default: 100)
  batch_size: 100

  # Optional: filter by KB source ID
  # kb_source_id: 1

  # Content fields to extract from articles (in order)
  content_fields:
    - introduction
    - cause
    - environment
    - resolution
    - additionalInfo
```

### 2. Add secrets to `secrets.toml`

Instead of putting credentials directly in the config file, you can use `secrets.toml`:

```toml
[default]
api_key = "your-vectara-api-key"
WOLKEN_API_ENDPOINT = "https://api-mycompany.wolkenservicedesk.com"
WOLKEN_DOMAIN = "mycompany"
WOLKEN_CLIENT_ID = "your-client-id"
WOLKEN_SERVICE_ACCOUNT = "service@mycompany.com"
WOLKEN_AUTH_CODE = "Basic ..."
WOLKEN_REFRESH_TOKEN = "your-refresh-token"
```

All keys prefixed with `WOLKEN_` are automatically mapped to the `wolken_crawler` config section with the prefix stripped and lowercased. For example, `WOLKEN_API_ENDPOINT` becomes `wolken_crawler.api_endpoint`.

When using `secrets.toml`, you can leave the credential fields empty in the YAML config:

```yaml
wolken_crawler:
  api_endpoint: ""
  domain: ""
  client_id: ""
  service_account: ""
  auth_code: ""
  refresh_token: ""
  batch_size: 100
  content_fields:
    - introduction
    - cause
    - environment
    - resolution
    - additionalInfo
```

### 3. Run the crawler

**Using Docker:**

```bash
./run.sh config/wolken-kb.yaml default
```

**Using the CLI directly:**

```bash
python ingest.py --config-file config/wolken-kb.yaml --profile default
```

## Configuration Options

| Option | Type | Default | Description |
|---|---|---|---|
| `api_endpoint` | string | required | Base URL of your Wolken instance |
| `domain` | string | required | Wolken tenant domain |
| `client_id` | string | required | OAuth client ID |
| `service_account` | string | required | Service account email |
| `auth_code` | string | required | Basic auth header for token endpoint |
| `refresh_token` | string | required | OAuth refresh token |
| `batch_size` | integer | 100 | Number of items per API page |
| `kb_source_id` | integer | none | Filter categories by KB source ID |
| `content_fields` | list | see below | Fields to extract from article details |

### Content Fields

The `content_fields` option controls which fields are extracted from the article's `articleOtherInfo` and in what order. Available fields:

| Field | Description |
|---|---|
| `introduction` | Article introduction/overview |
| `cause` | Root cause description |
| `environment` | Environment/context information |
| `resolution` | Resolution/fix steps |
| `additionalInfo` | Additional information |
| `internalNotes` | Internal notes (may not be visible externally) |

Default: `["introduction", "cause", "environment", "resolution", "additionalInfo"]`

Each non-empty field becomes a separate section in the Vectara document with the field name as the section title.

If none of the configured fields have content, the crawler falls back to the article's `description` and `summary` fields.

## Document Structure

Each article is indexed as a Vectara document with:

- **Document ID**: `wolken-kb-{articleId}`
- **Title**: Article title from Wolken
- **Sections**: One per content field (Introduction, Cause, Resolution, etc.)
- **Metadata**:
  - `source`: "wolken_kb"
  - `article_id`: Wolken article ID
  - `category`: KB category name
  - `created_time`: Article creation timestamp
  - `updated_time`: Last update timestamp
  - `status_id`: Article status
  - `validation_status_id`: Validation status
  - `published_date`: Publication date
  - `url`: Article URL (if available)

## Resume Support

The crawler supports resume via the `reindex` flag:

- `reindex: false` — On restart, skip articles that were already indexed (uses crawl tracking if enabled)
- `reindex: true` — Re-index all articles from scratch

## API Reference

The crawler uses the following Wolken KB REST API endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/wolken-secure/oauth/token` | Get access token via refresh token |
| `GET` | `/wolken-secure/api/kb/categories/{limit}/{offset}` | List KB categories |
| `GET` | `/wolken-secure/api/kb/articles/{catId}/{limit}/{offset}` | List articles by category |
| `GET` | `/wolken-secure/api/kb/articles/{articleId}` | Get full article details |

Full API documentation: https://developer-beta.wolkensoftware.com/kb/docs.html
