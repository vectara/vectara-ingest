# win-setup.ps1 - Windows setup script with conda installation

# Colors for output
function Write-Status {
    param($message)
    Write-Host "[+] $message" -ForegroundColor Green
}

function Write-Error {
    param($message)
    Write-Host "[-] $message" -ForegroundColor Red
}

function Write-Warning {
    param($message)
    Write-Host "[!] $message" -ForegroundColor Yellow
}

# Check if conda is installed, if not install Miniconda
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Status "Miniconda not found. Installing Miniconda..."
    
    # Download Miniconda installer
    $installerPath = "$env:TEMP\miniconda_installer.exe"
    Write-Status "Downloading Miniconda installer..."
    
    $webClient = New-Object System.Net.WebClient
    $webClient.DownloadFile("https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe", $installerPath)
    
    # Install Miniconda silently
    Write-Status "Installing Miniconda (this may take a few minutes)..."
    Start-Process -FilePath $installerPath -ArgumentList "/S /RegisterPython=1 /AddToPath=1" -Wait
    
    # Clean up
    Remove-Item $installerPath
    
    Write-Status "Miniconda installed."
    Write-Warning "You need to restart PowerShell to use conda."
    Write-Warning "Please close this window, open a new PowerShell window, and run this script again."
    exit 0
}

# Create a new conda environment
$envName = "vectara-ingest"
Write-Status "Creating conda environment '$envName' with Python 3.11..."
conda create -n $envName python=3.11 -y

# Activate the conda environment - PowerShell way
Write-Status "Activating conda environment..."
# Initialize conda for this PowerShell session
conda init powershell
# Need to use this method for PowerShell
& conda activate $envName

# If the above activation doesn't work properly, fall back to conda run
$useCondaRun = $true
try {
    # Test if environment is activated
    $activePython = (python -c "import sys; print(sys.prefix)")
    if ($activePython -match $envName) {
        Write-Status "Environment activated successfully."
        $useCondaRun = $false
    } else {
        Write-Warning "Environment activation didn't work as expected. Using conda run instead."
    }
} catch {
    Write-Warning "Environment activation didn't work as expected. Using conda run instead."
}

# Install system-level dependencies via conda
Write-Status "Installing system dependencies via conda..."
if ($useCondaRun) {
    conda install -y -n $envName -c conda-forge poppler tesseract jpeg libjpeg-turbo libmagic fontconfig
} else {
    conda install -y -c conda-forge poppler tesseract jpeg libjpeg-turbo libmagic fontconfig
}

# Install PyTorch CPU version
Write-Status "Installing PyTorch CPU version..."
if ($useCondaRun) {
    conda install -y -n $envName -c pytorch pytorch torchvision cpuonly
} else {
    conda install -y -c pytorch pytorch torchvision cpuonly
}

# Install UV package manager
Write-Status "Installing UV package manager..."
if ($useCondaRun) {
    conda run -n $envName python -m pip install uv
} else {
    python -m pip install uv
}

# Install Python requirements
Write-Status "Installing Python packages with UV..."
if ($useCondaRun) {
    conda run -n $envName uv pip install -r requirements.txt
    conda run -n $envName uv pip install -r requirements-extra.txt
} else {
    uv pip install -r requirements.txt
    uv pip install -r requirements-extra.txt
}

# Install spaCy language model
Write-Status "Installing spaCy language model..."
if ($useCondaRun) {
    conda run -n $envName python -m spacy download en_core_web_lg
} else {
    python -m spacy download en_core_web_lg
}

# Install Playwright browsers
Write-Status "Installing Playwright browsers..."
if ($useCondaRun) {
    conda run -n $envName python -m playwright install --with-deps firefox
} else {
    python -m playwright install --with-deps firefox
}

# Create .env file
Write-Status "Setting up environment variables..."
@"
XDG_RUNTIME_DIR=%TEMP%
RAY_DEDUP_LOGS=0
CUDA_VISIBLE_DEVICES=
"@ | Out-File -FilePath .env -Encoding utf8

# Check if secrets.toml exists, if not create from example
if (-not (Test-Path "secrets.toml")) {
    if (Test-Path "secrets.example.toml") {
        Write-Status "Creating secrets.toml from example..."
        Copy-Item "secrets.example.toml" "secrets.toml"
        Write-Warning "Please edit secrets.toml with your actual credentials"
    } else {
        Write-Error "secrets.example.toml not found. Please create secrets.toml manually"
    }
}

Write-Status "Setup completed successfully!"
Write-Warning "Don't forget to:"
Write-Warning "1. Edit secrets.toml with your actual credentials"
Write-Warning "2. Activate the conda environment with: conda activate $envName"
Write-Warning "3. Make sure to run your Python scripts from this conda environment"