<p align="center">
  <img src="../img/crawler.png" alt="Futuristic crawler">
</p>

<h1 align="center">vectara-ingest crawlers</h1>

## Overview

`vectara-ingest` includes a number of crawlers that make it easy to crawl data sources and index the results into Vectara.

If `remove_boilerplate` is enabled, `vectara-ingest` uses [Goose3](https://pypi.org/project/goose3/) and [JusText](https://pypi.org/project/jusText/) in `Indexer.index_url` to enhance text extraction from HTML content, ensuring relevant material is gathered while excluding ads and irrelevant content. 

`vectara-ingest` supports crawling and indexing web content in 42 languages currently. To determine the language of a given webpage, we utilize the [langdetect](https://pypi.org/project/langdetect/) package, and adjust the use of Goose3 and JusText accordingly.

Let's go through some of the main crawlers to explain how they work and how to customize them to your needs. This will also provide good background to creating (and contributing) new types of crawlers.

### Website crawler

```yaml
...
website_crawler:
    urls: [https://vectara.com]
    pos_regex: []
    neg_regex: []
    delay: 1
    pages_source: crawl
    max_depth: 3      # only needed if pages_source is set to 'crawl'
    extraction: playwright
    ray_workers: 0
...
```

The website crawler indexes the content of a given web site. It supports two modes for finding pages to crawl (defined by `pages_source`):
1. `sitemap`: in this mode the crawler retrieves the sitemap for each of the target websites (specificed in the `urls` parameter) and indexes all the URLs listed in each sitemap. Note that some sitemaps are partial only and do not list all content of the website - in those cases, `crawl` may be a better option.
2. `crawl`: in this mode for each url specified in `urls`, the crawler starts there and crawls the website recursively, following links no more than `max_depth`.

The `extraction` parameter defines how page content is extracted from URLs. 
1. The default (and better) option is `playwright` which results in using [playwright](https://playwright.dev/) to render the page content including JS and then extracting the HTML.
2. The other option is `pdf` which means the target URL is rendered into a PDF document, which is then uploaded to Vectara. 

Other parameters:
- `delay` specifies the number of seconds to wait between consecutive requests to avoid rate limiting issues. 
- `pos_regex` defines one or more (optional) regex expressions defining URLs to match for inclusion.
- `neg_regex` defines one or more (optional) regex expressions defining URLs to match for exclusion.

`ray_workers`, if defined, specifies the number of ray workers to use for parallel processing. ray_workers=0 means dont use Ray. ray_workers=-1 means use all cores available.
Note that ray with docker does not work on Mac M1/M2 machines.

### Database crawler

```yaml
...
database_crawler:
    db_url: "postgresql://<username>:<password>@my_db_host:5432/yelp"
    db_table: yelp_reviews                                 
    select_condition: "city='New Orleans'"
    doc_id_columns: [postal_code]
    text_columns: [business_name, review_text]
    metadata_columns: [city, state, postal_code]
```
The database crawler can be used to read data from a relational database and index relevant columns into Vectara.
- `db_url` specifies the database URI including the type of database, host/port, username and password if needed.
  - For MySQL: "mysql://username:password@host:port/database"
  - For PostgreSQL:"postgresql://username:password@host:port/database"
  - For Microsoft SQL Server: "mssql+pyodbc://username:password@host:port/database"
  - For Oracle: "oracle+cx_oracle://username:password@host:port/database"
- `db_table` the table name in the database
- `select_condition` optional condition to filter rows in the table by
- `doc_id_columns` defines one or more columns that will be used as a document ID, and will aggregate all rows associated with this value into a single Vectara document. The crawler will also use the content in these columns (concatenated) as the title for that row in the Vectara document. If this is not specified, the code will aggregate every `rows_per_chunk` (default 500) rows.
- `text_columns` a list of column names that include textual information we want to use as the main text indexed into vectara. The code concatenates these columns for each row.
- `title_column` is an optional column name that will hold textual information to be used as title at the document level.
- `metadata_columns` a list of column names that we want to use as metadata.

In the above example, the crawler would
1. Include all rows in the database "yelp" that are from the city of New Orleans (`SELECT * FROM yelp WHERE city='New Orleans'`)
2. Group all rows that have the same values for `postal_code` into the same Vectara document
3. Each such Vectara document that is indexed, will include several sections (one per row), each representing the textual fields `business_name` and `review_text` and including the meta-data fields `city`, `state` and `postal_code`.

### CSV crawler

```yaml
...
csv_crawler:
    csv_path: "/path/to/Game_of_Thrones_Script.csv"
    doc_id_columns: [Season, Episode]
    text_columns: [Name, Sentence]
    metadata_columns: ["Season", "Episode", "Episode Title"]
    separator: ','
```
The csv crawler is similar to the database crawler, but instead of pulling data from a database, it uses a local CSV file.
- `select_condition` optional condition to filter rows in the table by
- `doc_id_columns` defines one or more columns that will be used as a document ID, and will aggregate all rows associated with this value into a single Vectara document. This will also be used as the title. If this is not specified, the code will aggregate every `rows_per_chunk` (default 500) rows.
- `text_columns` a list of column names that include textual information we want to use 
- `title_column` is an optional column name that will hold textual information to be used as title
- `metadata_columns` a list of column names that we want to use as metadata
- `separator` a string that will be used as a separator in the CSV file (default ',')

In the above example, the crawler would
1. Read all the data from the local CSV file under `/path/to/Game_of_Thrones_Script.csv`
2. Group all rows that have the same values for both `Season` and `Episode` into the same Vectara document
3. Each such Vectara document that is indexed, will include several section (one per row), each representing the textual fields `Name` and `Sentence` and including the meta-data fields `Season`, `Episode` and `Episode Title`.

### Bulk Upload crawler

```yaml
...
bulkupload_crawler:
    json_path: "/path/to/file.JSON"
```
The Bulk Upload crawler accepts a single JSON file that is an array of Vectara JSON document objects as specified [here](https://docs.vectara.com/docs/api-reference/indexing-apis/file-upload/format-for-upload#sample-document-formats). It then iterates through these document objects, and uploads them one by one to Vectara.

This bulk upload crawler has no parameters.

### RSS crawler

```yaml
...
rss_crawler:
  source: bbc
  rss_pages: [
    "http://feeds.bbci.co.uk/news/rss.xml", "http://feeds.bbci.co.uk/news/world/rss.xml", "http://feeds.bbci.co.uk/news/uk/rss.xml",
    "http://feeds.bbci.co.uk/news/business/rss.xml", "http://feeds.bbci.co.uk/news/politics/rss.xml", 
    "http://feeds.bbci.co.uk/news/health/rss.xml", "http://feeds.bbci.co.uk/news/education/rss.xml", 
    "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "http://feeds.bbci.co.uk/news/technology/rss.xml", 
    "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "http://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "http://feeds.bbci.co.uk/news/world/asia/rss.xml",
    "http://feeds.bbci.co.uk/news/world/europe/rss.xml"
  ]
  days_past: 90
  delay: 1
  extraction: playwright           # pdf or playwright
```

The RSS crawler can be used to crawl URLs listed in RSS feeds such as on news sites. In the example above, the rss_crawler is configured to crawl various newsfeeds from the BBC. 
- `source` specifies the name of the rss data feed.
- `rss_pages` defines one or more RSS feed locations. 
- `days_past` specifies the number of days backward to crawl; for example with a value of 90 as in this example, the crawler will only index news items that have been published no earlier than 90 days in the past.
- `delay` defines the number of seconds between to wait between news articles, so as to make the crawl more friendly to the hosting site.
- `extraction` defines how text is extracted from the URLs referred to by the RSS feed, in a similar fashion to the website crawler above.

### Hackernews crawler

```yaml
...
hackernews_crawler:
  max_articles: 1000
  days_past: 3
  days_past_comprehensive: false
```

The hackernews crawler can be used to crawl stories and comments from hacker news.
- `max_articles` specifies a limit to the number of stories crawled. 
- `days_past` specifies the number of days backward to crawl, based on the top, new, ask, show and best story lists. For example with a value of 3 as in this example, the crawler will only index stories if the story or any comment in the story was published or updated in the last 3 days.
- `days_past_comprehensive` if true, then the crawler performs a comprehensive search for ALL stories published within the last `days_past` days (which takes longer to run)

### Docs crawler

```yaml
...
  docs_crawler:
    docs_repo: "https://github.com/vectara/vectara-docs"
    docs_homepage: "https://docs.vectara.com/docs"
    docs_system: "docusaurus"
    extensions_to_ignore: ["ipynb", "txt"]
    ray_workers: 0
```

The Docs crawler processes and indexes content published on different documentation systems.
It has two parameters
- `base_urls` defines one or more base URLS for the documentation content.
- `pos_regex` defines one or more (optional) regex expressions defining URLs to match for inclusion
- `neg_regex` defines one or more (optional) regex expressions defining URLs to match for exclusion
- `extensions_to_ignore` specifies one or more file extensions that we want to ignore and not index into Vectara.
- `doc_system` is a text string specifying the document system crawled, and is added to the metadata under "source"
- `ray_workers` if it exists defines the number of ray workers to use for parallel processing. ray_workers=0 means dont use Ray. ray_workers=-1 means use all cores available.
Note that Ray with docker does not work on Mac M1/M2 machines.


### Discourse crawler

```yaml
...
  discourse_crawler:
    base_url: "https://discuss.vectara.com"
```

The discourse forums crawler requires a single parameter, `base_url`, which specifies the home page for the public forum we want to crawl.
In the `secrets.toml` file you should have DISCOURSE_API_KEY="<YOUR_DISCOURSE_KEY>" which will provide the needed authentication for the crawler to access this data.

### Mediawiki crawler

The mediawiki crawler can crawl content in any wikimedia-powered website such as Wikipedia or others, and index it into Vectara.

```yaml
...
  wikimedia_crawler:
    project: "en.wikipedia"
    api_url: "https://en.wikipedia.org/w/api.php"
    n_pages: 1000
```

The mediawiki crawler first looks at media statistics to determine the most viewed pages in the last 7 days, and then based on that picks the top `n_pages` to crawl.
- `api_url` defines the base URL for the wiki
- `project` defines the mediawiki project name.

### GitHub crawler

```yaml
...
  github_crawler:
    owner: "vectara"
    repos: ["getting-started", "protos", "slackbot", "magazine-search-demo", "web-crawler", "Search-UI", "hotel-reviews-demo"]
    crawl_code: false
```

The GitHub crawler indexes content from GitHub repositories into Vectara. 
- `repos`: list of repository names to crawl
- `owner`: GitHub repository owner
- `crawl_code`: by default the crawler indexes only issues and comments; if this is set to True it will also index the source code (but that's usually not recommended).

It is highly recommended to add a `GITHUB_TOKEN` to your `secret.toml` file under the specific profile you're going to use. The GITHUB_TOKEN (see [here](https://docs.github.com/en/enterprise-server@3.10/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) for how to create one for yourself) ensures you don't run against rate limits.

### Jira crawler

```yaml
...
  jira_crawler:
    jira_base_url: "https://vectara.atlassian.net/"
    jira_username: ofer@vectara.com
    jira_jql: "created > -365d"
```

The JIRA crawler indexes issues and comments into Vectara. 
- `jira_base_url`: the Jira base_url
- `jira_username`: the user name that the crawler should use (`JIRA_PASSWORD` should be separately defined in the `secrets.toml` file)
- `jira_jql`: a Jira JQL condition on the issues identified; in this example it is configured to only include items from the last year.

### Notion crawler

To setup Notion you will have to setup a [Notion integration](https://www.notion.so/help/create-integrations-with-the-notion-api),
and [share the pages](https://www.notion.so/help/add-and-manage-connections-with-the-api) you want indexed with this connection.

The Notion crawler has no specific parameters, except the `NOTION_API_KEY` (which is associated with your custom integration)
that needs to be specified in the `secrets.toml` file. The crawler will index any content on your notion instance.

### Hubspot crawler

The HubSpot crawler has no specific parameters, except the `HUBSPOT_API_KEY` that needs to be specified in the `secrets.toml` file. The crawler will index the emails on your Hubspot instance. The crawler also uses `clean_email_text()` module which takes the email message as a parameter and cleans it to make it more presentable. This function in `core/utils.py` is taking care of indentation character `>`. 

The crawler leverages [Presidio Analyzer and Anonymizer](https://microsoft.github.io/presidio/analyzer/) to accomplish PII masking, achieving a notable degree of accuracy in anonymizing sensitive information with minimal error.

### Folder crawler

```yaml
...
  folder_crawler:
    path: "/Users/ofer/Downloads/some-interesting-content/"
    extensions: ['.pdf']
```

The folder crawler indexes all files specified from a local folder.
- `path`: the local folder location
- `extensions`: list of file extensions to be included. If one of those extensions is '*' then all files would be crawled, disregarding any other extensions in that list.
- `source`: a string that is added to each file's metadata under the "source" field

Note that the local path you specify is mapped into a fixed location in the docker container `/home/vectara/data`, but that is a detail of the implementation that you don't need to worry about in most cases, just specify the path to your local folder and this mapping happens automatically.

### S3 crawler

```yaml
...
  s3_crawler:
    s3_path: s3://my-bucket/files
    extensions: ['*']
```

The S3 crawler indexes all content that's in a specified S3 bucket path.
- `s3_path`: a valid S3 location where the files to index reside
- `extensions`: list of file extensions to be included. If one of those extensions is '*' then all files would be crawled, disregarding any other extensions in that list.

### Slack crawler

```yaml
...
slack_crawler:
  days_past: 30
  channels_to_skip: ["alerts"]
  retries: 5
```

To use the slack crawler you need to create slack bot app and give it permissions. Following are the steps.
- **Create a Slack App**: Log in to your Slack workspace and navigate to the Slack API website. Click on "Your Apps" and then "Create New App." Provide a name for your app, select the workspace where you want to install it, and click "Create App."

- **Configure Basic Information**: In the app settings, you can configure various details such as the app name, icon, and description. Make sure to fill out the necessary information accurately.

- **Install the Bot to Your Workspace**: Once you've configured your app, navigate to the "Install App" section. Click on the "Install App to Workspace" button to add the bot to your Slack workspace. This step will generate an OAuth access token that you'll need to use to authenticate your bot.

- **Add User Token Scope**: To add user token scope, navigate to the "OAuth & Permissions" section in your app settings. Under the "OAuth Tokens for Your Workspace" section, you'll need to add  `users:read`, `channel:read`, `channel:history` scopes.

- **Save Changes**: Make sure to save any changes you've made to your app settings.

- Place the generated user token in `secrets.toml`.
  - `SLACK_USER_TOKEN= <user_token>`

## Other crawlers:

- `Edgar` crawler: crawls SEC Edgar annual reports (10-K) and indexes those into Vectara
- `fmp` crawler: crawls information about public companies using the [FMP](https://site.financialmodelingprep.com/developer/docs/) API
- `PMC` crawler: crawls medical articles from PubMed Central and indexes them into Vectara.
- `Arxiv` crawler: crawls the top (most cited or latest) Arxiv articles about a topic and indexes them into Vectara.
