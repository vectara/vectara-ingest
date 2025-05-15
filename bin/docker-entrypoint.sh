#!/bin/bash

set -e

if [ -d "/ssl" ]; then
    echo "Found /ssl directory. Checking for .crt files..."
    CRT_FILES=$(find /ssl -type f -name "*.crt")
    if [ -n "$CRT_FILES" ]; then
        echo "Found .crt files:"
        for crt_file in $CRT_FILES; do
            echo "  $crt_file"
            dest_dir="/usr/local/share/ca-certificates$(dirname "$crt_file" | sed 's|^/ssl||')"
            mkdir -p "$dest_dir"
            echo "Copying $crt_file to $dest_dir/"
            if ! cp "$crt_file" "$dest_dir/"; then
                echo "Failed to copy $crt_file"
                exit 1
            fi
        done

        echo "Updating CA certificates..."
        if ! update-ca-certificates; then
            echo "Failed to update CA certificates."
            exit 1
        fi
        echo "CA certificates updated successfully."
        echo
    fi
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

python3 --version
echo "Starting Vectara Ingest"

# Run original command
exec /bin/bash -l -c "python3 ingest.py $CONFIG $PROFILE"