# GitHub Crawler

The GitHub crawler indexes issues, pull requests, and code documentation from GitHub repositories with full support for comments, metadata extraction, and markdown file indexing.

## Overview

- **Crawler Type**: `github`
- **Authentication**: Personal Access Token (optional for public repos)
- **API Support**: GitHub REST API v3
- **Content Types**: Issues, pull requests, comments, markdown files
- **Metadata Capture**: Author, creation/modification dates, state, labels
- **Code Indexing**: Markdown files (`.md`, `.mdx`) only

## Use Cases

- Knowledge base from GitHub issues and discussions
- Pull request tracking and review history
- Project documentation from repository code
- Feature requests and bug tracking database
- Technical specifications from GitHub
- Developer documentation and guides
- Open source project knowledge base

## Getting Started: API Authentication

### Get Your GitHub Personal Access Token

While the GitHub crawler can work with public repositories without authentication (limited to 60 requests/hour), using a Personal Access Token (PAT) is recommended for:
- Higher rate limits (5000 requests/hour)
- Access to private repositories
- Reliable crawler operation

#### Creating a Personal Access Token

1. Go to [GitHub Settings > Developer Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Click **Generate new token** (classic)
3. Give the token a descriptive name (e.g., "Vectara Ingest")
4. Select scopes:
   - For public repositories: `public_repo`
   - For private repositories: `repo` (full control)
   - Recommended for most use cases: `repo` (includes private repos)
5. Click **Generate token**
6. Copy the token immediately (you'll only see it once)

#### Token Permissions Required

The token needs these minimum permissions:

- **`public_repo`**: Access to public repositories only
  - Read issues and PRs
  - Read code files
  - Best for open source projects

- **`repo`**: Full control of private and public repositories
  - Read private repositories
  - Read issues and PRs
  - Read code files
  - Recommended for private projects

Example scopes JSON:
```json
{
  "scopes": ["public_repo"]  // For public repos only
}
```

Or:
```json
{
  "scopes": ["repo"]  // For public and private repos
}
```

### Setting Environment Variables

Store your token securely as an environment variable:

```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

The crawler will automatically read this from your environment.

**Security Note**: Never commit tokens to version control. Use environment variables or a secrets management system.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-repos

crawling:
  crawler_type: github

github_crawler:
  # Repository owner (user or organization)
  owner: "owner-name"

  # List of repository names to crawl
  repos:
    - "repo1"
    - "repo2"

  # Index markdown files from the codebase
  crawl_code: true

  # (Optional) GitHub Personal Access Token for higher rate limits
  github_token: "${GITHUB_TOKEN}"

  # (Optional) Rate limiting (requests per second)
  num_per_second: 2
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: github

github_crawler:
  owner: "vectara"
  repos:
    - "vectara-ingest"
    - "getting-started"
    - "protos"

  # Enable markdown file indexing
  crawl_code: true

  # Personal access token for authentication
  github_token: "${GITHUB_TOKEN}"

  # Rate limiting for API requests
  num_per_second: 2

metadata:
  source: github
  environment: production
  content_types:
    - issues
    - pull_requests
    - comments
    - code_documentation
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `owner` | string | Yes | - | Repository owner (user or organization name) |
| `repos` | list | Yes | - | List of repository names to crawl |
| `crawl_code` | bool | No | `false` | Index markdown files from the codebase |
| `github_token` | string | No | - | GitHub Personal Access Token (recommended for higher rate limits) |
| `num_per_second` | float | No | `2` | Rate limiting: requests per second |

## Rate Limiting

GitHub API has rate limits that vary based on authentication:

### Without Authentication (Public Repos Only)

- **Limit**: 60 requests/hour
- **Per Repository**: Limited requests
- **Use Case**: Small crawls of public repositories
- **Recommendation**: Only for testing/development

### With Personal Access Token (Recommended)

- **Limit**: 5000 requests/hour
- **Per Repository**: Sufficient for most crawls
- **Use Case**: Production use, regular updates
- **Recommendation**: Use for all production crawls

### Rate Limiter Configuration

The `num_per_second` parameter controls how many requests are made per second:

```yaml
github_crawler:
  num_per_second: 2  # Default: 2 requests/second
```

Higher values speed up crawling but risk hitting rate limits:

```yaml
# Conservative (safe for public crawls)
num_per_second: 1

# Moderate (recommended with token)
num_per_second: 2

# Aggressive (use with token and caution)
num_per_second: 5
```

### Rate Limit Headers

The GitHub API includes rate limit information in response headers:

```
X-RateLimit-Limit: 5000
X-RateLimit-Remaining: 4999
X-RateLimit-Reset: 1234567890
```

When rate limited (429 response), the crawler will retry with backoff.

## Public vs Private Repositories

### Public Repositories

```yaml
github_crawler:
  owner: "public-org"
  repos:
    - "open-source-project"
    - "another-project"
  # Token optional but recommended
  github_token: "${GITHUB_TOKEN}"
```

**Accessible without token**: Yes (limited to 60 requests/hour)
**Recommended token**: Yes (for 5000 requests/hour limit)

### Private Repositories

```yaml
github_crawler:
  owner: "company-org"
  repos:
    - "private-project"
    - "internal-docs"
  # Token REQUIRED with 'repo' scope
  github_token: "${GITHUB_TOKEN}"
```

**Accessible without token**: No
**Required token scope**: `repo`

### Mixed (Public + Private)

```yaml
github_crawler:
  owner: "mixed-org"
  repos:
    - "public-repo"
    - "private-repo"
  # Token with 'repo' scope allows access to both
  github_token: "${GITHUB_TOKEN}"
```

Token with `repo` scope allows access to both public and private repositories.

## Code Crawling: Markdown Files

The GitHub crawler can index markdown files (`.md`, `.mdx`) from your repository code, useful for:
- README files
- Technical documentation
- API documentation
- Architecture decision records (ADRs)
- Setup guides

### Enabling Code Crawling

```yaml
github_crawler:
  crawl_code: true  # Enable markdown file indexing
```

### How It Works

1. **Discovery**: Recursively scans repository for `.md` and `.mdx` files
2. **Parsing**: Converts markdown to HTML and extracts text content
3. **Chunking**: Splits content into indexed sections
4. **Metadata**: Captures file path and source information
5. **Indexing**: Sends to Vectara with document metadata

### Supported File Types

- `.md` - Standard markdown files
- `.mdx` - MDX format (markdown + JSX)

Unsupported:
- Source code files (`.js`, `.py`, `.go`, etc.)
- Binary files
- Other text formats

### File Crawling Examples

```yaml
# Basic: Crawl all markdown
github_crawler:
  crawl_code: true

# Advanced: Crawl without code
github_crawler:
  crawl_code: false  # Only issues and PRs
```

### Indexed Markdown Files

When crawling code, the crawler indexes files with metadata:

```
docs/README.md
docs/setup.md
docs/architecture/design.md
guides/api-reference.md
```

Each file becomes a separate document with metadata:
- `file`: File path (e.g., `docs/README.md`)
- `source`: Always "github"
- `url`: Direct link to file on GitHub
- `title`: File name
- `description`: Description of file content

## Issues and Pull Requests

### Issues Indexed

The crawler automatically indexes all GitHub issues with:

- **Title**: Issue title
- **Description**: Issue body/description
- **State**: open, closed
- **Labels**: Issue labels/tags
- **Author**: Who created the issue
- **Created**: Creation date
- **Updated**: Last modification date
- **Comments**: All issue comments with author metadata
- **URL**: Link to browse issue on GitHub

### Pull Requests Indexed

Similarly, all pull requests include:

- **Title**: PR title
- **Description**: PR description/body
- **State**: open, closed, merged
- **Author**: Who created the PR
- **Created**: Creation date
- **Updated**: Last modification date
- **Comments**: All PR review comments
- **URL**: Link to browse PR on GitHub

### Metadata Captured

The crawler automatically indexes:

- **ID**: Unique GitHub issue/PR ID
- **Number**: Sequential issue/PR number
- **Title**: Issue/PR title
- **Description**: Full body text
- **State**: Current state (open/closed/merged)
- **Author**: Creator username
- **Created Date**: When created
- **Updated Date**: Last modification time
- **Labels**: Associated labels/tags
- **URL**: GitHub web URL
- **Source**: Always "github"

## Comment Extraction

Comments on both issues and PRs are automatically indexed:

### Comment Structure

Each comment becomes a searchable section in the parent document with:

- **Author**: Comment author username
- **Text**: Full comment body
- **Created**: Comment creation date
- **Updated**: Comment modification date
- **URL**: Direct link to comment
- **ID**: Unique comment identifier

### Comment Example

For an issue with 3 comments:

```
Issue #42: Add dark mode support
├── Issue Description
├── Comment by alice: "Great idea! Here's my approach..."
├── Comment by bob: "I agree, let me start on this"
└── Comment by charlie: "PR ready for review"
```

All become searchable within the single issue document.

## Organization vs User Repositories

### User Repositories

Repositories owned by a personal GitHub account:

```yaml
github_crawler:
  owner: "username"
  repos:
    - "my-project"
    - "another-project"
```

Access:
- Public: Accessible without token
- Private: Requires token with `repo` scope

### Organization Repositories

Repositories owned by a GitHub organization:

```yaml
github_crawler:
  owner: "organization-name"
  repos:
    - "project1"
    - "project2"
  github_token: "${GITHUB_TOKEN}"
```

Access:
- Public: Accessible without token
- Private: Requires token with appropriate organization access

### Checking Repository Access

To verify token access to a repository:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/owner/repo
```

Returns 200 if accessible, 404 if not found or inaccessible.

## How It Works

### Crawl Process

1. **Fetch Issues**: Retrieves all issues (open and closed) for each repository
2. **Process Issues**: For each issue:
   - Extracts title, description, metadata
   - Fetches and includes all comments
   - Indexes with Vectara
3. **Fetch Pull Requests**: Retrieves all PRs (open, closed, merged)
4. **Process PRs**: For each PR:
   - Extracts title, description, metadata
   - Fetches and includes all PR review comments
   - Indexes with Vectara
5. **Crawl Code (Optional)**: If enabled, recursively crawls repository for markdown files
6. **Index Documents**: Sends all content to Vectara with structured metadata

### API Requests

The crawler makes these API calls:

```
GET /repos/{owner}/{repo}/issues?state=all
GET /repos/{owner}/{repo}/issues/{number}/comments
GET /repos/{owner}/{repo}/pulls?state=all
GET /repos/{owner}/{repo}/pulls/{number}/comments
GET /repos/{owner}/{repo}/contents/  (if crawl_code=true)
```

Each request consumes against rate limit.

### Rate Limiting in Action

The `RateLimiter` class manages request timing:

```python
# With num_per_second: 2
# Allows max 2 requests per second
# Distributes requests to stay within limits
```

## Troubleshooting

### Authentication Failed

**Error**: `401 Unauthorized`

**Solutions**:
1. Verify token is correct:
   ```bash
   echo $GITHUB_TOKEN
   ```
2. Check token hasn't expired
3. Verify token has correct scopes:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
   ```
4. Confirm token is set in environment:
   ```bash
   export GITHUB_TOKEN="ghp_xxxx..."
   ```

### Repository Not Found

**Error**: `404 Not Found`

**Solutions**:
1. Verify owner name is correct:
   ```bash
   curl https://api.github.com/users/{owner}
   ```
2. Check repository name spelling
3. For private repos, ensure token has `repo` scope
4. Verify token has access to organization (if org repo)

### Rate Limit Exceeded

**Error**: `429 Too Many Requests`

**Solutions**:
1. Ensure you're using a Personal Access Token (60 vs 5000 requests/hour)
2. Reduce `num_per_second`:
   ```yaml
   github_crawler:
     num_per_second: 1  # Instead of 2
   ```
3. Wait for rate limit to reset (shown in error headers)
4. Run fewer repositories at once:
   ```yaml
   # Split into multiple configs
   repos: ["repo1", "repo2"]  # Instead of 10 repos
   ```

### No Issues Found

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Verify repository has issues/PRs
2. Check repository is public or token has access
3. Verify owner/repos configuration
4. Test API access:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" \
     https://api.github.com/repos/{owner}/{repo}/issues
   ```

### Code Crawling Issues

**Error**: Markdown files not indexed

**Solutions**:
1. Verify `crawl_code: true` is set
2. Check repository has `.md` or `.mdx` files
3. Verify files are not in `.gitignore`
4. Test code crawl with smaller repository first

## Performance Tips

### 1. Use Targeted Repository Lists

Instead of crawling many repositories:

```yaml
# Bad: Too many repos at once
repos:
  - "repo1"
  - "repo2"
  # ... 20 more repos

# Good: Focused list
repos:
  - "active-project"
  - "documentation"
```

### 2. Batch by Project Type

Create separate configs for different purposes:

```yaml
# github-docs.yaml
repos:
  - "documentation"
  - "guides"
  crawl_code: true

# github-issues.yaml
repos:
  - "main-project"
  - "secondary-project"
  crawl_code: false
```

### 3. Optimize Code Crawling

Enable only when needed:

```yaml
# Issues and PRs only
github_crawler:
  crawl_code: false

# With markdown documentation
github_crawler:
  crawl_code: true
```

### 4. Schedule Off-Peak Runs

Run large crawls during off-hours:

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/github-prod.yaml default
```

### 5. Tune Rate Limiting

Adjust for your needs:

```yaml
# Conservative (avoid rate limits)
num_per_second: 1

# Balanced (recommended)
num_per_second: 2

# Aggressive (use with caution)
num_per_second: 5
```

### 6. Reindex Strategy

On subsequent runs, use appropriate settings:

```yaml
vectara:
  # First run: create new corpus
  reindex: true

  # Subsequent runs: update existing
  reindex: false
```

## Best Practices

### 1. Always Use Tokens for Production

```yaml
# Production: Always use token
github_token: "${GITHUB_TOKEN}"

# Development: Can skip for public repos
# But recommend token anyway
```

### 2. Secure Token Management

```bash
# DO: Use environment variables
export GITHUB_TOKEN="ghp_xxxx..."

# DO NOT: Hard-code in config
github_token: "ghp_xxxx..."  # WRONG!

# DO NOT: Commit to version control
git add config/github.yaml  # Contains token - WRONG!
```

### 3. Use Descriptive Metadata

```yaml
metadata:
  source: github
  environment: production
  organization: "my-org"
  content_types:
    - issues
    - pull_requests
    - documentation
  sync_frequency: "daily"
```

### 4. Version Your Configurations

```yaml
metadata:
  version: "1.0"
  created_date: "2024-11-18"
  notes: "Initial GitHub crawler setup"
```

### 5. Start Small

Test with one repository first:

```yaml
github_crawler:
  owner: "test-org"
  repos: ["test-repo"]  # Single repo
  crawl_code: true
```

Then expand:

```yaml
repos:
  - "test-repo"
  - "project1"
  - "project2"
```

### 6. Monitor Crawls

Watch logs during execution:

```bash
bash run.sh config/github.yaml default
# Monitor for errors and status
```

Check for:
- Authentication errors
- Rate limit warnings
- Successful document indexing
- Any failed requests

## Running the Crawler

### Create Your Configuration

```bash
# Create config file
vim config/github-repos.yaml
```

### Set Environment Variables

```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

Or leave unset for public repositories only:

```bash
unset GITHUB_TOKEN  # Public repos, 60 requests/hour limit
```

### Run the Crawler

```bash
# Run with your config
bash run.sh config/github-repos.yaml default

# Monitor logs
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/github-repos.yaml default

# Twice weekly
0 2 * * 1,4 cd /path/to/vectara-ingest && bash run.sh config/github-repos.yaml default

# Weekly on Monday
0 2 * * 1 cd /path/to/vectara-ingest && bash run.sh config/github-repos.yaml default
```

Or use a task scheduler like GitHub Actions:

```yaml
# .github/workflows/index-to-vectara.yml
name: Index to Vectara
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  crawl:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run GitHub Crawler
        env:
          GITHUB_TOKEN: ${{ secrets.VECTARA_GITHUB_TOKEN }}
        run: |
          bash run.sh config/github-repos.yaml default
```

## Complete Examples

### Example 1: Simple Organization Crawl

```yaml
# config/github-simple.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-org

crawling:
  crawler_type: github

github_crawler:
  owner: "my-organization"
  repos:
    - "main-project"
    - "documentation"
  crawl_code: false
  github_token: "${GITHUB_TOKEN}"

metadata:
  source: github
  environment: production
```

Run with:
```bash
export GITHUB_TOKEN="ghp_xxxx..."
bash run.sh config/github-simple.yaml default
```

### Example 2: Complete with Code Crawling

```yaml
# config/github-complete.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-knowledge-base
  reindex: false
  verbose: true

crawling:
  crawler_type: github

github_crawler:
  owner: "vectara"
  repos:
    - "vectara-ingest"
    - "getting-started"
    - "protos"
  crawl_code: true
  github_token: "${GITHUB_TOKEN}"
  num_per_second: 2

metadata:
  source: github
  environment: production
  content_types:
    - issues
    - pull_requests
    - comments
    - code_documentation
  sync_frequency: daily
```

Run with:
```bash
bash run.sh config/github-complete.yaml default
```

### Example 3: Multi-Organization Setup

```yaml
# config/github-multi-org.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-multi-org
  reindex: false

crawling:
  crawler_type: github

github_crawler:
  owner: "primary-org"
  repos:
    - "project-1"
    - "project-2"
    - "project-3"
  crawl_code: true
  github_token: "${GITHUB_TOKEN}"
  num_per_second: 2

metadata:
  source: github
  organization: "primary-org"
  content_types:
    - issues
    - pull_requests
    - documentation
```

Create separate configs for each organization:

```bash
config/github-org-1.yaml
config/github-org-2.yaml
config/github-org-3.yaml
```

Run all:
```bash
for config in config/github-org-*.yaml; do
  bash run.sh "$config" default
done
```

### Example 4: Markdown Documentation Only

```yaml
# config/github-docs-only.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-docs
  reindex: true

crawling:
  crawler_type: github

github_crawler:
  owner: "docs-org"
  repos:
    - "documentation"
    - "guides"
    - "tutorials"
  crawl_code: true  # Only markdown files indexed
  github_token: "${GITHUB_TOKEN}"

metadata:
  source: github
  content_type: documentation
```

### Example 5: Issues and PRs Only (No Code)

```yaml
# config/github-issues-prs.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: github-discussions

crawling:
  crawler_type: github

github_crawler:
  owner: "project-org"
  repos:
    - "main-project"
    - "secondary-project"
  crawl_code: false  # Only issues and PRs
  github_token: "${GITHUB_TOKEN}"
  num_per_second: 3  # Higher rate since no code crawling

metadata:
  source: github
  content_types:
    - issues
    - pull_requests
    - discussions
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## GitHub API Resources

- [GitHub REST API Documentation](https://docs.github.com/en/rest)
- [GitHub Authentication](https://docs.github.com/en/authentication)
- [Personal Access Tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [API Rate Limiting](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting)
- [Repository Contents API](https://docs.github.com/en/rest/repos/contents)
- [Issues API](https://docs.github.com/en/rest/issues)
- [Pull Requests API](https://docs.github.com/en/rest/pulls)
