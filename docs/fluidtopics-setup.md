# Fluid Topics crawler setup

The Fluid Topics crawler pulls content from a Fluid Topics tenant, extracts text
from HTML/XML/DITA-like payloads, maps metadata for filtering/access control, and
indexes structured documents into Vectara.

Fluid Topics tenant API shapes can vary by deployment/version, so the crawler is
configuration-driven: endpoint paths, JSON paths, pagination parameters, and the
API-key header are all configurable.

## Configuration

Start from the sample config:

```bash
cp config/fluidtopics.yaml config/my-fluidtopics.yaml
```

Set the Vectara corpus key and the tenant-specific Fluid Topics settings:

```yaml
vectara:
  corpus_key: my-fluidtopics-corpus
  reindex: false
  mask_pii: true       # optional; uses existing Presidio support

crawling:
  crawler_type: fluidtopics

fluidtopics_crawler:
  base_url: "https://<tenant>.fluidtopics.net"
  api_key_header: "X-FluidTopics-Api-Key"
  search_endpoint: "/api/search"
  content_endpoint_template: "/api/topics/{id}"

  query: "*"
  page_param: "page"
  page_size_param: "limit"
  page_size: 100

  id_paths: ["id", "khubId", "contentId", "topicId", "mapId"]
  title_paths: ["title", "name", "metadata.title"]
  content_paths: ["content", "body", "html", "xml", "dita", "data.content"]
  metadata_paths:
    device_family: "metadata.device_family"
    content_type: "metadata.content_type"
    version: "metadata.version"
    access_tier: "metadata.access_tier"
    publication_date: "metadata.publication_date"
```

Keep secrets in `secrets.toml`:

```toml
[altera-fluidtopics]
api_key="<VECTARA_INDEXING_API_KEY>"
FLUIDTOPICS_API_KEY="<FLUID_TOPICS_API_KEY>"
# or: FLUID_TOPICS_API_KEY="<FLUID_TOPICS_API_KEY>"
```

Run:

```bash
bash run.sh config/my-fluidtopics.yaml altera-fluidtopics
```

## Incremental refresh

The first implementation supports full/poll-style runs. If the tenant list API
supports a modified-since filter, set `since_param` and `since`:

```yaml
fluidtopics_crawler:
  since_param: "modifiedSince"
  since: "2026-01-01T00:00:00Z"
```

Webhook-triggered incremental updates can invoke the same job with a narrowed
query/filter once the tenant's webhook payload and update API are confirmed.

## Metadata and access control

By default, the crawler emits:

- `source: fluid-topics`
- `document_id`
- `title`
- `url` when present
- configured metadata paths such as `device_family`, `content_type`, `version`,
  `access_tier`, and `publication_date`

Access-control rules (for example MyAltera/Azure AD groups to `access_tier`
filters) are tenant-specific. Configure the metadata paths/static metadata to
match the taxonomy and apply the corresponding filters at query time.

## Altera / tenant dependencies

Confirm these before production runs:

1. Tenant base URL and API reference/version.
2. API-key header name and whether the value must be raw or `Bearer <token>`.
3. Search/list endpoint, pagination params, and result JSON path.
4. Content endpoint and content/body JSON path.
5. Metadata taxonomy and access-control mapping.
6. Tenant rate limits and whether modified-since or webhook updates are
   available.
