# Hugging Face Datasets Crawler

The Hugging Face Datasets crawler indexes datasets from the Hugging Face Hub with advanced filtering, column selection, and parallel processing capabilities. It supports streaming mode for large datasets and flexible data transformation options.

## Overview

- **Crawler Type**: `hfdataset`
- **Authentication**: Optional (public datasets)
- **Data Source**: Hugging Face Hub (huggingface.co/datasets)
- **Data Format**: Structured tabular data with metadata
- **Content**: Database-style records indexed by columns
- **Scaling**: Ray-based parallel processing for large datasets
- **Streaming**: Memory-efficient streaming for massive datasets

## Use Cases

- Index machine learning training datasets for discovery
- Create searchable data catalogs
- Build knowledge bases from structured data
- Index documentation datasets (e.g., DETR, SQuAD)
- Combine data records into searchable documents
- Parallel processing of large tabular datasets
- Build searchable repositories of research data

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hf-datasets

crawling:
  crawler_type: hfdataset

hfdataset_crawler:
  # Hugging Face dataset name
  dataset_name: "wikitext"

  # Dataset split to use
  split: "train"

  # Columns containing text to index
  text_columns:
    - "text"

  # Columns for metadata
  metadata_columns:
    - "title"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: hf-datasets
  reindex: false
  verbose: true

crawling:
  crawler_type: hfdataset

hfdataset_crawler:
  # Dataset identifier
  dataset_name: "multi_woz_v2.2"
  split: "train"

  # Text columns to index (required)
  text_columns:
    - "user_turns"
    - "system_turns"

  # Title for documents
  title_column: "dialogue_id"

  # Unique identifier for rows
  id_column: "dialogue_id"

  # Metadata columns
  metadata_columns:
    - "domain"
    - "services"

  # Filtering
  select_condition: "domain='restaurant'"

  # Row selection
  num_rows: 1000
  start_row: 0

  # Parallel processing
  ray_workers: 4  # -1=all cores, 0=sequential

metadata:
  source: hugging-face
  category: datasets
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `dataset_name` | string | Yes | - | Hugging Face dataset identifier |
| `split` | string | No | `corpus` | Dataset split to use |
| `text_columns` | list | Yes | - | Columns containing text to index |
| `title_column` | string | No | - | Column to use as document title |
| `id_column` | string | No | - | Column for unique document ID |
| `metadata_columns` | list | No | `[]` | Columns to include as metadata |
| `select_condition` | string | No | - | Filter condition (e.g., "domain=value") |
| `num_rows` | int | No | - | Maximum rows to index |
| `start_row` | int | No | `0` | Row offset to start from |
| `ray_workers` | int | No | `0` | Parallel workers (0=sequential, -1=all cores) |

## How It Works

1. **Dataset Loading**: Loads dataset from Hugging Face Hub in streaming mode
2. **Filtering**: Applies optional row filtering based on `select_condition`
3. **Row Selection**: Skips `start_row` rows and limits to `num_rows`
4. **Column Processing**: Combines text columns and extracts metadata
5. **Parallel Indexing**: Uses Ray for distributed processing (if configured)
6. **Document Creation**: Creates documents with ID, title, text, and metadata
7. **Indexing**: Uploads documents to Vectara

### Streaming Mode

The crawler uses Hugging Face streaming by default:

```yaml
hfdataset_crawler:
  dataset_name: "wikipedia"  # Streams data on-demand
```

**Advantages**:
- Works with datasets larger than available memory
- No download required upfront
- Cost-effective for large datasets

## Metadata Captured

The crawler extracts:

- **Document ID**: From `id_column` (or generated)
- **Title**: From `title_column` (optional)
- **Text Content**: Combined from all `text_columns`
- **Custom Metadata**: From `metadata_columns`
- **Source**: Always "hf_dataset"

### Metadata Example

```python
{
  "source": "hf_dataset",
  "_source": "multi_woz_v2.2",  # Original source
  "domain": "restaurant",         # From metadata_columns
  "services": "booking"           # From metadata_columns
}
```

## Examples

### Wikipedia Indexing

```yaml
vectara:
  corpus_key: wikipedia

crawling:
  crawler_type: hfdataset

hfdataset_crawler:
  dataset_name: "wikipedia"
  split: "train"

  text_columns:
    - "text"

  title_column: "title"
  id_column: "id"

  metadata_columns:
    - "url"

  num_rows: 10000  # Limit for testing

metadata:
  source: hugging-face
  dataset: wikipedia
  content_type: encyclopedia
```

### Multi-turn Dialogue Dataset

```yaml
hfdataset_crawler:
  dataset_name: "multi_woz_v2.2"
  split: "train"

  text_columns:
    - "user_turns"
    - "system_turns"

  title_column: "dialogue_id"
  id_column: "dialogue_id"

  metadata_columns:
    - "domain"
    - "services"
    - "turn_count"

  num_rows: 5000

metadata:
  source: hugging-face
  category: dialogue
  domain: conversational-ai
```

### Filtered Question Answering Dataset

```yaml
hfdataset_crawler:
  dataset_name: "squad"
  split: "train"

  text_columns:
    - "context"
    - "question"
    - "answers"

  title_column: "id"
  id_column: "id"

  metadata_columns:
    - "title"

  num_rows: 10000

metadata:
  source: hugging-face
  category: question-answering
```

### Code Dataset with Selection

```yaml
hfdataset_crawler:
  dataset_name: "the_stack"
  split: "train"

  text_columns:
    - "content"

  title_column: "hex_id"
  id_column: "hex_id"

  metadata_columns:
    - "language"
    - "ext"

  select_condition: "language='python'"

  num_rows: 5000
  ray_workers: 4

metadata:
  source: hugging-face
  category: code
  language: python
```

### Customer Support Tickets

```yaml
hfdataset_crawler:
  dataset_name: "customer_support"
  split: "train"

  text_columns:
    - "ticket_text"
    - "response_text"

  title_column: "ticket_id"
  id_column: "ticket_id"

  metadata_columns:
    - "category"
    - "priority"
    - "resolved"

  select_condition: "resolved='yes'"

  num_rows: 20000
  ray_workers: 2

metadata:
  source: hugging-face
  category: support-tickets
  domain: customer-service
```

### Scientific Papers Dataset

```yaml
hfdataset_crawler:
  dataset_name: "arxiv"
  split: "train"

  text_columns:
    - "abstract"
    - "title"

  title_column: "title"
  id_column: "paper_id"

  metadata_columns:
    - "categories"
    - "year"
    - "authors"

  start_row: 0
  num_rows: 50000
  ray_workers: 4

metadata:
  source: hugging-face
  category: research-papers
  domain: arxiv
```

## Column Selection

### Text Columns

Columns containing content to index:

```yaml
text_columns:
  - "text"
  - "description"
  - "content"
```

Texts from multiple columns are combined with " - " separator:

```python
"Column1 text - Column2 text - Column3 text"
```

### Title Column

Column to use as document title:

```yaml
title_column: "headline"  # Used as document title
```

If not specified, no title is set.

### ID Column

Column to use as unique document ID:

```yaml
id_column: "record_id"  # Unique identifier
```

If not specified, auto-generated as "doc-{index}".

### Metadata Columns

Columns to include as document metadata:

```yaml
metadata_columns:
  - "author"
  - "date"
  - "category"
```

All values become available in metadata searches and filters.

## Filtering and Selection

### Row Counting

Skip initial rows:

```yaml
hfdataset_crawler:
  start_row: 1000  # Skip first 1000 rows
  num_rows: 5000   # Process next 5000
```

This processes rows 1000-5999.

### Conditional Filtering

Filter rows by column value:

```yaml
hfdataset_crawler:
  select_condition: "domain='restaurant'"
```

**Format**: `"column_name=value"`

**Examples**:
```yaml
select_condition: "language='python'"
select_condition: "status='approved'"
select_condition: "category='science'"
```

Only rows matching the condition are indexed.

## Parallel Processing

### Ray Workers

Enable distributed processing:

```yaml
# Sequential (default)
ray_workers: 0

# 4 parallel workers
ray_workers: 4

# Use all CPU cores
ray_workers: -1
```

**When to use**:
- Large datasets (10000+ rows)
- Many text columns to process
- Sufficient system memory (4GB+)
- Processing intensive metadata

**Memory usage**:
- Each worker uses ~100-200MB
- Monitor with `top` or `htop`

### Batch Processing

Workers process data in batches:

```yaml
# Internal batch size: 256 rows
# Recommended for most datasets
```

Larger batches reduce overhead but increase memory usage.

## Troubleshooting

### Dataset Not Found

**Issue**: `Dataset not found` error

**Solutions**:
1. Verify dataset name is correct:
   ```bash
   # Check datasets.org or huggingface.co/datasets
   ```
2. Use full dataset identifier:
   ```yaml
   dataset_name: "username/dataset-name"
   ```
3. Check internet connection

### Split Not Found

**Issue**: `Split 'xyz' not found in dataset` error

**Solutions**:
1. List available splits:
   ```bash
   # Visit huggingface.co/datasets/DATASET_NAME
   ```
2. Use correct split name:
   ```yaml
   split: "train"  # or "validation", "test"
   ```

### No Data Indexed

**Issue**: Crawler runs but no documents indexed

**Solutions**:
1. Verify text_columns exist in dataset:
   ```yaml
   text_columns:
     - "text"  # Must exist in dataset
   ```
2. Check select_condition filtering:
   ```yaml
   select_condition: "status='active'"  # May filter all rows
   ```
3. Verify row limits:
   ```yaml
   num_rows: 10  # Too small?
   start_row: 1000000  # Beyond dataset?
   ```

### Out of Memory Errors

**Issue**: Process killed or system becomes unresponsive

**Solutions**:
1. Disable parallel processing:
   ```yaml
   ray_workers: 0  # Sequential
   ```
2. Reduce ray_workers:
   ```yaml
   ray_workers: 2  # Instead of 4
   ```
3. Limit rows:
   ```yaml
   num_rows: 10000  # Smaller chunks
   ```
4. Process in batches (separate configs):
   ```yaml
   # Part 1
   start_row: 0
   num_rows: 10000

   # Part 2
   start_row: 10000
   num_rows: 10000
   ```

### Slow Indexing

**Issue**: Crawler is very slow

**Solutions**:
1. Enable parallel processing:
   ```yaml
   ray_workers: 4  # Parallelize
   ```
2. Reduce text column count:
   ```yaml
   text_columns:
     - "main_text"  # Only essential columns
   ```
3. Disable metadata columns not needed:
   ```yaml
   metadata_columns:
     - "important_meta"  # Skip unnecessary ones
   ```

### Memory Leaks

**Issue**: Memory usage grows over time

**Solutions**:
1. The crawler includes garbage collection
2. Reduce ray_workers to free memory
3. Split large datasets into multiple configs

## Best Practices

### 1. Start with Small Samples

Test configuration before full indexing:

```yaml
hfdataset_crawler:
  num_rows: 100  # Test first
```

Once validated, increase `num_rows`.

### 2. Choose Appropriate Columns

Include only necessary columns:

```yaml
# Good: minimal columns
text_columns:
  - "content"
metadata_columns:
  - "author"

# Avoid: too many columns
text_columns:
  - "all"  # Too broad
```

### 3. Use Filtering Strategically

Filter at indexing time rather than post-processing:

```yaml
# Good: filter before indexing
select_condition: "quality='high'"

# Avoid: index everything, filter later
# (wastes resources)
```

### 4. Organize Large Datasets

Split very large datasets across multiple configs:

```yaml
# config/dataset-part1.yaml
start_row: 0
num_rows: 50000

# config/dataset-part2.yaml
start_row: 50000
num_rows: 50000
```

### 5. Use Meaningful IDs

```yaml
# Good: meaningful identifier
id_column: "paper_id"

# Avoid: auto-generated
# (no id_column specified)
```

### 6. Add Rich Metadata

```yaml
metadata_columns:
  - "author"
  - "date"
  - "category"
  - "quality_score"
```

### 7. Enable Parallel Processing Appropriately

```yaml
# Large dataset: parallelize
ray_workers: -1

# Small dataset: sequential
ray_workers: 0
```

### 8. Monitor Progress

```yaml
vectara:
  verbose: true
```

Logs show indexing progress:
```
Indexing document # 101
Indexing document # 201
Indexing document # 301
```

## Running the Crawler

### Find Datasets

Browse datasets at [huggingface.co/datasets](https://huggingface.co/datasets)

### Create Your Configuration

```bash
vim config/hf-dataset.yaml
```

### Run the Crawler

```bash
# Single run
bash run.sh config/hf-dataset.yaml default

# Monitor progress
docker logs -f vingest
```

### Schedule Regular Updates

For datasets that update regularly:

```bash
# Weekly updates
0 2 * * 0 cd /path/to/vectara-ingest && bash run.sh config/hf-dataset.yaml default
```

## Complete Example

```yaml
# Complete Hugging Face Datasets crawler configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: hf-qa-dataset
  reindex: false
  verbose: true

doc_processing:
  model: openai
  model_name: gpt-4o

crawling:
  crawler_type: hfdataset

hfdataset_crawler:
  # Dataset from Hugging Face Hub
  dataset_name: "squad"
  split: "train"

  # Text content to index
  text_columns:
    - "context"
    - "question"
    - "answers"

  # Document title
  title_column: "id"

  # Unique identifier
  id_column: "id"

  # Metadata
  metadata_columns:
    - "title"

  # Row limits
  num_rows: 50000
  start_row: 0

  # Parallel processing
  ray_workers: 4

metadata:
  source: hugging-face
  dataset: squad
  category: question-answering
  content_type: qa-pairs
```

Save as `config/hf-qa.yaml` and run:

```bash
bash run.sh config/hf-qa.yaml default
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Document Processing](../doc-processing.md) - Content processing options
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## External Resources

- [Hugging Face Datasets](https://huggingface.co/datasets) - Browse available datasets
- [Datasets Library Documentation](https://huggingface.co/docs/datasets/) - API reference
- [Popular Datasets](https://huggingface.co/datasets?p=1) - Featured datasets
- [Community Datasets](https://huggingface.co/datasets?p=1&sort=likes) - Community contributions
