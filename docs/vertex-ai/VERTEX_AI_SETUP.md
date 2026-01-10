# Vertex AI Integration for Table and Image Summarization

Vectara-ingest now supports Google Cloud Vertex AI as an alternative to OpenAI for table and image summarization.

## Why Use Vertex AI?

- **Cost-effective**: Generally lower pricing than OpenAI for similar tasks
- **Data sovereignty**: Keep data within Google Cloud ecosystem
- **Enterprise features**: Better SLA, audit logging, VPC support
- **Gemini models**: Google's latest multimodal AI models

## Prerequisites

### 1. Install Vertex AI SDK

```bash
pip install google-cloud-aiplatform
```

### 2. Set Up Google Cloud Authentication

You need to authenticate with Google Cloud. Choose one of these methods:

#### Option A: Service Account Key (Recommended for production)

1. Create a service account in Google Cloud Console
2. Grant it the "Vertex AI User" role
3. Download the JSON key file
4. Set environment variable:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

#### Option B: User Credentials (For development)

```bash
gcloud auth application-default login
```

### 3. Enable Vertex AI API

```bash
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

## Recommended Models

### For Table Summarization

**Best Choice: `gemini-1.5-flash-002`**
- **Cost**: $0.00001875/1K input tokens, $0.000075/1K output tokens
- **Speed**: Very fast (~1-2 seconds per table)
- **Quality**: Excellent for structured data
- **Context**: 1M token context window
- **Best for**: Most table summarization tasks

**Alternative: `gemini-1.5-pro-002`**
- **Cost**: $0.00125/1K input tokens, $0.005/1K output tokens
- **Speed**: Moderate (~2-4 seconds per table)
- **Quality**: Highest quality, better for complex tables
- **Context**: 2M token context window
- **Best for**: Complex tables with many columns, nested structures

**Budget Option: `gemini-2.0-flash-exp`** (Experimental, free during preview)
- **Cost**: Free during preview period
- **Speed**: Very fast
- **Quality**: Good for most use cases
- **Best for**: Testing and development

### For Image Summarization

**Best Choice: `gemini-1.5-flash-002`**
- **Cost**: $0.00001875/1K input tokens, $0.000075/1K output tokens
- **Speed**: Fast (~2-3 seconds per image)
- **Quality**: Excellent multimodal understanding
- **Best for**: Most image analysis tasks (charts, diagrams, photos)

**Alternative: `gemini-1.5-pro-002`**
- **Cost**: $0.00125/1K input tokens, $0.005/1K output tokens
- **Speed**: Moderate (~3-5 seconds per image)
- **Quality**: Best-in-class for complex images
- **Best for**: Complex diagrams, technical schematics, dense infographics

## Configuration Examples

### Example 1: Use Vertex AI for Both Tables and Images

In your config YAML file:

```yaml
vectara:
  corpus_key: my_corpus

  # Vertex AI project configuration
  vertex_project_id: "your-gcp-project-id"

  # Table summarization with Vertex AI
  table_model_config:
    provider: vertex
    model_name: gemini-1.5-flash-002
    project_id: your-gcp-project-id  # Optional if vertex_project_id is set
    location: us-central1

  # Image summarization with Vertex AI
  image_model_config:
    provider: vertex
    model_name: gemini-1.5-flash-002
    project_id: your-gcp-project-id  # Optional if vertex_project_id is set
    location: us-central1

crawling:
  crawler_type: folder

folder_crawler:
  path: /path/to/documents
  summarize_tables: true
  summarize_images: true
```

### Example 2: Mix OpenAI and Vertex AI

Use OpenAI for tables, Vertex AI for images (or vice versa):

```yaml
vectara:
  corpus_key: my_corpus

  # OpenAI configuration
  openai_api_key: sk-...

  # Vertex AI configuration
  vertex_project_id: "your-gcp-project-id"

  # Table summarization with OpenAI
  table_model_config:
    provider: openai
    model_name: gpt-4o-mini

  # Image summarization with Vertex AI (more cost-effective)
  image_model_config:
    provider: vertex
    model_name: gemini-1.5-flash-002
    location: us-central1

folder_crawler:
  path: /path/to/documents
  summarize_tables: true
  summarize_images: true
```

### Example 3: High-Quality Processing for Complex Documents

Use Pro models for best quality:

```yaml
vectara:
  corpus_key: technical_docs
  vertex_project_id: "your-gcp-project-id"

  # High-quality table summarization
  table_model_config:
    provider: vertex
    model_name: gemini-1.5-pro-002
    location: us-central1

  # High-quality image analysis
  image_model_config:
    provider: vertex
    model_name: gemini-1.5-pro-002
    location: us-central1

folder_crawler:
  path: /path/to/technical_docs
  summarize_tables: true
  summarize_images: true
```

### Example 4: Budget-Friendly with Experimental Model

```yaml
vectara:
  corpus_key: test_corpus
  vertex_project_id: "your-gcp-project-id"

  # Free experimental model (during preview)
  table_model_config:
    provider: vertex
    model_name: gemini-2.0-flash-exp
    location: us-central1

  image_model_config:
    provider: vertex
    model_name: gemini-2.0-flash-exp
    location: us-central1
```

## Configuration Options

### Required Fields

- `provider`: Must be `"vertex"` for Vertex AI
- `project_id`: Your Google Cloud project ID (can be set globally in `vectara.vertex_project_id`)

### Optional Fields

- `model_name`: Gemini model to use (default: `gemini-1.5-flash-002`)
- `location`: GCP region (default: `us-central1`)
  - Options: `us-central1`, `us-east4`, `europe-west1`, `asia-northeast1`, etc.

## Available Models (as of Dec 2024)

| Model | Input Cost | Output Cost | Speed | Best For |
|-------|-----------|-------------|-------|----------|
| `gemini-1.5-flash-002` | $0.01875/1M | $0.075/1M | Fast | General purpose, best balance |
| `gemini-1.5-pro-002` | $1.25/1M | $5.00/1M | Moderate | Complex analysis, highest quality |
| `gemini-2.0-flash-exp` | Free* | Free* | Fast | Development, testing |
| `gemini-1.0-pro` | $0.50/1M | $1.50/1M | Fast | Legacy, basic tasks |

*Free during preview period. Subject to rate limits and may require allowlist.

## Cost Comparison Example

Assuming 1,594 PDFs with average 5 tables and 3 images per PDF:

### OpenAI (GPT-4o-mini)
- Tables: 7,970 summaries × ~500 tokens × $0.15/1M = **$0.60**
- Images: 4,782 summaries × ~1000 tokens × $0.60/1M = **$2.87**
- **Total: ~$3.47**

### Vertex AI (gemini-1.5-flash-002)
- Tables: 7,970 summaries × ~500 tokens × $0.01875/1M = **$0.07**
- Images: 4,782 summaries × ~1000 tokens × $0.01875/1M = **$0.09**
- **Total: ~$0.16**

**Savings: ~95% with Vertex AI Flash model**

## Troubleshooting

### Error: "Vertex AI SDK not available"

```bash
pip install google-cloud-aiplatform
```

### Error: "Could not automatically determine credentials"

Set up authentication:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

Or use:
```bash
gcloud auth application-default login
```

### Error: "Permission denied" or "403 Forbidden"

1. Ensure Vertex AI API is enabled:
```bash
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

2. Grant service account the "Vertex AI User" role:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"
```

### Error: "Model not found" or "Model not supported in region"

Check model availability in your region:
```bash
gcloud ai models list --region=us-central1
```

Try a different region or model name.

### Rate Limiting

Vertex AI has rate limits:
- gemini-1.5-flash: 2,000 requests per minute
- gemini-1.5-pro: 1,000 requests per minute

If hitting limits, consider:
1. Adding delays between requests
2. Using multiple projects
3. Requesting quota increase

## Performance Tips

1. **Use Flash models for most tasks**: 95% of documents work great with `gemini-1.5-flash-002`
2. **Use Pro only when needed**: Reserve `gemini-1.5-pro-002` for complex technical documents
3. **Choose closest region**: Use `us-central1` for US, `europe-west1` for EU to reduce latency
4. **Batch processing**: Process multiple documents in parallel (crawler handles this automatically)

## Monitoring Costs

Track your Vertex AI usage in Google Cloud Console:
1. Go to "Billing" → "Reports"
2. Filter by "Vertex AI API"
3. Group by "SKU" to see model-specific costs

## Support

For Vertex AI specific issues:
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Gemini API Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/gemini)
- [Pricing Calculator](https://cloud.google.com/products/calculator)
