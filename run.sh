#!/bin/bash

# args[1] = config file
# args[2] = secrets profile
# example: sh run.sh <config>news-bbc.yaml dev

if [ $# -lt 2 ]; then
  echo "Missing arguments."
  echo "Usage: $0 <config-file> <secrets-profile>"
  exit 1
fi

if [ ! -f "$1" ]; then
  echo "Error: '$1' is not a valid configuration file"
  exit 2
fi

if [ ! -f secrets.toml ]; then
  echo "Error: secrets.toml file does not exist, please create one following the README instructions"
  exit 3
fi

RED='\033[0;31m'
NC='\033[0m'

# retrieve the crawler type from the config file
crawler_type=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['crawling']['crawler_type'])" | tr '[:upper:]' '[:lower:]'`

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


sum_tables=`python3 -c "import yaml; print(yaml.safe_load(open('$1')).get('doc_processing', {}).get('summarize_tables', ''))" | tr '[:upper:]' '[:lower:]'`
sum_images=`python3 -c "import yaml; print(yaml.safe_load(open('$1')).get('doc_processing', {}).get('summarize_images', ''))" | tr '[:upper:]' '[:lower:]'`
mask_pii=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['vectara'].get('mask_pii', 'false'))" | tr '[:upper:]' '[:lower:]'`

if [[ "$sum_tables" == "true" || $"sum_images" == "true" || "$mask_pii" == "true" ]]; then
    echo "Building with extra features"
    tag="vectara-ingest-full"
    echo "docker $BUILD_CMD $BUILD_ARGS --build-arg INSTALL_EXTRA=\"true\" --platform linux/$ARCH . --tag=\"$tag:latest\""
    docker $BUILD_CMD $BUILD_ARGS --build-arg INSTALL_EXTRA="true" --platform linux/$ARCH . --tag="$tag:latest"
else
  tag="vectara-ingest"
  echo "docker $BUILD_CMD $BUILD_ARGS --build-arg INSTALL_EXTRA=\"false\" --platform linux/$ARCH . --tag=\"$tag:latest\""
  docker $BUILD_CMD $BUILD_ARGS --build-arg INSTALL_EXTRA="false" --platform linux/$ARCH . --tag="$tag:latest"
fi

if [ $? -eq 0 ]; then
  echo "Docker build successful."
else
  echo "Docker build failed. Please check the messages above. Exiting..."
  exit 4
fi

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
ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v ${ABSOLUTE_CONFIG_PATH}:/home/vectara/env/${CONFIG_NAME}:ro"

if [[ -f secrets.toml ]]; then
  ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v ./secrets.toml:/home/vectara/env/secrets.toml:ro"
else
  echo "secrets.toml not found. Exiting"
  exit 1
fi

if [[ -f ca.pem ]]; then
  ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v ./ca.pem:/home/vectara/env/ca.pem:ro"
fi

if [[ -d ssl ]]; then
  ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v ./ssl:/ssl:ro"
fi

if [[ "$crawler_type" == "gdrive" ]]; then
  if [[ -f credentials.json ]]; then
    ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v ./credentials.json:/home/vectara/env/credentials.json:ro"
  fi
fi

if [[ -n "${LOGGING_LEVEL}" ]]; then
  ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -e LOGGING_LEVEL=${LOGGING_LEVEL}"
fi

# Run docker container
config_file_name="${1##*/}"
if [[ "${crawler_type}" == "folder" ]]; then
    # special handling of "folder crawler" where we need to mount the folder under /home/vectara/data
    folder=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['folder_crawler']['path'])"`
    if [ ! -d "$folder" ]; then
        echo "Error: Folder '$folder' does not exist."
        exit 6
    fi
    ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v $folder:/home/vectara/data"

elif [[ "$crawler_type" == "csv" ]]; then
    # special handling of "csv crawler" where we need to mount the csv file under /home/vectara/data
    file_path=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['csv_crawler']['file_path'])"`
    if [ ! -f "$file_path" ]; then
        echo "Error: CSV file '$file_path' does not exist."
        exit 5
    fi
    ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v $file_path:/home/vectara/data/file"

elif [[ "$crawler_type" == "bulkupload" ]]; then
    # special handling of "bulkupload crawler" where we need to mount the JSON file under /home/vectara/data
    json_path=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['bulkupload_crawler']['json_path'])"`
    if [ ! -f "$json_path" ]; then
        echo "Error: JSON file '$json_path' does not exist."
        exit 5
    fi
    ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -v $json_path:/home/vectara/data/file.json"
fi
ADDITIONAL_DOCKER_FLAGS="${ADDITIONAL_DOCKER_FLAGS} -e CONFIG=/home/vectara/env/$config_file_name"


echo Running docker: docker run -d ${ADDITIONAL_DOCKER_FLAGS} -e PROFILE=$2 --name "${CONTAINER_NAME}" $tag
docker run -d ${ADDITIONAL_DOCKER_FLAGS} -e PROFILE=$2 --name "${CONTAINER_NAME}" $tag

if [ $? -eq 0 ]; then
  echo "Success! Ingest job is running."
  echo -e "You can try ${RED}'docker logs -f ${CONTAINER_NAME}'${NC} to see the progress."
else
  echo "Ingest container failed to start. Please check the messages above."
fi