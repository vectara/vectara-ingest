# Folder Crawler

The Folder crawler indexes local files from your file system or mounted volumes. It supports various file types including documents (PDF, DOCX, XLSX), spreadsheets with multi-sheet support, audio/video files, and automatic metadata extraction from the file system.

## Overview

- **Crawler Type**: `folder`
- **Authentication**: None (local file system access)
- **File Types**: All formats (PDF, DOCX, XLSX, CSV, images, audio, video, etc.)
- **CSV/Excel**: Auto-separator detection, multi-sheet support
- **Metadata**: Automatic extraction from file system (creation time, modification time, size, parent folder)
- **Metadata Files**: Optional CSV files with custom metadata
- **Parallel Processing**: Ray-based distributed processing for large directories
- **Volume Support**: Docker volume mounting and local paths

## Use Cases

- Index local document repositories
- Crawl team file shares or network drives
- Process downloaded research papers or documentation
- Build searchable archives of local files
- Ingest spreadsheets with automatic table parsing
- Index media files with transcription support
- Batch process large collections of mixed file types
- Corporate knowledge base from shared network folders

## Getting Started

### Local File System

For local development or small file collections:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: local-files

crawling:
  crawler_type: folder

folder_crawler:
  path: "/home/user/documents"
  extensions: ["*"]  # All files
  source: "local-folder"
```

### Docker Volume

For containerized deployments, mount your folder as a Docker volume:

```bash
docker run -v /local/path:/home/vectara/data -it vectara-ingest
```

Configure the crawler to use the default Docker path:

```yaml
folder_crawler:
  path: "/home/vectara/data"
```

The crawler automatically detects if running in Docker and uses the mounted volume.

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: folder-corpus

crawling:
  crawler_type: folder

folder_crawler:
  # Local path to folder (required)
  path: "/path/to/folder"

  # File extensions to include (required)
  extensions: ["*"]  # All files, or ["pdf", ".docx", ".xlsx"]

  # Source label for metadata
  source: "folder"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: folder-corpus
  reindex: false
  verbose: true

  chunking_strategy: sentence
  chunk_size: 512
  remove_code: false

crawling:
  crawler_type: folder

folder_crawler:
  # File path (required)
  path: "/path/to/documents"

  # File type filtering (required)
  extensions: [".pdf", ".docx", ".xlsx", ".csv"]

  # Optional metadata CSV file
  metadata_file: "metadata.csv"

  # Source identifier for tracking
  source: "knowledge-base"

  # Parallel processing with Ray
  ray_workers: 4          # Number of parallel workers (0 = sequential, -1 = CPU count)
  num_per_second: 10      # Rate limiting

  # Excel sheet handling
  sheet_names: ["Summary", "Details"]  # Specific sheets, or all sheets if omitted

doc_processing:
  # For attachments and complex files
  doc_parser: unstructured
  parse_tables: true
  do_ocr: false           # Enable OCR for scanned PDFs (slower)
  summarize_images: false

metadata:
  source: folder
  collection_type: documents
  category: knowledge-base
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `path` | string | Yes | - | Local folder path or Docker mount path |
| `extensions` | list | Yes | - | File extensions to include: `["*"]` for all, or specific like `[".pdf", ".docx"]` |
| `metadata_file` | string | No | None | CSV file with custom metadata (filename in first column) |
| `source` | string | No | `"folder"` | Source label for metadata tracking |
| `ray_workers` | int | No | `0` | Parallel workers: 0 = sequential, -1 = auto (CPU count), N > 0 = N workers |
| `num_per_second` | int | No | `10` | Rate limiting (minimum 1) |
| `sheet_names` | list | No | All sheets | Excel sheets to process (if omitted, processes all sheets) |

## File Extension Filtering

### Include All Files

Process every file in the folder:

```yaml
folder_crawler:
  path: "/data"
  extensions: ["*"]
```

### Specific File Types

Process only certain file types:

```yaml
folder_crawler:
  path: "/data"
  extensions: [".pdf", ".docx", ".xlsx"]
```

### Common Extensions

```yaml
# Documents
extensions: [".pdf", ".doc", ".docx", ".ppt", ".pptx"]

# Data files
extensions: [".csv", ".xls", ".xlsx", ".json", ".xml"]

# Text files
extensions: [".txt", ".md", ".rst", ".html"]

# Media files (with transcription support)
extensions: [".mp3", ".wav", ".mp4", ".webm"]

# Images (with OCR support)
extensions: [".png", ".jpg", ".jpeg", ".gif", ".pdf"]
```

## Metadata File Format

The optional metadata CSV file allows you to attach custom metadata to specific files. The first column must be `filename` (relative path to files), and additional columns become metadata fields.

### Metadata CSV Example

```csv
filename,department,author,classification,review_status
reports/Q4-summary.pdf,Finance,John Smith,Confidential,Approved
reports/Q3-summary.pdf,Finance,Jane Doe,Confidential,Approved
guides/employee-handbook.pdf,HR,Alice Johnson,Public,Published
guides/onboarding.pdf,HR,Bob Lee,Internal,Draft
```

### Metadata File Structure

- **First Column**: `filename` - The relative path from your folder root to the file
- **Additional Columns**: Any custom metadata fields you want to attach
- **Format**: CSV (comma-separated by default)

### Usage in Configuration

```yaml
folder_crawler:
  path: "/documents"
  extensions: ["*"]
  metadata_file: "file-metadata.csv"
```

The crawler will:
1. Read the CSV file from `{path}/file-metadata.csv`
2. Match files by their relative path (filename column)
3. Attach custom metadata to indexed documents
4. Skip the metadata file itself during crawling

### Metadata Example

If you have:
```
/documents/
  ├── reports/
  │   ├── Q4-summary.pdf
  │   └── Q3-summary.pdf
  ├── guides/
  │   └── handbook.pdf
  └── file-metadata.csv
```

And `file-metadata.csv` contains:
```csv
filename,source_system,date_created,owner
reports/Q4-summary.pdf,SAP,2024-11-01,Finance Team
guides/handbook.pdf,Confluence,2024-06-15,HR Team
```

The metadata will be automatically attached to each document during indexing.

## CSV and Excel Processing

The Folder crawler includes special handling for spreadsheet files with intelligent parsing and optional table extraction.

### CSV Auto-Separator Detection

CSV files are automatically parsed with separator detection:

```yaml
folder_crawler:
  path: "/data"
  extensions: [".csv"]
```

Supported separators: comma (,), semicolon (;), tab (\t), pipe (|)

The crawler detects the separator automatically or uses the default for your locale.

### CSV Configuration

```yaml
folder_crawler:
  extensions: [".csv"]
  source: "csv-data"

doc_processing:
  parse_tables: true        # Extract and format table content
  doc_parser: unstructured
```

Example: Process a CSV with automatic formatting

```csv
Product,Q1 Sales,Q2 Sales,Q3 Sales,Q4 Sales
Widget A,1000,1200,1400,1600
Widget B,2000,2200,2400,2600
Widget C,3000,3200,3400,3600
```

This is indexed as:
- Document title: The filename
- Content: Table formatted for semantic search
- Metadata: File creation time, size, parent folder

### Excel Multi-Sheet Support

Excel files (.xls, .xlsx) can be processed sheet-by-sheet:

```yaml
folder_crawler:
  path: "/data"
  extensions: [".xlsx"]
  sheet_names: ["Summary", "Details"]  # Process specific sheets
```

Or process all sheets (default):

```yaml
folder_crawler:
  path: "/data"
  extensions: [".xlsx"]
  # sheet_names omitted = process all sheets
```

### Excel Configuration

```yaml
folder_crawler:
  extensions: [".xlsx"]
  sheet_names: ["Sheet1", "Sheet2"]  # Optional: specific sheets

doc_processing:
  parse_tables: true
  doc_parser: unstructured
```

How multi-sheet processing works:

1. **Per-Sheet Indexing**: Each sheet is indexed as a separate document
2. **Document Naming**: `{filename} - {sheet_name}`
3. **Table Parsing**: Tables are extracted from each sheet
4. **Metadata**: Each sheet includes parent file information

Example: File `sales.xlsx` with sheets "Summary" and "Regional"

```
Indexed as:
- Document 1: "sales.xlsx - Summary"
- Document 2: "sales.xlsx - Regional"
```

Both retain metadata:
- `title`: The sheet document name
- `created_at`: Original file creation time
- `last_updated`: Original file modification time
- `file_size`: Original file size
- `parent_folder`: Parent directory name
- `source`: "folder"

### Limiting Sheet Processing

To process only specific sheets:

```yaml
folder_crawler:
  path: "/data"
  extensions: [".xlsx"]
  sheet_names: ["Summary"]  # Only process "Summary" sheet
```

The crawler will:
- Skip sheets not in the list
- Log warnings for missing sheets
- Continue processing other files

## Audio and Video File Support

The Folder crawler can index media files with automatic transcription:

```yaml
folder_crawler:
  path: "/media"
  extensions: [".mp3", ".wav", ".mp4", ".webm"]
```

### Supported Audio Formats

- MP3
- WAV
- FLAC
- AAC
- OGG
- WMA
- M4A
- OPUS

### Supported Video Formats

- MP4
- AVI
- MOV
- WebM
- MKV
- WMV
- FLV
- MPEG / MPG
- M4V
- 3GP
- F4V

### Media Processing

```yaml
folder_crawler:
  extensions: [".mp3", ".mp4"]

doc_processing:
  # Audio/video transcription (requires appropriate model)
  model_config:
    text:
      provider: openai
      model_name: "whisper-1"
```

When enabled:
- Audio is transcribed to text
- Transcriptions are indexed with media metadata
- Original file metadata preserved
- Searchable through text content

### Metadata for Media Files

Each indexed media file includes:

- `created_at`: File creation timestamp
- `last_updated`: File modification timestamp
- `file_size`: File size in bytes
- `source`: Source identifier
- `title`: Filename
- `parent_folder`: Parent directory name
- `folder_path`: Full path to parent folder

## File Metadata Extraction

The crawler automatically extracts file system metadata for all indexed files:

### Automatic Metadata

For every file processed:

```yaml
created_at: "2024-11-18T10:30:45"     # File creation timestamp (ISO 8601)
last_updated: "2024-11-18T14:25:30"   # File modification timestamp
file_size: 102400                      # File size in bytes
source: "folder"                       # Source identifier
title: "document.pdf"                  # Filename
parent_folder: "reports"               # Immediate parent folder name
folder_path: "/documents/reports"      # Full path to parent folder
```

### Using File Metadata in Queries

You can filter indexed content using file metadata:

```
Find PDFs from the "reports" folder created in 2024
Filter: parent_folder = "reports" AND created_at >= "2024-01-01"

Find recently modified documents
Filter: source = "folder" AND last_updated >= "2024-11-01"

Find large documents (> 1MB)
Filter: file_size > 1000000
```

### Custom Metadata with CSV

Combine file system metadata with custom metadata:

```csv
filename,department,review_status
reports/Q4.pdf,Finance,Approved
reports/Q3.pdf,Finance,Draft
```

Result metadata includes both:
- Automatic: `created_at`, `last_updated`, `file_size`, etc.
- Custom: `department`, `review_status`

## Docker Volume Mounting

### Basic Volume Mount

Mount a local folder into the Docker container:

```bash
docker run -v /local/path:/home/vectara/data vectara-ingest
```

Configuration:

```yaml
folder_crawler:
  path: "/home/vectara/data"
```

### Docker Compose Example

```yaml
version: '3.8'
services:
  vectara:
    image: vectara-ingest:latest
    volumes:
      - /local/documents:/home/vectara/data
    environment:
      - VECTARA_API_KEY=${VECTARA_API_KEY}
    command: bash run.sh config/folder.yaml default
```

### Permissions in Docker

Ensure the Docker container has read access to mounted volumes:

```bash
# Make folder readable by container
chmod 755 /local/path

# Make files readable
chmod 644 /local/path/files
```

### Windows Paths

On Windows, use forward slashes or escape backslashes:

```bash
# Docker Desktop on Windows
docker run -v C:/Users/Documents:/home/vectara/data vectara-ingest

# Or with escaped backslashes
docker run -v "C:\\Users\\Documents:/home/vectara/data" vectara-ingest
```

## Performance Optimization

### Sequential vs Parallel Processing

For small folders (< 100 files), sequential processing is fine:

```yaml
folder_crawler:
  ray_workers: 0  # Sequential
```

For larger collections, enable parallel processing:

```yaml
folder_crawler:
  ray_workers: 4  # 4 parallel workers
```

Or auto-detect:

```yaml
folder_crawler:
  ray_workers: -1  # Use CPU count
```

### Rate Limiting

Control indexing rate for API limits:

```yaml
folder_crawler:
  num_per_second: 10  # 10 documents per second
```

Increase for faster crawling (respects API limits):

```yaml
folder_crawler:
  num_per_second: 20  # 20 documents per second
```

### Large Directory Handling

For folders with thousands of files:

1. **Use Parallel Processing**:
   ```yaml
   folder_crawler:
     ray_workers: -1  # Auto-detect CPU count
   ```

2. **Optimize Resource Usage**:
   ```yaml
   doc_processing:
     process_locally: true  # Saves memory
   ```

3. **Filter by Extension**:
   ```yaml
   folder_crawler:
     extensions: [".pdf", ".docx"]  # Only needed types
   ```

4. **Batch Processing**:
   Process large folders in parts:
   ```bash
   # Process first half
   bash run.sh config/folder-part1.yaml default

   # Process second half
   bash run.sh config/folder-part2.yaml default
   ```

### Monitoring Progress

Track crawling progress with logs:

```bash
# Watch logs in real-time
docker logs -f vingest

# Or check file
tail -f logs/ingest.log

# Check for errors
grep "Error" logs/ingest.log
```

### Memory Usage

For very large files or thousands of documents:

```yaml
doc_processing:
  process_locally: true      # Process in local workers

folder_crawler:
  ray_workers: 4             # Limited workers
```

### Chunk Size Optimization

Adjust chunking for your content:

```yaml
vectara:
  chunking_strategy: sentence  # Better for varied content
  chunk_size: 512              # Balanced (adjust 256-1024)
```

## Example Configurations

### PDF Documents

Index a folder of PDF files:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: pdf-archive
  reindex: true

crawling:
  crawler_type: folder

folder_crawler:
  path: "/documents/research-papers"
  extensions: [".pdf"]
  source: "pdf-archive"
  ray_workers: -1

doc_processing:
  do_ocr: false  # Enable if PDFs are scanned
  parse_tables: true

metadata:
  category: research
```

### Mixed Documents with Metadata

Index mixed file types with custom metadata:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: knowledge-base

crawling:
  crawler_type: folder

folder_crawler:
  path: "/shared/documents"
  extensions: [".pdf", ".docx", ".xlsx", ".csv"]
  metadata_file: "metadata.csv"
  source: "knowledge-base"
  ray_workers: 4

metadata:
  source: shared-drive
  environment: production
```

With metadata.csv:

```csv
filename,department,author,classification
docs/policy.pdf,HR,Jane Doe,Public
docs/budget.xlsx,Finance,John Smith,Confidential
data/sales.csv,Sales,Bob Johnson,Internal
```

### Spreadsheets with Specific Sheets

Process only certain Excel sheets:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: financial-data

crawling:
  crawler_type: folder

folder_crawler:
  path: "/finance/reports"
  extensions: [".xlsx"]
  sheet_names: ["Summary", "Detailed Results"]
  source: "financial-reports"

doc_processing:
  parse_tables: true

metadata:
  category: financial
```

### Media Files with Transcription

Index audio/video with transcription:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: media-transcripts

crawling:
  crawler_type: folder

folder_crawler:
  path: "/media/recordings"
  extensions: [".mp3", ".mp4"]
  source: "media-library"

doc_processing:
  model_config:
    text:
      provider: openai
      model_name: "whisper-1"

metadata:
  content_type: media
```

### Large-Scale Parallel Processing

Optimize for thousands of files:

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: large-archive
  reindex: false

crawling:
  crawler_type: folder

folder_crawler:
  path: "/archive"
  extensions: ["*"]
  source: "archive"
  ray_workers: -1              # Use all CPUs
  num_per_second: 20           # Higher rate

doc_processing:
  process_locally: true
  doc_parser: unstructured
  parse_tables: false          # Skip for speed

metadata:
  source: archive
  batch_size: large
```

## Troubleshooting

### Path Not Found

**Error**: `Path does not exist: /path/to/folder`

**Solutions**:
1. Verify the path exists and is accessible:
   ```bash
   ls -la /path/to/folder
   ```

2. For Docker, ensure volume is mounted:
   ```bash
   docker inspect vectara-ingest | grep Mounts
   ```

3. Check file permissions:
   ```bash
   ls -ld /path/to/folder  # Should have 'x' permission
   ```

### Permission Denied

**Error**: `Permission denied: /path/to/folder`

**Solutions**:
1. Make folder accessible:
   ```bash
   chmod 755 /path/to/folder
   ```

2. For Docker on Linux, run as appropriate user:
   ```bash
   docker run --user $(id -u):$(id -g) -v /path:/home/vectara/data vectara-ingest
   ```

3. Check file ownership:
   ```bash
   ls -l /path/to/folder
   ```

### No Files Found

**Error**: Crawler runs but indexes 0 files

**Solutions**:
1. Check file extensions:
   ```yaml
   extensions: ["*"]  # Include all files first
   ```

2. Verify files exist:
   ```bash
   find /path/to/folder -type f | head -20
   ```

3. Check extension format (include dot):
   ```yaml
   extensions: [".pdf", ".docx"]  # Correct
   extensions: ["pdf", "docx"]    # Wrong
   ```

### Metadata File Not Found

**Error**: `Metadata file not found: metadata.csv`

**Solutions**:
1. Ensure metadata file exists in folder:
   ```bash
   ls -la /path/to/folder/metadata.csv
   ```

2. Verify file name in config:
   ```yaml
   metadata_file: "metadata.csv"  # Must match exactly
   ```

3. Ensure metadata.csv is CSV format:
   ```bash
   file /path/to/metadata.csv
   ```

### CSV Parsing Errors

**Error**: `Failed to parse CSV: [error details]`

**Solutions**:
1. Verify CSV format is valid
2. Ensure filename column exists and is named exactly `filename`
3. Check for UTF-8 encoding (not ANSI)
4. Verify file paths match relative paths in your folder

### Ray Worker Errors

**Error**: `Failed to initialize Ray workers`

**Solutions**:
1. Reduce worker count:
   ```yaml
   ray_workers: 2  # Instead of auto-detect
   ```

2. Check system resources:
   ```bash
   free -h        # Memory
   nproc          # CPU cores
   ```

3. Enable local processing:
   ```yaml
   doc_processing:
     process_locally: true
   ```

### Out of Memory

**Error**: `MemoryError` or `killed` status

**Solutions**:
1. Reduce parallel workers:
   ```yaml
   folder_crawler:
     ray_workers: 2
   ```

2. Enable local processing:
   ```yaml
   doc_processing:
     process_locally: true
   ```

3. Process in smaller batches:
   ```bash
   # Create separate configs for different parts
   bash run.sh config/folder-part1.yaml default
   bash run.sh config/folder-part2.yaml default
   ```

4. Skip optional processing:
   ```yaml
   doc_processing:
     do_ocr: false
     summarize_images: false
   ```

### Excel Sheet Not Found

**Error**: `Sheet 'SheetName' not found in file.xlsx`

**Solutions**:
1. List available sheets:
   ```python
   import pandas as pd
   xls = pd.ExcelFile('file.xlsx')
   print(xls.sheet_names)
   ```

2. Verify sheet names in config:
   ```yaml
   sheet_names: ["Summary", "Details"]  # Case-sensitive
   ```

3. Omit sheet_names to process all:
   ```yaml
   folder_crawler:
     extensions: [".xlsx"]
     # sheet_names omitted = all sheets
   ```

### Performance Issues

**Issue**: Slow crawling or timeout

**Solutions**:
1. Reduce rate limiting:
   ```yaml
   folder_crawler:
     num_per_second: 5
   ```

2. Enable parallel processing:
   ```yaml
   folder_crawler:
     ray_workers: 4
   ```

3. Skip expensive processing:
   ```yaml
   doc_processing:
     do_ocr: false
     summarize_images: false
   ```

4. Reduce chunk size:
   ```yaml
   vectara:
     chunk_size: 256
   ```

## Best Practices

### 1. Use Specific Extensions

```yaml
# Good: Target specific file types
extensions: [".pdf", ".docx"]

# Bad: Process all files (slower, less relevant)
extensions: ["*"]
```

### 2. Organize with Subfolders

```
/documents/
  /reports/
    report1.pdf
    report2.pdf
  /guides/
    handbook.pdf
  metadata.csv
```

Then filter by parent_folder in metadata:

```csv
filename,department
reports/report1.pdf,Finance
guides/handbook.pdf,HR
```

### 3. Version Your Configurations

```yaml
metadata:
  version: "1.0"
  created_date: "2024-11-18"
  notes: "Initial knowledge base setup"
```

### 4. Test with Small Samples

```yaml
# First, test with a subset
folder_crawler:
  path: "/documents/test-sample"
  extensions: [".pdf"]
```

Then expand to production.

### 5. Use Metadata CSV for Organization

```csv
filename,source_system,date_acquired,review_status
reports/2024-Q4.pdf,SAP,2024-11-01,Approved
reports/2024-Q3.pdf,SAP,2024-08-01,Approved
guidelines/handbook.pdf,Wiki,2024-06-15,Published
```

### 6. Monitor Indexing Progress

```bash
# Watch real-time logs
docker logs -f vingest

# Check completion
docker logs vingest | grep -i "crawling complete\|indexed"
```

### 7. Document Your Folder Structure

```markdown
# Document Folder Structure

/documents/
- reports/: Financial and business reports
- guides/: User guides and handbooks
- policies/: Company policies
- archive/: Legacy documents

## Metadata File

See metadata.csv for department and classification info.
```

### 8. Regular Maintenance

```bash
# Periodic full reindex (weekly/monthly)
0 1 * * 0 cd /path && bash run.sh config/folder.yaml default

# Check for new files
find /path/to/documents -type f -mtime -7  # Modified in last 7 days
```

## Running the Crawler

### Create Configuration

```bash
# Create config file
vim config/folder-documents.yaml
```

Add your configuration (see examples above).

### Set Environment Variables

No environment variables required for local folder crawling.

For Vectara API:

```bash
export VECTARA_API_KEY="your-api-key"
```

### Run the Crawler

```bash
# Single run
bash run.sh config/folder-documents.yaml default

# Monitor progress
docker logs -f vingest
```

### Scheduling Regular Crawls

Use cron for scheduled indexing:

```bash
# Daily at 2 AM
0 2 * * * cd /path/to/vectara-ingest && bash run.sh config/folder.yaml default

# Weekly on Sunday
0 2 * * 0 cd /path/to/vectara-ingest && bash run.sh config/folder.yaml default

# Every 6 hours
0 */6 * * * cd /path/to/vectara-ingest && bash run.sh config/folder.yaml default
```

Or use your preferred scheduler (Jenkins, GitHub Actions, cron, etc.).

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Crawlers Overview](index.md) - Other available crawlers
- [Document Processing](../features/document-processing.md) - Advanced document processing options
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## Common Workflows

### Workflow 1: Index a Research Paper Collection

```yaml
# config/research-papers.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: research-papers
  reindex: true

crawling:
  crawler_type: folder

folder_crawler:
  path: "/research/papers"
  extensions: [".pdf"]
  source: "research-archive"
  ray_workers: -1

doc_processing:
  parse_tables: true

metadata:
  category: research
```

Run:
```bash
bash run.sh config/research-papers.yaml default
```

### Workflow 2: Ingest Company Knowledge Base

```yaml
# config/knowledge-base.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: company-kb

crawling:
  crawler_type: folder

folder_crawler:
  path: "/knowledge-base"
  extensions: [".pdf", ".docx", ".xlsx"]
  metadata_file: "kb-metadata.csv"
  source: "company-kb"

metadata:
  environment: production
  sync_frequency: daily
```

With metadata.csv:
```csv
filename,department,review_status,version
policies/security.pdf,IT,Approved,2.1
procedures/hiring.docx,HR,Published,1.3
templates/invoice.xlsx,Finance,Published,1.0
```

### Workflow 3: Monitor Shared Drive for Updates

```bash
#!/bin/bash
# Run weekly folder crawl
0 2 * * 0 cd /vectara-ingest && \
  bash run.sh config/shared-drive.yaml default && \
  echo "Shared drive indexing complete" | mail -s "Vectara Indexing" admin@example.com
```

### Workflow 4: Archive Legacy Documents

```yaml
# config/legacy-archive.yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: legacy-docs
  reindex: true

crawling:
  crawler_type: folder

folder_crawler:
  path: "/archive/legacy"
  extensions: ["*"]
  metadata_file: "archive-metadata.csv"
  ray_workers: -1
  source: "legacy-archive"

metadata:
  collection_type: archive
  retention: permanent
```

## Advanced Topics

### Custom Index Update Schedule

For incremental updates, disable reindex:

```yaml
vectara:
  reindex: false  # Only add new/updated files
```

Or enable for full replacement:

```yaml
vectara:
  reindex: true   # Replace all indexed content
```

### Metadata-Driven Processing

Use metadata CSV for sophisticated categorization:

```csv
filename,classification,retention_years,owner_team
sensitive/cfo-report.pdf,Confidential,7,Executive
public/press-release.docx,Public,10,Marketing
technical/architecture.pdf,Internal,5,Engineering
```

Query later with metadata:

```
Find all Confidential documents
Filter: classification = "Confidential"

Find Engineering team documents
Filter: owner_team = "Engineering"
```

### Multi-Source Consolidation

Crawl multiple folders into same corpus:

```bash
# Run multiple configs
bash run.sh config/folder-dept1.yaml default
bash run.sh config/folder-dept2.yaml default
bash run.sh config/folder-dept3.yaml default
```

All indexed into same corpus with different source/metadata.

## Performance Benchmarks

Typical performance on modern hardware (4 CPU cores, 8GB RAM):

- **Text documents (PDF, DOCX)**: 50-100 files/minute (no OCR), 10-20 files/minute (with OCR)
- **Spreadsheets**: 30-50 sheets/minute
- **Media files**: 5-10 files/minute (with transcription)
- **Mixed content**: 20-50 files/minute

With parallel processing (-1 workers):
- Increases throughput by 3-4x depending on file types
- Uses additional CPU and memory

For 10,000 files:
- Sequential: ~2-5 hours
- Parallel (4 workers): ~30-60 minutes

Actual performance depends on:
- File size and complexity
- Processor speed
- Disk speed
- Network latency to Vectara API
- Document processing options (OCR, table extraction, etc.)

## FAQ

**Q: Can I index files from network drives?**
A: Yes! Mount network drives as volumes or access them locally if already mounted.

**Q: Does the crawler modify my files?**
A: No, the crawler only reads files. Your original files are never modified.

**Q: Can I exclude certain files?**
A: Use the `extensions` parameter. The crawler only processes matching extensions.

**Q: What happens to files that are deleted?**
A: Documents remain indexed. Use `reindex: true` to replace indexed content on next run.

**Q: Can I update existing files?**
A: Yes. Rerun the crawler with the same corpus_key and `reindex: false` to update changed files.

**Q: How do I handle very large files?**
A: Large files are automatically split into chunks. Adjust chunk size if needed.

**Q: Can I prioritize certain files?**
A: Create separate configs for different file types or folders, then run in priority order.

**Q: What's the maximum folder size?**
A: No hard limit. Tested up to 100,000+ files. Adjust workers and rate limiting as needed.

**Q: How are permissions handled?**
A: The crawling process uses the permissions of the user running it. Ensure read access.

**Q: Can I use relative paths?**
A: Use absolute paths for reliability, especially in Docker and scheduled tasks.

**Q: How do I troubleshoot missing files?**
A: Check `extensions` parameter, verify file permissions, and check logs for errors.
