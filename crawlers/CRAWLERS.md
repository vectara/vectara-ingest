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
    num_per_second: 10
    pages_source: crawl
    crawl_method: internal  # "internal" (default) or "scrapy"
    max_depth: 3            # only needed if pages_source is set to 'crawl'
    html_processing:
      ids_to_remove: [td-123]
      tags_to_remove: [nav]
      classes_to_remove: []
    keep_query_params: false
    crawl_report: false
    remove_old_content: false
    ray_workers: 0
...
```

The website crawler indexes the content of a given web site. It supports two modes for finding pages to crawl (defined by `pages_source`):
1. `sitemap`: in this mode the crawler retrieves the sitemap for each of the target websites (specificed in the `urls` parameter) and indexes all the URLs listed in each sitemap. Note that some sitemaps are partial only and do not list all content of the website - in those cases, `crawl` may be a better option.
2. `crawl`: in this mode for each url specified in `urls`, the crawler starts there and crawls the website recursively, following links no more than `max_depth`. If you'd like to crawl only the URLs specified in the `urls` list (without any further hops) use `max_depth=0`.

Other parameters:
- `num_per_second` specifies the number of call per second when crawling the website, to allow rate-limiting. Defaults to 10.
- `pos_regex` defines one or more (optional) regex expressions defining URLs to match for inclusion.
- `neg_regex` defines one or more (optional) regex expressions defining URLs to match for exclusion.
- `keep_query_params`: if true, maintains the full URL including query params in the URL. If false, then it removes query params from collected URLs.
- `crawl_report`: if true, creates a file under ~/tmp/mount called `urls_indexed.txt` that lists all URLs crawled
- `remove_old_content`: if true, removes any URL that currently exists in the corpus but is NOT in this crawl. CAUTION: this removes data from your corpus. 
If `crawl_report` is true then the list of URLs associated with the removed documents is listed in `urls_removed.txt`

The `html_processing` configuration defines a set of special instructions that can be used to ignore some content when extracting text from HTML:
- `ids_to_remove` defines an (optional) list of HTML IDs that are ignored when extracting text from the page.
- `tags_to_remove` defines an (optional) list of HTML semantic tags (like header, footer, nav, etc) that are ignored when extracting text from the page.
- `classes_to_remove` defines an (optional) list of HTML "class" types that are ignored when extracting text from the page.

<br>**Note**: when specifying regular expressions it's recommended to use single quotes (as opposed to double quotes) to avoid issues with escape characters.

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

### Huggingface dataset crawler

```yaml
...
hfdataset_crawler:
    dataset_name: "coeuslearning/hotel_reviews"
    split: "train"
    select_condition: "city='New York City, USA'"
    start_row: 0
    num_rows: 55
    title_column: hotel
    text_columns: [review]
    metadata_columns: [city, hotel]
```
The huggingface crawler can be used to read data from a HF dataset and index relevant columns into Vectara.
- `dataset_name` the huggingface dataset name
- `split` the "split" of the dataset in the HF datasets hub (e.g. "train", or "test", or "corpus"; look at DS card to determine)
- `select_condition` optional condition to filter rows in the table by
- `start_row` if specified skips the specified number of rows from the start of the dataset
- `num_rows` if specified limits the dataset size by number of specified rows
- `id_column` optional column for the ID of the dataset. Must be unique if used
- `text_columns` a list of column names that include textual information we want to use as the main text indexed into vectara. The code concatenates these columns for each row.
- `title_column` is an optional column name that will hold textual information to be used as title at the document level.
- `metadata_columns` a list of column names that we want to use as metadata.

In the above example, the crawler would
1. Include all rows in the dataset that are from NYC
2. Each Vectara document that is indexed, will include a title as the value of `hotel` and text from `review`. The metadata will include the fields `city` and `hotel`.
3. include only the first 55 rows matching the condition

### CSV crawler

```yaml
...
csv_crawler:
    file_path: "/path/to/Game_of_Thrones_Script.csv"
    select_condition: "Season='Season 1'"
    doc_id_columns: [Season, Episode]
    text_columns: [Name, Sentence]
    metadata_columns: ["Season", "Episode", "Episode Title"]
    column_types: []
    separator: ','
    sheet_name: "my-sheet"
```
The csv crawler is similar to the database crawler, but instead of pulling data from a database, it uses a local CSV or XLSX file.
- `select_condition` optional condition to filter rows in the table by
- `doc_id_columns` defines one or more columns that will be used as a document ID, and will aggregate all rows associated with this value into a single Vectara document. This will also be used as the title. If this is not specified, the code will aggregate every `rows_per_chunk` (default 500) rows.
- `text_columns` a list of column names that include textual information we want to use 
- `title_column` is an optional column name that will hold textual information to be used as title
- `metadata_columns` a list of column names that we want to use as metadata
- `column_types` an optional dictionary of column name and type (int, float, str). If unspecified, or for columns not included, the default type is str.
- `separator` a string that will be used as a separator in the CSV file (default ',') (relevant only for CSV files)
- `sheet_name` the name of the sheet in the XLSX file to use (relevant only for XLSX files)

In the above example, the crawler would
1. Read all the data from the local CSV file under `/path/to/Game_of_Thrones_Script.csv`
2. Group all rows that have the same values for both `Season` and `Episode` into the same Vectara document
3. Each such Vectara document that is indexed, will include several sections (one per row), each representing the textual fields `Name` and `Sentence` and including the meta-data fields `Season`, `Episode` and `Episode Title`.

Note that the type of file is determined by it's extension (e.g. CSV vs XLSX)

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
```

The RSS crawler can be used to crawl URLs listed in RSS feeds such as on news sites. In the example above, the rss_crawler is configured to crawl various newsfeeds from the BBC. 
- `source` specifies the name of the rss data feed.
- `rss_pages` defines one or more RSS feed locations. 
- `days_past` specifies the number of days backward to crawl; for example with a value of 90 as in this example, the crawler will only index news items that have been published no earlier than 90 days in the past.
- `delay` defines the number of seconds to wait between news articles, so as to make the crawl more friendly to the hosting site.

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
- `ssl_verify`  If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.
### Docs crawler

```yaml
...
  docs_crawler:
    base_urls: ["https://docs.vectara.com/docs"]
    pos_regex: [".*vectara.com/docs.*"]
    neg_regex: [".*vectara.com/docs/rest-api/.*"]
    num_per_second: 10
    extensions_to_ignore: [".php", ".java", ".py", ".js"]
    docs_system: docusaurus
    crawl_method: internal  # "internal" (default) or "scrapy"
    remove_code: true
    html_processing:
      ids_to_remove: []
      tags_to_remove: [footer]
    crawl_report: false
    remove_old_content: false
    ray_workers: 0
```

The Docs crawler processes and indexes content published on different documentation systems.
It has the following parameters:
- `base_urls` defines one or more base URLS for the documentation content.
- `pos_regex` defines one or more (optional) regex expressions defining URLs to match for inclusion
- `neg_regex` defines one or more (optional) regex expressions defining URLs to match for exclusion
- `extensions_to_ignore` specifies one or more file extensions that we want to ignore and not index into Vectara.
- `docs_system` is a text string specifying the document system crawled, and is added to the metadata under "source"
- `ray_workers` if it exists defines the number of ray workers to use for parallel processing. ray_workers=0 means dont use Ray. ray_workers=-1 means use all cores available.
- `num_per_second` specifies the number of call per second when crawling the website, to allow rate-limiting. Defaults to 10.
- `crawl_report`: if true, creates a file under ~/tmp/mount called `urls_indexed.txt` that lists all URLs crawled
- `remove_old_content`: if true, removes any URL that currently exists in the corpus but is NOT in this crawl. CAUTION: this removes data from your corpus. 
If `crawl_report` is true then the list of URLs associated with the removed documents is listed in `urls_removed.txt`

The `html_processing` configuration defines a set of special instructions that can be used to ignore some content when extracting text from HTML:
- `ids_to_remove` defines an (optional) list of HTML IDs that are ignored when extracting text from the page.
- `tags_to_remove` defines an (optional) list of HTML semantic tags (like header, footer, nav, etc) that are ignored when extracting text from the page.
- `classes_to_remove` defines an (optional) list of CSS class names that are ignored when extracting text from the page.
- `ssl_verify`  If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.
- 
<br>**Note**: when specifying regular expressions it's recommended to use single quotes (as opposed to double quotes) to avoid issues with escape characters.

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
    num_per_second: 2

```

The GitHub crawler indexes content from GitHub repositories into Vectara. 
- `repos`: list of repository names to crawl
- `owner`: GitHub repository owner
- `crawl_code`: by default the crawler indexes only issues and comments; if this is set to True it will also index the source code (but that's usually not recommended).
- `num_per_second` specifies the number of call per second when crawling the website, to allow rate-limiting. Defaults to 10.


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
- `ssl_verify`  If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.
- 
### Confluence crawler

```yaml
  confluence_crawler:
    confluence_base_url: "https://vectara.atlassian.net/wiki"
    confluence_cql: 'space = Test and LastModified > now("-365d") and type IN (blogpost, page)'
    confluence_include_attachments: true
```

This Python crawler is designed to pull content from a Confluence instance and index it into Vectara. It queries Confluence using a [CQL query](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/), 
retrieves pages and blogposts (including attachments if configured), extracts relevant metadata (e.g., labels, authors, space information).  

- `ssl_verify`  If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.

### Twitter crawler

```yaml
...
  twitter_crawler:
    bearer_token: the Twitter API bearer token. see https://developer.twitter.com/en/docs/twitter-api/getting-started/getting-access-to-the-twitter-api'
    userhandles: a list of user handles to pull tweets from
    num_tweets: number of most recent tweets to pull from each user handle
    clean_tweets: whether to remove username / handles from tweet text (default: True)
```

The twitter crawler indexes top `num_tweeets` mentions from twitter
- `bearer_token`: the Twitter developer authentication token
- `userhandles`: a list of user handles to look for in mentions
- `num_tweets`: number of recent tweets mentioning each handle to pull
- `clean_tweets` if True removes all username/handle


### Notion crawler

To setup Notion you will have to setup a [Notion integration](https://www.notion.so/help/create-integrations-with-the-notion-api),
and [share the pages](https://www.notion.so/help/add-and-manage-connections-with-the-api) you want indexed with this connection.

```yaml
...
  notion_crawler:
    remove_old_content: false
```

The notion crawler indexes notion pages into Vectara:
- `remove_old_content`: if true, removes any document that currently exists in the corpus but is NOT in this crawl. CAUTION: this removes data from your corpus. 

For this crawler, you need to specify `NOTION_API_KEY` (which is associated with your custom integration) in the `secrets.toml` file. 


### Hubspot crawler

The HubSpot crawler has no specific parameters, except the `HUBSPOT_API_KEY` that needs to be specified in the `secrets.toml` file. The crawler will index the emails on your Hubspot instance. The crawler also uses `clean_email_text()` module which takes the email message as a parameter and cleans it to make it more presentable. This function in `core/utils.py` is taking care of indentation character `>`. 

The crawler leverages [Presidio Analyzer and Anonymizer](https://microsoft.github.io/presidio/analyzer/) to accomplish PII masking, achieving a notable degree of accuracy in anonymizing sensitive information with minimal error.

### Google Drive crawler

```yaml
...
  gdrive_crawler:
    permissions: ['Vectara', 'all']
    days_back: 365
    ray_workers: 0
    delegated_users:
      - ofer@vectara.com
      - jana@vectara.com
    credentials_file: /path/to/credential.json # In CLI version make sure that path points to credetianls.json

```

The gdrive crawler indexes content of your Google Drive folder
- `days_back`: include only files created within the last N days
- `permissions`: list of `displayName` values to include. We recommend including your company name (e.g. `Vectara`) and `all` to include all non-restricted files.
- `delegated_users`: list of user emails in your organization. 
- `ray_workers`: 0 if not using Ray, otherwise specifies the number of Ray workers to use.

This crawler identifies Google Drive files based on the list of delegated users. For each user it looks at those files that the user either created or has access to, but
limiting only to files that have "accessible by all" permissions (so that "restricted" files are not included)

Note that this crawler uses a Google Drive service account mode to access files, 
and you need to include a `credentials.json` file in the main vectara-ingest folder.
For more information see [Google documentation](https://developers.google.com/workspace/guides/create-credentials) under 
"Service account credentials".


### Folder crawler

```yaml
...
  folder_crawler:
    path: "/Users/ofer/Downloads/some-interesting-content/"
    extensions: ['.pdf']
    source: 'my-folder'
    metadata_file: '/path/to/metadata.csv'
```

The folder crawler indexes all files specified from a local folder.
- `path`: the local folder location
- `extensions`: list of file extensions to be included. If one of those extensions is '*' then all files would be crawled, disregarding any other extensions in that list.
- `source`: a string that is added to each file's metadata under the "source" field
- `metadata_file`: an optional CSV file for metadata. Each row should have a `filename` column as key to match the file in the folder, and 1 or more additional columns used as metadata. This file should be in the `path` folder, but will be ignored for indexing purposes.

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
- `metadata_file`: an optional CSV file for metadata. Each row should have a `filename` column as key to match the file in the folder, and 1 or more additional columns used as metadata. This file should be in the same `s3_path` folder, but will be ignored for indexing purposes.

### Youtube crawler

```yaml
...
  yt_crawler:
    playlist_url: <some-youtube-playlist-url>
```

The Youtube crawler loads all videos from a playlist, extracts the subtitles into text (or transcribes the audio if subtitles don't exist), and indexes that text.
- `playlist_url`: a valid youtube playlist URL

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

- **Add User Token Scope**: To add user token scope, navigate to the "OAuth & Permissions" section in your app settings. Under the "OAuth Tokens for Your Workspace" section, you'll need to add  `users:read`, `channels:read`, `channels:history` scopes.

- **Save Changes**: Make sure to save any changes you've made to your app settings.

- Place the generated user token in `secrets.toml`.
  - `SLACK_USER_TOKEN= <user_token>`

### ServiceNow Crawler

```yaml
servicenow_crawler:
  servicenow_instance_url: "https://dev189594.service-now.com/"
  servicenow_process_attachments: true
```

This crawler indexes articles (and optional file attachments) from a ServiceNow Knowledge Base into [Vectara](https://vectara.com). It uses 
the [ServiceNow Table API](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_TableAPI) to fetch data from the `kb_knowledge` 
table in batches and then sends each article's content to Vectara for indexing. If enabled, it will also retrieve attachments via ServiceNow's 
attachment API and index them in Vectara as well.

- `servicenow_instance_url`: The base URL of the ServiceNow instance (e.g., "https://dev12345.service-now.com/").
- `servicenow_process_attachments`: Boolean flag indicating whether to retrieve and index file attachments in addition to the article content.
- `servicenow_batch_size` (if present): The number of articles to fetch in each API call. Default: 100.
- `servicenow_table` (if present):The ServiceNow table to query for articles. Default: `"kb_knowledge"`.
- `servicenow_query` (if present): A query (e.g., `sysparm_query`) for filtering the knowledge-base articles returned by the ServiceNow API.
- `ssl_verify`  If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.

- **[Table API Reference](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_TableAPI)**  
  Contains details on the various endpoints, query parameters, and usage examples for retrieving data from ServiceNow tables.
- **[Attachment API Reference](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_AttachmentAPI)**  
  Covers how to list and download attachments from ServiceNow records.

### Sharepoint Crawler

```yaml
sharepoint_crawler:
  team_site_url: "https://yoursharepointdomain.sharepoint.com/sites/YourTeamSite"
  target_folder: "Shared Documents/TargetFolder"
  recursive: true
  mode: "folder" # Currently supports 'folder' mode only.
  auth_type: "user_credentials" # Options: 'user_credentials', 'client_credentials', 'client_certificate'
  username: "your.username@example.com"
  password: "your_password"
  client_id: "<your_client_id>"
  client_secret: "<your_client_secret>"
  tenant_id: "<your_tenant_id>"
  cert_thumbprint: "<certificate_thumbprint>"
  cert_path: "/path/to/certificate.pem"
  cert_passphrase: "<certificate_passphrase>" # optional
```

This Python crawler ingests documents from a SharePoint site and indexes them into Vectara. It authenticates to SharePoint using either user credentials, client credentials, or a client certificate. The crawler recursively scans folders, downloads supported file types (.pdf, .md, .odt, .doc, .docx, .ppt, .pptx, .txt, .html, .htm, .lxml, .rtf, .epub), and submits these files for indexing along with associated metadata.
-	`team_site_url`: The URL of your SharePoint site.
-	`target_folder`: The path to the SharePoint folder you wish to crawl.
-	`recursive`: Set to true if subfolders should be crawled recursively.
-	`mode`: Determines crawling behavior; currently supports "folder" only.
-	`auth_type`: Authentication method for SharePoint (user_credentials, client_credentials, or client_certificate).
-	For user_credentials: provide username and password.
-	For client_credentials: provide client_id, client_secret.
-	For client_certificate: provide client_id, tenant_id, cert_thumbprint, cert_path, and optionally cert_passphrase.

Ensure that sensitive information such as credentials and certificates are stored securely, and avoid disabling SSL verification in production environments.



## Other crawlers:

- `Edgar` crawler: crawls SEC Edgar annual reports (10-K) and indexes those into Vectara
- `fmp` crawler: crawls information about public companies using the [FMP](https://site.financialmodelingprep.com/developer/docs/) API
- `PMC` crawler: crawls medical articles from PubMed Central and indexes them into Vectara.
- `Arxiv` crawler: crawls the top (most cited or latest) Arxiv articles about a topic and indexes them into Vectara.
