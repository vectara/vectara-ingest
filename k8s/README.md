# Vectara Ingest on Kubernetes

This document provides comprehensive instructions for deploying and managing the Vectara Ingest service within a
Kubernetes environment. Vectara Ingest is a critical component responsible for crawling, processing, and indexing data
into your Vectara account. Running it on Kubernetes offers scalability, resilience, and efficient resource utilization.

## Overview of Vectara Ingest

Vectara Ingest is a powerful, configurable crawler designed to fetch data from various sources (e.g., websites, document
repositories, databases) and transform it into a format suitable for Vectara's neural search platform. It handles:

- **Crawling:** Navigating and retrieving content from specified sources.
- **Parsing:** Extracting meaningful text and metadata from diverse document types.
- **Chunking:** Breaking down large documents into smaller, semantically coherent chunks for optimal indexing.
- **Embedding:** Generating vector embeddings for each chunk, enabling semantic search.
- **Indexing:** Uploading the processed data and embeddings to your Vectara corpus.

## Kubernetes Deployment Strategy

Deploying Vectara Ingest on Kubernetes typically involves using Jobs or CronJobs, along with:

- **ConfigMaps:** To store configuration files that are not sensitive.
- **Secrets:** To store sensitive information like API keys, database credentials, and other access tokens.
- **CronJobs:** For scheduling periodic ingest runs.
- **Jobs:** For scheduling one off ingest runs.

## Key Environment Variables

Vectara Ingest relies heavily on environment variables for its configuration. Understanding these is crucial for a
successful deployment.

### `CONFIG`

The `CONFIG` environment variable is **paramount** for defining the crawler's behavior. It expects a path to a **YAML
file** within the container that specifies the entire crawling configuration. This configuration dictates:

- **Crawler Type:** The source to crawl (e.g., `website`, `sharepoint`, `jira`).
- **Vectara Corpus Key:** The target corpus for indexing.
- **Crawler-Specific Settings:** Such as start URLs, paths, or other connection details.
- **Document Processing:** How to handle parsing, chunking, and other transformations.
- **Re-indexing Logic:** Whether to re-index content that already exists.

### `secrets.toml` and `PROFILE`

Sensitive information, such as API keys, database credentials, and authentication tokens, should **never** be hardcoded
directly into the `CONFIG` environment variable or Kubernetes manifests. Instead, Vectara Ingest uses a `secrets.toml`
file to manage these credentials securely.

**Mounting `secrets.toml`:**

The `secrets.toml` file **must be mounted** into the Ingest container at the specific path:
`/home/vectara/env/secrets.toml`. This is typically achieved using a Kubernetes Secret, which is then mounted as a
volume.

**Example `secrets.toml` content:**

```toml
[default]
SHAREPOINT_USERNAME = "user@yourdomain.com"
SHAREPOINT_PASSWORD = "your_sharepoint_password"

[production]
VECTARA_API_KEY = "YOUR_PRODUCTION_VECTARA_API_KEY"

[staging]
VECTARA_API_KEY = "YOUR_STAGING_VECTARA_API_KEY"
```

**The `PROFILE` Environment Variable:**

The `PROFILE` environment variable is used to select which section (or "profile") from the `secrets.toml` file should be
loaded. If `PROFILE` is not set, the `[default]` profile is used. This allows you to manage multiple sets of
credentials (e.g., for different environments like `production`, `staging`, `development`) within a single
`secrets.toml` file and switch between them easily.

For instance, if `PROFILE=production` is set, Ingest will load secrets from the `[production]` section of
`secrets.toml`.

## Kubernetes Manifest Examples

The following sections provide examples of Kubernetes manifests for deploying Vectara Ingest.

### Web Crawler Example (`@README.md`)

This example demonstrates a basic deployment for crawling a website.

```yaml
# (Content will be inserted here from the example)
```

### Scheduled CronJob for Web Crawling (`@cron.yml`)

This example shows how to set up a scheduled crawl using a Kubernetes CronJob.

```yaml
# (Content will be inserted here from the example)
```

### SharePoint Crawler Example (`@sharepoint.yml`)

This example illustrates how to configure Ingest to crawl a SharePoint site.

```yaml
# (Content will be inserted here from the example)
```

## Best Practices

- **Secret Management:** Always use Kubernetes Secrets for sensitive data. Avoid hardcoding.
- **Configuration as Code:** Manage your `CONFIG` JSON and other configurations using ConfigMaps and version control.
- **Resource Limits:** Define `resources.limits` and `resources.requests` for your Ingest pods to ensure stable
  operation and prevent resource exhaustion.
- **Logging and Monitoring:** Integrate Ingest logs with your centralized logging solution (e.g., ELK stack, Grafana
  Loki) and set up monitoring for pod health and Ingest job status.
- **Idempotency:** Design your ingest jobs to be idempotent where possible, meaning running them multiple times with the
  same configuration produces the same result, preventing duplicate data.
- **Error Handling:** Configure appropriate retry mechanisms and alerts for failed ingest jobs.
- **Network Policies:** Implement network policies to restrict Ingest pod communication to only necessary endpoints (
  Vectara API, source systems).
- **Security Context:** Consider using a non-root user for the Ingest container.

By following these guidelines and leveraging Kubernetes' capabilities, you can build a robust, scalable, and
maintainable data ingestion pipeline for Vectara.