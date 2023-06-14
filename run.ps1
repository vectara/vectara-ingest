# Args[1] = config file
# Args[2] = secrets profile
# Example: .\run.ps1 <config>news-bbc.yaml dev

Import-Module -Name Powershell-Yaml
param(
  [Parameter(Mandatory=$true)]
  [string]$configFile,

  [Parameter(Mandatory=$true)]
  [string]$secretsProfile
)
$configFile = $Args[0]
$secretsProfile = $Args[1]

# Check if config file exists
if(!(Test-Path -Path $configFile))
{
  Write-Host "Error: '$configFile' is not a valid configuration file"
  exit 2
}

# Create necessary directories
New-Item -ItemType Directory -Path $env:USERPROFILE\tmp\mount -Force

# Copy necessary files
Copy-Item -Path .\secrets.toml -Destination $env:USERPROFILE\tmp\mount
Copy-Item -Path $configFile -Destination $env:USERPROFILE\tmp\mount

# Build docker image
docker build . --tag=vectara-ingest:latest

# Remove container if it already exists
docker container inspect vingest > $null 2>&1
if($?)
{
  docker rm -f vingest
}

# Get crawler_type
$yamlContent = ConvertFrom-Yaml (Get-Content -Raw -Path $configFile)
$crawler_type = $yamlContent.crawling.crawler_type

$config_file_name = Split-Path $configFile -Leaf

if ($crawler_type -eq "folder") {
    # Special handling of "folder crawler" where we need to mount the folder under /home/vectara/data
    $folder = $yamlContent.folder_crawler.path
    docker run -d --platform=linux/amd64 -v "$env:USERPROFILE\tmp\mount:/home/vectara/env" -v "${folder}:/home/vectara/data" -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$secretsProfile --name vingest vectara-ingest
} else {
    docker run -d --platform=linux/amd64 -v "$env:USERPROFILE\tmp\mount:/home/vectara/env" -e CONFIG=/home/vectara/env/$config_file_name -e PROFILE=$secretsProfile --name vingest vectara-ingest
}
Write-Host "Ingest job is running. You can try 'docker logs -f vingest' to see the progress."
