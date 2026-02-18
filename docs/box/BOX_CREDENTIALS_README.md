# Box Credentials Setup

This guide explains how to manage Box credentials securely for the vectara-ingest Box crawler.

## Quick Start

You have **two credential files** in your project:

### 1. `box_oauth_credentials.json` (Current - OAuth)
**Status:** ✅ Already created with your credentials
**Location:** `/Users/adeel/vectara/vectara-ingest/box_oauth_credentials.json`

This file contains your OAuth credentials and is ready to use.

**⚠️ Important:**
- This file is already in `.gitignore` and won't be committed to git
- OAuth tokens expire (typically 60 minutes for developer tokens)
- Good for testing, but for production use JWT instead

### 2. `box_config.json` (Future - JWT - Recommended)
**Status:** ⏳ Not yet created (see setup below)
**Template:** `box_config.json.example`

JWT authentication is more secure and doesn't expire. Set it up when ready for production.

---

## Current Setup (OAuth)

Your Box connector is configured to use OAuth with credentials from `box_oauth_credentials.json`.

### Config file location:
`config/box-adeel.yaml`

### To run:
```bash
./run.sh config/box-adeel.yaml default
```

### Monitor logs:
```bash
docker logs -f vingest-box-adeel
```

---

## File Structure

```
vectara-ingest/
├── box_oauth_credentials.json         # ← Your OAuth credentials (gitignored)
├── box_config.json.example            # ← Template for JWT config
├── config/
│   ├── box-adeel.yaml                 # ← Your config (using OAuth)
│   └── box-example.yaml               # ← Example config
├── crawlers/
│   ├── box_crawler.py                 # ← Box crawler code
│   └── BOX_SETUP.md                   # ← Detailed setup guide
└── .gitignore                          # ← Protects credential files
```

---

## Switching to JWT Authentication (Recommended for Production)

### Why JWT?
- ✅ Tokens don't expire
- ✅ More secure for automated workflows
- ✅ Supports enterprise-wide access
- ✅ No need to regenerate tokens

### Setup Steps:

1. **Create Box JWT App:**
   - Go to https://app.box.com/developers/console
   - Create new app → Custom App → Server Authentication (JWT)
   - Configure scopes and set "App + Enterprise Access"
   - Generate keypair and download the JSON file

2. **Save the JWT config:**
   ```bash
   # Save the downloaded file as box_config.json
   mv ~/Downloads/*_config.json box_config.json
   ```

3. **Authorize the app (required for admin access):**
   - Go to https://app.box.com/master/settings/custom
   - Authorize New App → Enter your Client ID → Authorize

4. **Update your config:**
   Edit `config/box-adeel.yaml`:
   ```yaml
   box_crawler:
     auth_type: jwt
     jwt_config_file: box_config.json
   ```

5. **Run it:**
   ```bash
   ./run.sh config/box-adeel.yaml default
   ```

See `crawlers/BOX_SETUP.md` for detailed instructions.

---

## Credential File Formats

### OAuth Credentials (`box_oauth_credentials.json`):
```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "access_token": "your_access_token"
}
```

### JWT Config (`box_config.json`):
```json
{
  "boxAppSettings": {
    "clientID": "...",
    "clientSecret": "...",
    "appAuth": {
      "publicKeyID": "...",
      "privateKey": "-----BEGIN ENCRYPTED PRIVATE KEY-----\n...",
      "passphrase": "..."
    }
  },
  "enterpriseID": "..."
}
```

---

## Security Best Practices

### ✅ DO:
- Keep credential files in `.gitignore` (already configured)
- Use JWT for production/automated workflows
- Regularly rotate OAuth tokens
- Use separate credentials for dev/staging/prod
- Store sensitive files outside the project directory when possible

### ❌ DON'T:
- Commit credential files to git
- Share credentials in chat/email
- Use the same credentials across multiple environments
- Put credentials directly in config files (use credential files instead)

---

## Troubleshooting

### "OAuth credentials file not found"
**Solution:** Check the path in your config. The path is relative to the project root:
```yaml
oauth_credentials_file: box_oauth_credentials.json  # ✅ Correct (relative to project root)
# NOT: ./config/box_oauth_credentials.json  # ❌ Wrong
```

### "JWT config file not found"
**Solution:** Make sure you downloaded the JWT config from Box Developer Console and saved it as `box_config.json` in the project root.

### "Authentication failed" / "Invalid token"
**Solution:** Your OAuth token expired. Options:
1. Generate a new developer token from Box Developer Console
2. Update `box_oauth_credentials.json` with the new token
3. Or switch to JWT (recommended)

### Token expired after 60 minutes
**Solution:** Developer tokens expire quickly. For long-term use:
1. Implement full OAuth flow with refresh tokens (complex)
2. Or switch to JWT authentication (easier, recommended)

---

## What's Protected by .gitignore

These files are automatically ignored by git:
- `box_config.json`
- `box_oauth_credentials.json`
- `.box_credentials.json`

You can safely create and use these files without worrying about accidentally committing them.

---

## Getting Help

- **Detailed Setup:** See `crawlers/BOX_SETUP.md`
- **Box SDK Docs:** https://github.com/box/box-python-sdk
- **Box Developer Docs:** https://developer.box.com/
- **Vectara Docs:** https://docs.vectara.com/

---

## Current Status Summary

✅ **OAuth credentials file created:** `box_oauth_credentials.json`
✅ **Config updated:** `config/box-adeel.yaml`
✅ **Gitignore updated:** Credential files are protected
✅ **Ready to run:** `./run.sh config/box-adeel.yaml default`

⏳ **Next step:** Switch to JWT for production (see above)
