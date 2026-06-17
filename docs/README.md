# Vectara Ingest Documentation

This directory contains the documentation for vectara-ingest, built with MkDocs and Material theme.

## Building Locally

To build and preview the documentation locally:

```bash
# Install documentation dependencies
pip install -r requirements-docs.txt

# Serve documentation locally
mkdocs serve
```

Then open http://127.0.0.1:8000 in your browser.

## Building Static Site

```bash
mkdocs build
```

The static site will be generated in the `site/` directory.

## Deployment

Documentation is automatically deployed to GitHub Pages when changes are pushed to the `main` branch.

The deployment is handled by `.github/workflows/docs.yml`.

## Documentation Structure

```
docs/
├── index.md                     # Home page
├── installation.md              # Installation guide
├── getting-started.md           # Quick start tutorial
├── configuration.md             # Configuration reference
├── secrets-management.md        # Secrets and API keys
├── crawlers/                    # Crawler documentation
│   ├── index.md                # Crawlers overview
│   ├── website.md              # Website crawler
│   ├── rss.md                  # RSS crawler
│   └── ...                     # Other crawlers
├── features/                    # Feature documentation
│   ├── document-processing.md
│   ├── table-extraction.md
│   └── ...
├── deployment/                  # Deployment guides
│   ├── docker.md
│   ├── render.md
│   └── ...
├── advanced/                    # Advanced topics
│   ├── custom-crawler.md
│   ├── saml-auth.md
│   └── ...
└── contributing.md              # Contributing guide
```

## Contributing to Documentation

1. Edit markdown files in the `docs/` directory
2. Preview changes with `mkdocs serve`
3. Commit and push to trigger automatic deployment

## Navigation

Navigation is configured in `mkdocs.yml` under the `nav:` section.
