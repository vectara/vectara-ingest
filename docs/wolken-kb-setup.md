# Wolken KB Crawler Setup Guide

This guide explains how to set up the Wolken KB crawler to index Knowledge Base articles from [Wolken ServiceDesk](https://www.wolkensoftware.com/) into Vectara.

## Overview

The Wolken KB crawler uses the [public Wolken Knowledge Base REST API](https://developer-beta.wolkensoftware.com/kb/docs.html) to fetch and index KB articles. It:

1. Authenticates using OAuth2 refresh token flow
2. Fetches all KB categories
3. For each category, fetches all articles (with pagination)
4. For each article, fetches the full details (introduction, cause, resolution, etc.)
5. Extracts configured product and ACL/entitlement metadata
6. Indexes each article as a structured document in one or more Vectara corpora

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

When using `secrets.toml`, you can leave the credential fields empty in the YAML config.

### 3. Optional: configure ACL/entitlement metadata

The crawler can extract ACL values from configurable Wolken fields. Dot paths are supported and are evaluated against article summary data, article detail data, and nested `articleOtherInfo` / `articleOtherInfoVO` objects.

```yaml
wolken_crawler:
  acl_fields:
    - entitlements
    - accessGroups
    - articleOtherInfo.visibilityGroups
  entitlements_metadata_key: entitlements
  default_entitlements:
    - public
```

If no ACL values are present, the crawler still writes the configured entitlement metadata key with an empty list (or `default_entitlements` if set) so downstream filters have a stable schema.

### 4. Optional: configure product-to-corpus routing

By default, all articles are indexed into `vectara.corpus_key` (`single_corpus` mode). For dev or customer deployments that require corpus mapping, enable `multi_corpus` and define exact product-name mappings:

```yaml
vectara:
  corpus_key: wolken-kb-default

wolken_crawler:
  mode: multi_corpus
  product_fields:
    - productname
    - products
    - articleOtherInfo.productname
  metadata_product_key: product
  corpus_mappings:
    vmware-cloud-foundation-wolken-kb:
      - VMware Cloud Foundation
    tanzu-wolken-kb:
      - Tanzu
```

An article is indexed into every mapped corpus whose product list matches. If no mapping matches, the article falls back to `vectara.corpus_key` and a warning is logged.

### 5. Run the crawler

**Using Docker:**

```bash
./run.sh config/wolken-kb.yaml default
```

**Using the CLI directly:**

```bash
python ingest.py --config-file config/wolken-kb.yaml --profile default
```

For an initial dev load, set `reindex: true` if you want to replace existing documents; otherwise leave `reindex: false` to skip documents tracked as already indexed.

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
| `mode` | string | `single_corpus` | `single_corpus` or `multi_corpus` |
| `product_fields` | list | see config | Wolken fields used for product extraction/routing |
| `metadata_product_key` | string | `product` | Metadata key for extracted products |
| `corpus_mappings` | map | `{}` | Target corpus key to product-name list mapping |
| `acl_fields` | list | `[]` | Wolken fields used for ACL/entitlement extraction |
| `entitlements_metadata_key` | string | `entitlements` | Metadata key for extracted ACL values |
| `default_entitlements` | list | `[]` | Entitlements to apply to every article |

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
  - `product` (configurable): Extracted product names, when present
  - `entitlements` (configurable): Extracted ACL/entitlement values
  - `target_corpus`: Target corpus key when `mode: multi_corpus`

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
