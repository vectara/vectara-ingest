# Box Ingestion Guide

Complete guide for ingesting all Box files into Vectara with error handling.

## Overview

This configuration will:
- ✅ Download all 2,652 supported files (2.10 GB) from Box
- ✅ Extract tables from PDFs (no AI summarization)
- ✅ Skip image summarization (faster processing)
- ✅ Ingest XLSX, DOCX, PPTX, and other supported formats
- ✅ Automatically save failed files to inspection folder
- ✅ Process 97.8% of your Box content

## What Files Will Be Ingested?

### ✅ Supported Files (2,652 files = 2.10 GB)

| Category | Files | Size | Examples |
|----------|-------|------|----------|
| **Documents** | 1,947 | 1.04 GB | PDF (1,594), DOCX (282), DOC (71) |
| **Spreadsheets** | 535 | 0.55 GB | XLSX (274), XLSM (98), XLSB (117), XLS (46) |
| **Presentations** | 105 | 0.48 GB | PPTX (89), PPT (16) |
| **Images** | 65 | 0.03 GB | PNG (29), JPG (36) |

### ❌ Unsupported Files (61 files = 1.15 GB)

Will be skipped automatically:
- ZIP files (31) - 0.76 GB
- EXE files (2) - 0.29 GB
- WRF files (2) - 0.08 GB
- DOTX, PPSX, MP4 (26) - 0.02 GB

## Configuration

The ingestion uses: [config/box-ingest.yaml](file:///Users/adeel/vectara/vectara-ingest/config/box-ingest.yaml)

### Key Settings

```yaml
vectara:
  store_docs: true                    # Save failed files
  output_dir: /tmp/box_inspection     # Where failed files go

doc_processing:
  parse_tables: true                  # Extract tables from PDFs
  summarize_tables: false             # Skip AI table summarization
  summarize_images: false             # Skip AI image summarization

box_crawler:
  skip_indexing: false                # Enable Vectara ingestion
  generate_report: false              # Ingest files (not just report)
  max_files: 0                        # Process all files
```

## Prerequisites

### 1. Update Configuration

Edit `config/box-ingest.yaml`:

```yaml
vectara:
  api_key: "YOUR_VECTARA_API_KEY"      # Replace with your API key
  customer_id: "YOUR_CUSTOMER_ID"      # Replace with your customer ID
  corpus_key: box                       # Or your corpus name
```

### 2. Verify Box Authentication

Ensure your `box_config.json` is present and has valid credentials.

If you need as-user authentication, uncomment in config:
```yaml
box_crawler:
  as_user_id: "45547231077"  # Your Box user ID
```

### 3. Install Dependencies (if needed)

```bash
pip install -r requirements.txt
```

## How to Run

### Option 1: Using Docker (Recommended)

```bash
cd /Users/adeel/vectara/vectara-ingest

# Run the ingestion
docker run -v $(pwd):/home/vectara/env vectara/vectara-ingest box-ingest
```

### Option 2: Local Python

```bash
cd /Users/adeel/vectara/vectara-ingest

# Run the ingestion
python -m vectara_ingest.main --config config/box-ingest.yaml
```

## What Happens During Ingestion

### Step 1: Download Phase
- Authenticates to Box using JWT
- Crawls all folders recursively from root
- Downloads files to `/tmp/box_downloads`
- Progress logged for each file

### Step 2: Processing Phase
- Parses documents (PDF, DOCX, XLSX, etc.)
- Extracts tables from PDFs using GMFT
- Skips table/image AI summarization (faster)
- Creates chunks for indexing

### Step 3: Indexing Phase
- Uploads processed documents to Vectara
- Includes table content in searchable text
- Preserves document metadata

### Step 4: Error Handling
- Failed files automatically copied to `/tmp/box_inspection`
- Logs error details for each failed file
- Continues processing remaining files

## Output Directories

### Downloaded Files
```
/tmp/box_downloads/
  ├── RoHS_report.pdf
  ├── Chemical_Assessment.pdf
  ├── Financial_Report.xlsx
  └── ...
```

### Failed Files (Inspection Folder)
```
/tmp/box_inspection/
  ├── problematic_file1.pdf
  ├── corrupted_doc.docx
  └── failed_metadata.json
```

Each failed file includes:
- Original file copy
- Metadata JSON with error details
- Timestamp and error message

## Expected Results

### Processing Statistics
- **Total files processed**: ~2,652
- **Expected success rate**: 95-98%
- **Failed files**: ~50-130 (saved for inspection)
- **Processing time**: 1-3 hours (depending on connection speed)

### What Gets Indexed

**For PDFs**:
- All text content
- Extracted table content (as text, not summarized)
- Document metadata (title, dates, owner)

**For XLSX/XLS**:
- All sheet data
- Cell values and formulas
- Sheet names

**For DOCX/DOC**:
- All text content
- Headings and structure
- Embedded tables

**For PPTX/PPT**:
- Slide text content
- Notes and comments
- Slide titles

## Monitoring Progress

### Watch Logs
```bash
# If using Docker
docker logs -f <container_id>

# Look for:
# - "Downloaded file: filename.pdf"
# - "Indexed document: filename.pdf"
# - "Failed to process: filename.pdf"
```

### Check Progress
```bash
# Count downloaded files
ls -1 /tmp/box_downloads | wc -l

# Check inspection folder for failures
ls -1 /tmp/box_inspection
```

## Troubleshooting

### Issue: No files being downloaded

**Check**:
1. Box authentication working?
   ```bash
   # Test Box connection
   python -c "from boxsdk import JWTAuth, Client; import json; config = json.load(open('box_config.json')); auth = JWTAuth.from_settings_dictionary(config); client = Client(auth); print(client.user().get().name)"
   ```

2. As-user authentication needed?
   - If using "App Access Only", uncomment `as_user_id` in config
   - Or share folders with service account

### Issue: All files failing to index

**Check**:
1. Vectara credentials correct?
2. Corpus exists and is accessible?
3. Check logs for specific error messages

### Issue: Some PDFs failing

**Possible causes**:
- Corrupted PDF files
- Password-protected PDFs
- Very large PDFs (>100MB)

**Solution**: Check `/tmp/box_inspection` for these files

### Issue: Out of disk space

**Solution**:
```bash
# Clean up downloaded files after successful indexing
rm -rf /tmp/box_downloads/*

# Or change download path to larger disk
# Edit config: download_path: /larger/disk/path
```

## Post-Ingestion

### 1. Review Failed Files
```bash
cd /tmp/box_inspection
ls -lh  # See which files failed
```

### 2. Verify Ingestion
Query your Vectara corpus to verify documents are searchable.

### 3. Clean Up
```bash
# Remove downloaded files (after verification)
rm -rf /tmp/box_downloads

# Keep inspection folder for manual review
```

## Cost Considerations

### Processing Costs
- **No AI summarization** → $0 LLM costs
- Only Vectara ingestion API costs apply

### Storage
- Temporary: ~2.10 GB during download
- Vectara: Depends on your pricing plan

### Time
- Download: ~30-60 minutes (depends on internet speed)
- Processing: ~1-2 hours (local processing)
- Total: ~2-3 hours for all 2,652 files

## Next Steps

After successful ingestion:

1. **Test search queries** on your Vectara corpus
2. **Review failed files** in `/tmp/box_inspection`
3. **Handle unsupported files** (ZIP, EXE) if needed
4. **Set up incremental sync** for new/updated Box files

## Advanced Configuration

### Enable OCR for Scanned PDFs
If you have scanned PDFs:
```yaml
doc_processing:
  do_ocr: true
  easy_ocr_config:
    force_full_page_ocr: true
    lang: ['en']
```

### Filter Specific File Types
To ingest only certain types:
```yaml
box_crawler:
  file_extensions: [".pdf", ".docx", ".xlsx"]  # Only these types
```

### Limit Files for Testing
Test with first 100 files:
```yaml
box_crawler:
  max_files: 100  # Limit for testing
```

## Summary

✅ **Code is ready** - No modifications needed
✅ **Configuration created** - `config/box-ingest.yaml`
✅ **Error handling built-in** - Failed files → `/tmp/box_inspection`
✅ **2,652 files ready** - 2.10 GB of supported content
✅ **Ready to run** - Just update API credentials and execute

The existing vectara-ingest infrastructure handles everything:
- Box file download
- Document parsing (PDF, DOCX, XLSX, PPTX)
- Table extraction (no summarization)
- Error handling and logging
- Vectara ingestion

**You can start the ingestion immediately after updating your API credentials in the config file!**
