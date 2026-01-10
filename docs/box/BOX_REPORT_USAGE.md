# Box Structure Report Generator

The Box crawler can generate a detailed report of all folders and files in your Box account without downloading any files.

## Features

- Lists all folders and subfolders recursively
- Shows all files with metadata (size, dates, owner)
- Generates JSON report with complete structure
- No file downloads (fast scanning)
- Shows total statistics (folder count, file count, total size)

## Configuration

In your `config/box-adeel.yaml`:

```yaml
box_crawler:
  # ... authentication settings ...

  folder_ids:
    - "0"  # Scan all folders (root)

  recursive: true  # Scan subfolders

  # Enable report generation
  generate_report: true

  # Output path for report
  report_path: /tmp/box_structure_report.json
```

## Report Output Format

The generated JSON report contains:

```json
{
  "scan_date": "2025-12-23T10:30:00",
  "authenticated_user": {
    "name": "Adeel Ehsan",
    "login": "adeel@vectara.com",
    "id": "45685194653"
  },
  "total_folders": 25,
  "total_files": 342,
  "total_size_bytes": 5368709120,
  "total_size_gb": 5.0,
  "folders": [
    {
      "name": "Marketing",
      "id": "123456789",
      "path": "Marketing",
      "created_at": "2024-01-15T10:30:00",
      "modified_at": "2024-12-01T15:45:00",
      "owner": "Adeel Ehsan",
      "file_count": 15,
      "total_size": 104857600,
      "files": [
        {
          "name": "Q4_Report.pdf",
          "id": "987654321",
          "size": 2048576,
          "extension": ".pdf",
          "created_at": "2024-11-01T09:00:00",
          "modified_at": "2024-11-15T14:30:00",
          "created_by": "John Doe",
          "url": "https://app.box.com/file/987654321"
        }
      ],
      "subfolders": [
        {
          "name": "Campaigns",
          "id": "111222333",
          "path": "Marketing/Campaigns",
          "files": [...],
          "subfolders": [...]
        }
      ]
    }
  ]
}
```

## Usage

### 1. Generate Report (No Downloads)

Set `generate_report: true` in config, then run:

```bash
docker run -v $(pwd):/home/vectara/env vectara/vectara-ingest box-adeel
```

The report will be saved to `/tmp/box_structure_report.json`

### 2. Download Files (No Report)

Set `generate_report: false` in config, then run the same command.

## Report Fields Explained

### Top Level:
- `scan_date`: When the report was generated
- `authenticated_user`: The Box user account used
- `total_folders`: Total number of folders scanned
- `total_files`: Total number of files found
- `total_size_bytes`: Total size in bytes
- `total_size_gb`: Total size in gigabytes

### Per Folder:
- `name`: Folder name
- `id`: Box folder ID
- `path`: Full path from root
- `created_at`: Creation timestamp
- `modified_at`: Last modification timestamp
- `owner`: Folder owner name
- `file_count`: Number of files in this folder and all subfolders
- `total_size`: Total size of all files in this folder tree
- `files`: Array of file objects
- `subfolders`: Array of subfolder objects (recursive)

### Per File:
- `name`: File name
- `id`: Box file ID
- `size`: File size in bytes
- `extension`: File extension (e.g., ".pdf")
- `created_at`: Creation timestamp
- `modified_at`: Last modification timestamp
- `created_by`: Creator name
- `url`: Direct Box URL to the file

## Use Cases

1. **Audit**: Get complete inventory of Box content
2. **Planning**: Estimate download time/bandwidth before actual download
3. **Analysis**: Understand folder structure and file distribution
4. **Reporting**: Share Box content summary with stakeholders
5. **Migration Planning**: Plan migration strategy based on structure

## Tips

- Report generation is fast (no file downloads)
- Works with both JWT and OAuth authentication
- Respects folder permissions (only lists accessible content)
- Can be run multiple times without affecting Box content
- Report is human-readable JSON (easy to parse with scripts)
