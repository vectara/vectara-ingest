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

# retrieve the crawler type from the config file
crawler_type=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['crawling']['crawler_type'])" | tr '[:upper:]' '[:lower:]'`

# Mount secrets file and other files as needed into docker container
mkdir -p ~/tmp/mount
[ -f secrets.toml ] && cp secrets.toml ~/tmp/mount
cp "$1" ~/tmp/mount/

if [[ "$crawler_type" == "gdrive" ]]; then
  [ -f credentials.json ] && cp credentials.json ~/tmp/mount
fi

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

sum_tables=`python3 -c "import yaml; print(yaml.safe_load(open('$1')).get('doc_processing', {}).get('summarize_tables', ''))" | tr '[:upper:]' '[:lower:]'`
sum_images=`python3 -c "import yaml; print(yaml.safe_load(open('$1')).get('doc_processing', {}).get('summarize_images', ''))" | tr '[:upper:]' '[:lower:]'`
mask_pii=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['vectara'].get('mask_pii', 'false'))" | tr '[:upper:]' '[:lower:]'`

if [[ "$sum_tables" == "true" || $"sum_images" == "true" || "$mask_pii" == "true" ]]; then
    echo "Building with extra features"
    tag="vectara-ingest-full"
    docker $BUILD_CMD --build-arg INSTALL_EXTRA="true" --platform linux/$ARCH . --tag="$tag:latest"
else
  tag="vectara-ingest"
  docker $BUILD_CMD --build-arg INSTALL_EXTRA="false" --platform linux/$ARCH . --tag="$tag:latest"
fi

if [ $? -eq 0 ]; then
  echo "Docker build successful."
else
  echo "Docker build failed. Please check the messages above. Exiting..."
  exit 4
fi

# remove old container if it exists
docker container inspect vingest &>/dev/null && docker rm -f vingest

# Run docker container
config_file_name="${1##*/}"
if [[ "${crawler_type}" == "folder" ]]; then
    # special handling of "folder crawler" where we need to mount the folder under /home/vectara/data
    folder=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['folder_crawler']['path'])"`
    if [ ! -d "$folder" ]; then
        echo "Error: Folder '$folder' does not exist."
        exit 6
    fi    
    docker run -d -v ~/tmp/mount:/home/vectara/env -v "$folder:/home/vectara/data" -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest $tag
elif [[ "$crawler_type" == "csv" ]]; then
    # special handling of "csv crawler" where we need to mount the csv file under /home/vectara/data
    file_path=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['csv_crawler']['file_path'])"`
    if [ ! -f "$file_path" ]; then
        echo "Error: CSV file '$file_path' does not exist."
        exit 5
    fi
    docker run -d -v ~/tmp/mount:/home/vectara/env -v "$file_path:/home/vectara/data/file" -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest $tag
elif [[ "$crawler_type" == "bulkupload" ]]; then
    # special handling of "bulkupload crawler" where we need to mount the JSON file under /home/vectara/data
    json_path=`python3 -c "import yaml; print(yaml.safe_load(open('$1'))['bulkupload_crawler']['json_path'])"`
    if [ ! -f "$file_path" ]; then
        echo "Error: CSV file '$json_path' does not exist."
        exit 5
    fi    
    docker run -d -v ~/tmp/mount:/home/vectara/env -v "$json_path:/home/vectara/data/file.json" -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest $tag
else
    docker run -d -v ~/tmp/mount:/home/vectara/env -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest $tag
fi

if [ $? -eq 0 ]; then
  echo "Success! Ingest job is running."
  echo "You can try 'docker logs -f vingest' to see the progress."
else
  echo "Ingest container failed to start. Please check the messages above."
fi