#!/bin/bash

# Post-install hook for vectara-ingest
# This script will be run after the package is installed
# Output will be captured in the post-link.log file

# Create a debug log file in a location we can access
DEBUG_LOG="${PREFIX}/share/vectara-ingest/post-link-debug.log"
touch "${DEBUG_LOG}"
chmod 777 "${DEBUG_LOG}"

echo "Starting post-link script at $(date)" >> "${DEBUG_LOG}"
echo "PREFIX=${PREFIX}" >> "${DEBUG_LOG}"
echo "PATH=${PATH}" >> "${DEBUG_LOG}"
ls -la "${PREFIX}/bin" >> "${DEBUG_LOG}" 2>&1

# Get the path to Python and pip
PYTHON="${PREFIX}/bin/python"
PIP="${PREFIX}/bin/pip"

echo "Using PYTHON=${PYTHON}" >> "${DEBUG_LOG}"
echo "Using PIP=${PIP}" >> "${DEBUG_LOG}"

echo ">>> Installing Python dependencies for vectara-ingest"
echo ">>> Installing Python dependencies for vectara-ingest" >> "${DEBUG_LOG}"

# Install core requirements
echo ">>> Installing core requirements from requirements.txt"
echo ">>> Installing core requirements from requirements.txt" >> "${DEBUG_LOG}"
echo "Running: ${PIP} install --index-url https://pypi.org/simple -r ${PREFIX}/share/vectara-ingest/requirements.txt" >> "${DEBUG_LOG}"
"${PIP}" install --index-url https://pypi.org/simple -r "${PREFIX}/share/vectara-ingest/requirements.txt" >> "${DEBUG_LOG}" 2>&1
PIP_EXIT_CODE=$?
echo "pip exit code: ${PIP_EXIT_CODE}" >> "${DEBUG_LOG}"

# Install extra requirements
echo ">>> Installing extra requirements from requirements-extra.txt"
echo ">>> Installing extra requirements from requirements-extra.txt" >> "${DEBUG_LOG}"
echo "Running: ${PIP} install --index-url https://pypi.org/simple -r ${PREFIX}/share/vectara-ingest/requirements-extra.txt" >> "${DEBUG_LOG}"
"${PIP}" install --index-url https://pypi.org/simple -r "${PREFIX}/share/vectara-ingest/requirements-extra.txt" >> "${DEBUG_LOG}" 2>&1
PIP_EXTRA_EXIT_CODE=$?
echo "pip exit code: ${PIP_EXTRA_EXIT_CODE}" >> "${DEBUG_LOG}"

# Install playwright browsers
echo ">>> Installing playwright browser binaries"
echo ">>> Installing playwright browser binaries" >> "${DEBUG_LOG}"
echo "Running: ${PYTHON} -m playwright install firefox" >> "${DEBUG_LOG}"
"${PYTHON}" -m playwright install firefox >> "${DEBUG_LOG}" 2>&1 || {
    PW_EXIT_CODE=$?
    echo ">>> Warning: Failed to install Playwright browsers"
    echo "playwright exit code: ${PW_EXIT_CODE}" >> "${DEBUG_LOG}"
}

echo ">>> vectara-ingest installation completed successfully!"
echo ">>> vectara-ingest installation completed at $(date)" >> "${DEBUG_LOG}" 