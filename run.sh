#!/bin/bash

# args[1] = config file
# args[2] = secrets profile
# example: sh run.sh <config>news-bbc.yaml dev

# Error handling with consistent exit codes
readonly ERR_MISSING_ARGS=1
readonly ERR_INVALID_CONFIG=2
readonly ERR_MISSING_SECRETS=3
readonly ERR_DOCKER_BUILD_FAILED=4
readonly ERR_MISSING_DATA_FILE=5
readonly ERR_MISSING_DATA_DIR=6
readonly ERR_MISSING_GDRIVE_CREDS=7
readonly ERR_CRAWLER_COPY_FAILED=8
readonly ERR_CUSTOM_CRAWLER_NOT_FOUND=9
readonly ERR_CRAWLER_FILENAME_MISMATCH=10
readonly ERR_CRAWLER_NOT_FOUND=11

if [[ $# -lt 2 ]]; then
  echo "Missing arguments." >&2
  echo "Usage: $0 <config-file> <secrets-profile>" >&2
  exit "$ERR_MISSING_ARGS"
fi

if [[ ! -f "$1" ]]; then
  echo "Error: '$1' is not a valid configuration file" >&2
  exit "$ERR_INVALID_CONFIG"
fi

if [[ ! -f secrets.toml ]]; then
  echo "Error: secrets.toml file does not exist, please create one following the README instructions" >&2
  exit "$ERR_MISSING_SECRETS"
fi

readonly RED='\033[0;31m'
readonly NC='\033[0m'
readonly CUSTOM_CRAWLER_DIR="crawlers/custom"

# Helper function to read YAML config values
read_yaml() {
  local key="$1"
  local default="${2:-}"
  python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE')).get('${key}', '${default}'))" 2>/dev/null || echo "$default"
}

read_yaml_nested() {
  local query="$1"
  python3 -c "import yaml; data=yaml.safe_load(open('$CONFIG_FILE')); print($query)" 2>/dev/null || echo ""
}

# Extract crawler type from config
readonly CONFIG_FILE="$1"
crawler_type=$(read_yaml_nested "data['crawling']['crawler_type'].lower()")

# Setup custom crawler if specified
setup_custom_crawler() {
  local custom_crawler
  custom_crawler=$(read_yaml_nested "data.get('vectara', {}).get('crawler_file', '')")

  [[ -z "$custom_crawler" ]] && return 0

  # Validate file exists
  if [[ ! -f "$custom_crawler" ]]; then
    echo "Error: Custom crawler file not found at '$custom_crawler'" >&2
    exit "$ERR_CUSTOM_CRAWLER_NOT_FOUND"
  fi

  local crawler_filename expected_filename
  crawler_filename=$(basename "$custom_crawler")
  expected_filename="${crawler_type}_crawler.py"

  # Validate naming convention
  if [[ "$crawler_filename" != "$expected_filename" ]]; then
    echo "Error: Crawler filename mismatch" >&2
    echo "Expected: $expected_filename" >&2
    echo "Actual: $crawler_filename" >&2
    echo "" >&2

    # Attempt to extract class name and suggest fix
    local class_name
    class_name=$(grep -oP '^class \K[A-Za-z_][A-Za-z0-9_]*(?=Crawler\(Crawler\))' "$custom_crawler" | head -1)

    if [[ -n "$class_name" ]]; then
      local suggested_type
      suggested_type=$(echo "$class_name" | tr '[:upper:]' '[:lower:]')
      echo "Found class: ${class_name}Crawler" >&2
      echo "Suggested crawler_type: $suggested_type" >&2
      echo "" >&2
      echo "Fix: Update 'crawler_type: $suggested_type' in your config" >&2
      echo "Or: Rename file to '$expected_filename'" >&2
    else
      echo "No Crawler class found in file." >&2
      echo "Fix: Rename file to '$expected_filename' or update crawler_type in config" >&2
    fi
    exit "$ERR_CRAWLER_FILENAME_MISMATCH"
  fi

  # Copy to custom directory
  mkdir -p "$CUSTOM_CRAWLER_DIR"
  if ! cp "$custom_crawler" "$CUSTOM_CRAWLER_DIR/$crawler_filename"; then
    echo "Error: Failed to copy crawler file to $CUSTOM_CRAWLER_DIR/" >&2
    exit "$ERR_CRAWLER_COPY_FAILED"
  fi
  echo "Copied custom crawler: $crawler_filename"
}

# Validate crawler file exists
validate_crawler_exists() {
  local crawler_file="${crawler_type}_crawler.py"

  if [[ -f "$CUSTOM_CRAWLER_DIR/$crawler_file" ]]; then
    return 0
  elif [[ -f "crawlers/$crawler_file" ]]; then
    return 0
  fi

  cat >&2 <<EOF
Error: Crawler file not found for crawler_type '$crawler_type'
Expected one of:
  - crawlers/$crawler_file (built-in)
  - $CUSTOM_CRAWLER_DIR/$crawler_file (custom)

Fix: Provide a custom crawler using 'crawler_file' in your config or check 'crawler_type' spelling
EOF
  exit "$ERR_CRAWLER_NOT_FOUND"
}

setup_custom_crawler
validate_crawler_exists

# Mount secrets file and other files as needed into docker container

# Build docker container
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    ARCH="amd64"
fi

# Determine the build command based on the availability of Buildx
function has_buildx() {
  docker buildx version > /dev/null 2>&1
}
if has_buildx; then
  BUILD_CMD="buildx build"
  echo "Building for $ARCH with buildx"
else
  BUILD_CMD="build"
  echo "Building for $ARCH"
fi

BUILD_ARGS=""

if [[ -n "${http_proxy}" ]]; then
  BUILD_ARGS="$BUILD_ARGS --build-arg HTTP_PROXY=\"${http_proxy}\""
fi
if [[ -n "${https_proxy}" ]]; then
  BUILD_ARGS="$BUILD_ARGS --build-arg HTTPS_PROXY=\"${https_proxy}\""
fi
if [[ -n "${no_proxy}" ]]; then
  BUILD_ARGS="$BUILD_ARGS --build-arg NO_PROXY=\"${no_proxy}\""
fi


# Read config values for extra features
sum_tables=$(read_yaml_nested "data.get('doc_processing', {}).get('summarize_tables', 'false').lower()")
sum_images=$(read_yaml_nested "data.get('doc_processing', {}).get('summarize_images', 'false').lower()")
mask_pii=$(read_yaml_nested "data.get('vectara', {}).get('mask_pii', 'false').lower()")
output_dir=$(read_yaml_nested "data.get('vectara', {}).get('output_dir', 'vectara_ingest_output')")

# Determine if extra features are needed
needs_extra_features() {
  [[ "$sum_tables" == "true" || "$sum_images" == "true" || "$mask_pii" == "true" ]]
}

if needs_extra_features; then
  tag="vectara-ingest-full"
  echo "Building with extra features (summarize_tables=$sum_tables, summarize_images=$sum_images, mask_pii=$mask_pii)"
else
  tag="vectara-ingest"
  echo "Building base image"
fi

# Build Docker image
docker_build_cmd="docker $BUILD_CMD $BUILD_ARGS --build-arg INSTALL_EXTRA=\"$(needs_extra_features && echo true || echo false)\" --platform linux/$ARCH . --tag=\"$tag:latest\""
echo "$docker_build_cmd"
eval "$docker_build_cmd"

if [[ $? -ne 0 ]]; then
  echo "Docker build failed. Please check the messages above. Exiting..." >&2
  exit "$ERR_DOCKER_BUILD_FAILED"
fi
echo "Docker build successful."

make_absolute() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    echo "$path"
  else
    echo "$(pwd)/$path"
  fi
}

sanitize_for_docker_name() {
  local filename="$1"
  local base=$(basename "$filename")     # Remove path
  base=$(echo "$base" | tr '[:upper:]' '[:lower:]')  # Lowercase
  base="${base%%.*}"                     # Remove extension

  # Replace invalid characters with underscore
  base=$(echo "$base" | sed 's/[^a-z0-9_-]/_/g')

  # Remove leading dashes
  base=$(echo "$base" | sed 's/^-*//')

  # Trim to 255 characters (Docker max)
  echo "${base:0:255}"
}

ABSOLUTE_CONFIG_PATH=`make_absolute $1`
CONFIG_NAME=`basename $1`
CONTAINER_NAME_SUFFIX=`sanitize_for_docker_name $1`
CONTAINER_NAME="vingest-${CONTAINER_NAME_SUFFIX}"

# remove old container if it exists
docker container inspect "${CONTAINER_NAME}" &>/dev/null && docker rm -f "${CONTAINER_NAME}"
DOCKER_RUN_ARGS=()
DOCKER_RUN_ARGS+=(-v "${ABSOLUTE_CONFIG_PATH}:/home/vectara/env/${CONFIG_NAME}:ro")

DOCKER_RUN_ARGS+=(-v "$(pwd)/secrets.toml:/home/vectara/env/secrets.toml:ro")

if [[ -f ca.pem ]]; then
  DOCKER_RUN_ARGS+=(-v "$(pwd)/ca.pem:/home/vectara/env/ca.pem:ro")
fi

if [[ -d ssl ]]; then
  DOCKER_RUN_ARGS+=(-v "$(pwd)/ssl:/ssl:ro")
fi

if [[ "$crawler_type" == "gdrive" ]]; then
  credentials_path=$(read_yaml_nested "data.get('gdrive_crawler', {}).get('credentials_file', 'credentials.json')")
  credentials_path="${credentials_path:-credentials.json}"

  # Expand tilde to home directory
  credentials_path="${credentials_path/#\~/$HOME}"

  if [[ ! -f "$credentials_path" ]]; then
    echo "Error: Google Drive credentials file not found at '$credentials_path'" >&2
    exit "$ERR_MISSING_GDRIVE_CREDS"
  fi

  DOCKER_RUN_ARGS+=(-v "$(realpath "$credentials_path"):/home/vectara/env/credentials.json:rw")
fi

if [[ -n "${LOGGING_LEVEL}" ]]; then
  DOCKER_RUN_ARGS+=(-e "LOGGING_LEVEL=${LOGGING_LEVEL}")
fi

if [[ -f .run-env ]]; then
  DOCKER_RUN_ARGS+=(--env-file .run-env)
fi

# Run docker container
config_file_name="${1##*/}"
case "$crawler_type" in
  folder)
    # Mount folder for folder crawler
    folder=$(read_yaml_nested "data['folder_crawler']['path']")
    if [[ ! -d "$folder" ]]; then
      echo "Error: Folder '$folder' does not exist." >&2
      exit "$ERR_MISSING_DATA_DIR"
    fi
    DOCKER_RUN_ARGS+=(-v "${folder}:/home/vectara/data")
    ;;

  csv)
    # Mount CSV file for CSV crawler
    file_path=$(read_yaml_nested "data['csv_crawler']['file_path']")
    if [[ ! -f "$file_path" ]]; then
      echo "Error: CSV file '$file_path' does not exist." >&2
      exit "$ERR_MISSING_DATA_FILE"
    fi
    file_name=$(basename "$file_path")
    DOCKER_RUN_ARGS+=(-v "${file_path}:/home/vectara/data/${file_name}")
    ;;

  bulkupload)
    # Mount JSON file for bulkupload crawler
    json_path=$(read_yaml_nested "data['bulkupload_crawler']['json_path']")
    if [[ ! -f "$json_path" ]]; then
      echo "Error: JSON file '$json_path' does not exist." >&2
      exit "$ERR_MISSING_DATA_FILE"
    fi
    DOCKER_RUN_ARGS+=(-v "${json_path}:/home/vectara/data/file.json")
    ;;
esac

# Mount output directory for persistent storage of URL reports and other output
DOCKER_RUN_ARGS+=(-v "$HOME/tmp/mount:/home/vectara/${output_dir}:rw")

DOCKER_RUN_ARGS+=(-e "CONFIG=/home/vectara/env/$config_file_name")


echo Running docker: docker run -d "${DOCKER_RUN_ARGS[@]}" -e PROFILE=$2 --name "${CONTAINER_NAME}" $tag
docker run -d "${DOCKER_RUN_ARGS[@]}" -e PROFILE=$2 --name "${CONTAINER_NAME}" $tag

if [ $? -eq 0 ]; then
  echo "Success! Ingest job is running."
  echo -e "You can try ${RED}'docker logs -f ${CONTAINER_NAME}'${NC} to see the progress."
else
  echo "Ingest container failed to start. Please check the messages above."
fi

