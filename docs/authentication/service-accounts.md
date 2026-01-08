# Service Accounts Authentication

Service accounts provide server-to-server authentication without user interaction. They're ideal for automated, headless environments like production servers and CI/CD pipelines.

## Overview

Service accounts are special accounts that:

- Authenticate without user login
- Use JSON key files for credentials
- Work in headless environments
- Have their own permissions and quotas
- Are managed separately from user accounts

## Crawlers Using Service Accounts

| Crawler | Service | Documentation |
|---------|---------|---------------|
| **Google Drive** | Google Cloud Platform | [Guide](../crawlers/gdrive.md) |

---

## Google Drive Service Account Setup

Service accounts are an alternative to OAuth for Google Drive, ideal for server environments where interactive OAuth flow isn't possible.

### When to Use Service Accounts

**Use Service Accounts when:**
- ✅ Running in headless/server environment
- ✅ No interactive browser available
- ✅ Crawling shared drives (Shared Drives support)
- ✅ Production deployments
- ✅ CI/CD pipelines

**Use OAuth when:**
- ✅ Local development with browser
- ✅ Accessing personal My Drive
- ✅ User-specific content

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project:
   - Name: "Vectara Ingest Production"
   - Project ID: `vectara-ingest-prod`
3. Note your Project ID

### Step 2: Enable Required APIs

1. Navigate to **APIs & Services** → **Library**
2. Search and enable:
   - **Google Drive API**
   - **Google Sheets API** (if indexing Sheets)

### Step 3: Create Service Account

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **Create Service Account**
3. Service account details:
   - **Name**: `vectara-ingest-gdrive`
   - **Service account ID**: `vectara-ingest-gdrive`
   - **Description**: "Service account for Vectara Ingest Google Drive crawler"
4. Click **Create and Continue**
5. Grant access (optional for this step)
6. Click **Done**

### Step 4: Create and Download Key

1. Find your new service account in the list
2. Click on the service account name
3. Go to **Keys** tab
4. Click **Add Key** → **Create new key**
5. Key type: **JSON**
6. Click **Create**
7. JSON file downloads automatically
8. Rename file to `gdrive_service_account.json`
9. Move to your project directory

### Step 5: Share Drive Content

The service account has an email address like:
```
vectara-ingest-gdrive@vectara-ingest-prod.iam.gserviceaccount.com
```

**For Personal Drives:**
1. Share folders/files with the service account email
2. Grant **Viewer** or **Reader** access

**For Shared Drives:**
1. Go to Shared Drive settings
2. Add member: service account email
3. Role: **Viewer** or **Content Manager**

### Step 6: Configure Crawler

In your Google Drive crawler config:

```yaml
gdrive_crawler:
  service_account_file: "./gdrive_service_account.json"

  # For Shared Drives
  crawl_shared_drives: true
  shared_drive_ids:
    - "0AB1cD2EfG3HiJ4KlM5NoPqRsT"
```

### Step 7: Verify Setup

Test access:

```bash
python3 -m vectara_ingest --config config/gdrive.yaml
```

The crawler will:
1. Load service account credentials
2. Authenticate automatically
3. Access shared content
4. Start indexing

---

## File Structure

### Service Account JSON Key

The JSON file contains:

```json
{
  "type": "service_account",
  "project_id": "vectara-ingest-prod",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "vectara-ingest-gdrive@vectara-ingest-prod.iam.gserviceaccount.com",
  "client_id": "123456789...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
}
```

### Important Fields

- **`client_email`**: Service account email (use this to share content)
- **`private_key`**: Authentication key (keep secret!)
- **`project_id`**: Your Google Cloud project

---

## Security Best Practices

### Protecting Service Account Keys

**File Permissions:**
```bash
# Set restrictive permissions
chmod 600 gdrive_service_account.json

# Verify permissions
ls -la gdrive_service_account.json
# Should show: -rw------- (600)
```

**Git Ignore:**
```gitignore
# Add to .gitignore
*_service_account.json
service-account.json
*.json
secrets.toml
```

**Never Commit:**
- ❌ Don't commit JSON keys to git
- ❌ Don't share in Slack/email
- ❌ Don't upload to public locations

### Key Rotation

Rotate service account keys periodically:

1. Create new key for the same service account
2. Update crawler configuration
3. Test with new key
4. Delete old key:
   - Go to service account **Keys** tab
   - Find old key (by creation date)
   - Click **Delete**

### Least Privilege Access

**Share with minimum permissions:**
- ✅ **Viewer/Reader** for indexing
- ❌ Avoid **Editor** unless needed
- ❌ Never use **Owner**

**Limit scope:**
- Share only necessary folders
- Use Shared Drives for better control
- Don't share entire "My Drive"

---

## Service Account Permissions

### Google Drive Specific

Service accounts can:
- ✅ Read files shared with them
- ✅ Access Shared Drives
- ✅ List files and folders
- ✅ Download content
- ✅ Read metadata

Service accounts cannot:
- ❌ Access other users' "My Drive" unless explicitly shared
- ❌ Authenticate interactively
- ❌ Use OAuth consent screen

### IAM Roles (Optional)

For organization-wide access, assign IAM roles:

1. Go to **IAM & Admin** → **IAM**
2. Click **Grant Access**
3. Add service account email
4. Assign role (if needed):
   - **Drive File Viewer**: Read files
   - **Drive Folder Viewer**: List folders

**Note**: IAM roles are optional; sharing content directly is usually sufficient.

---

## Quota & Rate Limits

### Google Drive API Quotas

**Default Limits:**
- Queries per day: 1,000,000,000
- Queries per 100 seconds per user: 1,000
- Queries per 100 seconds: 10,000

**Service Account Notes:**
- Each service account has its own quota
- Create multiple service accounts for higher throughput
- Monitor quota usage in Cloud Console

### Configure Rate Limiting

In crawler config:

```yaml
gdrive_crawler:
  service_account_file: "./gdrive_service_account.json"
  num_per_second: 10  # Limit to 10 requests/second
```

---

## Troubleshooting

### "Service account not found"

**Cause**: JSON file path incorrect

**Solution**:
```yaml
# Use absolute path
service_account_file: "/full/path/to/gdrive_service_account.json"

# Or relative to config file
service_account_file: "./gdrive_service_account.json"
```

### "Permission denied" or "403"

**Cause**: Content not shared with service account

**Solution**:
1. Find service account email in JSON file (`client_email`)
2. Share folder/file with this email
3. Grant **Viewer** access

### "File not accessible" for Shared Drive

**Cause**: Service account not added to Shared Drive

**Solution**:
1. Open Shared Drive
2. Right-click → **Manage members**
3. Add service account email
4. Role: **Viewer**

### "Invalid credentials"

**Cause**: JSON file corrupted or invalid

**Solution**:
1. Verify JSON file is valid (check for trailing commas, quotes)
2. Re-download key from Google Cloud Console
3. Check file permissions (should be readable)

### "Daily limit exceeded"

**Cause**: Exceeded API quota

**Solution**:
1. Wait 24 hours for quota reset
2. Request quota increase in Cloud Console
3. Use multiple service accounts
4. Add rate limiting to crawler config

---

## Advanced Configuration

### Multiple Service Accounts

For higher throughput, use multiple service accounts:

**Service Account 1:**
```yaml
gdrive_crawler_1:
  service_account_file: "./gdrive_sa_1.json"
  folder_ids:
    - "folder1"
    - "folder2"
```

**Service Account 2:**
```yaml
gdrive_crawler_2:
  service_account_file: "./gdrive_sa_2.json"
  folder_ids:
    - "folder3"
    - "folder4"
```

### Domain-Wide Delegation

For Google Workspace, enable domain-wide delegation to access all users' drives:

**Setup:**
1. Go to service account details
2. Enable **Enable Google Workspace Domain-wide Delegation**
3. Note the Client ID
4. In Workspace Admin console:
   - **Security** → **API controls** → **Domain-wide delegation**
   - Add service account Client ID
   - Scopes: `https://www.googleapis.com/auth/drive.readonly`

**Configuration:**
```yaml
gdrive_crawler:
  service_account_file: "./gdrive_service_account.json"
  domain_wide_delegation: true
  impersonate_user: "user@company.com"
```

---

## Comparison: Service Accounts vs OAuth

| Feature | Service Accounts | OAuth 2.0 |
|---------|-----------------|-----------|
| **Environment** | Headless, server | Interactive, browser |
| **Authentication** | JSON key file | User login |
| **Shared Drives** | ✅ Full support | ✅ Full support |
| **Personal Drives** | Only if shared | ✅ Full access |
| **Automation** | ✅ Perfect | ⚠️ Requires initial auth |
| **CI/CD** | ✅ Ideal | ⚠️ Token management |
| **Quotas** | Per service account | Per user |
| **Setup Complexity** | Medium | Easy |
| **Recommended For** | Production, servers | Local development |

---

## Related Documentation

- [Google Drive Crawler](../crawlers/gdrive.md)
- [OAuth 2.0 Authentication](oauth.md)
- [Secrets Management](../secrets-management.md)
- [Authentication Overview](index.md)
