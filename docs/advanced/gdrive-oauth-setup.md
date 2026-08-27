# Google Drive OAuth Setup Guide

This guide explains how to set up OAuth authentication for the Google Drive crawler.

## Overview

OAuth authentication allows you to crawl Google Drive files without requiring Google Workspace domain-wide delegation. The token is stored in `credentials.json` and automatically refreshed when it expires.

**Important**: OAuth mode supports crawling for a single user account only. For multi-user crawling, use the service account authentication method instead.

---

## Step 1: Create OAuth Credentials in Google Cloud Console

### 1.1 Access Google Cloud Console
- Go to: https://console.cloud.google.com
- Log in with your Google account
- Select your project (or create a new one)

### 1.2 Enable Google Drive API
- Navigate to: **APIs & Services** → **Library**
- Search for: **"Google Drive API"**
- Click on it and then click **ENABLE**

### 1.3 Configure OAuth Consent Screen (First Time Only)
- Go to: **APIs & Services** → **OAuth consent screen**
- Choose **External** (unless you have Google Workspace, then you can choose Internal)
- Click **CREATE**

Fill in the required information:
- **App name**: `Vectara GDrive Crawler` (or any name you prefer)
- **User support email**: Your email address
- **Developer contact information**: Your email address
- Click **SAVE AND CONTINUE**

On the Scopes page:
- Click **SAVE AND CONTINUE** (no need to add scopes manually)

On the Test users page:
- Click **ADD USERS**
- Add your Google email address (the one that has access to Google Drive)
- Click **SAVE AND CONTINUE**

On the Summary page:
- Click **BACK TO DASHBOARD**

### 1.4 Create OAuth 2.0 Client ID
- Go to: **APIs & Services** → **Credentials**
- Click **+ CREATE CREDENTIALS** at the top
- Select **OAuth client ID**

Configure the OAuth client:
- **Application type**: Choose **Desktop app** ⚠️ (This is important!)
- **Name**: `GDrive Crawler Desktop` (or any name)
- Click **CREATE**

### 1.5 Download the Credentials File
- A popup will appear with your client ID and secret
- Click **DOWNLOAD JSON** button (download icon)
- **Save the file as**: `oauth_client_credentials.json`
- **Move it to**: `scripts/gdrive/oauth_client_credentials.json`

The downloaded file should look like this:
```json
{
  "installed": {
    "client_id": "123456789-abc123def456.apps.googleusercontent.com",
    "project_id": "your-project-name",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "GOCSPX-xxxxxxxxxxxxxxxxxxxx",
    "redirect_uris": ["http://localhost"]
  }
}
```

**Important**: Make sure it has `"installed"` at the top (not `"web"`). If it says `"web"`, you chose the wrong application type in step 1.4.

---

## Step 2: Generate OAuth Token

Now that you have the OAuth client credentials, run the token generation script:

```bash
cd /Users/adeel/vectara/vectara-ingest
python scripts/gdrive/generate_oauth_token.py
```

### What happens:
1. The script checks for `oauth_client_credentials.json` in the `scripts/gdrive` folder
2. Opens a browser window
3. You log in with your Google account (the account that has access to the Google Drive files)
4. You authorize the application
5. The token is saved to `credentials.json` in the root directory

### Authorization Flow:
- **Browser opens** with Google login page
- **"Google hasn't verified this app"** warning appears:
  - Click **Advanced**
  - Click **Go to [your app name] (unsafe)**
  - This is normal for development apps in testing mode
- **Permission request**: "See and download all your Google Drive files"
  - Click **Allow**
- **Success message**: "The authentication flow has completed"
- Browser tab can be closed

### Output:
The script creates `credentials.json` in the root directory with this structure:
```json
{
  "token": "ya29.a0AfB_by...",
  "refresh_token": "1//0gXYZ...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "123456789-abc123def456.apps.googleusercontent.com",
  "client_secret": "GOCSPX-AbCdEfGhIjKlMnOpQrStUvWx",
  "scopes": ["https://www.googleapis.com/auth/drive.readonly"]
}
```