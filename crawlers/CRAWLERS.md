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

**SAML-protected sites** (optional): the website crawler can authenticate via SAML before crawling. To enable, add a `saml_auth` block to `website_crawler` (an opaque config consumed by `crawlers/auth/saml_manager.py` — see that module for fields), and either embed `saml_username` / `saml_password` directly under `website_crawler` or — recommended — place `SAML_USERNAME` / `SAML_PASSWORD` in `secrets.toml`. SAML works with both `internal` and `scrapy` crawl methods; if SAML setup fails on the Scrapy path the crawler falls back to the internal crawler.

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
The database crawler reads from a relational database and indexes relevant columns into Vectara. Two modes are supported (selected via `mode`, default `"table"`):

- **`mode: table`** — the complete table is summarized and indexed as a single table document, truncated to at most `max_rows` × `max_cols` (defaults `500` × `20`; controlled by `max_rows`, `max_cols`, `truncate_table_if_over_max`).
- **`mode: element`** — each row is ingested into Vectara, with the following options:
  - `db_url`: the SQLAlchemy database URI including type/host/port/credentials.
    - MySQL: `mysql://username:password@host:port/database`
    - PostgreSQL: `postgresql://username:password@host:port/database`
    - Microsoft SQL Server: `mssql+pyodbc://username:password@host:port/database`
    - Oracle: `oracle+cx_oracle://username:password@host:port/database`
  - `db_table`: the table name to read from.
  - `select_condition`: optional SQL `WHERE` clause (string is interpolated into `SELECT … FROM <db_table> WHERE <select_condition>`). Use parameterized values you trust — this is concatenated into the SQL string.
  - `doc_id_columns`: one or more columns whose concatenated values group rows into the same Vectara document. If omitted, rows are chunked every `rows_per_chunk` rows.
  - `text_columns`: columns whose text is concatenated as the indexed body for each row.
  - `title_column`: optional column to use as the document-level title.
  - `use_title_for_doc_only` (default `false`): when `true`, `title_column` is used only as the doc title and not duplicated as a section title.
  - `metadata_columns`: columns to attach as metadata.
  - `column_types`: optional dict mapping column name to type (`int`, `float`, `str`).
  - `rows_per_chunk` (default `500`): chunk size when `doc_id_columns` is not set.

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
The huggingface crawler reads a Hugging Face dataset and indexes selected columns into Vectara. Unlike the database/csv crawlers, this crawler uses a simple per-row indexer (not the dataframe parser), so `mode`, `column_types`, and `use_title_for_doc_only` are not honored here.

- `dataset_name`: Hugging Face dataset name (e.g., `coeuslearning/hotel_reviews`).
- `split`: dataset split (e.g., `"train"`, `"test"`, `"corpus"`). Default: `"corpus"`.
- `select_condition`: optional simple `column='value'` filter (a naïve `key='value'` parser is used — no compound conditions or `df.query()` syntax).
- `start_row`: number of rows to skip from the start.
- `num_rows`: max number of rows to index (after `start_row`).
- `id_column`: optional column whose value is used as each row's document ID. Must be unique if specified.
- `text_columns`: columns whose text is concatenated as the indexed body.
- `title_column`: optional column to use as the per-row title.
- `metadata_columns`: columns to attach as metadata.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes across N workers, `-1` uses all CPU cores.

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
    select_condition: "Season=='Season 1'"
    doc_id_columns: [Season, Episode]
    text_columns: [Name, Sentence]
    metadata_columns: ["Season", "Episode", "Episode Title"]
    column_types: {Season: str, Episode: int}
    sheet_names: ["my-sheet"]
    # Table-mode tuning
    max_rows: 500
    max_cols: 20
    truncate_table_if_over_max: true
```

The CSV crawler is the file-based counterpart to the database crawler — it reads a local CSV/TSV/PSV/XLSX file and indexes it. The file type is determined by extension; the column separator is auto-detected from the extension (`.csv` → `,`, `.tsv` → tab, `.psv`/`.pipe` → `|`) and is **not** configurable. There are two modes:

- **`mode: table`** — the entire file (or each sheet if XLSX) is summarized and indexed as a single table document. Tables larger than `max_rows` × `max_cols` are truncated when `truncate_table_if_over_max` is `true`.
- **`mode: element`** — each row becomes part of a document, controlled by the column options below.

Element-mode columns:
- `select_condition`: optional pandas `df.query()`-style condition for filtering rows (e.g., `"Season=='Season 1'"`).
- `doc_id_columns`: one or more columns whose concatenated values group rows into the same Vectara document. If omitted, rows are chunked every `rows_per_chunk` rows.
- `text_columns`: columns whose text becomes the indexed body.
- `title_column`: optional column to use as the document title.
- `use_title_for_doc_only` (default `false`): when `true`, `title_column` is used only as the doc title and not duplicated as a section title.
- `metadata_columns`: columns to attach as metadata.
- `column_types`: optional dict mapping column name to type (`int`, `float`, `str`). Columns not listed default to `str`.

XLSX-only:
- `sheet_names`: list of sheet names to ingest. If omitted, all sheets are processed. (For CSV/TSV/PSV files, this is ignored.)

Shared limits/tuning (apply to both modes):
- `max_rows` (default `500`): truncation cap on rows in table mode; also default chunk size in element mode.
- `max_cols` (default `20`): truncation cap on columns in table mode.
- `truncate_table_if_over_max` (default `true`): if `false`, oversized tables are dropped instead of truncated.
- `rows_per_chunk` (default `500`): chunk size when `doc_id_columns` is not set in element mode.

In the example above, in element mode the crawler would: (1) read the CSV; (2) group rows that share both `Season` and `Episode` into the same Vectara document; (3) each document includes one section per row, with `Name` and `Sentence` as text and `Season`/`Episode`/`Episode Title` as metadata.

> **Note**: previous versions of this doc listed `separator` and `sheet_name` as options. Neither is read by the code — the separator is auto-detected from the extension, and only `sheet_names` (plural) is supported.

### Bulk Upload crawler

```yaml
...
bulkupload_crawler:
    json_path: "/path/to/file.json"
```

The Bulk Upload crawler reads a single JSON file containing an **array** of Vectara document objects (in the [Vectara file-upload document format](https://docs.vectara.com/docs/api-reference/indexing-apis/file-upload/format-for-upload#sample-document-formats)) and uploads each object to Vectara one at a time.

- `json_path`: local path to the JSON array file. Like `folder_crawler.path`, this path is bind-mounted into the Docker container automatically.

Each object in the array must include `id` and `sections` — entries missing either are skipped with a warning. The file must be a JSON array (a single object will be rejected).

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
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes URL fetching/indexing across N workers, `-1` uses all CPU cores.

### Hackernews crawler

```yaml
...
hackernews_crawler:
  max_articles: 1000
  days_back: 3
  days_back_comprehensive: false
```

The hackernews crawler can be used to crawl stories and comments from Hacker News.
- `max_articles` specifies a limit to the number of stories crawled.
- `days_back` (default `3`) specifies the number of days backward to crawl. By default the crawler walks the top/new/ask/show/best story lists, and only indexes stories where the story itself or any of its comments was published or updated in the last `days_back` days.
- `days_back_comprehensive` if `true`, the crawler performs a comprehensive search for ALL stories published within the last `days_back` days (slower).
- `ssl_verify`: If `False`, SSL verification is disabled (not recommended for production). If a string, it is treated as the path to a custom CA certificate file. If `True` or not provided, default SSL verification is used.
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
    max_depth: 3            # only when crawl_method: scrapy
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
- `max_depth` is the BFS depth limit when `crawl_method: scrapy`. Default: `3`. **Not honored by the internal crawler**, which traverses unbounded.
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

The Discourse forums crawler iterates the site's `/latest.json` endpoint and indexes each topic (with all of its posts) as a single document.

- `base_url`: home page of the Discourse forum to crawl.
- `ssl_verify`: see standard SSL handling.

Place `DISCOURSE_API_KEY` in `secrets.toml`. The crawler authenticates via `api_key` plus `api_username` query parameters; the `api_username` is currently hardcoded in the source — this is something to be aware of if you want to crawl as a non-default user.

### Mediawiki crawler

The mediawiki crawler can crawl content in any MediaWiki-powered website (Wikipedia or otherwise) by walking the link graph from one or more seed pages and indexing each page's plain-text extract into Vectara.

```yaml
...
  mediawiki_crawler:
    api_url: "https://en.wikipedia.org/w/api.php"
    source_urls:
      - "https://en.wikipedia.org/wiki/Information_retrieval"
      - "https://en.wikipedia.org/wiki/Vector_database"
    depth: 2
    n_pages: 500
```

Starting from the page titles in `source_urls`, the crawler does a BFS over outgoing article links (namespace 0 only) up to `depth` hops, indexing up to `n_pages` pages total. Traversal is restricted to the same domain as each seed URL.

- `api_url`: base URL of the wiki's `api.php` endpoint (e.g. `https://en.wikipedia.org/w/api.php`).
- `source_urls`: list of full wiki page URLs to start from. The crawler extracts the page title from each URL's path.
- `depth`: maximum BFS depth from the seed pages (`0` = only seeds).
- `n_pages`: maximum number of pages to index (capped at 1000 internally).
- `ssl_verify`: optional, see standard SSL handling.

A bearer token must be provided at the top level of the config as `mediawiki_api_key` (read at the root of `cfg`, not inside `mediawiki_crawler`); place it in `secrets.toml` as `MEDIAWIKI_API_KEY`. The crawler also sleeps 1 second between requests for polite crawling (not configurable).

### GitHub crawler

```yaml
...
  github_crawler:
    owner: "vectara"
    repos: ["getting-started", "protos", "slackbot", "magazine-search-demo", "web-crawler", "Search-UI", "hotel-reviews-demo"]
    crawl_code: false
    num_per_second: 2
```

The GitHub crawler indexes issues, pull requests, and their comments from one or more GitHub repositories into Vectara, and optionally the source code.

- `owner`: GitHub repository owner (org or user).
- `repos`: list of repository names (under `owner`) to crawl.
- `crawl_code`: when `true`, also recursively walks the repository tree and indexes individual source files. Default: `false` (issues + PRs only).
- `num_per_second`: rate limit for GitHub API calls. **Default: `2`** (do not exceed without a token).
- `github_token` (optional): GitHub Personal Access Token. Can be set here directly, or — recommended — placed in `secrets.toml` as `GITHUB_TOKEN` so the value is not committed. See [GitHub docs](https://docs.github.com/en/enterprise-server@3.10/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) for how to create one. Without a token you will hit GitHub's anonymous rate limits very quickly.

### Jira crawler

```yaml
...
  jira_crawler:
    jira_base_url: "https://vectara.atlassian.net/"
    jira_username: ofer@vectara.com
    jira_jql: "created > -365d"
    
    # Optional API configuration parameters
    api_version: "3"                       # Default: "3" (Jira REST API version)
    api_endpoint: "search"                 # Default: "search" (API endpoint)
    fields: "*all"                         # Default: "*all" (fields to retrieve)
    max_results: 100                       # Default: 100 (results per page)
    start_at: 0                            # Default: 0 (starting index for pagination)

    # Optional attachment processing
    include_image_attachments: true        # Default: true
    include_document_attachments: false    # Default: false
```

The JIRA crawler indexes issues, comments, and (optionally) attachments into Vectara.
- `jira_base_url`: the Jira base URL.
- `jira_username`: the account email used for HTTP Basic Auth. The matching API token must be defined as `JIRA_PASSWORD` in `secrets.toml`.
- `jira_jql`: a JQL expression selecting the issues to index (e.g., `"created > -365d"` for the last year).
- `api_version`: Jira REST API version. Default: `"3"`.
- `api_endpoint`: search endpoint to call. Default: `"search"`.
- `fields`: fields to retrieve from each issue. Default: `"*all"`.
- `max_results`: results per page. Default: `100`.
- `start_at`: starting index for pagination. Default: `0`.
- `include_image_attachments`: when `true` (default), downloads image attachments and indexes them. Image-to-text descriptions require `doc_processing.summarize_images` to be enabled at the top level.
- `include_document_attachments`: when `true`, downloads document attachments (PDF, Office files, etc.). Default: `false`.
- `ssl_verify`: see standard SSL handling.

The crawler also parses Atlassian Document Format (ADF) for rich-text fields so descriptions/comments retain their plain-text content.
### Confluence crawler

```yaml
  confluence_crawler:
    confluence_base_url: "https://vectara.atlassian.net/wiki"
    confluence_username: "<email>"
    confluence_password: "<api-token>"
    confluence_cql: 'space = "TEST" and LastModified > now("-365d") and type IN (blogpost, page)'
    confluence_include_attachments: true
```

This crawler pulls content from an Atlassian Confluence Cloud instance and indexes it into Vectara. It queries Confluence using a [CQL query](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/), retrieves matching pages and blog posts (and their attachments if configured), and extracts metadata (labels, authors, space, version history). For Confluence Data Center / on-prem, see the **Confluence Data Center crawler** below.

- `confluence_base_url`: base URL of the Confluence Cloud wiki (e.g., `https://yourcompany.atlassian.net/wiki`).
- `confluence_username`: account email for HTTP Basic Auth. Required.
- `confluence_password`: an Atlassian **API token** (not your account password). Required. Place in `secrets.toml` (`CONFLUENCE_USERNAME`, `CONFLUENCE_PASSWORD`) so they are not committed.
- `confluence_cql`: a [CQL](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/) expression selecting the content to crawl.
- `confluence_include_attachments`: when `true`, downloads each page's attachments (PDF/DOCX/PPTX/CSV/XLSX/etc.) and indexes them as separate documents.
- `ssl_verify`: If `False`, SSL verification is disabled (not recommended for production). If a string, treated as a path to a custom CA certificate file. Default: `True`.

**Notes on behavior:** the crawler resolves author/owner account IDs to display names via additional API calls (transparent but adds round-trips). Search pagination is fixed at 25 results per page in the code.

### Confluence Data Center crawler

```yaml
crawling:
  crawler_type: confluencedatacenter

confluencedatacenter:
  base_url: "http://confluence.internal:8090"
  # Auth — use ONE of:
  #  (a) basic auth:
  confluence_datacenter_username: "<username>"
  confluence_datacenter_password: "<password>"
  #  (b) Personal Access Token (takes precedence if set):
  # confluence_datacenter_pat: "<token>"
  confluence_cql: 'space = "TEST" and type IN (page, blogpost)'

  confluence_include_attachments: true
  include_image_attachments: true
  include_document_attachments: true
  body_view: "export_view"
  limit: 25

  # Optional: route CSV/Excel attachments through the dataframe parser
  dataframe_processing:
    mode: "element"
```

This crawler is the on-prem / self-hosted counterpart of the Confluence (Cloud) crawler. It targets a Confluence Data Center instance via its REST API, using either HTTP Basic Auth or a Personal Access Token (PAT). Note: the YAML key is `confluencedatacenter` (not `confluencedatacenter_crawler`), and `crawling.crawler_type: confluencedatacenter`.

- `base_url`: base URL of your Confluence Data Center instance (e.g., `http://confluence.internal:8090`).
- Authentication — provide **one** of the following:
  - `confluence_datacenter_username` / `confluence_datacenter_password`: HTTP Basic Auth credentials.
  - `confluence_datacenter_pat`: a [Personal Access Token](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html), sent as `Authorization: Bearer <token>`. Use this for SSO/SAML-enforced instances where basic auth is disabled. If both a PAT and basic-auth credentials are set, the PAT takes precedence.
  - Place credentials in `secrets.toml` so they are not committed. The keys must be `CONFLUENCE_DATACENTER_USERNAME`, `CONFLUENCE_DATACENTER_PASSWORD`, and/or `CONFLUENCE_DATACENTER_PAT` (note the underscore between `CONFLUENCE` and `DATACENTER` — without it the value is not mapped to this crawler).
- `confluence_cql`: a [CQL](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/) query selecting the content to crawl.
- `confluence_include_attachments`: when `true`, also indexes attachments. Default: `false`.
- `include_image_attachments`: process image attachments (PNG/JPG/etc.). Default: `false`. Image-to-text descriptions require `doc_processing.summarize_images` at the top level.
- `include_document_attachments`: process document attachments (PDF/DOCX/PPTX/etc.). Default: `true`.
- `body_view`: which Confluence body view to fetch. Default: `"export_view"`. Options: `export_view`, `styled_view`, `storage`, `editor`.
- `limit`: page size for the search API. Default: `25`.
- `dataframe_processing`: optional dataframe-parser config applied to CSV/XLSX attachments. Same shape as in the SharePoint and CSV crawlers (`mode`, `doc_id_columns`, `text_columns`, `metadata_columns`, etc.).
- `ssl_verify`: see standard SSL handling.

Each indexed document gets metadata for `type` (page/blogpost/attachment), `id`, `title`, `source` (`"Confluence"` by default, overridable via the `source` config key), `last_updated`, `version`, `updated_by` (whichever of `username`/`userKey`/`displayName`/`accountId` the instance returns), `space` (id/key/name), and `url`. Attachments additionally get `filename` and `attachment_type`, and their `source` is set to `"confluence_attachment"`.

### Twitter crawler

```yaml
...
  twitter_crawler:
    twitter_bearer_token: "<bearer-token>"  # see https://developer.twitter.com/en/docs/twitter-api/getting-started/getting-access-to-the-twitter-api
    userhandles: ["vectara"]
    num_tweets: 100
    clean_tweets: true
```

The Twitter crawler indexes recent tweets that **mention** each given user handle (one document per handle, one section per tweet). Retweets are excluded from the search.

- `twitter_bearer_token`: Twitter API bearer token (the YAML key is `twitter_bearer_token`, not `bearer_token`).
- `userhandles`: list of user handles whose mentions to pull.
- `num_tweets`: number of recent mentions to fetch per handle.
- `clean_tweets`: if `true` (default), strips usernames/handles from tweet text.


### Notion crawler

To set up Notion, create a [Notion integration](https://www.notion.so/help/create-integrations-with-the-notion-api) and [share the pages](https://www.notion.so/help/add-and-manage-connections-with-the-api) you want indexed with that integration.

```yaml
...
  notion_crawler:
    remove_old_content: false
    crawl_report: false
    output_dir: vectara_ingest_output
```

The Notion crawler discovers all pages reachable by the integration via the Notion `search` API, fetches each page's block tree, and indexes the text content. Child pages (`child_page` blocks) are skipped during recursion to avoid duplicate indexing — they are picked up directly via `search`.

- `remove_old_content`: if `true`, removes any document that currently exists in the corpus but is NOT in this crawl. CAUTION: this removes data from your corpus.
- `crawl_report`: if `true`, writes a `pages_indexed.txt` file under `output_dir` listing the pages indexed.
- `output_dir`: directory for the crawl report. Default: `vectara_ingest_output`.

You must place `NOTION_API_KEY` (the integration's secret) in `secrets.toml`.


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

    # Crawl-time filters
    days_back: 7
    # Optional crawl-time displayName gate (default: unset, i.e. no filter).
    # When set, files are kept only if a permission's displayName matches.
    # permission_display_filter: ['Vectara', 'all']

    # Optional: restrict the crawl to a folder subtree
    # root_folder: https://drive.google.com/drive/folders/<folder_id>

    # Optional: parallelize across delegated users with Ray
    ray_workers: 0

    # For service_account mode only
    delegated_users:
      - user1@example.com
      - user2@example.com

    # Optional: emit ACL metadata for query-time access control
    abac:
      enabled: false
      resolve_inherited: false
      include_anyone: true
      fetch_labels: false
```

The gdrive crawler indexes content from Google Drive with support for two authentication methods.

**Common Parameters:**
- `auth_type`: `service_account` (default) or `oauth`. See "Authentication Methods" below.
- `credentials_file`: path to the credentials JSON file. The exact contents depend on `auth_type` (service-account JSON vs. OAuth token JSON).
- `days_back`: include only files modified within the last N days. **Default: 7.**
- `permission_display_filter`: optional list of permission `displayName` values to include. When set, a file is indexed only if at least one of its Drive permissions has a matching `displayName` (a typical pattern would be your company name plus `all` to admit files shared with `anyone`/the whole organization, since those grants are surfaced with `displayName: "all"`). **Default: unset (no filter)** — every file the delegated user can read flows through; use ABAC metadata for access control. Set to `null` or `[]` explicitly to disable. The legacy key `permissions` is still honored but deprecated — rename it to `permission_display_filter`.
- `root_folder` (optional): restrict the crawl to one or more subtrees. Accepts either a single Drive folder URL/id or a list of them, so a config can mix a My-Drive folder with a Shared Drive id in one run. Shared Drive ids are accepted (e.g. `https://drive.google.com/drive/folders/0AJb-TGGUWsU4Uk9PVA`). When unset, the crawler sweeps `root`, `sharedWithMe`, and files owned/shared with each delegated user. `days_back` still applies to leaf files; subfolders are always traversed so old folders containing recent files are not missed. Shortcuts inside a subtree are not followed, so the crawl stays strictly within the chosen folders. A file reachable from more than one configured root is indexed once.
- `ray_workers`: `0` to disable Ray (default), `>0` to parallelize across `delegated_users` with that many Ray workers, `-1` to use all cores. Only meaningful for service-account mode with multiple users.

**Authentication Methods:**

**1. Service Account Mode (`auth_type: service_account`)** — default
- Requires Google Workspace with domain-wide delegation.
- Supports multiple users via `delegated_users` list — the crawler impersonates each one in turn.
- `credentials_file` must point at a service-account JSON key.
- For setup instructions, see [Google documentation](https://developers.google.com/workspace/guides/create-credentials) under "Service account credentials".

**2. OAuth Mode (`auth_type: oauth`)**
- Use when you don't have Google Workspace domain-wide delegation.
- Supports a single user only (the user who authorized the app); `delegated_users` is ignored.
- `credentials_file` must point at an OAuth token JSON (see format below).
- The token is automatically refreshed and re-saved to `credentials_file` when it expires.

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

For detailed setup instructions, see: `docs/gdrive-oauth-setup.md`.

**OAuth Configuration Example:**
```yaml
gdrive_crawler:
  auth_type: oauth
  credentials_file: credentials.json
  days_back: 7
  # permission_display_filter: ['<your company>', 'all']   # opt-in; default is no filter
```

**Attribute-Based Access Control (ABAC):**

When `abac.enabled: true`, every indexed document is tagged with filterable ACL fields derived from the file's Drive permissions. The corpus admin must register these as filter attributes on the Vectara corpus before ABAC filter queries will work. List-valued fields should be registered as `Text List` so membership filters (`'x' IN doc.field`) work.

| Metadata field    | Type      | Meaning                                                                                  |
|-------------------|-----------|------------------------------------------------------------------------------------------|
| `acl_owners`      | Text List | Email addresses with the `owner` role.                                                   |
| `acl_readers`     | Text List | Emails with read-or-above access (`reader`, `commenter`, `writer`, `fileOrganizer`, `organizer`). |
| `acl_groups`      | Text List | Group emails granted access. **Resolution to individual members is the query layer's responsibility** — the crawler does not expand group membership, so look up the requesting user's transitive groups at query time and OR each one against `acl_groups`. This avoids stale-membership leaks on group removal. |
| `acl_domains`     | Text List | Domains granted access (e.g. `example.com`).                                             |
| `acl_is_public`   | Boolean   | `true` if the file is shared with `type=anyone` (and `include_anyone` is true).          |
| `acl_is_org_wide` | Boolean   | `true` if any domain grant is present.                                                   |
| `acl_labels`      | Text List | Drive Labels as `<LabelTitle>=<Value>` strings (only populated when `fetch_labels: true`). |
| `acl_source`      | Text      | Provenance of the ACL: `shared_drive`, `shared_drive_partial`, `my_drive_direct`, `my_drive_resolved`, or `my_drive_partial`. `shared_drive` and `my_drive_resolved` reflect a complete ACL; the two `*_partial` values mean Drive returned a permission error during inheritance resolution and the recorded grants may be incomplete; `my_drive_direct` is by design partial when `resolve_inherited: false`. |

**ABAC sub-options:**
- `abac.enabled`: emit `acl_*` metadata on every indexed document. Default: `false`.
- `abac.resolve_inherited`: My Drive files don't receive inherited permissions via the API. When `true`, the crawler walks each file's parent folders and unions their ACLs (folder lookups are cached per worker; adds API round-trips). Shared Drive files are handled separately and unconditionally: Drive's `files.list` does **not** propagate Shared Drive member grants onto a file's `permissions` array, so the crawler issues one `permissions.list(fileId=<driveId>)` per drive (cached per worker) and merges those members into each file's ACL. This call requires the delegated user to have at least the `fileOrganizer` role on the drive; otherwise Drive returns 403 and the crawler tags the affected files `acl_source: shared_drive_partial` so operators can spot the gap. Default: `false`.
- `abac.include_anyone`: treat `type=anyone` grants as public (sets `acl_is_public=true`). Default: `true`.
- `abac.fetch_labels`: fetch Drive Labels per file and store them in `acl_labels`. Adds one round-trip per file plus one definitions fetch per worker, and requires the `drive.labels.readonly` OAuth scope (added automatically when this flag is on). Default: `false`.
- `abac.shared_drive_admin_access`: issue the Shared Drive membership listing (`permissions.list` on the `driveId`) with `useDomainAdminAccess=true`. Use this when the delegated user is a Workspace domain admin but does not hold a `fileOrganizer`/organizer role on the shared drives being crawled; without it those listings return 403 and the affected files are tagged `acl_source: shared_drive_partial` with empty `acl_groups`. Default: `false`.

**Important Notes:**
- OAuth mode only supports a single user account; for multi-user crawling, use `service_account` mode.
- Both authentication modes use the same `credentials_file` field, but the file's contents differ.
- The OAuth token auto-refreshes and is rewritten back to `credentials_file` when it expires.
- Audio, video, archives, executables, and source-code-style text files are skipped by mime type. Standalone images are skipped unless `doc_processing.summarize_images` is enabled.

**Filter Pipeline:**

Each file passes through several gates between Drive and the indexer. A drop at any stage is logged at INFO with the file name, id, mime type, and reason; a per-user summary line of the form `gdrive filter summary for user=<u> :: listed=N display_name_dropped=N cache_skipped=N mime_dropped=N unsupported_ext_dropped=N download_failed=N index_error=N indexed=N` is emitted when the user is done. The stages, in order:

1. **Drive API query** — server-side `trashed=false AND modifiedTime > now - days_back`. Files outside the window are never returned by Drive and so are not counted.
2. **`permission_display_filter`** — optional. When set, keeps a file only if some permission's `displayName` matches the allowlist. **Default: unset (no filter).** Use this only for legacy gating; prefer ABAC metadata + query-time filters for new deployments.
3. **Shared cache** — when multiple `delegated_users` are crawled, the second-seen user skips files already indexed by the first.
4. **MIME prefix blocklist** — `audio*`, `video*`, folders, `application/x-adobe-indesign`, `application/zip`, `application/x-rar-compressed`, `application/x-7z-compressed`, `application/x-executable`, `text/php|javascript|css|xml|x-sql|x-python-script`, and `image*` unless `doc_processing.summarize_images: true`.
5. **Extension allowlist (post-download)** — file is rejected unless it's a dataframe (`.csv`, `.tsv`, `.psv`, `.pipe`, `.xls`, `.xlsx` — see `supported_by_dataframe_parser` in `core/dataframe_parser.py`) or extension is in `{.doc, .docx, .ppt, .pptx, .pdf, .odt, .txt, .html, .md, .rtf, .epub, .lxml}` (plus image extensions when `summarize_images` is on).
6. **Download/export** — files whose Drive download or Workspace export fails (e.g. `exportSizeLimitExceeded` with no PDF fallback) are counted as `download_failed`.
7. **Indexing** — `indexer.index_file` returning `False` or raising is counted as `index_error`; success is counted as `indexed`.


### Folder crawler

```yaml
...
  folder_crawler:
    path: "/Users/ofer/Downloads/some-interesting-content/"
    extensions: ['.pdf']
    source: 'my-folder'
    metadata_file: 'metadata.csv'   # relative to `path` (e.g. 'subdir/meta.csv'); must NOT be absolute
    num_per_second: 10
    ray_workers: 0
```

The folder crawler walks a local folder **recursively** (`os.walk`) and indexes every file whose extension matches `extensions`. CSV/Excel files are routed through the dataframe parser (configurable via a `dataframe_processing` section, just like the SharePoint and Confluence crawlers).

- `path`: local folder to crawl. The path is bind-mounted into the Docker container at `/home/vectara/data` automatically.
- `extensions`: list of file extensions to include. Use `["*"]` (the default if omitted) to include every file regardless of extension.
- `source`: string added to each file's metadata under the `"source"` field.
- `metadata_file`: optional CSV file for per-file metadata, given as a **relative path under `path`** (e.g. `metadata.csv` or `subdir/meta.csv`) — absolute paths will not resolve correctly. Each row needs a `filename` column matching a file in the folder; the remaining columns become metadata. The metadata file is itself excluded from indexing.
- `num_per_second`: rate limit when indexing files in parallel. Default: `10`.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes indexing across N workers, `-1` uses all CPU cores.

The crawler also auto-attaches `created_at`, `last_updated`, `file_size`, `parent_folder`, and `folder_path` metadata to every indexed file.

### S3 crawler

```yaml
...
  s3_crawler:
    s3_path: s3://my-bucket/files
    extensions: ['*']
    # Optional: AWS credentials (otherwise standard boto3 credential chain is used)
    aws_access_key_id: "<AKIA...>"
    aws_secret_access_key: "<secret>"
    # Optional: custom endpoint for S3-compatible services (MinIO, Wasabi, R2, etc.)
    endpoint_url: "https://s3.us-east-1.amazonaws.com"
    num_per_second: 10
    ray_workers: 0
    source: "S3"
```

The S3 crawler indexes content under a given S3 path. AWS credentials are picked up from the standard boto3 chain (env vars, profile, IAM role) unless explicitly provided in config.

- `s3_path`: S3 URI of the form `s3://bucket/prefix` whose files should be indexed.
- `extensions`: list of file extensions to include. Use `['*']` to include every file regardless of extension.
- `metadata_file`: optional CSV file under the same `s3_path` providing per-file metadata. Each row needs a `filename` column matching an object key; remaining columns become metadata. The metadata file itself is excluded from indexing.
- `aws_access_key_id` / `aws_secret_access_key`: optional, **must be set together or both omitted**. When set, used directly. Otherwise, the standard boto3 credential chain applies (env vars `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, shared config `~/.aws/credentials`, IAM role / EC2 instance metadata). If no credentials resolve, boto3 raises `NoCredentialsError` on the first S3 call.
- `endpoint_url`: optional. Use for S3-compatible services (MinIO, Cloudflare R2, Wasabi, etc.). When omitted, boto3 talks to AWS S3 directly.
- `num_per_second`: rate limit when downloading/indexing. Default: `10`.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes across N workers, `-1` uses all CPU cores.
- `source`: source label attached to each document's metadata. Default: `"S3"`.

**SSL note:** the crawler respects `vectara.ssl_verify`. If set to `false`, SSL verification is disabled for S3 calls (useful for self-signed S3-compatible endpoints). If set to a string, the path is `~`-expanded and used as a CA bundle.

### Youtube crawler

```yaml
...
  yt_crawler:
    playlist_url: "<some-youtube-playlist-url>"
    num_videos: 50
    merge_subtitles_gap: 0.5
    max_subtitle_duration: 30.0
```

The YouTube crawler iterates videos from a playlist. For each video it first tries the YouTube transcript API (English subtitles only — language is hardcoded), and falls back to downloading the audio and transcribing it locally with Whisper if no transcript is available. Adjacent subtitle entries are merged together so the indexed text reads more naturally.

- `playlist_url`: YouTube playlist URL.
- `num_videos`: maximum number of videos to process from the playlist. Optional — when omitted, the entire playlist is processed.
- `merge_subtitles_gap`: max gap (in seconds) between adjacent subtitle entries before they are merged into a single segment. Default: `0.5`.
- `max_subtitle_duration`: maximum duration (in seconds) of a merged subtitle segment before it is split. Default: `30.0`.

The Whisper model used for the audio fallback is taken from the top-level `vectara.whisper_model` config (e.g., `"base"`, `"small"`, `"medium"`, `"large"`); see the main README for that setting.

### Slack crawler

```yaml
...
slack_crawler:
  days_past: 30
  channels_to_skip: ["alerts"]
  retries: 5
  ray_workers: 0
  workspace_url: "https://vectara.slack.com"
```

The Slack crawler walks every channel the bot has joined and indexes each message (with its threaded replies merged in). Bot user IDs are resolved to display names so the indexed text reads naturally; bot-message attachments are indexed when the main message text is empty.

- `days_past`: only index messages newer than N days.
- `channels_to_skip`: list of channel names to exclude (filtered after enumeration — this isn't an API-level filter).
- `retries`: number of retries on rate-limit (HTTP 429) and `IncompleteRead` errors. Default: `5`.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes message indexing across N workers, `-1` uses all CPU cores.
- `workspace_url`: workspace URL used to construct message permalinks for metadata. Default: `"https://vectara.slack.com"`.

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
  servicenow_username: "<username>"
  servicenow_password: "<password>"
  servicenow_process_attachments: true
  servicenow_pagesize: 100
  servicenow_query: "workflow_state=published"
  servicenow_ignore_fields: ['text', 'short_description']
```

This crawler indexes articles (and optional file attachments) from a ServiceNow Knowledge Base into [Vectara](https://vectara.com). It uses the [ServiceNow Table API](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_TableAPI) to fetch records from the `kb_knowledge` table (this is hardcoded — the table is **not** a configurable option) and indexes each article's HTML content. If enabled, it then retrieves attachments via the [Attachment API](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_AttachmentAPI) and indexes them as separate documents.

- `servicenow_instance_url`: base URL of the ServiceNow instance (e.g., `https://dev12345.service-now.com/`).
- `servicenow_username` / `servicenow_password`: HTTP Basic Auth credentials. Required. Place them in `secrets.toml` (`SERVICENOW_USERNAME`, `SERVICENOW_PASSWORD`) so they are not committed to YAML.
- `servicenow_process_attachments`: when `true`, also retrieves and indexes file attachments. Required.
- `servicenow_pagesize`: page size for the article-listing API call. Default: `100`.
- `servicenow_query`: optional `sysparm_query` string for filtering KB articles (e.g., `workflow_state=published`).
- `servicenow_ignore_fields`: optional set of article field names to drop from the indexed metadata. Default: `{'text', 'short_description'}` — the article body and title are already captured separately, so they're excluded from metadata.
- `ssl_verify`: If `False`, SSL verification is disabled (not recommended for production). If a string, treated as a path to a custom CA certificate file. Default: `True`.

> **Note**: previous versions of this doc listed `servicenow_table` and `servicenow_batch_size`. Neither is read by the code — the table is hardcoded to `kb_knowledge`, and pagination is controlled by `servicenow_pagesize`.

- **[Table API Reference](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_TableAPI)**  
  Contains details on the various endpoints, query parameters, and usage examples for retrieving data from ServiceNow tables.
- **[Attachment API Reference](https://developer.servicenow.com/dev.do#!/reference/api/rome/rest/c_AttachmentAPI)**  
  Covers how to list and download attachments from ServiceNow records.

### Wolken KB crawler

```yaml
...
  wolken_crawler:
    api_endpoint: "https://api-mycompany.wolkenservicedesk.com"
    domain: "mycompany"
    client_id: "your-client-id"
    service_account: "service@mycompany.com"
    auth_code: "Basic ..."
    refresh_token: "your-refresh-token"

    batch_size: 100
    # kb_source_id: 1
    content_fields:
      - introduction
      - cause
      - environment
      - resolution
      - additionalInfo
```

The Wolken KB crawler indexes Knowledge Base articles from a [Wolken ServiceDesk](https://www.wolkensoftware.com/) instance using the [public Wolken KB REST API](https://developer-beta.wolkensoftware.com/kb/docs.html). It authenticates via OAuth2 refresh-token flow, walks every KB category, and for each article fetches the full details and indexes them as a structured document in Vectara (one section per content field). The access token is auto-refreshed on expiry and on `401` responses.

**Authentication parameters** (all required; obtain from your Wolken administrator):
- `api_endpoint`: base URL of your Wolken instance (e.g. `https://api-mycompany.wolkenservicedesk.com`).
- `domain`: Wolken tenant domain name, sent as the `domain` header.
- `client_id`: OAuth client ID, sent as the `clientId` header.
- `service_account`: service-account email, sent as the `serviceAccount` header.
- `auth_code`: full Basic-auth header value used against the token endpoint (e.g. `Basic dXNlcjpwYXNz`). The crawler sends it verbatim as the `Authorization` header — include the `Basic ` prefix.
- `refresh_token`: OAuth refresh token; exchanged for an access token at `/wolken-secure/oauth/token`.

These can also be supplied via `secrets.toml` using the `WOLKEN_` prefix (e.g. `WOLKEN_REFRESH_TOKEN`); the prefix is stripped and lowercased to map onto `wolken_crawler.*`.

**Crawl parameters:**
- `batch_size`: page size for paginated category and article listings. Default: `100`.
- `kb_source_id` (optional): when set, restricts category listing to a single KB source via the `kbSourceId` query parameter. Default: unset (all sources).
- `content_fields`: ordered list of fields read from each article's `articleOtherInfo`. Each non-empty field becomes a separate section in the indexed document, with the field's human title used as the section title. Available values: `introduction`, `cause`, `environment`, `resolution`, `additionalInfo`, `internalNotes`. Default: `[introduction, cause, environment, resolution, additionalInfo]`. If none of the configured fields contain text, the crawler falls back to the article's `description` and `summary`.

**Indexed document shape:**
- Document ID: `wolken-kb-{articleId}` (stable, so `reindex: false` skips already-indexed articles).
- Title: the article's `articleTitle`.
- Sections: one per non-empty content field, with HTML stripped and whitespace collapsed.
- Metadata: `source` (`"wolken_kb"`), `article_id`, `category`, `created_time`, `updated_time`, `status_id`, `validation_status_id`, `published_date`, and `url` (when the article exposes `articleUrlName`).

For step-by-step setup, secrets-file usage, and the full API reference, see [`docs/wolken-kb-setup.md`](../docs/wolken-kb-setup.md).

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

**Authentication Options** (all credentials should live in `secrets.toml`, not the YAML config):
- **`user_credentials`**: requires `username` + `password`. Supports NTLM for on-premises (`allow_ntlm: true`).
- **`client_credentials`**: app-only auth. Requires `client_id` + `client_secret`.
- **`client_certificate`**: certificate-based auth. Requires `client_id`, `tenant_id`, `cert_thumbprint`, `cert_path`, and optionally `cert_passphrase`.
- `auto_refresh_session` (default `true`): when `true`, the crawler retries on a 401 by re-acquiring a session before failing.

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
  topics:
    - "covid-19 treatment"
    - "long covid"
  n_papers: 100
  num_per_second: 3
  index_medline_plus: false
  scrape_method: playwright  # "playwright" (default) or "scrapy" - for web content extraction
```

The PMC (PubMed Central) crawler indexes medical research articles from PubMed Central into Vectara. For each topic in `topics`, it queries the NCBI E-utilities to find up to `n_papers` matching papers and indexes their content.

- `topics`: list of search query strings. The crawler indexes papers per topic, so a list with one entry is fine.
- `n_papers`: maximum number of papers to index **per topic**.
- `num_per_second`: rate limiting for NCBI/web calls. Default: `3`.
- `index_medline_plus`: when `true`, also indexes related MedlinePlus consumer-health pages for each topic. Default: `false`.
- `scrape_method`: extraction backend for processing article content (`"playwright"` or `"scrapy"`).
- `ssl_verify`: optional, see standard SSL handling.

### Arxiv Crawler

```yaml
arxiv_crawler:
  arxiv_category: "cs"
  query_terms: ["machine", "learning"]
  n_papers: 50
  start_year: 2020
  sort_by: "date"             # "date" or "citations"
  scrape_method: scrapy        # "playwright" (default) or "scrapy"
```

The Arxiv crawler queries the arXiv API and indexes matching papers into Vectara.

- `arxiv_category`: arXiv category code (e.g., `"cs"`, `"math"`, `"physics"`, or a sub-category like `"cs.IR"`). **Required.** The crawler validates this against the official category list and exits if unknown.
- `query_terms`: list of search terms (each is wrapped as `all:<term>` and AND-ed together, then AND-ed with the category).
- `n_papers`: maximum number of papers to index.
- `start_year`: only index papers published in `start_year` or later.
- `sort_by`: `"date"` (newest first) or `"citations"` (the crawler over-fetches 100× then ranks by Semantic Scholar citation count). **Required** — accessed without a default.
- `scrape_method`: `"playwright"` (default) or `"scrapy"` — selects the indexer backend used when fetching paper PDFs/HTML.

### Box crawler

```yaml
crawling:
  crawler_type: box

box_crawler:
  auth_type: jwt                      # "jwt" (recommended) or "oauth"
  jwt_config_file: box_config.json    # for auth_type: jwt
  # OAuth alternative:
  # oauth_credentials_file: oauth_creds.json
  # OR set client_id / client_secret / access_token directly

  folder_ids: ["0"]                   # "0" = all root-level folders accessible to the auth'd user
  download_path: /data/box_downloads  # local scratch dir for downloads
  tracking_dir: /data/box_tracking    # dir for indexed.csv / failed.csv / skipped.csv

  file_extensions: []                 # whitelist (empty = all)
  exclude_extensions: [".csv"]        # blacklist (skipped without download)

  recursive: true
  max_files: 0                        # 0 = unlimited
  delete_after_index: true
  ray_workers: 0

  # Optional behaviors
  collect_permissions: false          # include group-collab permissions in metadata
  generate_report: false              # write a folder-tree report instead of indexing
  retry_failed: false                 # retry only files in failed.csv
  use_existing_downloads: false       # reuse files already in download_path
  skip_indexed: false                 # resume mode: skip files in indexed.csv
  skip_indexing: false                # download only, do not index
  incremental_update: false
  hours_back: 24                      # for incremental_update
  as_user_id: "<box-user-id>"         # impersonate a Box user (enterprise)
```

The Box crawler indexes files from [Box](https://box.com) cloud storage. It supports JWT (recommended; no token expiration) or OAuth 2.0 authentication, and can run in **as-user** mode to access enterprise folders without that user's password. The architecture is a streaming producer/consumer: the main thread downloads files sequentially (to respect Box rate limits) while Ray workers index in parallel.

**Authentication:**
- `auth_type: jwt` — provide `jwt_config_file` pointing at the JSON key downloaded from the Box Developer Console. JWT credentials don't expire.
- `auth_type: oauth` — either set `oauth_credentials_file` to a saved-token JSON, or provide `client_id` + `client_secret` + `access_token` directly.
- `as_user_id` (optional): Box user ID to impersonate. Requires the Box app to be in "App + Enterprise Access" mode with "Perform Actions as Users" enabled.

**What to crawl:**
- `folder_ids`: list of Box folder IDs. Use `"0"` for the user's root.
- `recursive` (default `true`): traverse subfolders.
- `file_extensions`: extension whitelist (empty = include all). `exclude_extensions`: blacklist (excluded files are recorded in `skipped.csv` without ever being downloaded).
- `max_files`: cap on files to download. `0` = unlimited.

**Where it writes:**
- `download_path`: scratch dir for downloaded files (default `/tmp/box_downloads`). Auto-mounted by `run.sh` to `$HOME/tmp/box_data/downloads` under Docker.
- `tracking_dir`: dir for the three CSV ledgers — `indexed.csv`, `failed.csv`, `skipped.csv` — used to track progress and enable resume (default `/tmp/box_tracking`).
- `delete_after_index` (default `true`): remove downloaded files after indexing.

**Resume / re-run modes:**
- `skip_indexed`: skip files that appear in `indexed.csv` (resume after interruption).
- `retry_failed`: process only files in `failed.csv` (retry just the failures).
- `use_existing_downloads`: skip downloading; index files already present in `download_path`.
- `skip_indexing`: download files but do not push to Vectara.
- `generate_report`: write a folder-tree structure report instead of crawling.
- `incremental_update` + `hours_back`: only consider files modified in the last N hours.

**Other:**
- `collect_permissions`: when `true`, walks parent folders and includes group-based collaboration permissions in each document's metadata.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes indexing across N workers, `-1` uses all CPU cores.

**Indexed metadata:** `source` = `"Box"`, `title` (filename), `file_id`, `url` (`https://app.box.com/file/<file_id>`), `size_bytes`, `modified_date`, and (when `collect_permissions: true`) `permissions` (list of group names).

### Edgar crawler

```yaml
crawling:
  crawler_type: edgar

edgar_crawler:
  tickers: ["AAPL", "MSFT", "GOOGL"]
  start_date: "2022-01-01"
  end_date: "2024-12-31"
  filing_types: ["10-K", "10-Q", "8-K", "DEF 14A"]
  ray_workers: 0
```

The Edgar crawler downloads SEC filings (10-K, 10-Q, 8-K, DEF 14A by default) for the given ticker symbols and filing date range, and indexes them into Vectara. It uses anonymous access to SEC.gov via the `sec_downloader` library — no API key is required.

- `tickers`: list of stock tickers. The crawler maps tickers to CIKs by downloading SEC's `ticker.txt`.
- `start_date` / `end_date`: filing date range (`YYYY-MM-DD`).
- `filing_types`: SEC form types to fetch. Default: `["10-K", "10-Q", "8-K", "DEF 14A"]`.
- `ray_workers`: `0` disables Ray (default), `>0` parallelizes indexing across N workers, `-1` uses all cores.

**Indexed metadata:** `source` = `"edgar"`, `url` (the SEC primary doc URL), `title`, `ticker`, `company`, `filing_type`, `date`, `year`.

### FMP crawler

```yaml
crawling:
  crawler_type: fmp

fmp_crawler:
  tickers: ["AAPL", "MSFT"]
  start_year: 2022
  end_year: 2024
  fmp_api_key: "<your-fmp-api-key>"
  index_10k: true
  index_call_transcripts: true
```

The FMP crawler indexes financial data from the [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs/) API — structured 10-K filings and quarterly earnings call transcripts — for a list of tickers across a year range.

- `tickers`: list of stock tickers.
- `start_year` / `end_year`: inclusive year range.
- `fmp_api_key`: FMP API key. Place in `secrets.toml` as `FMP_API_KEY` so it is not committed.
- `index_10k`: when `true`, indexes structured 10-K filings from the FMP `financial-reports-json` endpoint. Default: `false`.
- `index_call_transcripts`: when `true` (default), indexes earnings-call transcripts (one document per quarter, four quarters per year).

**Indexed metadata:** `source` (lowercase ticker), `title`, `ticker`, `company name`, `year`, `type` (`filing` or `transcript`), and either `filing_type: "10-K"` + `url` (SEC link) for filings or `quarter` for transcripts.

### Synapse crawler

```yaml
crawling:
  crawler_type: synapse

synapse_crawler:
  synapse_token: "<synapse-personal-access-token>"
  programs_id: "syn12345678"
  studies_id: "syn87654321"
  source: "tables"
```

The Synapse crawler indexes research programs, studies, and study methods from the Synapse [AD Knowledge Portal](https://adknowledgeportal.synapse.org/). It queries two Synapse tables (programs and studies) via SQL, fetches associated wiki markdown for each entry, converts it to plain text, and indexes the result.

- `synapse_token`: a Synapse personal-access token (used as `authToken` for `synapseclient.Synapse.login`). Place in `secrets.toml` as `SYNAPSE_TOKEN`.
- `programs_id`: Synapse table ID containing programs (e.g., `syn12345678`).
- `studies_id`: Synapse table ID containing studies and their methods.
- `source`: source label attached to each indexed document. Default: `"tables"`.

**Indexed metadata:** `url` (the AD Knowledge Portal URL), `source`, `created` (wiki creation timestamp). Documents are written for programs, studies, and methods individually.
