# PubMed Central (PMC) Crawler

The PMC crawler indexes biomedical and life sciences research papers from PubMed Central, with support for indexed papers, MedlinePlus health topics, and advanced medical literature search capabilities.

## Overview

- **Crawler Type**: `pmc`
- **Authentication**: None required (uses NCBI Entrez API)
- **Data Source**: PubMed Central (NIH repository)
- **Additional Sources**: MedlinePlus health topics
- **Content**: Full-text PDF articles with comprehensive metadata
- **Search**: Relevance-based paper discovery by medical topics
- **Rate Limiting**: Built-in rate limiting for API compliance

## Use Cases

- Build medical knowledge bases for healthcare professionals
- Create searchable biomedical research repositories
- Index clinical trial information and results
- Archive and search health topics from MedlinePlus
- Medical document search and retrieval systems
- Healthcare research paper repositories
- Patient education content indexing

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: pmc-articles

crawling:
  crawler_type: pmc

pmc_crawler:
  # Topics to search for
  topics:
    - "machine learning diagnosis"
    - "AI healthcare"

  # Number of papers per topic
  n_papers: 50

  # Optional: index MedlinePlus health topics
  index_medline_plus: false
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: pmc-medical
  reindex: false
  verbose: true
  timeout: 120

crawling:
  crawler_type: pmc

pmc_crawler:
  # Multiple medical topics
  topics:
    - "cancer immunotherapy"
    - "gene therapy"
    - "COVID-19 treatment"
    - "Alzheimer's disease"
    - "diabetes management"

  # Papers per topic
  n_papers: 100

  # Index MedlinePlus content
  index_medline_plus: true

  # Number of requests per second (rate limiting)
  num_per_second: 3

  # SSL verification (optional)
  verify_ssl: true

  # Custom scrape method (optional)
  scrape_method: playwright

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: true

metadata:
  source: pmc
  domain: biomedical
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `topics` | list | Yes | - | Medical topics to search (list of strings) |
| `n_papers` | int | Yes | - | Number of papers per topic |
| `index_medline_plus` | bool | No | `false` | Index MedlinePlus health topics |
| `num_per_second` | int | No | `3` | Rate limiting: requests per second |
| `verify_ssl` | bool | No | `true` | Verify SSL certificates |
| `scrape_method` | string | No | - | Override scrape method (e.g., "playwright") |

## How It Works

### Paper Indexing

1. **Topic Search**: Searches PubMed Central by topic using Entrez API
2. **Results Retrieval**: Gets top N most relevant papers per topic
3. **Deduplication**: Removes duplicate papers across topics
4. **Metadata Extraction**: Parses XML to extract title, authors, publication date
5. **PDF Download**: Constructs and fetches PDF from NCBI servers
6. **Rate Limiting**: Enforces configured requests-per-second limit
7. **Indexing**: Uploads to Vectara with metadata

### MedlinePlus Indexing (Optional)

When `index_medline_plus: true`:

1. **Topic Fetch**: Retrieves latest MedlinePlus health topics XML
2. **Filtering**: Matches topics with configured `topics` list
3. **Parsing**: Extracts title, summary, synonyms, related sites
4. **Document Indexing**: Creates comprehensive health topic documents
5. **Site Indexing**: Indexes related health websites for each topic

## Metadata Captured

### Paper Metadata

The crawler extracts:

- **Title**: Article title from PMC
- **Authors**: Author names and affiliations
- **Publication Date**: Year-month-day when published
- **URL**: Link to PMC article page
- **PDF URL**: Direct link to PDF file
- **Source**: Always "pmc"

### MedlinePlus Metadata

When indexing health topics:

- **Topic Title**: Health topic name
- **Synonyms**: Alternative names (also-called)
- **Meta Description**: Brief topic summary
- **Full Summary**: Comprehensive topic information
- **Related Sites**: URLs of recommended resources
- **Creation Date**: When topic was created
- **Source**: "medline_plus"

## Search Topics and Examples

### Common Medical Topics

```yaml
pmc_crawler:
  topics:
    - "diabetes management"
    - "heart disease prevention"
    - "Alzheimer's disease"
    - "cancer immunotherapy"
    - "stroke treatment"
```

### Specific Research Areas

```yaml
pmc_crawler:
  topics:
    - "CRISPR gene editing"
    - "mRNA vaccines"
    - "CAR-T cell therapy"
    - "drug resistance bacteria"
    - "personalized medicine"
```

### Emerging Topics

```yaml
pmc_crawler:
  topics:
    - "AI diagnostic imaging"
    - "machine learning pathology"
    - "deep learning drug discovery"
    - "big data epidemiology"
```

## Examples

### Clinical Research Repository

```yaml
vectara:
  corpus_key: clinical-research

crawling:
  crawler_type: pmc

pmc_crawler:
  topics:
    - "clinical trial design"
    - "randomized controlled trial"
    - "systematic review"
    - "meta-analysis"

  n_papers: 100
  num_per_second: 3

metadata:
  source: pmc
  category: clinical-research
  domain: medicine
```

### Precision Medicine Knowledge Base

```yaml
pmc_crawler:
  topics:
    - "precision medicine"
    - "genomic medicine"
    - "pharmacogenomics"
    - "molecular biomarkers"
    - "patient stratification"

  n_papers: 75
  index_medline_plus: false

metadata:
  category: precision-medicine
  domain: genomics
```

### Comprehensive Health Topics with MedlinePlus

```yaml
pmc_crawler:
  topics:
    - "diabetes"
    - "hypertension"
    - "asthma"
    - "arthritis"
    - "depression"
    - "cancer"

  n_papers: 50
  index_medline_plus: true  # Include patient education
  num_per_second: 2

metadata:
  source: pmc
  categories:
    - clinical
    - patient-education
```

### Infectious Diseases Focus

```yaml
pmc_crawler:
  topics:
    - "COVID-19 treatment"
    - "long COVID"
    - "influenza vaccines"
    - "tuberculosis resistance"
    - "monkeypox"
    - "antibiotic resistance"

  n_papers: 100
  index_medline_plus: false

metadata:
  category: infectious-disease
  domain: epidemiology
```

### Mental Health Research

```yaml
pmc_crawler:
  topics:
    - "depression treatment"
    - "anxiety disorders"
    - "bipolar disorder"
    - "PTSD psychotherapy"
    - "schizophrenia antipsychotics"
    - "suicide prevention"

  n_papers: 75
  num_per_second: 2

metadata:
  category: mental-health
  domain: psychiatry
```

## Rate Limiting

The crawler respects API rate limits:

```yaml
pmc_crawler:
  num_per_second: 3  # Conservative default
```

**Recommendations**:
- `num_per_second: 1-2` - Very conservative (safe)
- `num_per_second: 3` - Default (recommended)
- `num_per_second: 5` - Fast (use with caution)

Exceeding limits may result in temporary IP blocking from NCBI.

## MedlinePlus Integration

### What Gets Indexed

When `index_medline_plus: true`:

1. **Health Topic Documents**:
   - Comprehensive health information
   - Synonyms and alternative names
   - Link to the topic page

2. **Related Website URLs**:
   - Partner sites with authoritative information
   - Government health resources
   - Patient support organizations

### Filtering Topics

Only health topics matching configured `topics` are indexed:

```yaml
pmc_crawler:
  topics:
    - "diabetes"
    - "heart disease"

  index_medline_plus: true
```

This will index BOTH:
- PMC research papers on diabetes and heart disease
- MedlinePlus health topics for diabetes and heart disease

### Benefits

- Combines research-level and patient education content
- Single search retrieves academic and lay explanations
- Comprehensive health information index

## Troubleshooting

### No Papers Found

**Issue**: Topics return 0 papers

**Solutions**:
1. Verify topic terms are medical/scientific
2. Try different topic names:
   ```yaml
   # Try this
   topics:
     - "acute myocardial infarction"
   # Instead of
   topics:
     - "heart attack"
   ```
3. Use more general terms:
   ```yaml
   topics:
     - "cancer"  # More general than "glioblastoma"
   ```

### Fewer Papers Than Requested

**Issue**: Fewer papers returned than `n_papers`

**Solutions**:
1. Topic may have fewer papers available
2. Try broader topic terms
3. Combine with other topics:
   ```yaml
   topics:
     - "machine learning healthcare"
     - "AI diagnosis"
   ```

### Rate Limiting Errors

**Issue**: Getting blocked or slow responses

**Solutions**:
1. Reduce request rate:
   ```yaml
   pmc_crawler:
     num_per_second: 1  # Very conservative
   ```
2. Run during off-peak hours
3. Add delay between crawls

### MedlinePlus Not Indexing

**Issue**: `index_medline_plus: true` but no health topics indexed

**Solutions**:
1. Check topic names match health topics:
   ```yaml
   topics:
     - "hypertension"  # Exact health topic name
   ```
2. Verify internet connection
3. MedlinePlus XML may be temporarily unavailable - retry later

### SSL Certificate Errors

**Issue**: `SSL: CERTIFICATE_VERIFY_FAILED` errors

**Solutions**:
1. Update certificates:
   ```bash
   pip install --upgrade certifi
   ```
2. For development only:
   ```yaml
   pmc_crawler:
     verify_ssl: false
   ```

### PDF Download Issues

**Issue**: Some PDFs fail to download

**Solutions**:
1. Increase timeout:
   ```yaml
   vectara:
     timeout: 180
   ```
2. Reduce `num_per_second` to avoid rate limiting:
   ```yaml
   pmc_crawler:
     num_per_second: 1
   ```

## Best Practices

### 1. Start with Popular Topics

Begin with well-indexed topics:

```yaml
pmc_crawler:
  topics:
    - "cancer"
    - "diabetes"
    - "heart disease"
  n_papers: 20  # Start small
```

Then expand to specialized topics.

### 2. Use Medical Terminology

Use proper medical terms for better results:

```yaml
# Good: proper medical terms
topics:
  - "myocardial infarction"
  - "pneumonia"
  - "hypertension"

# Less effective: common terms
topics:
  - "heart attack"
  - "lung infection"
  - "high blood pressure"
```

### 3. Combine with MedlinePlus

For comprehensive knowledge bases:

```yaml
pmc_crawler:
  topics:
    - "diabetes"
    - "asthma"
  index_medline_plus: true  # Include patient education
```

### 4. Respect Rate Limits

```yaml
pmc_crawler:
  num_per_second: 2  # Conservative
```

### 5. Organize by Medical Domain

Create separate configs for different medical domains:

```yaml
# config/pmc-oncology.yaml
pmc_crawler:
  topics:
    - "cancer immunotherapy"
    - "oncology"

# config/pmc-cardiology.yaml
pmc_crawler:
  topics:
    - "heart failure"
    - "coronary artery disease"
```

### 6. Use Descriptive Metadata

```yaml
metadata:
  source: pmc
  category: oncology
  domain: cancer-research
  indexed_date: "2024-11-18"
  content_type: research-papers
```

### 7. Schedule Regular Updates

```bash
# Weekly on Sunday at 2 AM
0 2 * * 0 cd /path/to/vectara-ingest && bash run.sh config/pmc.yaml default
```

### 8. Monitor Crawl Progress

```yaml
vectara:
  verbose: true
```

Watch logs:
```bash
docker logs -f vingest
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/pmc-articles.yaml
```

### Run the Crawler

```bash
# Single run
bash run.sh config/pmc-articles.yaml default

# Monitor progress
docker logs -f vingest
```

### Schedule Regular Crawls

Using cron:

```bash
# Weekly updates
0 2 * * 0 cd /path/to/vectara-ingest && bash run.sh config/pmc.yaml default
```

## Complete Example

```yaml
# Complete PMC crawler configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: pmc-research
  reindex: false
  verbose: true
  timeout: 120

doc_processing:
  model: openai
  model_name: gpt-4o
  parse_tables: true
  summarize_images: true

crawling:
  crawler_type: pmc

pmc_crawler:
  # Medical topics to index
  topics:
    - "precision medicine"
    - "genomic medicine"
    - "personalized therapy"
    - "molecular biomarkers"
    - "drug discovery AI"

  # Number of papers per topic
  n_papers: 100

  # Include patient education from MedlinePlus
  index_medline_plus: true

  # API rate limiting
  num_per_second: 3

  # SSL verification
  verify_ssl: true

metadata:
  source: pmc
  category: precision-medicine
  domain: genomics
  content_type: research-papers
  language: en
```

Save as `config/pmc-research.yaml` and run:

```bash
bash run.sh config/pmc-research.yaml default
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Document Processing](../doc-processing.md) - PDF processing and table extraction
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## External Resources

- [PubMed Central](https://www.ncbi.nlm.nih.gov/pmc/) - Main PMC repository
- [NCBI Entrez API](https://www.ncbi.nlm.nih.gov/books/NBK25499/) - PMC search API
- [MedlinePlus](https://medlineplus.gov/) - Health information from NIH
- [Medical Subject Headings (MeSH)](https://www.nlm.nih.gov/mesh/) - Medical terminology
