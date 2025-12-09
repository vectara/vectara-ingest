# Windows Installation Guide for vectara-ingest

Complete guide to set up vectara-ingest on Windows using Python virtual environment (no Docker).

---

## Part 1: System Dependencies

### Step 1: Install via Winget

Open **PowerShell as Administrator** (Win + X → PowerShell Admin):

```powershell
winget install Python.Python.3.11
winget install Gyan.FFmpeg
winget install Git.Git
winget install Microsoft.VCRedist.2015+.x64
```

### Step 2: Install Tesseract OCR

1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run installer `tesseract-ocr-w64-setup-*.exe`
3. Check "Add to PATH" during installation
4. Install to: `C:\Program Files\Tesseract-OCR`

**If not in PATH:**
```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "Machine") + ";C:\Program Files\Tesseract-OCR", "Machine")
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

### Step 3: Install Poppler

1. Download from: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract ZIP, rename to `poppler`
3. Copy to: `C:\Program Files\poppler`
4. Structure: `C:\Program Files\poppler\Library\bin\`

**Add to PATH:**
```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "Machine") + ";C:\Program Files\poppler\Library\bin", "Machine")
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
```

### Step 4: Verify System Dependencies

Close and reopen PowerShell, then verify:

```powershell
python --version      # Python 3.11.x
ffmpeg -version       # ffmpeg version x.x.x
git --version         # git version x.x.x
tesseract --version   # tesseract x.x.x
pdfinfo -v            # pdfinfo version x.x.x
```

---

## Part 2: Python Environment Setup

### Step 1: Create Virtual Environment

```powershell
cd C:\Users\<username>\vectara-ingest
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**If execution policy error:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 2: Install Python Packages

```powershell
# Upgrade pip
python -m pip install --upgrade pip
pip install wheel setuptools

# Install PyTorch (CPU)
pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu

# Install main requirements (10-20 minutes)
pip install -r requirements.txt

# Install Extra Features
pip install -r requirements-extra.txt
python -m spacy download en_core_web_lg

# Install Playwright browser
playwright install chromium

# Install python-magic-bin (Windows-specific)
pip uninstall python-magic python-magic-bin -y
pip install python-magic-bin

```

### Step 4: Verify Python Installation

```powershell
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import playwright; print('Playwright: OK')"
python -c "import magic; print('python-magic: OK')"
python -c "import pytesseract; print('pytesseract: OK')"
python -c "import pdf2image; print('pdf2image: OK')"
```

---

## Part 3: Configuration and Running

### Step 1: Configure Secrets

```powershell
copy secrets.example.toml secrets.toml
notepad secrets.toml
```

Add your credentials:
```toml
[default]
api_key = "your-vectara-api-key"
```

### Step 2: Run Crawler

```powershell
# Activate venv (if not already active)
.\venv\Scripts\Activate.ps1

# Run with config file
python ingest.py --config-file .\config\your-config.yaml --profile default
```

---

## What Each Dependency Does

| Package | Purpose | Used By |
|---------|---------|---------|
| **Python 3.11** | Runtime | All crawlers |
| **FFmpeg** | Audio/video processing | YouTube, audio/video files |
| **Tesseract** | OCR for images/scanned PDFs | PDF, Folder, Website crawlers |
| **Poppler** | PDF to image conversion | PDF, Folder, Website crawlers |
| **PyTorch** | ML/AI processing | Document analysis, embeddings |
| **Playwright** | Web browser automation | Website, RSS crawlers |
| **python-magic-bin** | File type detection | All file processing |
