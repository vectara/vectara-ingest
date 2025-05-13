#!/bin/bash

set -e

# Check if /ssl exists
if [ -d "/ssl" ]; then
    echo "Found /ssl directory. Copying contents..."

    # Recursively copy all files and folders from /ssl to the system CA cert directory
    if ! cp -r /ssl/. /usr/local/share/ca-certificates/; then
        echo "Failed to copy files from /ssl to /usr/local/share/ca-certificates/"
        exit 1
    fi

    echo "Updating CA certificates..."
    if ! update-ca-certificates; then
        echo "Failed to update CA certificates."
        exit 1
    fi

    echo "CA certificates updated successfully."
else
    echo "/ssl directory not found. Skipping CA certificate update."
fi

# Check required environment variables
if [ -z "$CONFIG" ]; then
    echo "Error: CONFIG environment variable is not set."
    exit 1
fi

if [ -z "$PROFILE" ]; then
    echo "Error: PROFILE environment variable is not set."
    exit 1
fi

# Run original command
exec /bin/bash -l -c "python3 ingest.py $CONFIG $PROFILE"