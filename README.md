<h1 align="center">Welcome to vectara-ingest</h1>
<p align="center">
  <img alt="logo" src="img/project-logo.png" height="122"/>
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

Crawl datasets and ingest them into Vectara using pre-built crawlers or by building your own. With Vectara’s [APIs](https://docs.vectara.com/docs/) you can create conversational experiences with your data, such as chatbots, semantic search, and workplace search.

`vectara-ingest` is an open source Python project that demonstrates how to crawl datasets and ingest them into Vectara. It provides a step-by-step guide on building your own crawler, as well as pre-built crawlers for ingesting data from sources such as: websites, RSS feeds, Jira, Notion, Docusaurus and more.

## QuickStart Guide

Let’s create a basic crawler to scrape content from [Paul Graham's website](http://www.paulgraham.com/index.html), and ingest it into Vectara. This guide assumes you’ve already signed up for a free Vectara account, created a corpus to contain your data, and created an API key with write-access to this corpus.

1. <b>Install dependencies</b>

Install [python >= 3.8](https://www.python.org/downloads/) if it's not already installed.

Install [yq](https://github.com/mikefarah/yq ):
   - Mac: `brew install yq`
   - Linux: `snap install yq`

Install [Docker](https://docs.docker.com/engine/install/)

Clone this repository:

  `git clone https://github.com/vectara/vectara-ingest.git`

2. <b>Configure the crawler</b>

Duplicate the `secrets.example.toml` file and rename the copy to `secrets.toml`.

Edit the `secrets.toml` file and change the `api_key` value to be your Vectara API Key.

Since the Paul Graham does not have a standard sitemap as a website, to crawl the content you’ll create a new crawler based on the pre-built RSS crawler, using the [RSS feed](http://www.paulgraham.com/rss.html) built by Aaron Swartz . You can do this by looking inside the `config` directory, duplicating the `news-bbc.yaml` config file, and renaming it to `pg-rss.yaml`.

Edit the pg-search.yaml file and make the following changes:
- Change the <b>corpus_id</b> value to the ID of the corpus into which you want to ingest the content of the website.
- Change the <b>account_id</b> value to the ID of your account. You can click on your username in the top-right corner to copy it to your clipboard.
- Change the <b>source</b> to `pg`
- Change the <b>rss_pages</b> to ["http://www.aaronsw.com/2002/feeds/pgessays.rss"]
- Change <b>days_past</b> to 365

3. <b>Run the crawler</b>

Execute the run script from the root directory using your config file to tell it what to crawl and where to ingest the data, and assigning the “default” profile from your secrets file:

  `bash run.sh config/pg-rss.yaml default`

The crawler executes inside of a [Docker container](https://www.docker.com/resources/what-container/) to protect your system’s resources and make it easier to move your crawlers to the cloud. This is a good time to grab a coffee or snack – the container needs to install a lot of dependencies, which will take some time.

When the container is set up, the process will exit and you’ll be able to track your crawler’s progress:

  `docker logs -f vingest`

4. <b>Done!</b>

Your crawler has ingested data into your Vectara corpus, and now you can build applications that query it!
Or try out some sample queries with the Vectara Console ("search" tab). One of my favoriates is "what is a maker schedule?"

## Code Organization

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


## Crawling
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

### Indexer Class
The `Indexer` class provides useful functionality to index documents into Vectara. 

<b>Methods</b>

<b>`index_url()`</b> 
This is probably the most useful method. It takes a URL as input and extracts the content from that URL (using the `playwright` and `unstructured` libraries), then sends that content to Vectara using the standard indexing API. If the URL points to a PDF document, special care is taken to ensure proper processing.

<b>`index_file()`</b>
Use this when you have a file that you want to index using Vectara's file_uplaod [API](https://docs.vectara.com/docs/indexing-apis/file-upload), so that it takes care of format identification, segmentation of text and indexing. 

<b>`index_document()` and `index_segments()`</b>
Use thesewhen you build the `document` JSON structure directly and want to index this document in the Vectara corpus.

<b>Parameters</b>
Specifically, the `reindex` parameter determines whether an existing document should be reindexed or not. If reindexing is required, the code automatically takes care of that by calling `delete_doc()` to first remove the document from the corpus and then sends it to the corpus index.

## Deployment
### Docker

The project is designed to be used within a Docker container, so that a crawl job can be run anywhere - on a local machine or on any cloud machine. see [Dockerfile](https://github.com/vectara/vectara-ingest/blob/main/Dockerfile) for more information on the Docker file structure and build.


### Local deployment
To run `vectara-ingest` locally, perform the following steps:
1. Make sure you have [Docker installed](https://docs.docker.com/engine/install/) on your machine. 
2. Clone this repo into a local folder using `git clone https://github.com/vectara/vectara-ingest.git`
3. Enter the folder by `cd vectara-ingest`
4. Choose the configuration file for your project and run `bash run.sh config/<config-file>.yaml <profile>`. This command creates the Docker container locally, configures it with the parameters specified in your configuration file (with secrets taken from the appropriate `<profile>` in `secrets.toml`), and starts up the Docker container. 

### Cloud deployment
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

- Website: [vectara.com](https://vectara.com)
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
