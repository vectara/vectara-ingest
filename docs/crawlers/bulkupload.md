# Bulk Upload Crawler

The Bulk Upload crawler enables batch ingestion of pre-formatted JSON documents directly into Vectara. It provides a flexible way to index structured data from any source by converting it to the Vectara document format.

## Overview

**Crawler Type:** `bulkupload`

**Supported Content:**
- Pre-formatted JSON documents
- Any data that can be converted to JSON format
- Structured and semi-structured data
- Custom document formats
- Batch uploads from external sources

**Key Features:**
- Simple JSON file input format
- Flexible document structure
- Batch processing with progress tracking
- Validation of document structure
- Direct indexing without transformations
- Support for Docker and local file paths

## Quick Start

### Basic Configuration

```yaml
vectara:
  corpus_key: bulk-data
  reindex: true

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "/path/to/documents.json"
```

### Prepare Your JSON File

Create a JSON file containing an array of document objects:

```json
[
  {
    "id": "doc1",
    "title": "Document Title",
    "sections": [
      { "text": "First section content" },
      { "text": "Second section content" }
    ],
    "metadata": {
      "source": "my-system",
      "date": "2024-01-15"
    }
  },
  {
    "id": "doc2",
    "title": "Another Document",
    "sections": [
      { "text": "Content here" }
    ]
  }
]
```

## Prerequisites

### JSON File Format Requirements

The Bulk Upload crawler requires a properly formatted JSON file with specific structure.

**File Requirements:**
- Must be valid JSON format
- Root must be an array `[]`
- Each element must be a valid document object
- Accessible from crawler (local or Docker path)
- UTF-8 encoding

### Understanding the Document Schema

Each document object must contain:

**Required Fields:**
- `id` - Unique document identifier (string)
- `sections` - Array of content sections (array of objects)

**Optional Fields:**
- `title` - Document title (string)
- `metadata` - Document metadata (object)
- `properties` - Custom document properties (object)

## Configuration

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `json_path` | Path to JSON file with documents | `/data/documents.json` |

### Optional Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| None | - | All parameters are optional once path is set |

### Full Configuration Example

```yaml
vectara:
  corpus_key: bulk-upload
  reindex: true
  create_corpus: false

  # Processing options
  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  # Path to JSON file (supports both local and Docker paths)
  json_path: "/data/documents.json"
```

## Document Format

### Required Structure

Every document in the JSON array must have:

```json
{
  "id": "unique-identifier",
  "sections": [
    { "text": "content" }
  ]
}
```

### Complete Example

```json
{
  "id": "doc-001",
  "title": "Complete Example Document",
  "sections": [
    {
      "text": "Introduction paragraph"
    },
    {
      "text": "Main content paragraph"
    },
    {
      "text": "Conclusion"
    }
  ],
  "metadata": {
    "source": "data-system",
    "date_created": "2024-01-15",
    "author": "System Admin",
    "category": "technical-docs"
  }
}
```

### Field Descriptions

**id (Required)**
- Unique identifier for the document
- Must be a string
- Used to track and update documents
- Cannot be duplicated within the same file
- Example: `"doc-123"`, `"article-2024-001"`

**title (Optional)**
- Human-readable document title
- Displayed in search results
- Helps users identify documents
- Example: `"Product Documentation"`, `"User Guide"`

**sections (Required)**
- Array of content sections
- Each section contains searchable text
- At least one section required
- Order is preserved for multi-section documents
- Example:
  ```json
  "sections": [
    { "text": "First part" },
    { "text": "Second part" }
  ]
  ```

**metadata (Optional)**
- Object containing document metadata
- Any custom key-value pairs allowed
- Useful for filtering and faceting
- Preserved in indexed documents
- Example:
  ```json
  "metadata": {
    "source": "crm",
    "customer_id": "12345",
    "updated": "2024-01-15",
    "tags": ["important", "new"]
  }
  ```

**properties (Optional)**
- Custom document properties
- For application-specific data
- Preserved in indexed documents
- Example:
  ```json
  "properties": {
    "priority": "high",
    "status": "active"
  }
  ```

## File Path Handling

The Bulk Upload crawler supports multiple file path modes:

### Local File Path

For local development:

```yaml
bulkupload_crawler:
  json_path: "/Users/username/data/documents.json"
```

Or with relative path:

```yaml
bulkupload_crawler:
  json_path: "./data/documents.json"
```

### Docker File Path

When running in Docker:

```yaml
bulkupload_crawler:
  json_path: "/home/vectara/data/file.json"
```

The crawler automatically maps:
- Docker path: `/home/vectara/data/`
- Local mount: Your volume mount path

### Environment Variable Reference

The file path can reference environment variables:

```yaml
bulkupload_crawler:
  json_path: "${DATA_PATH}/documents.json"
```

Set environment variable:
```bash
export DATA_PATH=/data
```

## How It Works

### Crawl Process

1. **File Discovery**
   - Locates JSON file using configured path
   - Handles both local and Docker paths
   - Resolves environment variables

2. **File Loading**
   - Reads entire JSON file into memory
   - Validates JSON syntax
   - Ensures file is array format

3. **Document Validation**
   - Checks each document has required fields
   - Validates document structure
   - Logs warnings for invalid documents

4. **Document Indexing**
   - Iterates through valid documents
   - Sends each to Vectara indexer
   - Tracks progress every 100 documents

5. **Completion**
   - Reports total documents indexed
   - Logs any skipped invalid documents

### Validation Rules

Documents must pass validation before indexing:

**Required Fields Check:**
- `id` field exists and is string
- `sections` field exists and is array
- At least one section present

**Invalid Document Handling:**
```python
def is_valid(json_object):
    return 'id' in json_object and 'sections' in json_object
```

- Invalid documents are skipped
- Warning logged with document details
- Processing continues

## Features

### Flexible Document Structure

Documents can contain any metadata structure:

```json
{
  "id": "product-123",
  "title": "Product X Documentation",
  "sections": [
    { "text": "Feature overview" },
    { "text": "Installation guide" },
    { "text": "API reference" }
  ],
  "metadata": {
    "product": "Product X",
    "version": "2.0",
    "status": "published",
    "team": "documentation",
    "created": "2024-01-15",
    "tags": ["docs", "api", "guide"]
  },
  "properties": {
    "internal_id": 12345,
    "department": "engineering"
  }
}
```

### Batch Processing

Progress tracking for large datasets:

```
Indexing 10000 JSON documents from JSON file
finished 0 documents so far
finished 100 documents so far
finished 200 documents so far
...
finished 9900 documents so far
```

- Progress logged every 100 documents
- Helpful for monitoring long-running crawls

### Multiple Document Types

Handle different document structures in same file:

```json
[
  {
    "id": "article-1",
    "title": "Blog Post",
    "sections": [{ "text": "Blog content" }],
    "metadata": { "type": "blog" }
  },
  {
    "id": "doc-1",
    "title": "Technical Doc",
    "sections": [{ "text": "Technical content" }],
    "metadata": { "type": "documentation" }
  },
  {
    "id": "faq-1",
    "title": "FAQ Entry",
    "sections": [{ "text": "FAQ content" }],
    "metadata": { "type": "faq" }
  }
]
```

## Common Use Cases

### Simple Data Migration

Migrate data from external systems:

```json
[
  {
    "id": "migrated-1",
    "title": "From Legacy System",
    "sections": [{ "text": "Migrated content" }]
  }
]
```

### Knowledge Base Import

Import structured knowledge base:

```json
[
  {
    "id": "kb-001",
    "title": "How to Configure API",
    "sections": [
      { "text": "Step 1: Setup" },
      { "text": "Step 2: Authentication" },
      { "text": "Step 3: Testing" }
    ],
    "metadata": {
      "category": "API",
      "difficulty": "intermediate"
    }
  }
]
```

### Product Documentation

Index product documentation:

```json
[
  {
    "id": "product-features",
    "title": "Feature Overview",
    "sections": [
      { "text": "Feature A description" },
      { "text": "Feature B description" }
    ],
    "metadata": {
      "product": "Product X",
      "version": "2.0"
    }
  }
]
```

### CRM Data Export

Index CRM data:

```json
[
  {
    "id": "account-12345",
    "title": "Acme Corporation",
    "sections": [
      { "text": "Company overview and description" }
    ],
    "metadata": {
      "account_id": "12345",
      "industry": "Technology",
      "revenue": "1M-10M"
    }
  }
]
```

### Custom Application Data

Index custom application data:

```json
[
  {
    "id": "app-record-123",
    "title": "Custom Record",
    "sections": [{ "text": "Record content" }],
    "metadata": {
      "app_id": "app123",
      "user_id": "user456"
    },
    "properties": {
      "custom_field": "custom_value"
    }
  }
]
```

## Metadata

Each indexed document preserves its structure and metadata:

```yaml
# Content metadata
id: "unique-doc-id"
title: "Document Title"

# User-provided metadata
metadata:
  source: "data-system"
  category: "documentation"
  date: "2024-01-15"
  # Any custom fields

# Custom properties
properties:
  # Application-specific data
```

## Error Handling

Common issues and solutions:

### Invalid JSON Format

```
Error: json.JSONDecodeError - JSON file contains syntax error
```

**Solution:**
- Validate JSON syntax (use JSON validator tool)
- Ensure file is valid JSON
- Check for missing quotes, commas, brackets
- Verify UTF-8 encoding

### File Not Found

```
Error: FileNotFoundError - JSON file not found
```

**Solution:**
- Verify file path is correct
- Check file exists at specified location
- For Docker: verify volume mount
- Check file permissions

### File is Not Array

```
Error: JSON file must contain an array of JSON objects
```

**Solution:**
- Root of JSON must be array `[]`
- Not valid: `{ "doc": {} }`
- Valid: `[{ "doc": {} }]`
- Wrap non-array content in array

### Missing Required Fields

```
Warning: invalid JSON object - missing required fields
```

**Solution:**
- Every document needs `id` and `sections`
- `id` must be string
- `sections` must be array with at least one element
- Invalid documents are skipped with warning

### Empty Sections

```
Warning: Document with empty sections array
```

**Solution:**
- Each section must have `text` field
- Add at least one section with content
- Section format: `{ "text": "content" }`

### Duplicate Document IDs

```
Warning: Duplicate document ID - using last occurrence
```

**Solution:**
- Ensure each document has unique `id`
- Rename documents with conflicting IDs
- Check for accidental duplicates in file

## Performance Tips

1. **File Size Management**
   - Split very large files (>100k documents)
   - Process in batches for better memory usage
   - Monitor progress output

2. **Data Preparation**
   - Validate JSON before upload
   - Ensure proper encoding
   - Remove unnecessary fields to reduce file size

3. **Incremental Uploads**
   - Use separate files for different data types
   - Process on schedule if regularly updated
   - Use `reindex: false` after initial load

4. **Memory Optimization**
   - Reduce chunk size for large documents
   - Adjust Docker memory allocation if needed
   - Monitor system resources during indexing

## Configuration Reference

See the [Configuration Reference](../configuration.md) for global Vectara settings like chunking strategy, SSL verification, and content processing options.

## Examples

### Basic Example

```yaml
vectara:
  corpus_key: my-bulk-data

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "./data/documents.json"
```

### With Metadata

```yaml
vectara:
  corpus_key: structured-data

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "/data/products.json"
```

Example JSON:
```json
[
  {
    "id": "prod-001",
    "title": "Product A",
    "sections": [{ "text": "Product description" }],
    "metadata": {
      "sku": "SKU-001",
      "price": "$99.99",
      "category": "Electronics"
    }
  }
]
```

### With Custom Processing

```yaml
vectara:
  corpus_key: bulk-upload-full
  reindex: false
  verbose: true

  # Processing options
  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "/home/vectara/data/file.json"

metadata:
  source: bulk-upload
  environment: production
```

### Docker Configuration

```yaml
vectara:
  corpus_key: docker-bulk-data

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "/home/vectara/data/file.json"
```

Set up Docker volume mount:
```bash
docker run -v /local/data:/home/vectara/data vectara-ingest:latest
```

### Large Batch Processing

For large datasets, split into multiple files:

**config/bulk-batch-1.yaml:**
```yaml
vectara:
  corpus_key: bulk-data-1

bulkupload_crawler:
  json_path: "/data/batch1.json"
```

**config/bulk-batch-2.yaml:**
```yaml
vectara:
  corpus_key: bulk-data-2

bulkupload_crawler:
  json_path: "/data/batch2.json"
```

Run both:
```bash
bash run.sh config/bulk-batch-1.yaml default
bash run.sh config/bulk-batch-2.yaml default
```

## Troubleshooting

### Slow Processing

**Symptoms:** Indexing takes very long time

**Solutions:**
- Check JSON file size (very large files take longer)
- Verify network connectivity to Vectara
- Monitor progress output for hanging
- Split file into smaller batches

### Memory Issues

**Symptoms:** Out of memory errors, process crashes

**Solutions:**
- Reduce chunk size in Vectara config
- Split large JSON files into smaller pieces
- Increase Docker memory allocation
- Process in smaller batches

### Missing Content

**Symptoms:** Some documents don't get indexed

**Solutions:**
- Verify all documents have `id` and `sections`
- Check JSON file validity
- Review logs for invalid document warnings
- Validate required fields present

### Character Encoding Issues

**Symptoms:** Special characters display incorrectly

**Solutions:**
- Ensure JSON file uses UTF-8 encoding
- Validate UTF-8 in source system
- Check for encoding declaration in JSON

## Limits and Constraints

- **File Size**: Limited by available memory
- **Document Count**: Can handle thousands of documents
- **Document Size**: Individual documents should be reasonable size
- **Section Count**: No hard limit on sections per document
- **Metadata Size**: Metadata should be reasonable size

## Preparing Your JSON File

### Using Python

```python
import json

documents = [
    {
        "id": "doc-1",
        "title": "First Document",
        "sections": [
            {"text": "This is the first document"}
        ],
        "metadata": {
            "source": "my-system",
            "date": "2024-01-15"
        }
    }
]

with open("documents.json", "w") as f:
    json.dump(documents, f, indent=2)
```

### Using Node.js

```javascript
const documents = [
    {
        id: "doc-1",
        title: "First Document",
        sections: [
            { text: "This is the first document" }
        ],
        metadata: {
            source: "my-system",
            date: "2024-01-15"
        }
    }
];

const fs = require('fs');
fs.writeFileSync('documents.json', JSON.stringify(documents, null, 2));
```

### Using CSV to JSON

Convert CSV to JSON format:

```python
import csv
import json

documents = []
with open('data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        doc = {
            "id": f"doc-{i+1}",
            "title": row.get('title', ''),
            "sections": [
                {"text": row.get('content', '')}
            ],
            "metadata": row
        }
        documents.append(doc)

with open('documents.json', 'w') as f:
    json.dump(documents, f, indent=2)
```

## JSON Validation

Validate your JSON file before uploading:

### Online Tools
- [JSONLint](https://jsonlint.com/) - Quick JSON validation
- [JSON Schema Validator](https://www.jsonschemavalidator.net/)

### Command Line

```bash
# Using Python
python3 -m json.tool documents.json > /dev/null && echo "Valid JSON"

# Using jq (if installed)
jq '.' documents.json > /dev/null && echo "Valid JSON"

# Using Node.js
node -e "JSON.parse(require('fs').readFileSync('documents.json', 'utf8'))" && echo "Valid JSON"
```

## API Integration

The Bulk Upload crawler uses the core indexer:

```python
from core.crawler import Crawler

class BulkuploadCrawler(Crawler):
    def crawl(self) -> None:
        # Load JSON file
        # Validate documents
        # Index each document
        self.indexer.index_document(document)
```

## Running the Crawler

### Prepare Your Data

1. Create or export JSON file
2. Validate JSON format
3. Ensure all documents have required fields
4. Update configuration with file path

### Create Configuration

```yaml
vectara:
  corpus_key: my-bulk-data

crawling:
  crawler_type: bulkupload

bulkupload_crawler:
  json_path: "/path/to/your/documents.json"
```

### Run the Crawler

```bash
bash run.sh config/bulk-data.yaml default
```

### Monitor Progress

```bash
# Watch logs
docker logs -f vingest
```

## Resources

- [JSON Documentation](https://www.json.org/)
- [JSON Schema](https://json-schema.org/)
- [Vectara Documentation](https://docs.vectara.com/)

## Related Crawlers

- [Folder Crawler](folder.md) - Index local files
- [Website Crawler](website.md) - Crawl websites
- [Database Crawler](database.md) - Index database records

## Support

For help with the Bulk Upload crawler:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Verify your JSON format is valid
3. Ensure required fields are present
4. Check crawler logs for detailed error messages
5. See [Crawlers Overview](index.md) for general crawler help
