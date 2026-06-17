# Secrets Management

<p class="subtitle">Learn how to securely manage API keys and credentials for vectara-ingest. This guide covers the secrets.toml file, profile management, and best practices for secure ingestion.</p>

---

## The secrets.toml File

Vectara-ingest uses a `secrets.toml` file to store API keys, passwords, and other sensitive information. This file uses the TOML format and supports multiple profiles for different environments or projects.

## Creating secrets.toml

Start by copying the example file:

```bash
cp secrets.example.toml secrets.toml
```

<div class="warning-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Security Warning</p>
    <p>Never commit <code>secrets.toml</code> to version control. It's included in <code>.gitignore</code> by default. Accidentally committed secrets should be rotated immediately.</p>
  </div>
</div>

---

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

---

## Using Profiles

Specify which profile to use when running a crawler:

```bash
bash run.sh config/my-config.yaml production
```

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">Default Profile</p>
    <p>If no profile is specified, vectara-ingest uses the <code>[default]</code> profile automatically.</p>
  </div>
</div>

---

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

<div class="info-admonition">
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="admonition-icon"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
  <div class="admonition-content">
    <p class="admonition-title">API Key Permissions</p>
    <p>Ensure your API key has <strong>indexing</strong> permissions to upload documents to your corpus.</p>
  </div>
</div>

---

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

These keys enable features like:

- **Table summarization** (requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- **Image processing** (requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- **Contextual chunking** (requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)
- **LlamaIndex parsing** (requires `LLAMA_CLOUD_API_KEY`)
- **DocuPanda parsing** (requires `DOCUPANDA_API_KEY`)
- **Private model endpoints** (requires `PRIVATE_API_KEY`)

---

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

---

## Multi-Environment Setup

Manage multiple environments with separate profiles:

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

---

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
4. **Keep [general] Clean**: Only LLM keys in `[general]` profile

---

## Private Model APIs

For private or self-hosted LLM endpoints, add the API key to the `[general]` profile:

```toml
[general]
PRIVATE_API_KEY = "your-private-api-key"
```

Then configure your crawler YAML to use the private endpoint:

```yaml
doc_processing:
  model_config:
    text:
      provider: private
      base_url: "http://host.docker.internal:5000/v1"
      model_name: "custom-model"
```

---

## Troubleshooting

<div class="troubleshooting-section">
  <div class="troubleshooting-card">
    <h3>Authentication Failed</h3>
    <p><strong>Error:</strong> <code>Authentication failed</code></p>
    <p><strong>Solutions:</strong></p>
    <ul>
      <li>Verify API key is correct in <code>secrets.toml</code></li>
      <li>Check key has proper permissions (indexing)</li>
      <li>Ensure profile name matches command line argument</li>
      <li>Check for extra spaces or quotes in <code>secrets.toml</code></li>
    </ul>
  </div>

  <div class="troubleshooting-card">
    <h3>Missing Credentials</h3>
    <p><strong>Error:</strong> <code>Missing required credential: NOTION_API_KEY</code></p>
    <p><strong>Solutions:</strong></p>
    <ul>
      <li>Add the required key to your profile in <code>secrets.toml</code></li>
      <li>Ensure the key name is in UPPERCASE</li>
      <li>Verify you're using the correct profile</li>
    </ul>
  </div>

  <div class="troubleshooting-card">
    <h3>Wrong Profile</h3>
    <p><strong>Error:</strong> Can't find corpus or authentication issues</p>
    <p><strong>Solutions:</strong></p>
    <ul>
      <li>Verify you're using the correct profile:</li>
    </ul>
    <pre><code class="language-bash">bash run.sh config/my-config.yaml [profile-name]</code></pre>
    <ul>
      <li>Check that the profile exists in <code>secrets.toml</code></li>
      <li>Ensure the profile has the required <code>api_key</code></li>
    </ul>
  </div>
</div>

---

## Example: Complete Setup

Here's a complete `secrets.toml` example with multiple environments:

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

---

## Next Steps

<div class="next-steps-grid">
  <a href="configuration-reference.md" class="next-step-card">
    <h3>Configuration Reference →</h3>
    <p>Learn about all configuration options for vectara-ingest</p>
  </a>

  <a href="getting-started.md" class="next-step-card">
    <h3>Run Your First Crawl →</h3>
    <p>Follow the step-by-step guide to start ingesting content</p>
  </a>
</div>

---

## Getting Help

Need assistance with secrets management? Here are your resources:

<div class="help-grid">
  <a href="https://github.com/vectara/vectara-ingest/issues" target="_blank" class="help-card">
    <h4>GitHub Issues</h4>
    <p>Report bugs or ask questions</p>
  </a>

  <a href="https://discord.gg/GFb8gMz6UH" target="_blank" class="help-card">
    <h4>Discord Community</h4>
    <p>Chat with other users</p>
  </a>

  <a href="https://docs.vectara.com" target="_blank" class="help-card">
    <h4>Vectara Docs</h4>
    <p>Platform documentation</p>
  </a>
</div>
