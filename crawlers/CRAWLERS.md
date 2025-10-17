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
    scrape_method: playwright  # "playwright" (default) or "scrapy" - for web content extraction
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
- `pos_regex` defines one or more (optional) regex patterns for URL inclusion. URLs must match at least one positive pattern to be crawled. If the list is empty, all URLs are matched.
  - **Important**: Patterns use Python's `.match()` method, which matches from the **beginning** of the string
  - Examples:
    - Match all URLs from domain: `[".*"]` or leave empty `[]`
    - Match only blog pages: `[".*\/blog\/.*"]`
    - Match exact domain only: `["^https:\/\/example\.com\/.*"]`
    - Match multiple sections: `[".*\/blog\/.*", ".*\/news\/.*", ".*\/articles\/.*"]`
- `neg_regex` defines one or more (optional) regex patterns for URL exclusion. URLs matching any negative pattern will be skipped.
  - Examples:
    - Exclude admin pages: `[".*\/admin\/.*"]`
    - Exclude specific subdomain: `[".*care\.example\..*"]`
    - Exclude PDFs and ZIPs: `[".*\.pdf$", ".*\.zip$"]`
    - Exclude query parameters: `[".*\?.*"]`
- `keep_query_params`: if true, maintains the full URL including query params in the URL. If false, then it removes query params from collected URLs.
- `crawl_report`: if true, creates a file under ~/tmp/mount called `urls_indexed.txt` that lists all URLs crawled
- `remove_old_content`: if true, removes any URL that currently exists in the corpus but is NOT in this crawl. CAUTION: this removes data from your corpus.
If `crawl_report` is true then the list of URLs associated with the removed documents is listed in `urls_removed.txt`

The `html_processing` configuration defines a set of special instructions that can be used to ignore some content when extracting text from HTML:
- `ids_to_remove` defines an (optional) list of HTML IDs that are ignored when extracting text from the page.
- `tags_to_remove` defines an (optional) list of HTML semantic tags (like header, footer, nav, etc) that are ignored when extracting text from the page.
- `classes_to_remove` defines an (optional) list of HTML "class" types that are ignored when extracting text from the page.

#### Important Notes on Regex Patterns

**Best Practices for Regex Patterns:**
1. **Use single quotes** in YAML files to avoid escape character issues: `pos_regex: ['.*\/blog\/.*']` instead of `pos_regex: [".*\/blog\/.*"]`
2. **Escape dots** in domain names for exact matching: `\.com` instead of `.com`
3. **Test your patterns** - Remember that `.match()` starts from the beginning of the URL string
4. **URL format** - Patterns are matched against full URLs including protocol (e.g., `https://example.com/page`)

**Common Pattern Examples:**
```yaml
# Match everything (equivalent to empty list)
pos_regex: ['.*']

# Match exact domain, excluding subdomains
pos_regex: ['^https:\/\/example\.com\/.*']

# Match domain with optional www
pos_regex: ['^https:\/\/(www\.)?example\.com\/.*']

# Match specific paths
pos_regex: ['.*\/documentation\/.*', '.*\/guides\/.*']

# Exclude file types
neg_regex: ['.*\.(pdf|zip|tar|gz)$']
```

**Troubleshooting Regex Patterns:**
- If your pattern isn't matching expected URLs, remember that `.match()` anchors to the start of the string
- To debug patterns, test them in Python: `re.compile(pattern).match(url)`
- An empty `pos_regex` list `[]` matches all URLs (no filtering)
- URLs must match at least one positive pattern (if any defined) AND not match any negative patterns

`ray_workers`, if defined, specifies the number of ray workers to use for parallel processing. ray_workers=0 means dont use Ray. ray_workers=-1 means use all cores available.
Note that ray with docker does not work on Mac M1/M2 machines.

`scrape_method` defines the extraction backend for processing web content ("playwright" or "scrapy"):
- `playwright` (default): Uses Playwright browser automation for JavaScript-heavy sites, SPAs, and dynamic content
- `scrapy`: Uses Scrapy for faster, lightweight extraction of static HTML content


### Database crawler

```yaml
...
database_crawler:
    mode: element
    db_url: "postgresql://<username>:<password>@my_db_host:5432/yelp"
    db_table: yelp_reviews
    select_condition: "city='New Orleans'"
    doc_id_columns: [postal_code]
    text_columns: [business_name, review_text]
    metadata_columns: [city, state, postal_code]
```
The database crawler can be used to read data from a relational database and index relevant columns into Vectara.
This has two modes: `element` or `table`
- In the `table` mode, the complete table content is ingested into Vectara as a single table entity.
  Note that table size is limited to 1000 rows and 100 columns
- In the `element` mode, each row in the table is ingested as a separate "document", whose structure depends on the following:
  - `db_url` specifies the database URI including the type of database, host/port, username and password if needed.
    - For MySQL: "mysql://username:password@host:port/database"
    - For PostgreSQL:"postgresql://username:password@host:port/database"
    - For Microsoft SQL Server: "mssql+pyodbc://username:password@host:port/database"
    - For Oracle: "oracle+cx_oracle://username:password@host:port/database"
  - `db_table` the table name in the database
  - `select_condition` optional condition to filter rows in the table by
  - `doc_id_columns` defines one or more columns that will be used as a document ID, and will aggregate all rows associated with this
    value into a single Vectara document. The crawler will also use the content in these columns (concatenated) as the title for that row in the Vectara document. If this is not specified, the code will aggregate every `rows_per_chunk` (default 500) rows.
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
    mode: element
    file_path: "/path/to/Game_of_Thrones_Script.csv"
    select_condition: "Season='Season 1'"
    doc_id_columns: [Season, Episode]
    text_columns: [Name, Sentence]
    metadata_columns: ["Season", "Episode", "Episode Title"]
    column_types: []
    separator: ','
    sheet_name: "my-sheet"
    sheet_names: ["my-sheet"]
```
The csv crawler is similar to the database crawler, but instead of pulling data from a database, it uses a local CSV or XLSX file.
This has two modes: `element` or `table`
- In the `table` mode, the complete CSV table (or each named sheet if XLSX) is ingested into Vectara as a complete table
  Note that table size is limited to 10000 rows and 100 columns
- In the `element` mode, each row in the table is ingested as a separate "document", whose structure depends on the following:
  - `select_condition` optional condition to filter rows of the table. If applied only selected rows are included.
  - `doc_id_columns` defines one or more columns that will be used as a document ID, and will aggregate all rows associated with this
    value into a single Vectara document. This will also be used as the title. If this is not specified, the code will aggregate every `rows_per_chunk` (default 500) rows.
  - `text_columns` a list of column names that include textual information we want to use
  - `title_column` is an optional column name that will hold textual information to be used as title
  - `metadata_columns` a list of column names that we want to use as metadata
  - `column_types` an optional dictionary of column name and type (int, float, str). If unspecified, or for columns not included, the default type is str.
  - `separator` a string that will be used as a separator in the CSV file (default ',') (relevant only for CSV files)
- `sheet_names` a list of the sheets in the XLSX file to use (relevant only for XLSX files).
  if sheet_names is unspecified, all sheets are indexed.
- `mode`: element or table as specified above.

In the above example, the crawler would work in element mode as follows:
1. Read all the data from the local CSV file under `/path/to/Game_of_Thrones_Script.csv`
2. Group all rows that have the same values for both `Season` and `Episode` into the same Vectara document
3. Each such Vectara document that is indexed, will include several sections (one per row), each representing the textual fields `Name` and `Sentence` and including the meta-data fields `Season`, `Episode` and `Episode Title`.
4. Since this is a CSV file, sheet_names is ignored.

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
  scrape_method: playwright  # "playwright" (default) or "scrapy" - for article content extraction
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
- `scrape_method` defines the extraction backend for processing article content ("playwright" or "scrapy").

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
    scrape_method: playwright  # "playwright" (default) or "scrapy" - for docs content extraction
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
- `pos_regex` defines one or more (optional) regex patterns for URL inclusion. Uses the same matching behavior as website crawler (see regex documentation above)
- `neg_regex` defines one or more (optional) regex patterns for URL exclusion. Uses the same matching behavior as website crawler (see regex documentation above)
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
- `scrape_method` defines the extraction backend for processing documentation content ("playwright" or "scrapy").


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
    
    # Optional API configuration parameters
    api_version: "3"           # Default: "3" (Jira REST API version)
    api_endpoint: "search"     # Default: "search" (API endpoint)
    fields: "*all"             # Default: "*all" (fields to retrieve)
    max_results: 100           # Default: 100 (results per page)
    start_at: 0                # Default: 0 (starting index for pagination)
```

The JIRA crawler indexes issues and comments into Vectara. 
- `jira_base_url`: the Jira base_url
- `jira_username`: the user name that the crawler should use (`JIRA_PASSWORD` should be separately defined in the `secrets.toml` file)
- `jira_jql`: a Jira JQL condition on the issues identified; in this example it is configured to only include items from the last year.
- `api_version`: (optional) Jira REST API version to use (default: "3")
- `api_endpoint`: (optional) API endpoint to use for searching (default: "search")
- `fields`: (optional) Fields to retrieve from Jira issues (default: "*all" for all fields)
- `max_results`: (optional) Maximum number of results per API request (default: 100)
- `start_at`: (optional) Starting index for pagination (default: 0)
- `ssl_verify`: If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used. 
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


### HubSpot crawler

The unified HubSpot crawler supports two modes for different use cases:
- **Email mode** (`emails`): Lightweight crawling of email engagements only
- **CRM mode** (`crm`): Comprehensive crawling of all CRM data

#### Configuration

```yaml
crawling:
  crawler_type: hubspot

hubspot_crawler:
  hubspot_customer_id: "YOUR_CUSTOMER_ID"  # Required: Your HubSpot account ID
  mode: crm                                 # 'emails' or 'crm' (default: 'crm')

  # CRM mode specific options
  ray_workers: 4                            # Parallel workers: -1 (all CPUs), 0 (disable), or specific number
  start_date: "2024-01-01"                  # Optional: Filter data from this date (YYYY-MM-DD)
  end_date: "2024-12-31"                    # Optional: Filter data until this date (YYYY-MM-DD)
```

#### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `hubspot_customer_id` | string | required | Your HubSpot customer/portal ID (found in account URL) |
| `mode` | string | `"crm"` | Crawling mode: `"emails"` for email-only, `"crm"` for full CRM |
| `ray_workers` | integer | `0` | Number of parallel workers (CRM mode only):<br>• `-1`: Use all available CPUs<br>• `0`: Disable parallel processing<br>• `N`: Use N workers |
| `start_date` | string | none | Filter data from this date (format: YYYY-MM-DD) |
| `end_date` | string | none | Filter data until this date (format: YYYY-MM-DD) |

#### Mode Comparison

**Email Mode** (`mode: "emails"`):
- **Use Case**: Organizations only needing email communications indexed
- **Data Indexed**: Email engagements from contacts only
- **API Used**: Legacy Engagements V1 API for compatibility
- **Performance**: Sequential processing, suitable for smaller datasets

**CRM Mode** (`mode: "crm"`):
- **Use Case**: Organizations needing comprehensive CRM data for RAG applications
- **Data Indexed**:
  - Deals with associated company/contact context
  - Companies with business intelligence
  - Contacts with profile information
  - Support tickets with resolution status
  - All engagement types (emails, calls, meetings, notes, tasks)
- **API Used**: Modern CRM v3 API
- **Performance**: Ray-based parallel processing for large datasets
- **Features**:
  - Deal-focused extraction strategy
  - Hierarchical references between objects
  - Denormalized data for better search context
  - Date range filtering for incremental updates

#### Built-in Data Quality Features

The crawler automatically ensures data quality by:

**PII Protection**: All engagement content (emails, notes, meeting notes, call logs) is automatically processed through [Presidio](https://microsoft.github.io/presidio/analyzer/) to mask sensitive information including:
- Phone numbers, credit cards, email addresses
- Social security numbers, passport numbers
- Personal names and locations

**Smart Content Filtering**: Automatically skips empty or low-value content:
- Emails without body text
- Meeting invitations without notes or agenda
- Call logs without notes (only direction/duration)
- Tasks without description
- Notes with less than 20 characters

These features are always enabled to ensure high-quality, privacy-compliant data indexing.

#### Authentication

Both modes require `HUBSPOT_API_KEY` to be specified in the `secrets.toml` file:
```toml
HUBSPOT_API_KEY = "your-private-app-key"
```

#### Example Use Cases

1. **Sales Team RAG System** (CRM mode):
   ```yaml
   mode: crm
   ray_workers: 4
   ```

2. **Email Archive Search** (Email mode):
   ```yaml
   mode: emails
   ```

3. **Quarterly CRM Snapshot** (CRM mode with date filtering):
   ```yaml
   mode: crm
   start_date: "2024-01-01"
   end_date: "2024-03-31"
   ray_workers: -1
   ```


### Google Drive crawler

```yaml
...
  gdrive_crawler:
    # Authentication type: "service_account" (default) or "oauth"
    auth_type: service_account

    # Path to credentials.json file (used for both auth types)
    credentials_file: /path/to/credentials.json

    # Configuration parameters
    permissions: ['Vectara', 'all']
    days_back: 365
    ray_workers: 0

    # For service_account mode only
    delegated_users:
      - user1@example.com
      - user2@example.com
```

The gdrive crawler indexes content from Google Drive with support for two authentication methods:

**Common Parameters:**
- `days_back`: include only files modified within the last N days
- `permissions`: list of `displayName` values to include. We recommend including your company name (e.g. `Vectara`) and `all` to include all non-restricted files.
- `ray_workers`: 0 if not using Ray, otherwise specifies the number of Ray workers to use.
- `credentials_file`: Path to credentials JSON file (format depends on auth_type)

**Authentication Methods:**

**1. Service Account Mode (`auth_type: service_account`)** - Default
- Requires Google Workspace with domain-wide delegation
- Supports multiple users via `delegated_users` list
- `credentials.json` should contain service account credentials
- For setup instructions, see [Google documentation](https://developers.google.com/workspace/guides/create-credentials) under "Service account credentials"

**2. OAuth Mode (`auth_type: oauth`)**
- Use when you don't have Google Workspace domain-wide delegation
- Supports single user only (the user who authorized the app)
- `credentials.json` should contain OAuth token
- The token will be automatically refreshed when it expires

**OAuth Setup:**

Your `credentials.json` file for OAuth should look like this:
```json
{
  "token": "ya29.a0AfB_by...",
  "refresh_token": "1//0gXYZ...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "123456789-abc123def456.apps.googleusercontent.com",
  "client_secret": "GOCSPX-AbCdEfGhIjKlMnOpQrStUvWx",
  "scopes": ["https://www.googleapis.com/auth/drive.readonly"]
}
```

To generate the OAuth token:
1. Create OAuth 2.0 Client ID in Google Cloud Console (Desktop app type)
2. Download and save as `scripts/gdrive/oauth_client_credentials.json`
3. Run: `python scripts/gdrive/generate_oauth_token.py`
4. Authorize in the browser
5. The token is saved to `credentials.json` automatically

For detailed setup instructions, see: `docs/gdrive-oauth-setup.md`

**OAuth Configuration Example:**
```yaml
gdrive_crawler:
  auth_type: oauth
  credentials_file: credentials.json
  days_back: 7
  permissions: ['Vectara', 'all']
```

**Important Notes:**
- OAuth mode only supports a single user account
- For multi-user crawling, use `service_account` mode
- The OAuth token will auto-refresh and save itself when it expires
- Both authentication modes use the same `credentials_file` field


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

**Note**: The S3 crawler respects the `ssl_verify` setting from the `vectara` configuration section. If `ssl_verify: false` is set in your configuration, SSL certificate verification will be disabled for S3 connections as well. This is useful when connecting to S3-compatible services with self-signed certificates.

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

### SharePoint Crawler

```yaml
sharepoint_crawler:
  team_site_url: "https://yoursharepointdomain.sharepoint.com/sites/YourTeamSite"
  mode: "site"  # Options: 'site', 'folder', 'list'
  recursive: true
  auth_type: "user_credentials" # Options: 'user_credentials', 'client_credentials', 'client_certificate'
  allow_ntlm: true  # Enable NTLM authentication for on-premises SharePoint
  
  # Mode-specific configuration
  target_folder: "Shared Documents/TargetFolder"  # Required for 'folder' mode
  target_list: "MySharePointList"  # Required for 'list' mode
  
  # Library filtering (for 'site' mode)
  exclude_libraries: ["Form Templates", "Style Library"]
  
  # CSV/Excel processing configuration
  dataframe_processing:
    mode: "element"  # Options: 'element', 'table'
    # Element mode configuration (for row-by-row processing)
    doc_id_columns: ["Season", "Episode"]
    text_columns: ["Name", "Sentence"]
    metadata_columns: ["Season", "Episode", "Episode Title"]
    csv_encoding: "utf-8"
    sheet_names: ["Sheet1", "Data"]  # For Excel files, leave empty for all sheets
    
    # Table mode requires only the mode setting:
    # mode: "table"  # Processes entire CSV/Excel as single table document
  
  # Processing options
  cleanup_temp_files: true
  retry_attempts: 3
  retry_delay: 5
  list_item_metadata_properties: ["Title", "Author", "Modified"]
```

This Python crawler ingests documents from SharePoint sites and indexes them into Vectara. It supports both cloud and on-premises SharePoint instances with multiple authentication methods and crawling modes.

**Crawling Modes - Linear Explanation:**

**1. Site Mode (`mode: "site"`)**
- **What it does**: Discovers and crawls ALL document libraries in the SharePoint site
- **How it works**: 
  1. Connects to the SharePoint site
  2. Queries the Lists API to find all document libraries (BaseTemplate = 101)
  3. Filters out system libraries (Form Templates, Style Library, etc.)
  4. Crawls each library recursively (if `recursive: true`)
  5. Processes all files in each library
- **Use when**: You want to index everything in a SharePoint site
- **Configuration**: Only requires `team_site_url` and `mode: "site"`

**2. Folder Mode (`mode: "folder"`)**
- **What it does**: Crawls a specific SharePoint folder and its contents
- **How it works**:
  1. Connects to the SharePoint site
  2. Navigates to the specified `target_folder` path
  3. Lists all files in that folder (and subfolders if `recursive: true`)
  4. Downloads and processes each file
- **Use when**: You want to index only a specific folder (e.g., "Shared Documents/Project Files")
- **Configuration**: Requires `target_folder` path (e.g., "Shared Documents/MyFolder")

**3. List Mode (`mode: "list"`)**
- **What it does**: Crawls a SharePoint list and processes file attachments from list items
- **How it works**:
  1. Connects to the SharePoint site
  2. Queries the specified `target_list` for all items
  3. For each list item, checks if it has file attachments
  4. Downloads and processes each attachment file
  5. Extracts metadata from list item properties
- **Use when**: Your files are stored as attachments to list items (not in document libraries)
- **Configuration**: Requires `target_list` name and `list_item_metadata_properties`

**Authentication Options:**
- **`user_credentials`**: Username and password authentication (supports NTLM for on-premises)
- **`client_credentials`**: App-only authentication using client_id and client_secret
- **`client_certificate`**: Certificate-based authentication for enhanced security. Provide client_id, tenant_id, cert_thumbprint, cert_path, and optionally cert_passphrase

**Document Processing:**
- **Supported file types**: `.pdf`, `.md`, `.odt`, `.doc`, `.docx`, `.ppt`, `.pptx`, `.txt`, `.html`, `.htm`, `.lxml`, `.rtf`, `.epub`, `.csv`, `.xlsx`, `.xls`
- **System file filtering**: Automatically skips SharePoint system files, forms, and temporary files
- **CSV/Excel processing**: Special handling for structured data files with configurable column mapping

**CSV/Excel Processing Features:**

The SharePoint crawler provides two distinct modes for processing CSV and Excel files:

**Element Mode (`mode: "element"`):**
- Each row in the CSV/Excel file becomes a separate document in Vectara
- Configurable column mapping for document IDs, text content, and metadata
- Ideal for datasets where each row represents a distinct entity (e.g., customer records, product catalogs)
- Column configuration options:
  - `doc_id_columns`: Columns used to create unique document IDs (combines multiple columns if specified)
  - `text_columns`: Columns containing the main text content to be indexed
  - `metadata_columns`: Columns to be stored as document metadata
- Example: A customer database where each row becomes a separate customer document

**Table Mode (`mode: "table"`):**
- The entire CSV/Excel file (or individual sheets) is indexed as a single table document
- Preserves the tabular structure and relationships between data
- Requires `doc_processing` configuration with table parsing enabled
- Ideal for structured data where relationships between rows/columns are important
- Table size limitations: 10,000 rows and 100 columns maximum
- **Required configuration for table mode:**
  ```yaml
  doc_processing:
    parse_tables: true
    model: "openai"
    model_config:
      text: "gpt-4"
  ```

**Complete Configuration Examples:**

*Element Mode Configuration:*
```yaml
doc_processing:
  model: "openai"
  model_config:
    text: "gpt-4"

sharepoint_crawler:
  dataframe_processing:
    mode: "element"
    doc_id_columns: ["CustomerID"]
    text_columns: ["Name", "Description", "Notes"]
    metadata_columns: ["Category", "Region", "Date"]
```

*Table Mode Configuration:*
```yaml
doc_processing:
  parse_tables: true
  model: "openai"
  model_config:
    text: "gpt-4"

sharepoint_crawler:
  dataframe_processing:
    mode: "table"
    # No additional column configuration needed for table mode
```

**Library Management:**
- **System library exclusion**: Automatically skips built-in SharePoint libraries (Form Templates, Style Library, etc.)
- **Custom exclusions**: Configure additional libraries to exclude via `exclude_libraries`
- **Hidden library filtering**: Automatically skips hidden document libraries

**Configuration Parameters:**
- `team_site_url`: The URL of your SharePoint site
- `mode`: Crawling behavior - must be explicitly specified ('site', 'folder', or 'list')
- `recursive`: Set to true if subfolders should be crawled recursively
- `allow_ntlm`: Enable NTLM authentication for on-premises SharePoint instances
- `target_folder`: SharePoint folder path (required for 'folder' mode)
- `target_list`: SharePoint list name (required for 'list' mode)
- `exclude_libraries`: List of additional document libraries to skip during site crawling
- `cleanup_temp_files`: Remove temporary downloaded files after processing (default: true)
- `retry_attempts`: Number of retry attempts for failed SharePoint operations (default: 3)
- `retry_delay`: Delay in seconds between retry attempts (default: 5)

**Requirements:**
- **For element mode**: Requires `doc_processing` configuration with model settings
- **For table mode**: Requires `doc_processing` with `parse_tables: true` and model configuration
- Sensitive credentials should be stored in `secrets.toml`
- SSL verification should remain enabled in production environments



### PMC Crawler

```yaml
pmc_crawler:
  n_pmc_papers: 100
  search_query: "covid-19 treatment"
  num_per_second: 3
  scrape_method: playwright  # "playwright" (default) or "scrapy" - for web content extraction
```

The PMC (PubMed Central) crawler indexes medical research articles from PubMed Central into Vectara:
- `n_pmc_papers`: Maximum number of papers to index
- `search_query`: Search query to find relevant papers
- `num_per_second`: Rate limiting for API calls (default: 3)
- `scrape_method`: Extraction backend for processing article content ("playwright" or "scrapy")

### Arxiv Crawler

```yaml
arxiv_crawler:
  query_terms: "machine learning"
  n_papers: 50
  start_year: 2020
  scrape_method: scrapy  # "playwright" (default) or "scrapy" - for metadata extraction
```

The Arxiv crawler indexes academic papers from arXiv.org into Vectara:
- `query_terms`: Search terms to find relevant papers
- `n_papers`: Maximum number of papers to index
- `start_year`: Only index papers published after this year
- `scrape_method`: Extraction backend for processing web content ("playwright" or "scrapy")

## Other crawlers:

- `Edgar` crawler: crawls SEC Edgar annual reports (10-K) and indexes those into Vectara
- `fmp` crawler: crawls information about public companies using the [FMP](https://site.financialmodelingprep.com/developer/docs/) API
