# Box Connector Setup Guide

This guide explains how to set up and use the Box connector to download files from Box cloud storage.

## Features

- ✅ JWT authentication (recommended for enterprise apps)
- ✅ OAuth 2.0 authentication
- ✅ Download files from specific folders or entire Box account
- ✅ Recursive folder traversal
- ✅ File extension filtering
- ✅ Download-only mode (skip Vectara indexing)
- ✅ Full metadata capture

## Prerequisites

1. **Box Account**: You need a Box account with access to the files you want to download
2. **Box Developer App**: Create an app in the Box Developer Console

## Setup Instructions

### Option 1: JWT Authentication (Recommended)

JWT authentication is best for server-to-server applications and doesn't require user interaction.

#### Step 1: Create a Box App

1. Go to [Box Developer Console](https://app.box.com/developers/console)
2. Click "Create New App"
3. Choose "Custom App"
4. Choose "Server Authentication (with JWT)"
5. Give your app a name (e.g., "Vectara Ingest")

#### Step 2: Configure App Settings

1. In your app settings, navigate to "Configuration"
2. Under "Application Scopes", select:
   - ✅ Read all files and folders stored in Box
   - ✅ Write all files and folders stored in Box (if needed)
3. Under "Advanced Features", enable:
   - ✅ Generate user access tokens
4. Scroll down to "App Access Level" and select:
   - **Service Account** (for accessing content owned by the Service Account)
   - OR **App + Enterprise Access** (for accessing all content in your enterprise)

#### Step 3: Generate Keypair and Download Config

1. In "Configuration", scroll to "Add and Manage Public Keys"
2. Click "Generate a Public/Private Keypair"
3. This will download a JSON file (e.g., `box_config.json`)
4. **IMPORTANT**: Keep this file secure - it contains your private key!

#### Step 4: Authorize the App (if using Enterprise Access)

1. In Box Developer Console, copy your "Client ID"
2. In Box Admin Console (admin.box.com):
   - Go to "Enterprise Settings" > "Apps" > "Custom Apps"
   - Click "Authorize New App"
   - Paste your Client ID
   - Click "Authorize"

#### Step 5: Update Configuration

Edit `config/box-example.yaml`:

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: /path/to/your/box_config.json
  folder_ids:
    - "0"  # Root folder, or specify folder IDs
  download_path: /tmp/box_downloads
  skip_indexing: true  # Set to false when ready to index to Vectara
```

### Option 2: OAuth 2.0 Authentication

OAuth is best for applications that need to access user-specific content.

#### Step 1: Create a Box App

1. Go to [Box Developer Console](https://app.box.com/developers/console)
2. Click "Create New App"
3. Choose "Custom App"
4. Choose "User Authentication (OAuth 2.0)"
5. Give your app a name

#### Step 2: Get OAuth Tokens

You'll need to obtain an access token through the OAuth flow. You can use Box's OAuth playground or implement the flow yourself.

For testing, you can use Box's API token generator:
1. In your app's "Configuration" tab
2. Scroll to "Developer Token"
3. Click "Generate Developer Token"
4. **Note**: Developer tokens expire after 60 minutes

#### Step 3: Update Configuration

Edit `config/box-example.yaml`:

```yaml
box_crawler:
  auth_type: oauth
  client_id: YOUR_CLIENT_ID
  client_secret: YOUR_CLIENT_SECRET
  access_token: YOUR_ACCESS_TOKEN
  folder_ids:
    - "0"
  download_path: /tmp/box_downloads
  skip_indexing: true
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `auth_type` | string | `jwt` | Authentication method: `jwt` or `oauth` |
| `jwt_config_file` | string | - | Path to Box JWT config file (JWT only) |
| `client_id` | string | - | OAuth client ID (OAuth only) |
| `client_secret` | string | - | OAuth client secret (OAuth only) |
| `access_token` | string | - | OAuth access token (OAuth only) |
| `folder_ids` | list | `["0"]` | List of folder IDs to crawl (`"0"` = root) |
| `download_path` | string | `/tmp/box_downloads` | Local directory for downloads |
| `file_extensions` | list | `[]` | Filter by extension (empty = all files) |
| `max_files` | integer | `0` | Max files to download (0 = unlimited) |
| `recursive` | boolean | `true` | Recursively crawl subfolders |
| `skip_indexing` | boolean | `true` | Skip Vectara indexing (download only) |

## Finding Folder IDs

To find a Box folder ID:

1. Open the folder in Box web app
2. Look at the URL: `https://app.box.com/folder/123456789`
3. The number `123456789` is your folder ID

## Usage Examples

### Example 1: Download All Files (No Indexing)

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: /path/to/box_config.json
  folder_ids: ["0"]
  skip_indexing: true
```

Run:
```bash
python ingest.py config/box-example.yaml
```

### Example 2: Download Only PDFs from Specific Folders

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: /path/to/box_config.json
  folder_ids:
    - "123456789"
    - "987654321"
  file_extensions: [".pdf"]
  skip_indexing: true
```

### Example 3: Download and Index to Vectara

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: /path/to/box_config.json
  folder_ids: ["0"]
  skip_indexing: false  # Enable indexing
```

### Example 4: Limited Download for Testing

```yaml
box_crawler:
  auth_type: jwt
  jwt_config_file: /path/to/box_config.json
  folder_ids: ["0"]
  max_files: 10  # Only download 10 files
  recursive: false  # Don't crawl subfolders
  skip_indexing: true
```

## Installation

Install the Box SDK:

```bash
pip install boxsdk[jwt]==3.10.0
```

Or if you're using the requirements file:

```bash
pip-compile requirements.in
pip install -r requirements.txt
```

## Troubleshooting

### Error: "jwt_config_file is required"

Make sure you've set the correct path to your Box JWT config file in the YAML config.

### Error: "JWT config file not found"

Check that the file path is correct and the file exists at that location.

### Error: "OAuth authentication failed"

- Verify your client ID, secret, and access token are correct
- Check if your access token has expired (developer tokens expire after 60 minutes)
- Ensure your app has the correct scopes enabled

### Error: "Permission denied" or "Access denied"

- For JWT: Make sure your app is authorized in Box Admin Console
- For OAuth: Ensure the user has access to the folders you're trying to crawl
- Check that your app has the correct application scopes

### Files not downloading

- Check the folder IDs are correct
- Verify file extension filters aren't too restrictive
- Check `max_files` isn't set too low
- Ensure `recursive` is `true` if you want to crawl subfolders

## Metadata Captured

The connector captures the following metadata for each file:

- `source`: "Box"
- `title`: Original filename
- `file_id`: Box file ID
- `url`: Direct link to file in Box
- `size`: File size in bytes
- `created_at`: Creation timestamp
- `modified_at`: Last modification timestamp
- `created_by`: Name of user who created the file
- `modified_by`: Name of user who last modified the file

## Security Notes

1. **Keep JWT config secure**: The JWT config file contains your private key. Never commit it to version control.
2. **Use environment variables**: Consider storing sensitive values in environment variables or secrets management.
3. **Rotate tokens**: Regularly rotate OAuth tokens and JWT keys.
4. **Least privilege**: Only grant the minimum required permissions to your Box app.

## Next Steps

Once you've successfully downloaded files:

1. Set `skip_indexing: false` in your config
2. Configure your Vectara corpus settings
3. Run the ingestion to index files to Vectara
4. Set up a schedule for regular crawls

## Support

For issues or questions:
- Box SDK Documentation: https://github.com/box/box-python-sdk
- Box Developer Documentation: https://developer.box.com/
- Vectara Documentation: https://docs.vectara.com/
