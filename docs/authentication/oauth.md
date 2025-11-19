# OAuth 2.0 Authentication

OAuth 2.0 is an authorization framework that enables applications to obtain limited access to user accounts on services like Google Drive, Notion, and Slack.

## Overview

OAuth 2.0 provides secure, token-based authentication without sharing passwords. The process involves:

1. Creating an OAuth application in the service
2. Obtaining client credentials (Client ID, Client Secret)
3. Authorizing the application
4. Receiving access tokens
5. Using tokens to access APIs

## Crawlers Using OAuth 2.0

| Crawler | Service | Documentation |
|---------|---------|---------------|
| **Google Drive** | Google Cloud Platform | [Guide](../crawlers/gdrive.md) |
| **Notion** | Notion Integrations | [Guide](../crawlers/notion.md) |
| **Slack** | Slack Apps | [Guide](../crawlers/slack.md) |

---

## Google Drive OAuth Setup

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Note your Project ID

### Step 2: Enable Google Drive API

1. Navigate to **APIs & Services** → **Library**
2. Search for "Google Drive API"
3. Click **Enable**

### Step 3: Create OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Choose **External** (or Internal for workspace)
3. Fill in required fields:
   - App name: "Vectara Ingest"
   - User support email: your email
   - Developer contact: your email
4. Click **Save and Continue**
5. **Scopes**: Add `https://www.googleapis.com/auth/drive.readonly`
6. **Test users**: Add your email address
7. Click **Save and Continue**

### Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Application type: **Desktop app**
4. Name: "Vectara Ingest Client"
5. Click **Create**
6. Download the JSON file
7. Save as `oauth_credentials.json` in your project directory

### Step 5: Add to secrets.toml

The OAuth credentials are loaded from the JSON file, no need to add to secrets.toml.

### Step 6: First-Time Authorization

Run the crawler for the first time:

```bash
python3 -m vectara_ingest --config config/gdrive.yaml
```

A browser window will open:
1. Sign in to your Google account
2. Review permissions
3. Click **Allow**
4. Browser will show "Authentication successful"

A `google_drive_token.json` file will be created with your access token.

### Step 7: Token Storage

The token file is saved locally:
- **Location**: Same directory as script
- **Name**: `google_drive_token.json`
- **Permissions**: Automatically managed
- **Expiration**: Tokens auto-refresh

---

## Notion OAuth Setup

### Step 1: Create Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click **New integration**
3. Fill in details:
   - Name: "Vectara Ingest"
   - Associated workspace: Select your workspace
   - Type: Internal (or Public for multiple workspaces)
4. Click **Submit**

### Step 2: Get Integration Token

1. On the integration page, find **Internal Integration Token**
2. Click **Show** and copy the token
3. It starts with `secret_`

### Step 3: Add to secrets.toml

```toml
[default]
NOTION_API_KEY = "secret_abc123..."
```

### Step 4: Share Pages with Integration

For each Notion page/database you want to index:

1. Open the page in Notion
2. Click **Share** in the top right
3. Search for your integration name
4. Click **Invite**

The integration now has access to that page and all child pages.

---

## Slack OAuth Setup

### Step 1: Create Slack App

1. Go to [Slack API](https://api.slack.com/apps)
2. Click **Create New App**
3. Choose **From scratch**
4. App Name: "Vectara Ingest"
5. Select your workspace
6. Click **Create App**

### Step 2: Add OAuth Scopes

1. Go to **OAuth & Permissions**
2. Scroll to **Bot Token Scopes**
3. Add required scopes:
   - `channels:history` - Read public channel messages
   - `channels:read` - View basic channel info
   - `users:read` - View people in workspace
   - `groups:history` - Read private channel messages (if needed)
   - `im:history` - Read direct messages (if needed)

### Step 3: Install App to Workspace

1. Scroll to top of **OAuth & Permissions** page
2. Click **Install to Workspace**
3. Review permissions
4. Click **Allow**

### Step 4: Get Bot Token

1. After installation, you'll see **Bot User OAuth Token**
2. Copy the token (starts with `xoxb-`)

### Step 5: Add to secrets.toml

```toml
[default]
SLACK_TOKEN = "xoxb-123456-789012-abc..."
```

### Step 6: Invite Bot to Channels

For private channels, invite the bot:

```
/invite @vectara-ingest
```

---

## Token Management

### Token Storage

OAuth tokens are stored securely:

**Google Drive:**
```
google_drive_token.json
```

**Notion:**
```toml
# In secrets.toml
NOTION_API_KEY = "secret_..."
```

**Slack:**
```toml
# In secrets.toml
SLACK_TOKEN = "xoxb-..."
```

### Token Refresh

**Google Drive:**
- Tokens auto-refresh when expired
- Refresh token stored in `google_drive_token.json`
- No manual intervention needed

**Notion & Slack:**
- Tokens don't expire
- Revoke from service if compromised

### Token Revocation

**Google Drive:**
1. Go to [Google Account](https://myaccount.google.com/permissions)
2. Find "Vectara Ingest"
3. Click **Remove Access**

**Notion:**
1. Go to [My Integrations](https://www.notion.so/my-integrations)
2. Select your integration
3. Click **Delete Integration**

**Slack:**
1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Select your app
3. Go to **OAuth & Permissions**
4. Click **Revoke Token**

---

## Troubleshooting

### "OAuth error: invalid_grant"

**Cause**: Token expired or revoked

**Solution**:
1. Delete `google_drive_token.json`
2. Run crawler again
3. Re-authorize in browser

### "Integration not found"

**Cause**: Notion integration not shared with page

**Solution**:
1. Open page in Notion
2. Click **Share**
3. Invite your integration

### "not_in_channel"

**Cause**: Slack bot not added to channel

**Solution**:
```
/invite @your-bot-name
```

### "insufficient_scope"

**Cause**: Missing required OAuth scopes

**Solution**:
1. Go to OAuth settings
2. Add missing scopes
3. Reinstall app to workspace
4. Get new token

---

## Security Best Practices

### Protecting OAuth Tokens

- ✅ **Never commit token files to git**
- ✅ **Add to .gitignore**:
  ```gitignore
  google_drive_token.json
  secrets.toml
  oauth_credentials.json
  ```
- ✅ **Use restrictive file permissions**:
  ```bash
  chmod 600 google_drive_token.json
  chmod 600 oauth_credentials.json
  ```

### Scope Management

- ✅ **Request minimum scopes needed**
- ✅ **Review permissions regularly**
- ✅ **Use read-only scopes when possible**

### Token Rotation

- ✅ **Rotate tokens periodically**
- ✅ **Revoke unused integrations**
- ✅ **Monitor access logs**

---

## Related Documentation

- [Google Drive Crawler](../crawlers/gdrive.md)
- [Notion Crawler](../crawlers/notion.md)
- [Slack Crawler](../crawlers/slack.md)
- [Secrets Management](../secrets-management.md)
- [Authentication Overview](index.md)
