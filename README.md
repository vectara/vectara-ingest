<h1 align="center">Welcome to vectara-ingest</h1>
<p align="center">
  <img alt="logo" src="img/project-logo.png" height="244"/>
</p>

<p>
  <img alt="Version" src="https://img.shields.io/badge/version-1.1-blue.svg?cacheSeconds=2592000" />
  <a href="https://github.com/vectara/vectara-ingest#readme" target="_blank">
    <img alt="Documentation" src="https://img.shields.io/badge/documentation-yes-brightgreen.svg" />
  </a>
  <a href="https://github.com/vectara/vectara-ingest/graphs/commit-activity" target="_blank">
    <img alt="Maintenance" src="https://img.shields.io/badge/Maintained%3F-yes-green.svg" />
  </a>
  <a href="https://twitter.com/vectara" target="_blank">
    <img alt="Twitter: vectara" src="https://img.shields.io/twitter/follow/vectara.svg?style=social" />
  </a>
</p>

## About

`vectara-ingest` is an open source project that demonstrates how to crawl datasets and ingest them into [Vectara](https://www.vectara.com).
Written in Python, the project includes several types of crawlers like website, RSS, Jira, Notion, or docusarurus, and you can add your own crawler very easily to handle other data sources. 

With `vectara-ingest` you can quickly and easily setup a process to regularly crawl and ingest data into your Vectara corpus, supporting LLM-poweree applications and use cases like conversational AI, chatbot, semantic search and workplace search.


## Prerequisites

- python >= 3.8
- yq package

## QuickStart Guide

Let's start with a quick example - we want to run a crawl job for a website www.example.com.

1. Install [python >= 3.8](https://www.python.org/downloads/) if it's not already installed.
2. Install `yq`:
   - for Mac: `brew install yq`
   - for Linux: `snap install yq`
3. Make sure you have [Docker installed](https://docs.docker.com/engine/install/) on your machine. 
4. Clone this repo into a local folder using `git clone https://github.com/vectara/vectara-ingest.git`
4. Enter the folder by `cd vectara-ingest`
5. Create a `secrets.toml` file by copying the `secrets.example.toml`.
6. Fill in the appropriate Vectara API key in `secrets.toml`.
7. Create a configuration file for your crawl-job: `cp config/vectara-website-search.yaml config/my-config.yaml`, and then edit that file with the correct `corpus_id`, `account_id` and replace `urls` with `[https://www.example.com]`.
8. Choose the configuration file for your project and run `bash run.sh config/my-config.yaml default`. This command creates the Docker container locally, configures it with the parameters specified in your configuration file (with secrets taken from the "default" profile in `secrets.toml`), and starts up the Docker container. 
9. Track progress of the job with `docker logs -f vingest`

## Structure of the Repository

The codebase includes the following components:

1. `core` folder: core `vectara-ingest` code
   - `ingest.py`: the main entry point for a crawl job. 
   - `indexer.py`: defines the `Indexer` class which implements helpful methods to index data into Vectara such as `index_url`, `index_file()` and `index_document()`. 
   - `crawler.py`: defines the `Crawler` class which implements a base class for crawling, where each specific crawler should implement the `crawl()` method specific to its type.
   - `pdf_convert.py`: helper class to convert URLs into local PDF documents.
   - `utils.py`: some utility functions used by the other code.
2. `crawlers` folder: includes implementations of the various specific crawlers
3. `config` folder: includes example YAML configuration files for various crawling jobs.
4. `run.sh`: the main shell script to execute when you want to launch a crawl job (see below for more details).
5. `Dockerfile`: defines the Docker container image.

### Configuration

To crawl and index a source you run a crawl "job", which is controlled by several paramters that you can define in a YAML configuration file. You can see example configuration files in the <a href='https://github.com/vectara/vectara-ingest/tree/main/config' target="_blank">config</a> folder.

Each configuration YAML file includes a set of standard variables, for example:

```yaml
vectara:
  # the corpus ID for indexing
  corpus_id: 4
  # the Vectara customer ID
  customer_id: 1234567
  # flag: should vectara-ingest reindex if document already exists
  reindex: false

crawling:
  # type of crawler; valid options are website, docusaurus, notion, jira, rss, mediawiki, discourse, github and others (this continues to evolve as new crawler types are added)
  crawler_type: XXX
```

Following that, where needed, the same YAML configuration file will include crawler-specific section with crawler-specific parameters (see [about crawlers](crawlers/CRAWLERS.md)):

```yaml
XXX_crawler:
  # specific parameters for the crawler XXX
```

### Secrets management
We use a `secrets.toml` file to hold secret keys and parameters. You need to create this file in the main repository folder before running a crawl job. The TOML file can hold multiple "profiles", and specific specific secrets for each of these profiles. For example:

```
[profile1]
auth_url="https://vectara-prod-<CUSTOMER-ID>.auth.us-west-2.amazoncognito.com"
api_key="<VECTAR-API-KEY-1>

[profile2]
auth_url="https://vectara-prod-<CUSTOMER-ID>.auth.us-west-2.amazoncognito.com"
api_key="<VECTARA-API-KEY-2>"

[profile3]
auth_url="https://vectara-prod-<CUSTOMER-ID>.auth.us-west-2.amazoncognito.com"
api_key="<VECTARA-API-KEY-3>"
MOTION_API_KEY="<YOUR-NOTION-API-KEY>
```

This allows easy secrets management when you have multiple crawl jobs that may not share the same secrets. For example when you have a different Vectara API key for indexing differnet corpora.
Many of the crawlers have their own secrets, for example Notion, Discourse, Jira, or GitHub. These are also kept in the secrets file in the appropriate section and need to be all upper case (e.g. `NOTION_API_KEY` or `JIRA_PASSWORD`).

### About the Indexer Class
The `Indexer` class provides useful functionality to index documents into Vectara. 
- `index_url()` is probably the most useful method. It takes a `url` as input and extract the content from that URL (using the `playwright` and `unstructured` libraries), then sends that content to Vectara using the standard indexing API. If the url points to a PDF document, special care is taken to ensure proper processing.
- `index_file()` is useful when you have a file that you want to index using Vectara's file_uplaod [API](https://docs.vectara.com/docs/indexing-apis/file-upload), so that it takes care of format identification, segmentation of text and indexing. 
- `index_document()` and `index_segments()` are commonly used when you build the `document` JSON structure directly and want to index this document in the Vectara corpus.

the `reindex` parameter determines whether an existing document should be reindexed or not. If reindexing is required, the code automatically takes care of that by calling `delete_doc()` to first remove the document from the corpus and then sends it to the corpus index.

### Docker

The project is designed to be used within a Docker container, so that a crawl job can be run anywhere - on a local machine or on any cloud machine. see [Dockerfile](https://github.com/vectara/vectara-ingest/blob/main/Dockerfile) for more information on the Docker file structure and build.


### How to run locally
To run `vectara-ingest` locally, perform the following steps:
1. Make sure you have [Docker installed](https://docs.docker.com/engine/install/) on your machine. 
2. Clone this repo into a local folder using `git clone https://github.com/vectara/vectara-ingest.git`
3. Enter the folder by `cd vectara-ingest`
4. Choose the configuration file for your project and run `bash run.sh config/<config-file>.yaml <profile>`. This command creates the Docker container locally, configures it with the parameters specified in your configuration file (with secrets taken from the appropriate `<profile>` in `secrets.toml`), and starts up the Docker container. 

### How to run on a cloud platform
`vectara-ingest` can be easily deployed on any cloud platform such as AWS, Azure or GCP.
1. Create your configuration file for the project under the *`config`* folder
2. Run `docker build . --tag=vectara-ingest:latest` to generate the docker container
3. Push the docker to the cloud specific docker container registry:
   - For AWS, follow the instructions [here](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/docker-basics.html)
   - For Azure follow the instructions [here](https://learn.microsoft.com/en-us/azure/container-apps/get-started-existing-container-image-portal?pivots=container-apps-private-registry)
   - For GCP, follow the instructions [here](https://cloud.google.com/run/docs/quickstarts/build-and-deploy)
4. Launch the container on a VM instance based on the docker image now hosted in your cloud environment

## Author

👤 **Vectara**

- Website: [vectara.com](https://www.vectara.com)
- Twitter: [@vectara](https://twitter.com/vectara)
- GitHub: [@vectara](https://github.com/vectara)
- LinkedIn: [@vectara](https://www.linkedin.com/company/vectara/)

## 🤝 Contributing

Contributions, issues and feature requests are welcome and appreciated!<br />
Feel free to check [issues page](https://github.com/vectara/vectara-ingest/issues). You can also take a look at the [contributing guide](https://github.com/vectara/vectara-ingest/blob/master/CONTRIBUTING.md).

## Show your support

Give a ⭐️ if this project helped you!

## 📝 License

Copyright © 2023 [Vectara](https://github.com/vectara).<br />
This project is [Apache 2.0](https://github.com/vectara/vectara-ingest/blob/master/LICENSE) licensed.
