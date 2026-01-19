# macOS Installation Guide for vectara-ingest

Complete guide to set up vectara-ingest on macOS using Python virtual environment (no Docker).

---

## Part 1: System Dependencies

### Step 1: Install Homebrew (if not installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**For Apple Silicon (M1/M2/M3), add to PATH:**
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Step 2: Install via Homebrew

```bash
brew install python@3.11
brew install ffmpeg
brew install git
brew install tesseract
brew install poppler
brew install libmagic
```

### Step 3: Verify System Dependencies

```bash
python3.11 --version   # Python 3.11.x
ffmpeg -version        # ffmpeg version x.x.x
git --version          # git version x.x.x
tesseract --version    # tesseract x.x.x
pdfinfo -v             # pdfinfo version x.x.x
```

---

## Part 2: Python Environment Setup

### Step 1: Create Virtual Environment

```bash
cd ~/vectara-ingest
python3.11 -m venv venv
source venv/bin/activate
```

### Step 2: Install Python Packages

```bash
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
playwright install-deps chromium
```

### Step 3: Verify Python Installation

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import playwright; print('Playwright: OK')"
python -c "import magic; print('python-magic: OK')"
python -c "import pytesseract; print('pytesseract: OK')"
python -c "import pdf2image; print('pdf2image: OK')"
```

---

## Part 3: Configuration and Running

### Step 1: Configure Secrets

```bash
cp secrets.example.toml secrets.toml
nano secrets.toml  # or use any text editor
```

Add your credentials:
```toml
[default]
api_key = "your-vectara-api-key"
```

### Step 2: Run Crawler

```bash
# Activate venv (if not already active)
source venv/bin/activate

# Run with config file
python ingest.py --config-file ./config/your-config.yaml --profile default
```

---

## What Each Dependency Does

| Package | Purpose | Used By |
|---------|---------|---------|
| **Python 3.11** | Runtime | All crawlers |
| **FFmpeg** | Audio/video processing | YouTube, audio/video files |
| **Tesseract** | OCR for images/scanned PDFs | PDF, Folder, Website crawlers |
| **Poppler** | PDF to image conversion | PDF, Folder, Website crawlers |
| **libmagic** | File type detection | All file processing |
| **PyTorch** | ML/AI processing | Document analysis, embeddings |
| **Playwright** | Web browser automation | Website, RSS crawlers |
