#!/usr/bin/env python3
"""Google Drive OAuth Token Generator.

This script generates OAuth 2.0 credentials for the Google Drive crawler by running
an interactive authorization flow. It opens a browser for user authorization and
saves the resulting token to credentials.json.

Prerequisites:
    - OAuth client credentials file from Google Cloud Console
    - File must be placed as 'oauth_client_credentials.json' in scripts/gdrive/

Usage:
    python scripts/gdrive/generate_oauth_token.py

For detailed setup instructions, see: docs/gdrive-oauth-setup.md
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

from google_auth_oauthlib.flow import InstalledAppFlow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SCRIPT_DIR = Path(__file__).resolve().parent
OAUTH_CLIENT_CREDENTIALS = SCRIPT_DIR / "oauth_client_credentials.json"
OUTPUT_TOKEN_FILE = SCRIPT_DIR.parent.parent / "credentials.json"


class OAuthTokenGenerator:
    """Handles OAuth token generation for Google Drive API."""

    def __init__(self, credentials_path: Path, output_path: Path):
        """Initialize the token generator.

        Args:
            credentials_path: Path to OAuth client credentials file
            output_path: Path where the generated token will be saved
        """
        self.credentials_path = credentials_path
        self.output_path = output_path

    def validate_credentials_file(self) -> None:
        """Validate the OAuth client credentials file.

        Raises:
            FileNotFoundError: If credentials file doesn't exist
            ValueError: If credentials file format is invalid
        """
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"OAuth client credentials file not found at:\n"
                f"{self.credentials_path}\n\n"
                f"Please download OAuth credentials from Google Cloud Console:\n"
                f"1. Go to: https://console.cloud.google.com/apis/credentials\n"
                f"2. Create OAuth 2.0 Client ID (Application type: Desktop app)\n"
                f"3. Download the JSON file\n"
                f"4. Save it as: {self.credentials_path}\n\n"
                f"For detailed instructions, see: docs/gdrive-oauth-setup.md"
            )

        try:
            with open(self.credentials_path, 'r') as f:
                creds_data = json.load(f)

            if "installed" not in creds_data:
                raise ValueError(
                    "Invalid credentials file format.\n\n"
                    "The file should have an 'installed' key (Desktop app type).\n"
                    "Make sure you created 'Desktop app' OAuth credentials, "
                    "not 'Web application'."
                )

            logger.info("✓ Valid OAuth client credentials file")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in credentials file: {e}")

    def run_authorization_flow(self) -> Dict[str, Any]:
        """Run the OAuth authorization flow.

        Returns:
            Dictionary containing OAuth token data

        Raises:
            Exception: If authorization flow fails
        """
        logger.info("Starting OAuth authorization flow...")
        logger.info("")
        logger.info("A browser window will open. Please:")
        logger.info("  1. Log in with your Google account")
        logger.info("  2. Click 'Advanced' if you see a warning")
        logger.info("  3. Click 'Go to [app name] (unsafe)'")
        logger.info("  4. Click 'Allow' to grant permissions")
        logger.info("")

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                SCOPES
            )
            creds = flow.run_local_server(port=0)

            logger.info("✓ Authorization successful!")

            return {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes
            }

        except Exception as e:
            logger.error(f"Authorization flow failed: {e}")
            logger.error("")
            logger.error("Common issues:")
            logger.error("  - Browser didn't open? Check firewall settings")
            logger.error("  - Access denied? Make sure you clicked 'Allow'")
            logger.error("  - API not enabled? Enable Google Drive API in Cloud Console")
            raise

    def save_token(self, token_data: Dict[str, Any]) -> None:
        """Save the OAuth token to file.

        Args:
            token_data: Dictionary containing OAuth token information

        Raises:
            IOError: If unable to write token file
        """
        try:
            with open(self.output_path, 'w') as f:
                json.dump(token_data, f, indent=2)

            logger.info("")
            logger.info("=" * 70)
            logger.info("✓ SUCCESS!")
            logger.info("=" * 70)
            logger.info("")
            logger.info(f"OAuth token saved to: {self.output_path}")
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Your credentials.json is ready to use")
            logger.info("  2. Run: sh run.sh config/vectara-gdrive-oauth.yaml default")
            logger.info("")
            logger.info("Note: The token will be automatically refreshed when it expires.")

        except IOError as e:
            raise IOError(f"Failed to save token file: {e}")

    def generate(self) -> None:
        """Execute the complete token generation process."""
        logger.info("=" * 70)
        logger.info("Google Drive OAuth Token Generator")
        logger.info("=" * 70)
        logger.info("")

        try:
            # Validate credentials file
            self.validate_credentials_file()

            # Run authorization flow
            token_data = self.run_authorization_flow()

            # Save token
            self.save_token(token_data)

        except (FileNotFoundError, ValueError) as e:
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            sys.exit(1)


def main():
    """Main entry point for the script."""
    generator = OAuthTokenGenerator(
        credentials_path=OAUTH_CLIENT_CREDENTIALS,
        output_path=OUTPUT_TOKEN_FILE
    )
    generator.generate()


if __name__ == "__main__":
    main()
