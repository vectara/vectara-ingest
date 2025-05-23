#!/bin/bash

# Post-install hook for vectara-ingest
# This script will be run after the package is installed
# Output will be captured in the post-link.log file

echo ">>> Installing Python dependencies for vectara-ingest"

# Install core requirements
echo ">>> Installing core requirements from requirements.txt"
"${PREFIX}/bin/pip" install --index-url https://pypi.org/simple -r "${PREFIX}/share/vectara-ingest/requirements.txt"

# Install extra requirements
echo ">>> Installing extra requirements from requirements-extra.txt"
"${PREFIX}/bin/pip" install --index-url https://pypi.org/simple -r "${PREFIX}/share/vectara-ingest/requirements-extra.txt"

# Install playwright browsers
echo ">>> Installing playwright browser binaries"
"${PREFIX}/bin/python" -m playwright install firefox || echo ">>> Warning: Failed to install Playwright browsers"

echo ">>> vectara-ingest installation completed successfully!" 