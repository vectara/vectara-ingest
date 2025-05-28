# Windows Native Setup for Vectara-Ingest

This guide helps you set up and run vectara-ingest natively on Windows without requiring Windows Subsystem for Linux (WSL) or Docker.

## Prerequisites

- Windows 10 or Windows 11
- PowerShell 5.1 or later
- Internet connection
- Administrator privileges (for initial setup)

## Installation Steps

1. **Open PowerShell as Administrator**
   
   Right-click on PowerShell in the Start menu and select "Run as Administrator".

2. **Clone the repository**
   ```powershell
   git clone https://github.com/vectara/vectara-ingest.git
   cd vectara-ingest
   ```

3. **Enable script execution** (one-time setup if not already done)
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```

4. **Run the setup script**
   ```powershell
   .\win-setup.ps1
   ```
   This script will:
   - Install Miniconda if not already installed
   - Create a conda environment with all necessary dependencies
   - Install system libraries required for document processing
   - Configure the environment for Windows compatibility

5. **Activate the conda environment**
   ```powershell
   conda activate vectara-ingest
   ```

6. **Run a crawler**
   ```powershell
   conda run -n vectara-ingest python ingest.py --config-file config/vectara-docs.yaml --profile default
   ```

## Troubleshooting

- If you encounter permission issues, ensure you're running PowerShell as Administrator