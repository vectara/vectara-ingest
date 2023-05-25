<p align="center">
  <img src="../img/crawler.png" alt="Futuristic crawler">
</p>

<h1 align="center">vectara-ingest crawlers</h1>

## Overview

`vectara-ingest` includes a number of crawlers that make it easy to crawl data sources and index the results into Vectara.
Let's go through each of these crawlers to explain how they work and how to customize them to your needs. This will also provide good background to creating (and contributing) new types of crawlers.

### website crawler

```yaml
...
website_crawler:
    urls: [https://vectara.com]
    delay: 1
    pages_source: sitemap
    extraction: playwright
    max_depth: 3      # only needed if pages_source is set to 'crawl'
...
```

The website crawler indexes the content of a given web site. It supports two modes for finding pages to crawl (defined by `pages_source`):
1. `sitemap`: in this mode the crawler retrieves the sitemap of the target websites (`urls`: list of URLs) and indexes all the URLs listed in each sitemap
2. `crawl`: in this mode the crawler starts from the homepage and crawls the website, following links no more than `max_depth`

The `extraction` parameter defines how page content is extracted from URLs. 
1. The default value is `pdf` which means the target URL is rendered into a PDF document, which is then uploaded to Vectara. This is the preferred method as the rendering operation is helpful to extract any text that may be due to Javascript or other scriping execution. 
2. The other option is `playwright` which results in using [playwright](https://playwright.dev/) to render the page content including JS and then extracting the HTML.

`delay` specifies the number of seconds to wait between to consecutive requests to avoid rate limiting issues. 

`url_regex` if it exists defines a regular expression that is used to filter URLs. For example, if I want only the developer pages from vectara.com to be indexed, I can use ".*vectara.com/developer.*" 

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
  extraction: pdf           # pdf or html
```

The RSS crawler can be used to crawl URLs listed in RSS feeds such as on news sites. In the example above, the rss_crawler is configured to crawl various newsfeeds from the BBC. 
- `source` specifies the name of the rss data feed
- `rss_pages` defines one or more RSS feed locations. 
- `days_past` specifies the number of days backward to crawl; for example with a value of 90 as in this example, the crawler will only index news items that have been published no earlier than 90 days in the past.
- `delay` defines the number of seconds between to wait between news articles, so as to make the crawl more friendly to the hosting site.
- `extraction` defines how we process URLs (pdf or html) as as with the website crawler.

### Docusaurus crawler

```yaml
...
  docusaurus_crawler:
    docs_repo: "https://github.com/vectara/vectara-docs"
    docs_homepage: "https://docs.vectara.com/docs"
```

The Docusaurus crawler processes and indexes content published on a Docusaurus documenation repository.
It has two parameters
- `docs_repo` defines the repository where the content resides.
- `docs_homepage` defines the URL where the documenation is hosted.


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

The Notion crawler has no specific parameters, except the `NOTION_API_KEY` that needs to be specified in the `secrets.toml` file. 
The crawler will index any content that is associated with this key that is on your notion instance.

### Folder crawler

```yaml
...
  folder_crawler:
    path: "/Users/ofer/Downloads/some-interesting-content/"
    extensions: ['.pdf']
```

The folder crawler simple indexes all content that's in a specified local folder.
- `path`: the local folder location
- `extensions`: list of file extensions to be included. If one of those extensions is '*' then all files would be crawled, disregarding any other extensions in that list.

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


## Other crawlers:

- `Edgar` crawler: crawls SEC Edgar annual reports (10-K) and indexes those into Vectara
- `fmp` crawler: crawls information about public companies using the [FMP](https://site.financialmodelingprep.com/developer/docs/) API
- `Hacker News` crawler: crawls the best, most recent an most popular Hacker News stories
- `PMC` crawler: crawls medical articles from PubMed Central and indexes them into Vectara.
