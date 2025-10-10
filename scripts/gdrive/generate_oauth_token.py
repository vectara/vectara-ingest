#!/usr/bin/env python3
"""
Google Drive OAuth Token Generator

This script generates an OAuth token for the Google Drive crawler.
It will open a browser window for authorization and save the token to credentials.json.

Prerequisites:
- OAuth client credentials JSON file (download from Google Cloud Console)
- Place the file as 'oauth_client_credentials.json' in the scripts/gdrive directory
"""

from google_auth_oauthlib.flow import InstalledAppFlow
import json
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_CLIENT_CREDENTIALS = os.path.join(SCRIPT_DIR, "oauth_client_credentials.json")
OUTPUT_TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "credentials.json")

def main():
    print("=" * 70)
    print("Google Drive OAuth Token Generator")
    print("=" * 70)
    print()

    # Check if client credentials file exists
    if not os.path.exists(OAUTH_CLIENT_CREDENTIALS):
        print(f"❌ Error: OAuth client credentials file not found!")
        print(f"   Expected location: {OAUTH_CLIENT_CREDENTIALS}")
        print()
        print("Please follow these steps:")
        print("1. Go to: https://console.cloud.google.com/apis/credentials")
        print("2. Create OAuth 2.0 Client ID (Application type: Desktop app)")
        print("3. Download the JSON file")
        print(f"4. Save it as: {OAUTH_CLIENT_CREDENTIALS}")
        print()
        print("For detailed instructions, see: docs/gdrive-oauth-setup.md")
        print()
        sys.exit(1)

    print(f"✓ Found OAuth client credentials")
    print()

    # Validate credentials file format
    try:
        with open(OAUTH_CLIENT_CREDENTIALS, 'r') as f:
            creds_data = json.load(f)

        if "installed" not in creds_data:
            print("❌ Error: Invalid credentials file format!")
            print()
            print("The file should have an 'installed' key (Desktop app type).")
            print("Make sure you created 'Desktop app' OAuth credentials, not 'Web application'.")
            print()
            sys.exit(1)

        print("✓ Valid OAuth client credentials file")
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON format: {e}")
        sys.exit(1)

    print()
    print("Starting OAuth authorization flow...")
    print()
    print("A browser window will open. Please:")
    print("  1. Log in with your Google account")
    print("  2. Click 'Advanced' if you see a warning")
    print("  3. Click 'Go to [app name] (unsafe)'")
    print("  4. Click 'Allow' to grant permissions")
    print()

    try:
        # Run the OAuth flow
        flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_CREDENTIALS, SCOPES)
        creds = flow.run_local_server(port=0)

        print()
        print("✓ Authorization successful!")
        print()

        # Save the token
        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }

        with open(OUTPUT_TOKEN_FILE, 'w') as f:
            json.dump(token_data, f, indent=2)

        print("=" * 70)
        print("✓ SUCCESS!")
        print("=" * 70)
        print()
        print(f"OAuth token saved to: {OUTPUT_TOKEN_FILE}")
        print()
        print("Next steps:")
        print("  1. Your credentials.json is ready to use")
        print("  2. Run the crawler with: sh run.sh config/vectara-gdrive-oauth.yaml default")
        print()
        print("Note: The token will be automatically refreshed when it expires.")
        print()

    except Exception as e:
        print()
        print("=" * 70)
        print("❌ Error occurred:")
        print("=" * 70)
        print(str(e))
        print()
        print("Common issues:")
        print("  - Browser didn't open? Try a different port or check firewall")
        print("  - Access denied? Make sure you clicked 'Allow'")
        print("  - API not enabled? Enable Google Drive API in Cloud Console")
        print()
        sys.exit(1)

if __name__ == "__main__":
    main()
