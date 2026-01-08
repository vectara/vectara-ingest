# Database Crawler

The Database crawler indexes data from SQL databases with support for multiple database types, flexible SQL queries, custom column mapping, table summarization, and comprehensive metadata extraction. It handles structured data transformation into searchable documents.

## Overview

- **Crawler Type**: `database`
- **Authentication**: Database connection strings with credentials
- **Supported Databases**: PostgreSQL, MySQL, MariaDB, SQLite, Oracle, SQL Server, and any SQLAlchemy-compatible database
- **Query Support**: Custom SQL queries with WHERE conditions
- **Column Mapping**: Flexible text, metadata, and document ID column configuration
- **Table Summarization**: Automatic table content analysis and summarization
- **Metadata**: Row-level metadata from specified columns
- **Document IDs**: Custom composite document IDs from multiple columns
- **Title Column**: Custom document titles from database column
- **Batch Processing**: Efficient processing of large datasets

## Use Cases

- Index data from relational databases as searchable documents
- Build knowledge bases from database content
- Create searchable interfaces for structured data
- Integrate database records with semantic search
- Index employee directories, product catalogs, or resource lists
- Process business intelligence and analytics data
- Create searchable audit logs or transaction records
- Index survey results, feedback, or customer data
- Build compliance or regulatory document repositories
- Real-time data indexing from database tables

## Getting Started: Database Connection

### Prerequisites

- Access to a SQL database (PostgreSQL, MySQL, SQLite, etc.)
- Database connection credentials (username, password, hostname, port)
- Database name and table name to crawl
- Appropriate database permissions to read the table
- SQLAlchemy driver installed for your database type

### Supported Databases

The crawler supports any database with a SQLAlchemy driver:

| Database | Driver | Connection String Example |
|----------|--------|---------------------------|
| PostgreSQL | psycopg2 | `postgresql://user:password@localhost:5432/dbname` |
| MySQL | pymysql | `mysql+pymysql://user:password@localhost:3306/dbname` |
| MariaDB | pymysql | `mysql+pymysql://user:password@localhost:3306/dbname` |
| SQLite | sqlite | `sqlite:////path/to/database.db` |
| Oracle | cx_oracle | `oracle://user:password@localhost:1521/dbname` |
| SQL Server | pyodbc | `mssql+pyodbc://user:password@dsn_name` |

### Credentials Setup

Store database credentials securely using environment variables:

```bash
# PostgreSQL example
export DATABASE_URL="postgresql://user:password@localhost:5432/mydatabase"

# MySQL example
export DATABASE_URL="mysql+pymysql://user:password@localhost:3306/mydatabase"

# SQLite example (local file)
export DATABASE_URL="sqlite:////home/user/mydatabase.db"
```

**Security Note**: Never hardcode database credentials in configuration files. Always use environment variables or connection string files with restricted permissions.

### Connection String Format

```
database_type://username:password@host:port/database_name
```

Components:
- **database_type**: Dialect + driver (e.g., `postgresql`, `mysql+pymysql`)
- **username**: Database user
- **password**: User password
- **host**: Database hostname or IP
- **port**: Database port (default varies by database)
- **database_name**: Name of the database to connect to

### Testing Database Connection

```bash
# Using Python to test connection
python3 << 'EOF'
import sqlalchemy
try:
    engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text("SELECT 1"))
        print("Connection successful!")
except Exception as e:
    print(f"Connection failed: {e}")
EOF
```

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: database-records

crawling:
  crawler_type: database

database_crawler:
  # Database connection string (use environment variable)
  db_url: "${DATABASE_URL}"

  # Table name to crawl
  db_table: "customers"

  # Columns containing text to index
  text_columns:
    - "description"
    - "notes"

metadata:
  source: database
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: database-knowledge-base
  reindex: false
  verbose: true

  chunking_strategy: sentence
  chunk_size: 512

crawling:
  crawler_type: database

database_crawler:
  # Database connection
  db_url: "${DATABASE_URL}"

  # Table to crawl
  db_table: "products"

  # Text columns to index (required)
  text_columns:
    - "description"
    - "features"
    - "specifications"

  # Title column for each document
  title_column: "name"

  # Metadata columns (attached to each document)
  metadata_columns:
    - "category"
    - "status"
    - "created_date"
    - "owner"

  # Document ID columns (composite primary key)
  doc_id_columns:
    - "product_id"
    - "version"

  # Optional SQL WHERE clause for filtering
  select_condition: "status = 'active' AND category IN ('electronics', 'books')"

doc_processing:
  # Table processing options
  summarize_tables: true
  parse_tables: true

metadata:
  source: database
  environment: production
  database_name: "production_db"
  table_name: "products"
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `db_url` | string | Yes | - | Database connection string (use environment variable) |
| `db_table` | string | Yes | - | Table name to crawl |
| `text_columns` | list | Yes | - | Column names containing text to index (one or more required) |
| `title_column` | string | No | None | Column to use as document title |
| `metadata_columns` | list | No | [] | Column names to attach as metadata to each document |
| `doc_id_columns` | list | No | [] | Column names to use as composite document ID |
| `select_condition` | string | No | None | SQL WHERE clause to filter rows (e.g., `status = 'active'`) |

## Database Connection Examples

### PostgreSQL

```yaml
database_crawler:
  db_url: "${DATABASE_URL}"  # postgresql://user:pass@localhost:5432/mydb
  db_table: "articles"
  text_columns: ["title", "content"]
```

Environment setup:
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/mydatabase"
```

### MySQL

```yaml
database_crawler:
  db_url: "${DATABASE_URL}"  # mysql+pymysql://user:pass@localhost:3306/mydb
  db_table: "blog_posts"
  text_columns: ["title", "body"]
```

Environment setup:
```bash
export DATABASE_URL="mysql+pymysql://user:password@localhost:3306/mydatabase"
```

### SQLite (Local File)

```yaml
database_crawler:
  db_url: "${DATABASE_URL}"  # sqlite:////path/to/database.db
  db_table: "documents"
  text_columns: ["content"]
```

Environment setup:
```bash
export DATABASE_URL="sqlite:////home/user/mydatabase.db"
```

### Oracle

```yaml
database_crawler:
  db_url: "${DATABASE_URL}"  # oracle://user:pass@localhost:1521/mydb
  db_table: "documents"
  text_columns: ["document_text"]
```

Environment setup:
```bash
export DATABASE_URL="oracle://user:password@localhost:1521/mydatabase"
```

### SQL Server

```yaml
database_crawler:
  db_url: "${DATABASE_URL}"  # mssql+pyodbc://user:pass@dsn_name
  db_table: "articles"
  text_columns: ["content"]
```

Environment setup:
```bash
export DATABASE_URL="mssql+pyodbc://user:password@dsn_name"
```

## Text Columns Configuration

Define which database columns contain the text content to index:

### Single Text Column

```yaml
database_crawler:
  text_columns:
    - "content"  # Index only the content column
```

### Multiple Text Columns

```yaml
database_crawler:
  text_columns:
    - "title"      # Combine these columns
    - "description"
    - "body"       # Into one indexed document
```

When multiple text columns are specified:
- Content from all columns is combined
- Columns are concatenated in the order specified
- All text becomes searchable in a single document per row
- Structure is preserved for readability

### Text Column Examples

```yaml
# Blog posts
text_columns:
  - "title"
  - "excerpt"
  - "content"

# Product catalog
text_columns:
  - "product_name"
  - "description"
  - "features"
  - "specifications"

# Knowledge base articles
text_columns:
  - "article_title"
  - "article_body"
  - "faq_content"

# Customer feedback
text_columns:
  - "feedback_text"
  - "notes"
```

## Title Column

Use a database column as the document title for each indexed row:

```yaml
database_crawler:
  db_table: "products"
  text_columns: ["description", "features"]

  # Use product_name as title
  title_column: "product_name"
```

Effect:
- Each document's title becomes the value from the specified column
- Improves document identification in search results
- Optional but recommended for better UX

### Title Column Examples

```yaml
# Blog posts - use article title
title_column: "article_title"

# Products - use product name
title_column: "product_name"

# Employees - use full name
title_column: "full_name"

# News articles - use headline
title_column: "headline"

# Support tickets - use ticket subject
title_column: "subject"
```

## Metadata Columns

Attach metadata from database columns to each indexed document:

```yaml
database_crawler:
  db_table: "articles"
  text_columns: ["content"]

  # These columns become metadata
  metadata_columns:
    - "author"
    - "published_date"
    - "category"
    - "status"
```

Metadata is attached to each document and can be used for:
- Filtering in search queries
- Additional context about the document
- Sorting and ranking
- Analytics and tracking

### Metadata Column Examples

```yaml
# Blog posts
metadata_columns:
  - "author"
  - "published_date"
  - "category"
  - "tags"
  - "read_time"

# Products
metadata_columns:
  - "category"
  - "price"
  - "stock_level"
  - "supplier"
  - "sku"

# Employees
metadata_columns:
  - "department"
  - "title"
  - "location"
  - "hire_date"
  - "manager"

# Support tickets
metadata_columns:
  - "priority"
  - "status"
  - "created_date"
  - "assigned_to"
  - "resolution_time"
```

## Document ID Columns

Use one or more database columns as the document ID (composite key):

```yaml
database_crawler:
  db_table: "documents"
  text_columns: ["content"]

  # Use these columns as document ID
  doc_id_columns:
    - "document_id"
    - "version"
```

Document IDs:
- Uniquely identify each indexed document
- Used for updates and re-indexing
- Composite IDs combine multiple columns with `_` separator
- Example: `doc-123_v2` (from document_id=doc-123, version=v2)

### Single ID Column

```yaml
doc_id_columns:
  - "id"
```

### Composite IDs

```yaml
# Example 1: Product with version
doc_id_columns:
  - "product_id"
  - "version"
  # Results in IDs like: "SKU-123_v2"

# Example 2: Multi-level document hierarchy
doc_id_columns:
  - "organization_id"
  - "department_id"
  - "document_id"
  # Results in IDs like: "ORG-1_DEPT-5_DOC-999"

# Example 3: Temporal documents
doc_id_columns:
  - "record_id"
  - "date"
  # Results in IDs like: "REC-123_2024-11-18"
```

## Filtering with WHERE Clause

Use SQL WHERE conditions to filter which rows are indexed:

### Basic Filtering

```yaml
database_crawler:
  db_table: "articles"
  text_columns: ["content"]

  # Only index published articles
  select_condition: "status = 'published'"
```

### Multiple Conditions

```yaml
select_condition: "status = 'active' AND created_date >= '2024-01-01'"
```

### IN Clause

```yaml
select_condition: "category IN ('tech', 'business', 'science')"
```

### Comparison Operators

```yaml
# Greater than
select_condition: "price > 100"

# Less than or equal
select_condition: "stock_level <= 50"

# Not equal
select_condition: "status != 'archived'"

# LIKE pattern matching
select_condition: "name LIKE '%urgent%'"

# BETWEEN
select_condition: "created_date BETWEEN '2024-01-01' AND '2024-12-31'"
```

### Complex Conditions

```yaml
select_condition: |
  status = 'active'
  AND category IN ('product', 'service')
  AND created_date >= '2024-01-01'
  AND (priority = 'high' OR is_featured = true)
```

### Filtering Examples

```yaml
# Blog posts - only published
select_condition: "is_published = true"

# Products - in stock and active
select_condition: "stock_level > 0 AND status = 'active'"

# Employees - current employees
select_condition: "hire_date <= NOW() AND termination_date IS NULL"

# Support tickets - open issues
select_condition: "status IN ('open', 'in_progress') AND priority = 'high'"

# Articles - recent and featured
select_condition: "published_date >= NOW() - INTERVAL 30 DAY AND is_featured = true"
```

## Table Summarization

Enable automatic table/structured data analysis and summarization:

```yaml
database_crawler:
  db_table: "data_table"
  text_columns: ["content"]

doc_processing:
  # Analyze and summarize table content
  summarize_tables: true
  parse_tables: true
```

When enabled:
- Table structure is analyzed
- Content summaries are generated
- Structured data is properly formatted
- Better semantic indexing of tabular content

## Complete Configuration Examples

### Blog Platform

```yaml
# config/database-blog.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: blog-posts

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "posts"

  text_columns:
    - "title"
    - "content"

  title_column: "title"

  metadata_columns:
    - "author"
    - "published_date"
    - "category"
    - "tags"

  select_condition: "status = 'published' AND published_date <= NOW()"

metadata:
  source: database
  collection_type: blog
```

### Product Catalog

```yaml
# config/database-products.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: product-catalog

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "products"

  text_columns:
    - "product_name"
    - "description"
    - "features"
    - "specifications"

  title_column: "product_name"

  metadata_columns:
    - "category"
    - "price"
    - "sku"
    - "stock_level"
    - "supplier"

  doc_id_columns:
    - "product_id"
    - "version"

  select_condition: "status = 'active' AND stock_level > 0"

metadata:
  source: database
  environment: production
```

### Knowledge Base Articles

```yaml
# config/database-kb.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: knowledge-base

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "kb_articles"

  text_columns:
    - "title"
    - "content"
    - "faq"

  title_column: "title"

  metadata_columns:
    - "category"
    - "author"
    - "last_updated"
    - "is_featured"
    - "difficulty_level"

  doc_id_columns:
    - "article_id"

  select_condition: "is_published = true AND is_archived = false"

doc_processing:
  summarize_tables: true
  parse_tables: true

metadata:
  source: database
  environment: production
  collection_type: knowledge-base
```

### Employee Directory

```yaml
# config/database-employees.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: employee-directory

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "employees"

  text_columns:
    - "full_name"
    - "bio"
    - "skills"
    - "expertise"

  title_column: "full_name"

  metadata_columns:
    - "department"
    - "job_title"
    - "location"
    - "email"
    - "phone"
    - "hire_date"

  select_condition: "status = 'active' AND termination_date IS NULL"

metadata:
  source: database
  department: hr
```

### Support Tickets

```yaml
# config/database-tickets.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: support-tickets

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "support_tickets"

  text_columns:
    - "title"
    - "description"
    - "resolution"

  title_column: "title"

  metadata_columns:
    - "priority"
    - "status"
    - "category"
    - "created_date"
    - "assigned_to"
    - "resolution_time"

  select_condition: "status IN ('resolved', 'closed')"

metadata:
  source: database
  collection_type: support
```

## Troubleshooting

### Connection Failed

**Error**: `Cannot connect to database` or `Connection refused`

**Solutions**:
1. Verify connection string is correct:
   ```bash
   echo $DATABASE_URL
   ```

2. Check database is running and accessible:
   ```bash
   # PostgreSQL
   psql -h localhost -U user -d database

   # MySQL
   mysql -h localhost -u user -p
   ```

3. Verify firewall allows connection to database port

4. Check database credentials (username, password)

### Table Not Found

**Error**: `Table does not exist` or `No such table`

**Solutions**:
1. Verify table name spelling:
   ```yaml
   db_table: "correct_table_name"
   ```

2. List available tables:
   ```bash
   # PostgreSQL
   psql -c "\dt" -U user -d database

   # MySQL
   mysql -e "SHOW TABLES;" -u user -p database
   ```

3. Check if table is in specific schema:
   ```yaml
   db_table: "schema_name.table_name"
   ```

### Column Not Found

**Error**: `Column 'column_name' does not exist`

**Solutions**:
1. Verify column names exist in table:
   ```yaml
   text_columns:
     - "correct_column_name"
   ```

2. List table columns:
   ```bash
   # PostgreSQL
   psql -c "\d table_name" -U user -d database

   # MySQL
   mysql -e "DESCRIBE table_name;" -u user -p database
   ```

3. Check column name case sensitivity (databases vary)

### No Data Indexed

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Verify table has data:
   ```bash
   # PostgreSQL
   psql -c "SELECT COUNT(*) FROM table_name;" -U user -d database
   ```

2. Check WHERE clause filters correctly:
   ```yaml
   select_condition: null  # Try without filtering first
   ```

3. Verify text_columns are not NULL:
   ```bash
   SELECT COUNT(*) FROM table WHERE column_name IS NOT NULL
   ```

### Permission Denied

**Error**: `Permission denied` or `Access denied for user`

**Solutions**:
1. Verify user has SELECT permission:
   ```bash
   # Grant permission
   GRANT SELECT ON table_name TO username;
   ```

2. Check user account:
   ```bash
   whoami  # For local user running crawler
   ```

3. Verify database credentials in connection string

### Encoding Issues

**Error**: `UnicodeDecodeError` or garbled text in documents

**Solutions**:
1. Ensure database uses UTF-8 encoding:
   ```bash
   # PostgreSQL
   psql -l | grep database_name
   ```

2. Specify encoding in connection string:
   ```yaml
   db_url: "postgresql://user:pass@localhost/db?client_encoding=utf8"
   ```

3. Check for special characters in text columns

### Large Dataset Issues

**Error**: Timeout, memory error, or slow performance

**Solutions**:
1. Use WHERE clause to filter data:
   ```yaml
   select_condition: "created_date >= '2024-01-01'"  # Limit by date
   ```

2. Batch process by category:
   ```bash
   # Create separate configs for each category
   bash run.sh config/db-category-a.yaml default
   bash run.sh config/db-category-b.yaml default
   ```

3. Reduce chunk size:
   ```yaml
   vectara:
     chunk_size: 256
   ```

4. Process during off-peak hours

### SQL Syntax Errors

**Error**: `SQL syntax error` in WHERE clause

**Solutions**:
1. Verify SQL syntax is correct for your database:
   ```bash
   # Test the query
   SELECT * FROM table WHERE your_condition
   ```

2. Use database-specific syntax:
   ```yaml
   # PostgreSQL
   select_condition: "created_at >= CURRENT_DATE - INTERVAL '7 days'"

   # MySQL
   select_condition: "created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)"
   ```

3. Quote identifiers if needed:
   ```yaml
   select_condition: '"column-name" = 5'  # Column with special chars
   ```

## Best Practices

### 1. Use Specific Text Columns

```yaml
# Good: Only necessary columns
text_columns:
  - "title"
  - "description"

# Bad: Too many columns
text_columns:
  - "id"
  - "created_by"
  - "last_modified_by"
  - "notes"
  - "internal_comments"
```

### 2. Filter Data with WHERE Clause

```yaml
# Good: Only active records
select_condition: "status = 'active'"

# Bad: Index everything
select_condition: null
```

### 3. Use Meaningful Titles

```yaml
# Good: User-friendly title
title_column: "product_name"

# Bad: Generic ID
title_column: "id"
```

### 4. Include Relevant Metadata

```yaml
# Good: Useful for filtering/context
metadata_columns:
  - "category"
  - "author"
  - "created_date"

# Bad: Too many metadata fields
metadata_columns:
  - "internal_id_1"
  - "internal_id_2"
  - "deprecated_field"
```

### 5. Use Composite Document IDs

```yaml
# Good: Unique and meaningful
doc_id_columns:
  - "product_id"
  - "version"

# Bad: Single generic ID
doc_id_columns:
  - "row_id"
```

### 6. Test Queries First

Test your SQL query before running crawler:

```bash
# Test connection and query
psql -h localhost -U user -d database << EOF
SELECT COUNT(*) FROM table_name WHERE status = 'active';
EOF
```

### 7. Monitor Index Progress

```bash
# Watch logs in real-time
docker logs -f vingest

# Check for errors
docker logs vingest | grep -i error
```

### 8. Use Incremental Indexing

For large tables, consider incremental updates:

```yaml
vectara:
  reindex: false  # Only add/update changed records

# Only index recently modified records
select_condition: "updated_date >= DATE_SUB(NOW(), INTERVAL 1 DAY)"
```

### 9. Version Your Configurations

```yaml
metadata:
  version: "1.0"
  created_date: "2024-11-18"
  last_updated: "2024-11-18"
  notes: "Production database crawler config"
```

### 10. Secure Credentials

```bash
# DO: Use environment variables
export DATABASE_URL="postgresql://..."
bash run.sh config/database.yaml default

# DO NOT: Hard-code in config
db_url: "postgresql://user:pass@..."  # WRONG!
```

## Running the Crawler

### Set Environment Variables

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/mydatabase"
export VECTARA_API_KEY="your-vectara-key"
```

### Run Single Crawl

```bash
bash run.sh config/database.yaml default
```

### Monitor Progress

```bash
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && \
  export DATABASE_URL="postgresql://..." && \
  bash run.sh config/database.yaml default

# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && \
  export DATABASE_URL="postgresql://..." && \
  bash run.sh config/database.yaml default

# Weekly on Sunday
0 2 * * 0 cd /path/to/vectara-ingest && \
  export DATABASE_URL="postgresql://..." && \
  bash run.sh config/database.yaml default
```

Or use `.env` file:

```bash
# .env file
DATABASE_URL="postgresql://user:password@localhost:5432/db"

# Cron job (with sourcing)
0 2 * * * cd /path && source .env && bash run.sh config/database.yaml default
```

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Document Processing](../features/document-processing.md) - Advanced document processing options
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Database Resources

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [SQLAlchemy Connection Strings](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls)
- [PostgreSQL Python Driver](https://www.psycopg.org/)
- [MySQL Python Driver](https://pymysql.readthedocs.io/)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [Oracle Python Driver](https://cx-oracle.readthedocs.io/)
- [SQL Server Python Driver](https://github.com/mkleehammer/pyodbc/wiki)

## Common Workflows

### Workflow 1: Index Active Products

```yaml
# config/db-products.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: products

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "products"
  text_columns: ["name", "description"]
  title_column: "name"
  metadata_columns: ["category", "price"]
  select_condition: "status = 'active'"

metadata:
  source: database
```

### Workflow 2: Update Recently Changed Records

```yaml
# config/db-incremental.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: articles
  reindex: false

crawling:
  crawler_type: database

database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "articles"
  text_columns: ["title", "content"]
  select_condition: "updated_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)"

metadata:
  source: database
```

Run daily:
```bash
0 * * * * cd /vectara && source .env && bash run.sh config/db-incremental.yaml default
```

### Workflow 3: Multi-Table Indexing

Create separate configs for each table:

```bash
config/db-products.yaml
config/db-articles.yaml
config/db-employees.yaml
```

Run all:
```bash
for config in config/db-*.yaml; do
  bash run.sh "$config" default
done
```

### Workflow 4: Department-Specific Crawls

```yaml
# config/db-sales.yaml
database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "leads"
  text_columns: ["company", "description"]
  select_condition: "department = 'sales' AND status = 'active'"

# config/db-marketing.yaml
database_crawler:
  db_url: "${DATABASE_URL}"
  db_table: "campaigns"
  text_columns: ["name", "description"]
  select_condition: "department = 'marketing' AND status = 'active'"
```

## Performance Considerations

### Indexing Large Datasets

For tables with millions of rows:

1. **Use WHERE Clause to Filter**:
   ```yaml
   select_condition: "created_date >= '2024-01-01'"
   ```

2. **Process Incrementally**:
   ```yaml
   select_condition: "created_date >= DATE_SUB(NOW(), INTERVAL 1 DAY)"
   ```

3. **Batch by Category**:
   ```yaml
   select_condition: "category = 'A'"
   # Then run separate configs for categories B, C, D
   ```

4. **Optimize Database Query**:
   - Ensure indexes on filtered columns
   - Use EXPLAIN to check query performance
   - Consider views for complex queries

### Memory Usage

For memory-constrained environments:

```yaml
vectara:
  chunk_size: 256  # Smaller chunks

doc_processing:
  process_locally: true

database_crawler:
  select_condition: "..."  # Limit data volume
```

### Connection Pooling

For multiple crawlers, consider connection pooling:

```yaml
db_url: "${DATABASE_URL}?pool_size=5&max_overflow=10"
```

## FAQ

**Q: Can I index multiple tables?**
A: Yes, create separate configurations for each table and run them sequentially.

**Q: How do I update already-indexed records?**
A: Use `reindex: false` and rerun the crawler. Updated records are automatically refreshed.

**Q: What's the maximum table size?**
A: No hard limit, but use WHERE clause to filter data for large tables.

**Q: Can I use complex SQL queries?**
A: The crawler uses simple SELECT queries. For complex joins, create a view and crawl the view.

**Q: How often should I re-index?**
A: Schedule based on your data update frequency (daily, weekly, or on-demand).

**Q: What happens if the database is unavailable?**
A: The crawler will fail. Implement retry logic in your cron job or scheduler.

**Q: Can I use the same crawler for multiple databases?**
A: Create separate configurations for each database connection.

**Q: How do I handle NULL values in columns?**
A: Use WHERE clause to filter: `WHERE column IS NOT NULL`

**Q: Can I index specific rows based on criteria?**
A: Yes, use the `select_condition` parameter with a WHERE clause.

**Q: How do I monitor crawler progress?**
A: Check logs: `docker logs -f vingest` or examine indexed document count in Vectara console.

**Q: What if my database uses special characters?**
A: Ensure database uses UTF-8 encoding. Quote column names if they have special characters.
