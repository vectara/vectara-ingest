<h1 align="center">Welcome to vectara-ingest</h1>
<p align="center">
  <img style="max-width: 100%;" alt="logo" src="img/project-logo.png"/>
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

# About `vectara-ingest`
This project allows you to crawl datasets and ingest them into Vectara by using pre-built or custom crawlers. You can use Vectara’s [APIs](https://docs.vectara.com/docs/) to create conversational experiences&mdash;such as chatbots, semantic search, and workplace search&mdash;from your data.

For more information about this repository, see [Code Organization](#code-organization) and [Crawling](#crawling).

`vectara-ingest` is an open source Python project that demonstrates how to crawl datasets and ingest them into Vectara. It provides a step-by-step guide on building your own crawler and some pre-built crawlers for ingesting data from sources such as:

* Websites
* RSS feeds
* Jira tickets
* Notion notes
* Docusaurus documents

# Getting Started Guide
This guide explains how to create a basic crawler to scrape content from [Paul Graham's website](http://www.paulgraham.com/index.html), and ingest it into Vectara.

## Prerequisites
* [Free Vectara account](https://console.vectara.com/signup)
* Created data corpus
* [API key](https://docs.vectara.com/docs/api-keys)
* Write access to the corpus
* [Python 3.8 (or higher)](https://www.python.org/downloads/)
* [pyyaml](https://pypi.org/project/PyYAML/) - install with: `pip install pyyaml`
* [Docker](https://docs.docker.com/engine/install/)

## Step 1: Clone the `vectara-ingest` repository
This section explains how to clone the `vectara-ingest` repository to your machine.

### On Linux
Open a terminal session and clone the repository to a directory on your machine:

```bash
git clone https://github.com/vectara/vectara-ingest.git
```

### On Windows
1. Open a Windows PowerShell terminal.
  
1. Update your Windows Subsystem for Linux (WSL):

   ```bash
   wsl --update
   ```
   
1. Ensure that WSL has the correct version of Linux:

   ```bash
   wsl --install ubuntu-20.04
   ```
   
1. Open your Linux terminal and clone the repository to a directory on your machine:

   ```bash
   git clone https://github.com/vectara/vectara-ingest.git
   ```

## Step 2: Configure the crawler
For our example we would index the content of https://www.paulgraham.com website to Vectara. Since this website does not provide a sitemap, but does provide an [RSS feed](http://www.paulgraham.com/rss.html), we will use the vectara-ingest RSS crawler instead.

1. Navigate to the directory that you have cloned.

2. Copy the `secrets.example.toml` to `secrets.toml`.

3. In the `secrets.toml` file, change `api_key` to the Vectara API Key.

   To retrieve your API key from the Vectara console, click **API Access > API Keys**.

4. In the `config/` directory, copy the `news-bbc.yaml` config file to `pg-rss.yaml`.

5. Edit the `pg-rss.yaml` file and make the following changes:

   1. Change the `vectara.corpus_id` value to the ID of the corpus into which you want to ingest the content of the website.

      To retrieve your corpus ID from the Vectara console, click **Data > Your Corpus Name**.
      
   2. Change the `vectara.account_id` value to the ID of your account.

      To retrieve your account ID from the Vectara console, click your username in the upper-right corner.

   3. Change `rss_crawler.source` to `pg`.
      
   4. Change `rss_crawler.rss_pages` to `["http://www.aaronsw.com/2002/feeds/pgessays.rss"]`.
      
   5. Change `rss_crawler.days_past` to `365`.

## Step 3: Run the crawler

1. Ensure that Docker is running.

1. Run the script from the directory that you cloned and specify your `.yaml` configuration file and your `default` profile from the `secrets.toml` file.

   ```bash
   bash run.sh config/pg-rss.yaml default
   ```
   
   **Note:**
   * On Linux, ensure that the `run.sh` file is executable by running the following command:
  
     ```bash
     cmhod +x run.sh
     ```

   * On Windows, ensure that you run this command from within the WSL 2 environment.

   **Note:** To protect your system's resources and make it easier to move your crawlers to the cloud, the crawler executes inside a Docker container. This is a lengthy process because in involves numerous dependencies

1. When the container is set up, you can track your crawler’s progress:

   ```bash
   docker logs -f vingest
   ```

## Step 4: Try queries on your corpus

While your crawler is ingesting data into your Vectara corpus, you can try  queries against your corpus on the Vectara Console, click **Data > Your Corpus Name** and type in a query such as "What is a maker schedule?"

## Code organization
The codebase includes the following components.

### `core/` directory
Fundamental utilities depended upon by the crawlers:

- **`ingest.py`:** The main entry point for a crawl job.
- **`indexer.py`:** Defines the `Indexer` class which implements helpful methods to index data into Vectara such as `index_url`, `index_file()` and `index_document()`.
- **`crawler.py`:** Defines the `Crawler` class which implements a base class for crawling, where each specific crawler should implement the `crawl()` method specific to its type.
- **`pdf_convert.py`:** Helper class to convert URLs into local PDF documents.
- **`utils.py`:** Some utility functions used by the other code.

### `crawlers/` directory
Includes implementations of the various specific crawlers.

### `config/` directory
Includes example YAML configuration files for various crawling jobs.

### `run.sh`
The main shell script to execute when you want to launch a crawl job (see below for more details).

### `Dockerfile`
Defines the Docker container image.

## Crawling

### Configuration

To crawl and index a source you run a crawl "job", which is controlled by several paramters that you can define in a YAML configuration file. You can see example configuration files in the [config/](config) directory.

Each configuration YAML file includes a set of standard variables, for example:

```yaml
vectara:
  # the corpus ID for indexing
  corpus_id: 4
  # the Vectara customer ID
  customer_id: 1234567
  # flag: should vectara-ingest reindex if document already exists (optional)
  reindex: false
  # timeout (optional); sets the URL crawling timeout in seconds
  timeout:60

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

We use a `secrets.toml` file to hold secret keys and parameters. You need to create this file in the root directory before running a crawl job. This file can hold multiple "profiles", and specific specific secrets for each of these profiles. For example:

```
[profile1]
api_key="<VECTAR-API-KEY-1>

[profile2]
api_key="<VECTARA-API-KEY-2>"

[profile3]
api_key="<VECTARA-API-KEY-3>"
MOTION_API_KEY="<YOUR-NOTION-API-KEY>
```

This allows easy secrets management when you have multiple crawl jobs that may not share the same secrets. For example when you have a different Vectara API key for indexing differnet corpora.

Many of the crawlers have their own secrets, for example Notion, Discourse, Jira, or GitHub. These are also kept in the secrets file in the appropriate section and need to be all upper case (e.g. `NOTION_API_KEY` or `JIRA_PASSWORD`).

### Indexer Class

The `Indexer` class provides useful functionality to index documents into Vectara.

#### Methods

##### `index_url()`

This is probably the most useful method. It takes a URL as input and extracts the content from that URL (using the `playwright` and `Goose3` libraries), then sends that content to Vectara using the standard indexing API. If the URL points to a PDF document, special care is taken to ensure proper processing.
Please note that we use `Goose3` to extract the main (most important) content of the article, ignoring links, ads and other not-important content. If your crawled content has different requirements you can change the code to use a different extraction mechanism (html to text).

##### `index_file()`

Use this when you have a file that you want to index using Vectara's file_uplaod [API](https://docs.vectara.com/docs/indexing-apis/file-upload), so that it takes care of format identification, segmentation of text and indexing.

##### `index_document()` and `index_segments()`

Use these when you build the `document` JSON structure directly and want to index this document in the Vectara corpus.

#### Parameters

Specifically, the `reindex` parameter determines whether an existing document should be reindexed or not. If reindexing is required, the code automatically takes care of that by calling `delete_doc()` to first remove the document from the corpus and then sends it to the corpus index.

## Deployment

### Docker

The project is designed to be used within a Docker container, so that a crawl job can be run anywhere - on a local machine or on any cloud machine. See the [Dockerfile](https://github.com/vectara/vectara-ingest/blob/main/Dockerfile) for more information on the Docker file structure and build.

### Local deployment

To run `vectara-ingest` locally, perform the following steps:

1. Make sure you have [Docker installed](https://docs.docker.com/engine/install/) on your machine.
2. Clone this repo locally with `git clone https://github.com/vectara/vectara-ingest.git`.
3. Enter the directory with `cd vectara-ingest`.
4. Choose the configuration file for your project and run `bash run.sh config/<config-file>.yaml <profile>`. This command creates the Docker container locally, configures it with the parameters specified in your configuration file (with secrets taken from the appropriate `<profile>` in `secrets.toml`), and starts up the Docker container.

### Cloud deployment on Render

If you want your `vectara-ingest` to run on [Render](https://render.com/), please follow these steps:

1. <b>Sign Up/Log In</b>: If you don't have a Render account, you'll need to create one. If you already have one, just log in.
2. <b>Create New Service</b>: Once you're logged in, click on the "New" button usually found on the dashboard and select "Background Worker".
3. Choose "Deploy an existing image from a registry" and click "Next"
Specify Docker Image: In the "Image URL" fill in "vectara/vectara-ingest" and click "Next"
4. Choose a name for your deployment (e.g. "vectara-ingest"), and if you need to pick a region or leave the default. Then pick your instance type.
5. Click "Create Web Service"
6. Click "Environment", then "Add Secret File": name the file config.yaml, and copy the contents of the config.yaml for your crawler
7. Assuming you have a secrets.toml file with multiple profiles and you want to use the secrets for the profile <my-profile>, click "Environment", then "Add Secret File": name the file secrets.toml, and copy only the contents of <my-profile> from the secrets.toml to this file (incuding the profile name)
8. Click "Settings" and go to "Docker Command" and click "Edit", the put in the following command:
`/bin/bash -c mkdir /home/vectara/env && cp /etc/secrets/config.yaml /home/vectara/env/ && cp /etc/secrets/secrets.toml /home/vectara/env/ && python3 ingest.py /home/vectara/env/config.yaml <my-profile>"`

Then click "Save Changes", and your application should now be deployed.

Note:
* Hosting in this way does not support the CSV or folder crawlers.
* Where vectara-ingest uses `playwright` to crawl content (e.g. website crawler or docs crawler), the Render instance may require more RAM to work properly with headless browser.

### Cloud deployment on Cloud VM

`vectara-ingest` can be easily deployed on any cloud platform such as AWS, Azure or GCP. You simply create a cloud VM and follow the local-deployment instructions after 
you SSH into that machine.

### docker-hub

The `vectara-ingest` container is available for easy deployment via [docker-hub](https://hub.docker.com/repository/docker/vectara/vectara-ingest/general).

## Author

👤 **Vectara**

- Website: [vectara.com](https://vectara.com)
- Twitter: [@vectara](https://twitter.com/vectara)
- GitHub: [@vectara](https://github.com/vectara)
- LinkedIn: [@vectara](https://www.linkedin.com/company/vectara/)
- Discord: [@vectara](https://discord.gg/GFb8gMz6UH)

## 🤝 Contributing

Contributions, issues and feature requests are welcome and appreciated!<br />
Feel free to check [issues page](https://github.com/vectara/vectara-ingest/issues). You can also take a look at the [contributing guide](https://github.com/vectara/vectara-ingest/blob/master/CONTRIBUTING.md).

## Show your support

Give a ⭐️ if this project helped you!

## 📝 License

Copyright © 2023 [Vectara](https://github.com/vectara).<br />
This project is [Apache 2.0](https://github.com/vectara/vectara-ingest/blob/master/LICENSE) licensed.
