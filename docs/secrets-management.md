# Secrets Management

Learn how to securely manage API keys and credentials for vectara-ingest.

## The secrets.toml File

Vectara-ingest uses a `secrets.toml` file to store API keys, passwords, and other sensitive information. This file uses the TOML format and supports multiple profiles.

## Creating secrets.toml

Start by copying the example file:

```bash
cp secrets.example.toml secrets.toml
```

!!! warning "Security"
    Never commit `secrets.toml` to version control. It's included in `.gitignore` by default.

## Profile Structure

The `secrets.toml` file can contain multiple profiles for different environments or projects:

```toml
[general]
OPENAI_API_KEY = "sk-..."
ANTHROPIC_API_KEY = "sk-ant-..."

[default]
api_key = "your-vectara-api-key"

[production]
api_key = "prod-vectara-api-key"

[staging]
api_key = "staging-vectara-api-key"
```

## Using Profiles

Specify which profile to use when running a crawler:

```bash
bash run.sh config/my-config.yaml production
```

## Required Credentials

### Vectara API Key

Every profile needs a Vectara API key:

```toml
[default]
api_key = "your-vectara-api-key"
```

### Getting Your API Key

1. Log in to [console.vectara.com](https://console.vectara.com)
2. Navigate to your corpus
3. Click **Access Control** or **Authorization**
4. Copy your personal API key or create a query+index API key

## The [general] Profile

The `[general]` profile is special - it's used for LLM API keys required by advanced features:

```toml
[general]
OPENAI_API_KEY = "sk-..."
ANTHROPIC_API_KEY = "sk-ant-..."
LLAMA_CLOUD_API_KEY = "llx-..."
DOCUPANDA_API_KEY = "..."
PRIVATE_API_KEY = "..."
```

## Crawler-Specific Credentials

Add crawler-specific credentials to your profiles using UPPERCASE names:

```toml
[default]
api_key = "your-vectara-api-key"

# Notion
NOTION_API_KEY = "secret_..."

# Jira
JIRA_USERNAME = "user@example.com"
JIRA_PASSWORD = "your-api-token"

# GitHub
GITHUB_TOKEN = "ghp_..."

# Slack
SLACK_TOKEN = "xoxb-..."

# ServiceNow
SERVICENOW_USERNAME = "admin"
SERVICENOW_PASSWORD = "password"

# Confluence
CONFLUENCE_USERNAME = "user@example.com"
CONFLUENCE_PASSWORD = "api-token"

# Google Drive (OAuth - see separate guide)
# Box (OAuth - see separate guide)
```

## Multi-Environment Setup

Manage multiple environments with profiles:

```toml
[general]
OPENAI_API_KEY = "sk-..."

[dev]
api_key = "dev-corpus-api-key"
JIRA_USERNAME = "dev-user@example.com"
JIRA_PASSWORD = "dev-token"

[staging]
api_key = "staging-corpus-api-key"
JIRA_USERNAME = "staging-user@example.com"
JIRA_PASSWORD = "staging-token"

[prod]
api_key = "prod-corpus-api-key"
JIRA_USERNAME = "prod-user@example.com"
JIRA_PASSWORD = "prod-token"
```

Run with specific profiles:

```bash
bash run.sh config/jira.yaml dev
bash run.sh config/jira.yaml staging
bash run.sh config/jira.yaml prod
```

## Best Practices

### Security

1. **Never Commit Secrets**: Ensure `secrets.toml` is in `.gitignore`
2. **Rotate Keys Regularly**: Update API keys periodically
3. **Limit Permissions**: Use minimal required permissions for API keys
4. **Separate Environments**: Use different keys for dev/staging/prod

### Organization

1. **Group by Environment**: Create profiles for each environment
2. **Document Keys**: Add comments explaining key purposes
3. **Consistent Naming**: Use UPPERCASE for all secret keys
4. **Keep [general] Clean**: Only LLM keys in `[general]`

## OAuth Credentials

Some crawlers require OAuth authentication:

### Google Drive

See [Google Drive OAuth Setup](gdrive-oauth-setup.md)

### Box

Requires `box_oauth_credentials.json` - see Box crawler documentation

## Private Model APIs

For private LLM endpoints:

```toml
[general]
PRIVATE_API_KEY = "your-private-api-key"
```

Configure in your crawler YAML:

```yaml
doc_processing:
  model_config:
    text:
      provider: private
      base_url: "http://host.docker.internal:5000/v1"
      model_name: "custom-model"
```

## Troubleshooting

### Authentication Failed

**Error**: `Authentication failed`

**Solutions**:
- Verify API key is correct
- Check key has proper permissions (indexing)
- Ensure profile name matches command line argument
- Check for extra spaces in `secrets.toml`

### Missing Credentials

**Error**: `Missing required credential: NOTION_API_KEY`

**Solution**: Add the required key to your profile in `secrets.toml`

### Wrong Profile

**Error**: Can't find corpus or authentication issues

**Solution**: Verify you're using the correct profile:
```bash
bash run.sh config/my-config.yaml [profile-name]
```

## Example: Complete Setup

```toml
# secrets.toml

# LLM API keys for advanced features
[general]
OPENAI_API_KEY = "sk-proj-..."
ANTHROPIC_API_KEY = "sk-ant-..."

# Development environment
[dev]
api_key = "zwt_dev_..."
NOTION_API_KEY = "secret_dev..."
JIRA_USERNAME = "dev@company.com"
JIRA_PASSWORD = "dev-token"
SLACK_TOKEN = "xoxb-dev..."

# Production environment
[prod]
api_key = "zwt_prod_..."
NOTION_API_KEY = "secret_prod..."
JIRA_USERNAME = "prod@company.com"
JIRA_PASSWORD = "prod-token"
SLACK_TOKEN = "xoxb-prod..."
```

## Next Steps

- **Configure Your Crawler**: See [Configuration Reference](configuration.md)
- **Run Your First Crawl**: Follow the [Getting Started Guide](getting-started.md)
- **OAuth Setup**: Learn about [Google Drive OAuth](gdrive-oauth-setup.md)
