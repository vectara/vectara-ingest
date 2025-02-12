<h1 align="center">Welcome to vectara-ingest</h1>
<p align="center">
  <img style="max-width: 100%;" alt="logo" src="img/project-logo.png"/>
</p>

<h2>Build Ingest pipeline for Vectara<h2>

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Maintained](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/vectara/vectara-ingest/graphs/commit-activity)

[![Twitter](https://img.shields.io/twitter/follow/vectara.svg?style=social&label=Follow%20%40Vectara)](https://twitter.com/vectara)
[![Discord](https://img.shields.io/badge/Discord-Join%20Us-blue?style=social&logo=discord)](https://discord.com/invite/GFb8gMz6UH)

[![Open in Dev Containers](https://img.shields.io/static/v1?label=Dev%20Containers&message=Open&color=blue&logo=visualstudiocode)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/vectara/vectara-ingest)

# About `vectara-ingest`
Vectara is the trusted GenAI platform providing simple [APIs](https://docs.vectara.com/docs/) to create conversational experiences&mdash;such as chatbots, semantic search, and question answering&mdash;from your data.

`vectara-ingest` is an open source Python project that demonstrates how to crawl datasets and ingest them into Vectara. It provides a step-by-step guide on building your own crawler and some pre-built crawlers for ingesting data from sources such as:

* Websites
* RSS feeds
* Jira tickets
* Notion notes
* Docusaurus documentation sites
* Slack
* And many others...

For more information about this repository, see [Code Organization](#code-organization) and [Crawling](#crawling).

# Getting Started Guide
This guide explains how to create a basic crawler to scrape content from [Paul Graham's website](http://www.paulgraham.com/index.html), and ingest it into Vectara.

## Prerequisites
* A [Vectara account](https://console.vectara.com/signup)
* A Vectara corpus with an [API key](https://docs.vectara.com/docs/api-keys) that provides indexing permissions
* [Python 3.8 (or higher)](https://www.python.org/downloads/)
* [pyyaml](https://pypi.org/project/PyYAML/) - install with: `pip install pyyaml`
* [Docker](https://docs.docker.com/engine/install/) installed

## Step 1: Clone the `vectara-ingest` repository
This section explains how to clone the `vectara-ingest` repository to your machine.

### On Linux or MacOS
Open a terminal session and clone the repository to a directory on your machine:

```bash
git clone https://github.com/vectara/vectara-ingest.git
```

### On Windows
1. Open a Windows PowerShell terminal.
  
2. Update your Windows Subsystem for Linux (WSL):

   ```bash
   wsl --update
   ```

3. Ensure that WSL has the correct version of Linux:

   ```bash
   wsl --install ubuntu-20.04
   ```
   
4. Open your **Linux terminal** and clone the repository to a directory on your machine:

   ```bash
   git clone https://github.com/vectara/vectara-ingest.git
   ```

Note: make sure you execute step #4 above only within your Linux environment and not in the windows environment. 
You may need to choose a username for your Ubuntu environment as part of the setup process.

## Step 2: Configure the crawler
For our example we would index the content of https://www.paulgraham.com website to Vectara. Since this website does not provide a sitemap, but does provide an [RSS feed](http://www.paulgraham.com/rss.html), we will use the vectara-ingest `RSS crawler` instead.

1. Navigate to the directory that you have cloned.

2. Copy the `secrets.example.toml` to `secrets.toml`. 

3. In the `secrets.toml` file, change `api_key` to the Vectara API Key.

   To retrieve your API key from the Vectara console, click **Access Control** in your corpus view or use the **Authorization** Tab.
   You can use your Vectara personal API key, or a query+write API key.

4. In the `config/` directory, copy the `news-bbc.yaml` config file to `pg-rss.yaml`.

5. Edit the `pg-rss.yaml` file and make the following changes:

   1. Change the `vectara.corpus_key` value to the corpus_key for the corpus into which you want to ingest the content of the website.

      To retrieve your corpus key from the Vectara console, click your corpus name dropdown and you will see the key on the top of the screen.

   2. Change `rss_crawler.source` to `pg`.
      
   3. Change `rss_crawler.rss_pages` to `["http://www.aaronsw.com/2002/feeds/pgessays.rss"]` so it points to the Paul Graham RSS feed.
      
   4. Change `rss_crawler.days_past` to `365`.

## Step 3: Run the crawler

1. Ensure that Docker is running on your local machine.

2. Run the script from the directory that you cloned and specify your `.yaml` configuration file and your `default` profile from the `secrets.toml` file.

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

While your crawler is ingesting data into your Vectara corpus, you can try  queries against your corpus on the Vectara Console, click **Data > Your Corpus Name** and the under the **Query** tab type in a query such as "What is a maker schedule?"

## Code organization
The codebase includes the following components.

### main folder
- **`run.sh`:** The main shell script to execute when you want to launch a crawl job (see below for more details).
- **`ingest.py`:** The main entry point for a crawl job.
- **`Dockerfile`:** The Docker image definition file
- Various documentation files like **`README.MD`**, **`CONTRIBUTING.MD`**, or **`SECURITY.MD`**

### `core/` directory
Fundamental utilities depended upon by the crawlers:

- **`indexer.py`:** Defines the `Indexer` class which implements helpful methods to index data into Vectara such as `index_url`, `index_file()` and `index_document()`.
- **`crawler.py`:** Defines the `Crawler` class which implements a base class for crawling, where each specific crawler should implement the `crawl()` method specific to its type.
- **`pdf_convert.py`:** Helper class to convert URLs into local PDF documents.
- **`extract.py`:** Utilities for text extraction from HTML
- **`utils.py`:** Some utility functions used by the other code.

### `crawlers/` directory
Includes implementations of the various specific crawlers. Crawler files are always in the form of `xxx_crawler.py` where `xxx` is the type of crawler.

### `config/` directory
Includes example YAML configuration files for various crawling jobs.

### `img/` directory
Includes some images (png files) used in the documentation

## Crawling

### Configuration

To crawl and index a source you run a crawl "job", which is controlled by several paramters that you can define in a YAML configuration file. You can see example configuration files in the [config/](config) directory.

Each configuration YAML file includes a set of standard variables, for example:

```yaml
vectara:
  # the corpus key for indexing
  corpus_key: my-corpus
  
  # flag: should vectara-ingest reindex if document already exists (optional)
  reindex: false

  # flag: should vectara-ingest create the corpus (optional). defaults to false. 
  # When using this option, make sure your secrets.toml includes the personal API key.
  create_corpus: false
  
  # flag: store a copy of all crawled data that is indexed into a local folder
  store_docs: false
  
  # timeout: sets the URL crawling timeout in seconds (optional)
  timeout: 90

  # post_load_timeout: sets additional timeout past full page load to wait for animations and AJAX
  post_load_timeout: 5

  # flag: if true, will print extra debug messages when active
  verbose: false

  # flag: remove code or not from HTML (optional)
  remove_code: true
  
  # flag: should text extraction from web pages use special processing to remove boilerplate (optional)
  # this can be helpful when processing news pages or others which have a lot of advertising content
  remove_boilerplate: false

  # Whether masking of PII is attempted on all text fields (title, text, metadata values)
  # Notes: 
  # 1. This masking is never done on files uploaded to Vectara directly (via e.g. indexer.index_file())
  # 2. Masking is done using Microsoft Presidio PII analyzer and anonymizer, and is limited to English only
  mask_pii: false

  # Which whisper model to use for audio files (relevant for YT, S3 and folder crawlers)
  # Valid values: tiny, base, small, medium or large. Defaults to base.
  whisper_model: the model name for whisper


doc_processing:

  # which model to use for table summary, image summary or contextual retrevial
  # Options are "openai" or "anthropic". default is "openai"
  model: openai

  # which document parser to use for local file parsing: unstructured, llama_parse or docling
  # If using llama_parse you need to add LLAMA_CLOUD_API_KEY in your `secrets.toml` file.
  doc_parser: docling

  # Whether or not to parse tables from documents and ingest into Vectara.
  # When enabled this feature applies to PDF, HTML, PPT, DOCX files and requires setting 
  # the OPENAI_API_KEY or ANTHROPIC_API_KEY in your `secrets.toml` under a special profile called `general`.
  # Tables extracted will be ingested into Vectara along with a summary generated by the LLM
  # This processing might be slow and will require you to have an additional paid subscription to OpenAI or ANTHROPIC. 
  # Table parsing will be performed by the doc_parser, unless `enable_gmft` is enabled (only for PDF files).
  # See [here](TABLE_SUMMARY.md) for some examples of how table summary works.
  parse_tables: false

  # use GMFT to parse tables from PDF
  enable_gmft: true

  # Whether or not to summarize image content using GPT-4o vision 
  # When using this feature, you need to list the OPENAI_API_KEY or ANTHRPIC_API_KEY in your `secrets.toml` 
  # under a special profile called `general`.
  # This processing might be slow and will require you to have an additional paid subscription to OpenAI or ANTHROPIC. 
  summarize_images: false

  # Unstructured document parsing configuration
  unstructured_config:
    chunking_strategy: by_title        # chunking strategy to use: basic, by_title or none; default none
    chunk_size: 1024                   # chunk size if using unstructured chunking; default 1024

  # Docling document parsing configuation
  docling_config:
    chunking_strategy: hybrid          # chunking strategy to use: hierarchical, hybrid or none (default hybrid)

  # whether to use core_indexing which maintains the chunks from unstructured or docling, or let vectara chunk further
  use_core_indexing: false            

  # enable contextual chunking (only for PDF files at the moment)
  contextual_chunking: false            

  # defines a set of optional metadata attributes, each with a "query" to extract that value
  # requires OPENAI_API_KEY or ANTHROPIC_API_KEY to be defined.
  extract_metadata:
    'num_pages': 'number of pages in this document'
    'date': 'date of this document'


crawling:
  # type of crawler; valid options are website, docusaurus, notion, jira, rss, mediawiki, discourse, github and others (this continues to evolve as new crawler types are added)
  crawler_type: XXX
```

Following that, where needed, the same YAML configuration file will a include crawler-specific section with crawler-specific parameters (see [about crawlers](crawlers/CRAWLERS.md)):

```yaml
XXX_crawler:
  # specific parameters for the crawler XXX
```

### Secrets management

We use a `secrets.toml` file to hold secret keys and parameters. You need to create this file in the root directory before running a crawl job. This file can hold multiple "profiles", and specific specific secrets for each of these profiles. For example:

```
[general]
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-..."

[profile1]
api_key="<VECTAR-API-KEY-1>"

[profile2]
api_key="<VECTARA-API-KEY-2>"

[profile3]
api_key="<VECTARA-API-KEY-3>"
MOTION_API_KEY="<YOUR-NOTION-API-KEY>
```

The use of the `toml` standard allows easy secrets management when you have multiple crawl jobs that may not share the same secrets. For example when you have a different Vectara API key for indexing differnet corpora.

Many of the crawlers have their own secrets, for example Notion, Discourse, Jira, or GitHub. These are also kept in the `secrets.toml` file in the appropriate section and need to be all upper case (e.g. `NOTION_API_KEY` or `JIRA_PASSWORD`).

If you are using the table summarization, image summarization or contextual retreival features, 
you have to provide your own LLM key (either OPENAI_API_KEY or ANTHROPIC_API_KEY). 
In this case, you would need to put that key under the `[general]` profile. This is a special profile name reserved for this purpose.

### Indexer Class

The `Indexer` class provides useful functionality to index documents into Vectara.

#### Methods

##### `index_url()`

This is probably the most useful method. It takes a URL as input and extracts the content from that URL (using the `playwright` library), then sends that content to Vectara using the standard indexing API. If the URL points to a PDF document, special care is taken to ensure proper processing.
Please note that the special flag `remove_boilerplate` can be set to true if you want the content to be stripped of boilerplate text (e.g. advertising content). In this case the indexer uses `Goose3` and `justext` to extract the main (most important) content of the article, ignoring links, ads and other not-important content. 

##### `index_file()`

Use this when you have a file that you want to index using Vectara's file_uplaod [API](https://docs.vectara.com/docs/indexing-apis/file-upload), so that it takes care of format identification, segmentation of text and indexing.

##### `index_document()` and `index_segments()`

Use these when you build the `document` JSON structure directly and want to index this document in the Vectara corpus.

#### Parameters

The `reindex` parameter determines whether an existing document should be reindexed or not. If reindexing is required, the code automatically takes care of that by calling `delete_doc()` to first remove the document from the corpus and then indexes the document.

## Deployment

### Docker

The project is designed to be used within a Docker container, so that a crawl job can be run anywhere - on a local machine or on any cloud machine. See the [Dockerfile](https://github.com/vectara/vectara-ingest/blob/main/Dockerfile) for more information on the Docker file structure and build.

### Local deployment

To run `vectara-ingest` locally, perform the following steps:

1. Make sure you have [Docker installed](https://docs.docker.com/engine/install/) on your machine, and that there is enough memory and storage to build the docker image.
2. Clone this repo locally with `git clone https://github.com/vectara/vectara-ingest.git`.
3. Enter the directory with `cd vectara-ingest`.
4. Choose the configuration file for your project and run:
  > `bash run.sh config/<config-file>.yaml <profile>`. 
  
  This command creates the Docker container locally, configures it with the parameters specified in your configuration file (with secrets taken from the appropriate `<profile>` in `secrets.toml`), and starts up the Docker container.

### Cloud deployment on Render

If you want your `vectara-ingest` to run on [Render](https://render.com/), please follow these steps:

1. <b>Sign Up/Log In</b>: If you don't have a Render account, you'll need to create one. If you already have one, just log in.
2. <b>Create New Service</b>: Once you're logged in, click on the "New" button usually found on the dashboard and select "Background Worker".
3. Choose "Deploy an existing image from a registry" and click "Next"
Specify Docker Image: In the "Image URL" fill in "vectara/vectara-ingest" and click "Next"
1. Choose a name for your deployment (e.g. "vectara-ingest"), and if you need to pick a region or leave the default. Then pick your instance type.
2. Click "Create Web Service"
3. Click "Environment", then "Add Secret File": name the file config.yaml, and copy the contents of the config.yaml for your crawler
4. Assuming you have a `secrets.toml` file with multiple profiles and you want to use the secrets for the profile `[my-profile]`, click "Environment", then "Add Secret File": name the file secrets.toml, and copy only the contents of `[my-profile]` from the secrets.toml to this file (incuding the profile name). 
Make sure to copy `[general]` profile and your OPENAI_API_KEY or ANTHROPIC_API_KEY if you are using table summarization, image summarization of contextual retreival.
5. Click "Settings" and go to "Docker Command" and click "Edit", the enter the following command:
`/bin/bash -c mkdir /home/vectara/env && cp /etc/secrets/config.yaml /home/vectara/env/ && cp /etc/secrets/secrets.toml /home/vectara/env/ && python3 ingest.py /home/vectara/env/config.yaml <my-profile>"`

Then click "Save Changes", and your application should now be deployed.

Note:
* Hosting in this way does not support the CSV or folder crawlers.
* Where vectara-ingest uses `playwright` to crawl content (e.g. website crawler or docs crawler), the Render instance may require more RAM to work properly with headless browser. Make sure your Render deployment uses the correct machine type to allow that.

### Cloud deployment on Cloud VM

`vectara-ingest` can be easily deployed on any cloud platform such as AWS, Azure or GCP. You simply create a cloud VM, SSH into your machine, and follow the local-deployment instructions above.

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

Copyright © 2024 [Vectara](https://github.com/vectara).<br />
This project is [Apache 2.0](https://github.com/vectara/vectara-ingest/blob/master/LICENSE) licensed.
