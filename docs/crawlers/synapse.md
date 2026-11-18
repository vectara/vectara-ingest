# Synapse Crawler

The Synapse crawler indexes programs, studies, and associated wiki content from Synapse research platforms. It provides seamless integration with the AD Knowledge Portal and other Synapse-based knowledge systems.

## Overview

**Crawler Type:** `synapse`

**Supported Content:**
- Programs (research programs with descriptions)
- Studies (research studies with metadata)
- Study methods and methodologies
- Wiki pages associated with studies
- Research metadata and descriptions

**Key Features:**
- Multi-level content hierarchy (programs → studies → methods)
- Wiki content extraction and markdown conversion
- Synapse table queries for structured data
- Rich metadata preservation
- Support for complex research datasets

## Quick Start

### Basic Configuration

```yaml
vectara:
  corpus_key: synapse-research
  reindex: true

crawling:
  crawler_type: synapse

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
```

### Set Your Credentials

Add to `secrets.toml`:

```toml
[default]
SYNAPSE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## Prerequisites

### Getting a Synapse Authentication Token

The Synapse crawler requires a personal authentication token for API access.

**Steps to Generate Token:**

1. Log in to your Synapse account at [https://www.synapse.org/](https://www.synapse.org/)
2. Navigate to your account settings (click profile icon > Settings)
3. Go to the "Personal Access Tokens" section
4. Click "Create New Personal Access Tokens"
5. Give the token a descriptive name (e.g., "Vectara Ingest")
6. Select scopes for the token:
   - `view` - View profile and public content
   - `download` - Download files and access data
   - `modify` - Create and modify entities
7. Copy the generated token (you'll only see it once)
8. Add to `secrets.toml`:
   ```toml
   SYNAPSE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

**Important:** Keep your token secure and never commit it to version control.

### Getting Your Synapse Table IDs

The crawler requires Synapse table IDs for programs and studies.

**Finding Table IDs:**

1. Navigate to the Synapse project containing your tables
2. Click on the Programs table
3. In the browser URL, the ID appears as: `https://www.synapse.org/#!Synapse:syn12345678`
4. The ID is `syn12345678`
5. Record both your programs table ID and studies table ID

**Example Structure:**
- Programs Table ID: `syn12345678`
- Studies Table ID: `syn87654321`

## Configuration

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `synapse_token` | Synapse personal access token | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` |
| `programs_id` | Synapse ID of programs table | `syn12345678` |
| `studies_id` | Synapse ID of studies table | `syn87654321` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `source` | `"tables"` | Source identifier for metadata |

### Full Configuration Example

```yaml
vectara:
  corpus_key: synapse-knowledge-base
  reindex: true
  create_corpus: false

  # Processing options
  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: synapse

synapse_crawler:
  # Authentication
  synapse_token: "${SYNAPSE_TOKEN}"

  # Table Configuration
  programs_id: "syn12345678"
  studies_id: "syn87654321"

  # Optional: Source identifier
  source: "AD Knowledge Portal"
```

## How It Works

### Crawl Process

The Synapse crawler follows a three-phase indexing process:

1. **Phase 1: Index Programs**
   - Queries the programs table using Synapse table query API
   - Extracts: Program name, long description
   - Creates documents for each program
   - URLs point to AD Knowledge Portal program pages

2. **Phase 2: Index Studies**
   - Queries the studies table for all research studies
   - Extracts: Study name, description, associated methods
   - For each study, retrieves and indexes associated wiki content
   - Creates separate documents for studies and methods

3. **Phase 3: Index Methods**
   - For each study, parses comma-separated methods list
   - Retrieves wiki content for each method
   - Converts markdown to searchable text
   - Creates separate indexed documents per method

### Document Structure

Each indexed document contains:

```yaml
id: "unique_synapse_id"
title: "Program/Study/Method Name"
metadata:
  url: "https://adknowledgeportal.synapse.org/..."
  source: "AD Knowledge Portal"
  created: "2024-01-15T10:30:00Z"
sections:
  - text: "Description text"
  - text: "Wiki content (markdown converted to text)"
```

## Features

### Programs

The crawler indexes research programs with:

- **Program Name**: Extracted from table data
- **Description**: Full long description from table
- **URL**: Direct link to program details on AD Knowledge Portal
- **Metadata**: Creation timestamp, source identifier

Example indexed program:
```
Program AMP-AD
├── Description: A comprehensive study of Alzheimer's mechanisms...
├── URL: https://adknowledgeportal.synapse.org/Explore/Programs/DetailsPage?Program=AMP-AD
└── Metadata: Created on 2024-01-15
```

### Studies

Each study includes:

- **Study Name**: Extracted from studies table
- **Description**: Study description from table
- **Methods**: Comma-separated method list
- **Wiki Content**: Full wiki page content for study
- **URL**: Direct link to study details on AD Knowledge Portal
- **Metadata**: Creation timestamp, source identifier

### Methods

Methods are indexed as separate documents with:

- **Method Name**: Individual method name
- **Study Association**: Linked to parent study
- **Wiki Content**: Full wiki page content for method
- **URL**: Points to study page with methods anchor
- **Metadata**: Creation timestamp, method-specific metadata

### Wiki Content Processing

The crawler automatically:

1. Retrieves wiki pages associated with studies and methods
2. Converts markdown to HTML
3. Extracts plain text from HTML
4. Preserves content structure
5. Handles extraction errors gracefully (logs and continues)

**Error Handling:**
- If wiki retrieval fails, logs warning and continues
- Invalid wiki IDs are skipped
- Continues indexing remaining content

## Table Query Format

The crawler uses Synapse Query Language (SQL) to extract data:

### Programs Query

```sql
SELECT * from syn12345678;
```

Expected columns:
- `Program` - Program identifier/name
- `Long Description` - Full program description

### Studies Query

```sql
SELECT * from syn87654321;
```

Expected columns:
- `Program` - Associated program
- `Study` - Study identifier/name
- `Study_Description` - Study description text
- `Methods` - Comma-separated method names

## Metadata

Each indexed document contains the following metadata:

```yaml
# Content metadata
id: "syn123456789"
title: "Study Name or Method Name"
created: "2024-01-15T10:30:00Z"

# Source tracking
source: "AD Knowledge Portal"
url: "https://adknowledgeportal.synapse.org/Explore/Studies/DetailsPage/StudyDetails?Study=STUDY_ID"

# Content classification
type: "program" | "study" | "method"
```

## Common Use Cases

### Full Knowledge Base Index

Index all programs, studies, and methods:

```yaml
synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
```

This indexes:
- All programs
- All studies
- All associated methods

### AD Knowledge Portal Integration

Create a searchable index of the AD Knowledge Portal:

```yaml
vectara:
  corpus_key: ad-knowledge-portal

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
  source: "AD Knowledge Portal"
```

### Research Program Discovery

Index specific research programs:

```yaml
vectara:
  corpus_key: amp-ad-research

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
```

## Error Handling

Common issues and solutions:

### Authentication Error (401)

```
Error: 401 Unauthorized accessing Synapse
```

**Solution:**
- Verify token is correct and not expired
- Ensure token has required scopes
- Check SYNAPSE_TOKEN is set correctly in secrets.toml
- Regenerate token if needed

### Table Not Found (404)

```
Error: 404 Not Found: Table not found
```

**Solution:**
- Verify program and study table IDs are correct
- Ensure you have read access to the tables
- Check table IDs are in format `syn########`
- Verify tables still exist in Synapse

### Wiki Retrieval Failed

```
Error getting wiki WIKI_ID: [details]
```

**Solution:**
- This is logged as a warning and doesn't stop indexing
- Verify wiki page exists in Synapse
- Check user has read permission on wiki
- Some wiki pages may not exist - this is normal

### No Results

```
No content indexed / Empty table results
```

**Solution:**
- Verify table IDs point to valid, non-empty tables
- Check CQL query in UI works
- Ensure user has read access to tables
- Verify table schema matches expected columns

## Performance Tips

1. **Token Efficiency**
   - Reuse tokens across multiple crawls
   - Regenerate only when expired

2. **Table Query Optimization**
   - Verify table IDs are correct before crawling
   - Large tables may take longer to query

3. **Incremental Updates**
   - Use `reindex: false` for updates after first crawl
   - Full re-index with `reindex: true` when needed

4. **Resource Allocation**
   - Adequate memory for large wiki content
   - Monitor for wiki retrieval timeout issues

## Configuration Reference

See the [Configuration Reference](../configuration.md) for global Vectara settings like chunking strategy, SSL verification, and content processing options.

## Examples

### Basic Example

```yaml
vectara:
  corpus_key: synapse-research

crawling:
  crawler_type: synapse

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
```

### With Custom Source

```yaml
vectara:
  corpus_key: ad-knowledge-base

crawling:
  crawler_type: synapse

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
  source: "AD Knowledge Portal"
```

### With Advanced Processing

```yaml
vectara:
  corpus_key: synapse-full
  reindex: false
  verbose: true

  # Processing options
  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: synapse

synapse_crawler:
  synapse_token: "${SYNAPSE_TOKEN}"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
  source: "Synapse Knowledge Base"

metadata:
  source: synapse
  environment: production
  content_types:
    - programs
    - studies
    - methods
```

## Troubleshooting

### Slow Crawling

**Symptoms:** Crawler takes very long time

**Solutions:**
- Verify network connectivity to Synapse
- Check table sizes (large tables take longer)
- Monitor wiki retrieval performance
- Consider smaller table queries if possible

### Memory Issues

**Symptoms:** Out of memory errors, process crashes

**Solutions:**
- Reduce chunk size in Vectara config
- Increase Docker memory allocation
- Index in smaller batches
- Monitor wiki content sizes

### Missing Content

**Symptoms:** Some programs/studies don't appear in index

**Solutions:**
- Verify table IDs are correct
- Check user has read access to tables
- Verify table columns match expected schema
- Test table queries in Synapse UI

### Character Encoding Issues

**Symptoms:** Special characters display incorrectly

**Solutions:**
- Ensure UTF-8 encoding throughout pipeline
- Check wiki content encoding in Synapse
- Verify markdown conversion handling

## Limits and Constraints

- **API Rate Limits**: Synapse has API rate limits for authenticated requests
- **Table Size**: Large tables may take longer to query
- **Wiki Content**: Very large wiki pages may be chunked multiple times
- **Query Length**: Table queries must use valid Synapse Query Language syntax
- **Concurrent Requests**: Limited by Synapse API rate limits

## API Integration

### Synapse Client Library

The crawler uses the `synapseclient` Python library:

```python
import synapseclient
syn = synapseclient.Synapse()
syn.login(authToken=token)
```

### Query API

Queries Synapse tables using Synapse Query Language (SQL):

```python
df = syn.tableQuery("SELECT * from syn123456;", resultsAs="rowset").asDataFrame()
```

### Wiki API

Retrieves wiki pages:

```python
wiki_dict = syn.getWiki(wiki_id)
markdown = wiki_dict['markdown']
```

## Resources

- [Synapse Documentation](https://help.synapse.org/)
- [Synapse Python Client](https://python-docs.synapse.org/)
- [Synapse Query Language](https://help.synapse.org/articles/284495-using-synapse-query-language-sql)
- [Personal Access Tokens](https://help.synapse.org/articles/3796510)
- [AD Knowledge Portal](https://adknowledgeportal.synapse.org/)

## Related Crawlers

- [GitHub Crawler](github.md) - Index repositories and issues
- [Confluence Crawler](confluence.md) - Index wiki content
- [Website Crawler](website.md) - Crawl research portal websites

## Support

For help with the Synapse crawler:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Verify your Synapse token and table IDs
3. Check crawler logs for detailed error messages
4. See [Crawlers Overview](index.md) for general crawler help
5. Consult [Synapse Help Documentation](https://help.synapse.org/)
