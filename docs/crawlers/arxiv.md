# arXiv Crawler

The arXiv crawler indexes academic papers from the arXiv preprint repository with advanced search, sorting, and citation tracking capabilities.

## Overview

- **Crawler Type**: `arxiv`
- **Authentication**: None required
- **Data Source**: arXiv.org preprint repository
- **Citation Tracking**: Optional Semantic Scholar API integration
- **Content**: PDF files with metadata extraction
- **Search Capabilities**: Query-based paper discovery with category filtering

## Use Cases

- Build searchable academic paper repositories
- Create domain-specific knowledge bases (AI, Physics, Mathematics, etc.)
- Track trending and highly-cited papers in specific fields
- Automate research paper archival and indexing
- Research topic monitoring and analysis
- Build academic search interfaces

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: arxiv-papers

crawling:
  crawler_type: arxiv

arxiv_crawler:
  # Query terms to search for
  query_terms:
    - "machine learning"
    - "neural networks"

  # arXiv category (required)
  arxiv_category: cs  # Computer Science

  # Number of papers to index
  n_papers: 100

  # Minimum publication year
  start_year: 2020

  # Sort by relevance or citations
  sort_by: relevance  # or "citations"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: arxiv-papers
  reindex: false
  verbose: true
  timeout: 120

crawling:
  crawler_type: arxiv

arxiv_crawler:
  # Multiple search terms
  query_terms:
    - "transformer"
    - "attention mechanism"
    - "BERT"
    - "GPT"

  # arXiv category
  arxiv_category: cs

  # Number of papers to retrieve
  n_papers: 500

  # Minimum publication year
  start_year: 2019

  # Sort by citations (more computationally intensive)
  sort_by: citations

  # SSL verification (optional)
  verify_ssl: true

  # Custom scrape method (optional)
  scrape_method: playwright

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: false

metadata:
  source: arxiv
  category: ai-ml
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query_terms` | list | Yes | - | Search terms for paper discovery (list of strings) |
| `arxiv_category` | string | Yes | - | arXiv category code (e.g., "cs", "math", "physics") |
| `n_papers` | int | Yes | - | Number of papers to index |
| `start_year` | int | Yes | - | Minimum publication year for papers |
| `sort_by` | string | No | `relevance` | Sort criterion: `relevance` or `citations` |
| `verify_ssl` | bool | No | `true` | Verify SSL certificates |
| `scrape_method` | string | No | - | Override scrape method (e.g., "playwright") |

## Valid arXiv Categories

The crawler supports all arXiv categories:

**Computer Science**:
- `cs` - General Computer Science

**Mathematics**:
- `math` - General Mathematics
- `math-ph` - Mathematical Physics
- `stat` - Statistics

**Physics**:
- `physics` - General Physics
- `astro-ph` - Astrophysics
- `cond-mat` - Condensed Matter Physics
- `gr-qc` - General Relativity and Quantum Cosmology
- `hep-ex` - High Energy Physics - Experiment
- `hep-lat` - High Energy Physics - Lattice
- `hep-ph` - High Energy Physics - Phenomenology
- `hep-th` - High Energy Physics - Theory
- `nucl-ex` - Nuclear Experiment
- `nucl-th` - Nuclear Theory
- `quant-ph` - Quantum Physics

**Quantitative Finance**:
- `q-fin` - Quantitative Finance
- `q-bio` - Quantitative Biology

**Economics**:
- `econ` - Economics

## How It Works

1. **Query Construction**: Combines category filter with search terms
2. **Paper Discovery**: Searches arXiv API with constructed query
3. **Year Filtering**: Filters results by `start_year` minimum
4. **Sorting**: Orders results by relevance or citation count
5. **Citation Retrieval**: Optionally fetches citation counts from Semantic Scholar
6. **PDF Indexing**: Downloads PDF files and indexes them with metadata
7. **Metadata Extraction**: Extracts and indexes author, abstract, publication date information

## Metadata Captured

The crawler automatically extracts and indexes:

- **Title**: Paper title from arXiv
- **Authors**: Author names (list)
- **Abstract**: Paper abstract/summary
- **URL**: arXiv paper page URL
- **Publication Date**: Date paper was published/submitted
- **PDF URL**: Direct link to PDF file
- **Citations**: Citation count from Semantic Scholar (if sort_by="citations")
- **Source**: Always "arxiv"

## Sorting Methods

### Relevance Sorting (Default)

Orders papers by relevance to search terms:

```yaml
arxiv_crawler:
  sort_by: relevance
  n_papers: 100  # Get top 100 most relevant papers
```

**Characteristics**:
- Fastest option (no external API calls)
- Orders by match quality with query terms
- Good for targeted searches

### Citation Sorting

Orders papers by number of citations:

```yaml
arxiv_crawler:
  sort_by: citations
  n_papers: 100
```

**How it works**:
1. Retrieves 100x papers initially (for better citation data)
2. Fetches citation counts from Semantic Scholar API
3. Sorts by citation count
4. Returns top N papers

**Characteristics**:
- Slower due to external API calls
- Good for finding influential papers
- May have rate limiting from Semantic Scholar

## Examples

### AI and Machine Learning Papers

```yaml
vectara:
  corpus_key: ai-papers

crawling:
  crawler_type: arxiv

arxiv_crawler:
  query_terms:
    - "large language models"
    - "transformer"
    - "attention"
    - "fine-tuning"

  arxiv_category: cs
  n_papers: 500
  start_year: 2020
  sort_by: citations

metadata:
  category: ai-ml
  domain: machine-learning
```

### Recent Physics Papers

```yaml
arxiv_crawler:
  query_terms:
    - "quantum computing"
    - "quantum error correction"

  arxiv_category: physics
  n_papers: 200
  start_year: 2022
  sort_by: relevance

metadata:
  category: physics
  domain: quantum-computing
```

### Mathematics and Statistics

```yaml
arxiv_crawler:
  query_terms:
    - "graph neural networks"
    - "probabilistic models"

  arxiv_category: math
  n_papers: 150
  start_year: 2021
  sort_by: citations

metadata:
  category: math
  domain: computational-math
```

### Multi-term Search in Computer Science

```yaml
arxiv_crawler:
  query_terms:
    - "federated learning"
    - "privacy"
    - "differential privacy"
    - "distributed"

  arxiv_category: cs
  n_papers: 300
  start_year: 2019
  sort_by: relevance

metadata:
  category: cs
  subdomain: privacy-ml
```

### Biophysics and Computational Biology

```yaml
arxiv_crawler:
  query_terms:
    - "protein folding"
    - "AlphaFold"
    - "molecular dynamics"

  arxiv_category: q-bio
  n_papers: 250
  start_year: 2020
  sort_by: citations

metadata:
  category: biology
  domain: computational-biology
```

## Query Term Best Practices

### Multiple Terms (AND Logic)

All terms must appear in the paper:

```yaml
arxiv_crawler:
  query_terms:
    - "machine learning"
    - "interpretability"
```

Returns papers containing BOTH "machine learning" AND "interpretability"

### Single Term Searches

```yaml
arxiv_crawler:
  query_terms:
    - "transformers"
```

Returns papers about transformers

### Avoiding False Positives

Use specific terms:

```yaml
# Good: specific terms
query_terms:
  - "reinforcement learning"
  - "policy gradient"

# Avoid: too broad
query_terms:
  - "learning"  # Matches too many papers
```

## Citation Tracking

When `sort_by: citations` is configured:

1. Crawler retrieves 100x papers initially
2. Uses Semantic Scholar API to fetch citation counts
3. Sorts papers by citation count
4. Returns top N papers
5. Citation count stored in metadata as `citations`

**Example metadata**:
```
citations: "1,234"  # Paper has 1,234 citations
```

## Troubleshooting

### No Papers Found

**Issue**: Query returns 0 papers

**Solutions**:
1. Verify search terms are appropriate
2. Check category is valid
3. Try broader search terms:
   ```yaml
   query_terms:
     - "machine learning"  # More general
   ```
4. Check year range isn't too restrictive:
   ```yaml
   start_year: 2015  # Go back further
   ```

### Too Few Papers Retrieved

**Issue**: Fewer papers returned than requested in `n_papers`

**Solutions**:
1. Increase `n_papers` value
2. Use broader `query_terms`
3. Reduce `start_year` minimum
4. Switch to `sort_by: relevance` (citation sorting may limit results)

### Citation Count Not Available

**Issue**: Citation count shows -1

**Solutions**:
1. Semantic Scholar API may be rate limited
2. Paper may be too new for Semantic Scholar index
3. Try again later
4. Not all papers are indexed in Semantic Scholar

### Slow Crawling with Citations Enabled

**Issue**: Crawler is very slow when `sort_by: citations`

**Cause**: Makes API calls to Semantic Scholar for each paper (slow)

**Solutions**:
1. Reduce `n_papers` value
2. Switch to `sort_by: relevance` for faster indexing
3. Run during off-peak hours

### SSL Certificate Errors

**Issue**: `SSL: CERTIFICATE_VERIFY_FAILED` errors

**Solutions**:
1. Disable SSL verification (development only):
   ```yaml
   arxiv_crawler:
     verify_ssl: false
   ```
2. Update certificates:
   ```bash
   pip install --upgrade certifi
   ```

### PDF Download Failures

**Issue**: Some PDFs fail to download

**Solutions**:
1. Increase timeout:
   ```yaml
   vectara:
     timeout: 180
   ```
2. Check internet connection
3. Retry the crawl

## Best Practices

### 1. Start Small

Begin with a test crawl:

```yaml
arxiv_crawler:
  n_papers: 10
  start_year: 2023
```

Once validated, expand to larger crawls.

### 2. Use Specific Categories

Be specific with categories:

```yaml
# Good: specific category
arxiv_category: cs

# Less specific: parent category
arxiv_category: physics
```

### 3. Optimize Search Terms

Use multiple specific terms:

```yaml
# Good: specific and targeted
query_terms:
  - "transformer"
  - "attention mechanism"
  - "BERT"

# Avoid: too generic
query_terms:
  - "learning"
```

### 4. Set Reasonable Year Ranges

Consider when papers were published:

```yaml
# Recent papers
start_year: 2023

# Historical papers
start_year: 2000
```

### 5. Choose Sort Method Carefully

- **Relevance**: Faster, good for exploratory searches
- **Citations**: Slower, good for finding influential papers

```yaml
# Fast crawl
sort_by: relevance

# Comprehensive crawl
sort_by: citations
```

### 6. Batch Large Crawls

Split very large requests into multiple configs:

```yaml
# config/arxiv-ml-2023.yaml
arxiv_crawler:
  query_terms: ["machine learning"]
  start_year: 2023
  n_papers: 200

# config/arxiv-ml-2020-2022.yaml
arxiv_crawler:
  query_terms: ["machine learning"]
  start_year: 2020
  n_papers: 500
```

### 7. Use Descriptive Metadata

```yaml
metadata:
  source: arxiv
  category: machine-learning
  domain: nlp
  indexed_date: "2024-11-18"
```

### 8. Handle Rate Limiting

If experiencing Semantic Scholar rate limits:

```yaml
# Reduce load
arxiv_crawler:
  sort_by: relevance  # Don't use citations
  n_papers: 50        # Smaller batches
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/arxiv-papers.yaml
```

### Run the Crawler

```bash
# Single run
bash run.sh config/arxiv-papers.yaml default

# Monitor progress
docker logs -f vingest
```

### Schedule Regular Crawls

Using cron for periodic updates:

```bash
# Daily at 3 AM
0 3 * * * cd /path/to/vectara-ingest && bash run.sh config/arxiv-papers.yaml default
```

Or use a CI/CD system like GitHub Actions.

## Complete Example

```yaml
# Complete arXiv crawler configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: arxiv-research
  reindex: false
  verbose: true
  timeout: 120

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: false

crawling:
  crawler_type: arxiv

arxiv_crawler:
  # Search terms (all must match)
  query_terms:
    - "large language models"
    - "fine-tuning"
    - "instruction"

  # arXiv category
  arxiv_category: cs

  # Number of papers to retrieve
  n_papers: 200

  # Minimum publication year
  start_year: 2022

  # Sort by citations (influential papers first)
  sort_by: citations

  # SSL verification
  verify_ssl: true

metadata:
  source: arxiv
  category: ai-ml
  domain: nlp
  content_type: research-papers
  language: en
```

Save as `config/arxiv-research.yaml` and run:

```bash
bash run.sh config/arxiv-research.yaml default
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Document Processing](../doc-processing.md) - PDF processing options
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## External Resources

- [arXiv.org](https://arxiv.org/) - Main preprint repository
- [arXiv API Documentation](https://arxiv.org/api/) - Query syntax and categories
- [Semantic Scholar API](https://www.semanticscholar.org/product/api) - Citation tracking
