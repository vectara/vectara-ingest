# CSV Crawler

The CSV crawler indexes structured data from CSV, TSV, and Excel (XLSX/XLS) files. It supports multiple processing modes, column-based text and metadata extraction, row filtering, dynamic type conversion, and customizable document grouping strategies.

## Overview

- **Crawler Type**: `csv`
- **File Formats**: CSV, TSV, XLSX, XLS
- **Processing Modes**:
  - `element` - Each row becomes a separate document
  - `table` - Entire table becomes one document
- **Text Extraction**: Multi-column concatenation with customizable separators
- **Metadata**: Column-based metadata assignment and filtering
- **Document Grouping**: By ID column(s) or fixed row chunks
- **Column Features**: Type conversion, filtering, dynamic column selection
- **Excel Support**: Multi-sheet handling with selective sheet indexing
- **Data Validation**: Row filtering with pandas query syntax
- **Table Limits**: Automatic truncation for large tables

## Use Cases

- Index product catalogs from CSV exports
- Ingest customer contact databases
- Index survey responses and feedback data
- Create searchable FAQ databases from spreadsheets
- Index reference data (pricing, features, specifications)
- Build knowledge bases from tabular data exports
- Archive and search historical records
- Index data from business intelligence exports
- Create searchable inventories from spreadsheet data

## Getting Started: Preparing Your Data

### Supported File Formats

| Format | Extension | Support | Notes |
|--------|-----------|---------|-------|
| **CSV** | `.csv` | Full | Custom separators (comma, tab, semicolon, etc.) |
| **TSV** | `.tsv` | Full | Tab-separated values |
| **XLSX** | `.xlsx` | Full | Modern Excel format, multi-sheet support |
| **XLS** | `.xls` | Full | Legacy Excel format, multi-sheet support |

### File Requirements

- **Size**: Reasonable file size (< 100 MB recommended for Docker)
- **Encoding**: UTF-8 (best), other encodings may work
- **Headers**: First row should contain column names
- **Data**: Consistent column structure throughout

### Data Preparation

1. Ensure headers are descriptive
2. Use consistent data types within columns
3. Remove empty rows and columns if not needed
4. Consider your document grouping strategy:
   - By ID column(s) for related rows
   - By chunk size for flat data

## Configuration

### Basic Configuration (Element Mode)

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: my-csv-data

crawling:
  crawler_type: csv

csv_crawler:
  # File path to CSV/XLSX
  file_path: "/path/to/your/data.csv"

  # Mode: 'element' = row-based, 'table' = entire table
  mode: "element"

  # Columns containing text content
  text_columns: ["description", "notes"]

  # Column to use as document ID/title
  doc_id_columns: ["product_id"]

  # Columns to use as metadata
  metadata_columns: ["category", "author", "date"]
```

### Advanced Configuration (Element Mode)

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: csv-detailed
  reindex: true
  verbose: true
  create_corpus: true

crawling:
  crawler_type: csv

csv_crawler:
  # File configuration
  file_path: "/path/to/products.csv"
  mode: "element"
  separator: ","  # CSV separator (only for .csv)

  # Text content columns
  text_columns: ["title", "description", "features", "specifications"]

  # Document grouping
  doc_id_columns: ["product_id"]  # Group rows by this column
  title_column: "product_name"     # Use this column for document title

  # Metadata columns
  metadata_columns: ["category", "brand", "price", "rating", "availability"]

  # Row filtering - only index rows matching this condition
  select_condition: "status == 'active' and price > 0"

  # Column type conversion
  column_types:
    price: "float"
    rating: "float"
    quantity: "int"
    product_id: "str"

  # Table size limits (for truncation)
  max_rows: 10000
  max_cols: 100
  truncate_table_if_over_max: true

doc_processing:
  use_core_indexing: false
  process_locally: true

metadata:
  source: csv
  content_type: product_catalog
  update_frequency: daily
```

### Table Mode Configuration

```yaml
vectara:
  corpus_key: csv-table-view

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/path/to/data.xlsx"
  mode: "table"  # Entire table as one document

  # Table-specific parameters
  max_rows: 1000
  max_cols: 50
  truncate_table_if_over_max: true

  # Sheet selection (XLSX only)
  sheet_names: ["Sales", "Inventory"]  # Or list all sheets to process
```

## Configuration Parameters

### Core Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | Yes | - | Path to CSV/XLSX file |
| `mode` | string | Yes | - | `element` (row-based) or `table` (full table) |

### Element Mode Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text_columns` | list | Yes | - | Columns containing text to index |
| `doc_id_columns` | list | No | - | Column(s) for grouping rows into documents |
| `title_column` | string | No | - | Column to use as document title |
| `metadata_columns` | list | No | - | Columns to use as metadata |
| `select_condition` | string | No | - | Pandas query to filter rows |
| `column_types` | dict | No | - | Column type specifications |
| `rows_per_chunk` | int | No | `500` | Rows per document (if no doc_id_columns) |
| `separator` | string | No | `,` | CSV separator (CSV files only) |

### XLSX-Specific Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `sheet_names` | list | No | All sheets | Which sheets to process |
| `sheet_name` | string | No | - | Alternative: single sheet name |

### Table Size Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `max_rows` | int | No | `500` | Maximum rows to include (per table) |
| `max_cols` | int | No | `20` | Maximum columns to include |
| `truncate_table_if_over_max` | bool | No | `true` | Truncate if exceeds size limits |

## Operating Modes

### Element Mode

Each row (or group of rows) becomes a separate document:

```yaml
mode: "element"
```

**Process**:
1. Read CSV/XLSX file
2. For each row (or group of rows):
   - Extract text from `text_columns`
   - Create document with extracted text
   - Assign metadata from `metadata_columns`
   - Use `doc_id_columns` as grouping key
3. Index each document

**Best For**:
- Product catalogs (each product = 1 document)
- Contact databases (each contact = 1 document)
- Survey responses (each response = 1 document)
- Records with significant text content

### Table Mode

The entire table becomes one document:

```yaml
mode: "table"
```

**Process**:
1. Read CSV/XLSX file
2. Convert entire table to structured format
3. Create single document with table
4. Index as complete table

**Best For**:
- Reference data (pricing tables, feature matrices)
- Lookup tables
- Small structured datasets
- Data that should be searched together

**Limitations**:
- Maximum 10,000 rows per table
- Maximum 100 columns per table
- Use `truncate_table_if_over_max` to handle larger files

## Text Extraction

### Multi-Column Concatenation

Combine multiple columns into searchable text:

```yaml
text_columns: ["title", "description", "features", "specifications"]
```

**Result**: For each row, text from all specified columns is concatenated with " - " separator.

**Example**:
```
Title: "Laptop Pro 15"
Description: "High-performance laptop for professionals"
Features: "16GB RAM, 512GB SSD, M1 Pro chip"
Specifications: "15.3 inch, weight 3.5 lbs"

Indexed as:
"Laptop Pro 15 - High-performance laptop for professionals - 16GB RAM, 512GB SSD, M1 Pro chip - 15.3 inch, weight 3.5 lbs"
```

### Column Selection

Choose which columns contain the content to index:

```yaml
# Good: Just text columns
text_columns: ["description", "notes"]

# Avoid: Including ID or date columns
text_columns: ["id", "date", "description"]  # Not ideal
```

## Document Grouping Strategies

### Strategy 1: By ID Column(s)

Group rows with the same ID value into one document:

```yaml
doc_id_columns: ["product_id"]  # Single column
```

Or multiple columns:

```yaml
doc_id_columns: ["product_id", "variant_id"]  # Multiple columns
```

**Use Case**: Product with multiple rows (sizes, colors):

```
Product ID | Variant ID | Size  | Color  | Description
-----------+------------+-------+--------+------------------
PROD-001   | VAR-001    | Small | Red    | Red small variant
PROD-001   | VAR-002    | Large | Red    | Red large variant
PROD-001   | VAR-003    | Small | Blue   | Blue small variant
```

Result: 1 document with all variants combined.

### Strategy 2: By Fixed Chunk Size

Group by number of rows:

```yaml
# Remove doc_id_columns to use chunk size instead
rows_per_chunk: 500  # Default: each 500 rows = 1 document
```

**Use Case**: Large flat dataset:

```
Document 1: Rows 1-500
Document 2: Rows 501-1000
Document 3: Rows 1001-1500
```

### Strategy 3: By Title Column

Use a specific column as document title:

```yaml
doc_id_columns: ["product_id"]
title_column: "product_name"  # Use this for human-readable title
```

If `title_column` not specified, uses `doc_id_columns` value.

## Row Filtering

### Using select_condition

Filter rows using pandas query syntax:

```yaml
select_condition: "status == 'active' and price > 0"
```

**Supported Operators**:
- `==` - Equals
- `!=` - Not equals
- `>`, `<`, `>=`, `<=` - Comparisons
- `in` - List membership
- `and`, `or` - Logical operators

### Examples

```yaml
# Active products only
select_condition: "status == 'active'"

# Price between 10 and 100
select_condition: "price >= 10 and price <= 100"

# Multiple categories
select_condition: "category in ['Electronics', 'Software', 'Services']"

# Complex conditions
select_condition: "status == 'published' and rating >= 4.0 and year >= 2020"

# String matching
select_condition: "department.str.contains('Engineering', regex=False)"
```

## Column Type Conversion

### Type Specification

Explicitly specify column types for proper handling:

```yaml
column_types:
  product_id: "str"      # Force as string (not int)
  price: "float"         # Number with decimals
  quantity: "int"        # Whole number
  date: "str"            # Keep as string
  rating: "float"        # Decimal rating
```

### Supported Types

- `str` - String/text (default)
- `int` - Integer (whole number)
- `float` - Float (decimal number)

### Why Type Conversion Matters

```yaml
# Without type specification
product_id: 001  # Treated as integer (becomes 1)

# With type specification
column_types:
  product_id: "str"  # Stays as "001"
```

## Excel Multi-Sheet Support

### Processing Multiple Sheets

Specify which sheets to process:

```yaml
# Process specific sheets
sheet_names: ["Sales", "Inventory"]

# For single sheet
sheet_name: "Data"  # Alternative syntax
```

### Processing All Sheets

If neither `sheet_names` nor `sheet_name` specified:

```yaml
# All sheets processed
# Each sheet becomes separate documents (or groups)
```

## How It Works

### Element Mode Processing

```
1. Load CSV/XLSX file
   └─ Convert to DataFrame
        ↓
2. Apply column type conversions
   └─ Convert columns to specified types
        ↓
3. Apply row filtering
   └─ Keep only rows matching select_condition
        ↓
4. Group rows
   ├─ By doc_id_columns (if specified)
   └─ Or by rows_per_chunk (default)
        ↓
5. For each group
   ├─ Extract text from text_columns
   ├─ Combine into single text
   ├─ Extract metadata from metadata_columns
   ├─ Create document
   └─ Index in Vectara
```

### Metadata Capture

**Document ID**: Generated from:
- `doc_id_columns` value(s) if specified
- Auto-generated based on chunk if not specified

**Document Title**: From:
- `title_column` if specified
- `doc_id_columns` if no title_column
- Auto-generated if neither specified

**Metadata**: All columns specified in `metadata_columns` become searchable metadata

## Troubleshooting

### File Not Found

**Error**: `File not found` or `Path does not exist`

**Solutions**:
1. Verify file path is absolute:
   ```yaml
   file_path: "/Users/adeel/data/products.csv"  # Absolute
   file_path: "data/products.csv"               # Won't work in Docker
   ```
2. In Docker, use `/home/vectara/data/`:
   ```yaml
   file_path: "/home/vectara/data/products.csv"
   ```
3. Ensure file is readable:
   ```bash
   ls -la /path/to/your/file.csv
   ```

### Encoding Issues

**Error**: `UnicodeDecodeError` or garbled characters

**Solutions**:
1. Save CSV as UTF-8:
   - Excel: File > Save As > CSV UTF-8
   - Sheets: Download > CSV (.UTF-8)
2. Try specifying encoding (if supported by crawler)
3. Convert file to UTF-8:
   ```bash
   iconv -f ISO-8859-1 -t UTF-8 input.csv > output.csv
   ```

### Column Not Found

**Error**: `Column 'column_name' not found`

**Solutions**:
1. Check column names in file exactly match configuration:
   ```yaml
   text_columns: ["Title", "Description"]  # Case-sensitive
   ```
2. View first row to see actual column names:
   ```bash
   head -1 file.csv
   ```
3. Use correct column names from file

### No Data Indexed

**Error**: Crawler runs but indexes 0 documents

**Solutions**:
1. Check `select_condition` - might filter out all rows:
   ```yaml
   # Remove condition to test
   # select_condition: "status == 'active'"
   ```
2. Verify file has data (not just headers)
3. Check that text_columns exist and have content
4. Try with minimal configuration:
   ```yaml
   file_path: "/path/to/file.csv"
   mode: "element"
   text_columns: ["description"]
   ```

### Type Conversion Errors

**Error**: `Cannot convert column to type` or `ValueError`

**Solutions**:
1. Check column actually contains that data type:
   ```yaml
   column_types:
     price: "float"  # But column contains "N/A"?
   ```
2. Remove type specification for problem column
3. Fix data in source file
4. Use `str` type as fallback

### Large File Issues

**Error**: Out of memory or slow processing

**Solutions**:
1. Use `select_condition` to filter data:
   ```yaml
   select_condition: "year >= 2023"  # Recent data only
   ```
2. Reduce columns:
   ```yaml
   text_columns: ["description"]  # Only essential columns
   ```
3. Use `truncate_table_if_over_max`:
   ```yaml
   max_rows: 5000
   truncate_table_if_over_max: true
   ```
4. Split file into multiple CSVs and crawl separately

### Excel Sheet Issues

**Error**: Sheet not found or no data from Excel file

**Solutions**:
1. Check sheet names exactly:
   ```bash
   # View sheet names
   python -c "import openpyxl; wb = openpyxl.load_workbook('file.xlsx'); print(wb.sheetnames)"
   ```
2. Verify sheet has data (not blank)
3. Try without specifying sheets:
   ```yaml
   # Remove sheet_names to process all sheets
   ```
4. Ensure file isn't corrupted

## Best Practices

### 1. Start with Basic Configuration

Test with minimal configuration first:

```yaml
csv_crawler:
  file_path: "/path/to/data.csv"
  mode: "element"
  text_columns: ["content"]
```

Then add complexity:

```yaml
doc_id_columns: ["id"]
metadata_columns: ["date", "author"]
select_condition: "status == 'active'"
```

### 2. Use Appropriate Text Columns

```yaml
# Good: Columns with descriptive text
text_columns: ["title", "description", "notes"]

# Avoid: ID, date, and numeric columns
text_columns: ["id", "date", "amount"]  # Not searchable text
```

### 3. Set Up Meaningful Document Grouping

```yaml
# If data has meaningful IDs
doc_id_columns: ["product_id"]
title_column: "product_name"

# For flat data without IDs
rows_per_chunk: 100
```

### 4. Use Metadata Strategically

```yaml
# Include columns useful for filtering/context
metadata_columns: ["category", "date", "author", "status"]

# Avoid: Too many columns (makes metadata verbose)
metadata_columns: ["col1", "col2", "col3", "col4", "col5"]
```

### 5. Test Filters Before Indexing

Test your `select_condition` in pandas first:

```python
import pandas as pd
df = pd.read_csv("file.csv")
# Test your condition
filtered = df.query("status == 'active' and price > 0")
print(f"Filtered: {len(filtered)} rows out of {len(df)}")
```

### 6. Document Your Configuration

```yaml
metadata:
  version: "1.0"
  source_file: "product_catalog_2024.csv"
  notes: "Product catalog filtered to active items"
  last_updated: "2024-11-18"
  row_count: "~2500"
```

## Running the Crawler

### Prepare Your Data

```bash
# Ensure CSV is UTF-8 encoded
file_type=$(file -b data.csv)
echo $file_type
```

### Create Configuration

```bash
vim config/my-csv.yaml
```

### Run the Crawler

```bash
bash run.sh config/my-csv.yaml default
```

### Monitor Progress

```bash
docker logs -f vingest
```

## Examples

### Example 1: Product Catalog (Element Mode)

```yaml
vectara:
  corpus_key: products

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/home/vectara/data/products.csv"
  mode: "element"
  text_columns: ["name", "description", "features"]
  doc_id_columns: ["product_id"]
  title_column: "product_name"
  metadata_columns: ["category", "price", "rating"]
  select_condition: "status == 'active'"

metadata:
  source: product_database
  type: catalog
```

### Example 2: Customer Database (Element Mode)

```yaml
vectara:
  corpus_key: customers

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/home/vectara/data/customers.csv"
  mode: "element"
  text_columns: ["company_description", "industry", "notes"]
  doc_id_columns: ["customer_id"]
  metadata_columns: ["company_name", "contact_email", "region", "status"]
  select_condition: "account_status == 'active'"
  column_types:
    annual_revenue: "float"
    employee_count: "int"

metadata:
  source: crm_export
  class: customer_data
```

### Example 3: Excel Multiple Sheets

```yaml
vectara:
  corpus_key: sales_data

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/home/vectara/data/sales_report.xlsx"
  mode: "element"
  text_columns: ["transaction_description", "notes"]
  metadata_columns: ["date", "amount", "region", "representative"]
  sheet_names: ["2023", "2024"]  # Process these sheets
  column_types:
    amount: "float"
    transaction_id: "str"

metadata:
  source: sales_database
  coverage: "2023-2024"
```

### Example 4: FAQ/Knowledge Base

```yaml
vectara:
  corpus_key: faqs

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/home/vectara/data/faq.csv"
  mode: "element"
  text_columns: ["question", "answer"]
  title_column: "topic"
  metadata_columns: ["category", "difficulty", "date_updated"]

metadata:
  source: customer_support
  type: faq
  update_frequency: weekly
```

### Example 5: Reference/Lookup Table

```yaml
vectara:
  corpus_key: reference_data

crawling:
  crawler_type: csv

csv_crawler:
  file_path: "/home/vectara/data/feature_matrix.csv"
  mode: "table"  # Entire table as one document
  max_rows: 500
  max_cols: 50

metadata:
  source: product_specifications
  type: reference_table
```

## Supported Data Types

### Text-Based Data
- Product descriptions and specifications
- Customer notes and comments
- FAQ entries
- Survey responses
- News articles or blog posts
- Policy documents
- Contact information

### Structured Data
- Product catalogs with prices and features
- Customer relationship management (CRM) data
- Inventory databases
- Sales records and transactions
- Employee directories
- Reference tables and lookup data

### Multi-Sheet Workbooks
- Financial reports (multiple years)
- Department data (each sheet = one department)
- Regional information (each sheet = one region)
- Time-series data (each sheet = one period)

## Performance Considerations

### File Size

| File Size | Time | Memory | Notes |
|-----------|------|--------|-------|
| < 1 MB | < 1 sec | 50 MB | Instant indexing |
| 1-10 MB | 5-30 sec | 100-200 MB | Normal processing |
| 10-50 MB | 30-300 sec | 200-500 MB | May need optimization |
| 50-100 MB | Minutes | 500+ MB | Use filtering or chunking |
| > 100 MB | Large | > 1 GB | Split into multiple files |

### Optimization

1. **Filter rows**: `select_condition` reduces data
2. **Limit columns**: Only include necessary text and metadata columns
3. **Use chunking**: `rows_per_chunk` for flat data
4. **Increase Docker resources** if running containerized

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Support

For issues:

1. Check file encoding and format (UTF-8, valid CSV/XLSX)
2. Verify column names match exactly
3. Test with minimal configuration first
4. Review [Troubleshooting Guide](../deployment/troubleshooting.md)
5. Open [GitHub issue](https://github.com/vectara/vectara-ingest/issues)
