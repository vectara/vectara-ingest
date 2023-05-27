#!/bin/bash

# This script requires yq to be installed https://github.com/mikefarah/yq 
# args[1] = config file
# args[2] = secrets profile
# example: sh run.sh <config>news-bbc.yaml dev true

if [ $# -lt 2 ]; then
  echo "Missing arguments."
  echo "Usage: $0 <config-file> <secrets-profile>"
  exit 1
fi

if [ ! -f "$1" ]; then
  echo "Error: '$1' is not a valid configuration file"
  exit 2
fi

mkdir -p ~/tmp/mount
cp secrets.toml ~/tmp/mount
cp $1 ~/tmp/mount/
docker build . --tag=vectara-ingest:latest
docker container inspect vingest &>/dev/null && docker rm -f vingest

crawler_type="$(yq e '.crawling.crawler_type' $1)"
config_file_name="${1##*/}"
if [[ "$crawler_type" == "folder" ]]; then
    # special handling of "folder crawler" where we need to mount the folder under /home/vectara/data
    folder=$(yq e '.folder_crawler.path' $1)
    docker run -d --platform=linux/amd64 -v ~/tmp/mount:/home/vectara/env -v $folder:/home/vectara/data -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest vectara-ingest
else
    docker run -d --platform=linux/amd64 -v ~/tmp/mount:/home/vectara/env -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$2 --name vingest vectara-ingest
fi
echo "Ingest job is running. You can try 'docker logs -f vingest' to see the progress."