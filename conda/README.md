# vectara-ingest as a Conda Package

This document outlines how use the vectara-ingest conda package.

## Prerequisites
- Python 3.11
- Install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/download/)
- Install conda-build: `conda install conda-build conda-verify`


## Choose one of the following installation methods:

   **Option A: Install directly in your base environment**
   ```bash
   conda install vectara::vectara-ingest -c conda-forge
   ```

   **Option B: Install in a dedicated environment (recommended)**
   ```bash
   # Create a new conda environment
   conda create -n vectara-ingest python=3.11
   
   # Activate the conda environment
   conda activate vectara-ingest
   
   # Install the package
   conda install vectara::vectara-ingest -c conda-forge
   ```

## Using the Package

### Command-Line Interface

After installing vectara-ingest, you can run it using the command-line interface:

```bash
vectara-ingest --config-file your_config.yaml --profile default --secrets-path path/to/secrets.toml
```

### Running on Red Hat Linux / Amazon Linux

If you're using Red Hat Linux, Amazon Linux, or other Red Hat-based distributions, follow these steps to ensure Playwright works correctly.

1. Create a Conda Environment with Python 3.11

```bash
# Install conda if not already installed
# For miniconda (recommended):
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh

# Create a conda environment with Python 3.11
conda create -n vectara-ingest python=3.11
conda activate vectara-ingest

# Install vectara-ingest from conda
conda install vectara::vectara-ingest -c conda-forge
```

2. Install System Dependencies for Playwright

Playwright requires several system dependencies that need to be installed using yum:

```bash
# Core dependencies
sudo yum install -y alsa-lib gtk3 libX11-xcb libXcomposite libXcursor libXdamage \
  libXext libXi libXrandr libXtst mesa-libgbm pango cups-libs

# Fonts
sudo yum install -y liberation-fonts dejavu-sans-fonts

# Additional dependencies if available
sudo yum install -y libcanberra-gtk3 atk || true
```

3. Install Firefox Browser

vectara-ingest uses Firefox for web crawling. Install it using:

```bash
# Install Firefox for Playwright
playwright install firefox
```

4. Known Issues

- The command `python -m playwright install-deps` will not work on Red Hat-based systems as it uses apt-get (Ubuntu's package manager)
- You may see warnings about "OS is not officially supported by Playwright" - this is expected and the fallback build should work fine with the system dependencies installed above
- If you encounter browser-related issues, ensure all system dependencies are properly installed


### As an Importable Python Package

You can use vectara-ingest as a Python package in your own code.

```python
from vectara_ingest import run_ingest

# Configure your ingestion parameters
config_file = "config.yaml"
profile = "profile to use form secrets.toml"
secrets_path = "~/vectara/secrets.toml"
reset_corpus = False # Set to True to delete all documents in the corpus before indexing

# Call the run_ingest function directly
run_ingest(
    config_file=config_file,
    profile=profile,
    secrets_path=secrets_path,
    reset_corpus=reset_corpus
)
```

This allows you to integrate vectara-ingest into your own Python applications or workflows.

### Parameter Explanation

- `config_file`: Path to your YAML configuration file (required)
- `profile`: Profile name in your secrets.toml file (required)
- `secrets_path`: Path to your secrets.toml file (optional, defaults to looking for secrets.toml in current directory)
- `reset_corpus`: Flag to reset the corpus before indexing (optional, defaults to False)

## SSL Certificate Handling

If your Vectara instance uses custom SSL certificates, the CLI package supports several ways to configure certificate verification:

### Configuration in YAML

In your configuration YAML file, add the `ssl_verify` parameter under the `vectara` section:

```yaml
vectara:
  # Other Vectara settings...
  ssl_verify: /path/to/ca.pem
```

### SSL Certificate Options

- You can use absolute paths: `/etc/ssl/certs/mycert.pem`
- You can use home directory paths: `~/certs/mycert.pem`

### Certificate Path Resolution

The package uses the following approach to find certificate files:

1. First tries the direct path as specified (works with absolute paths)
2. Then tries the expanded path (resolves `~` to home directory)
3. Raises an error if the certificate cannot be found at either location

### Auto-Detection

If you don't specify `ssl_verify` in your configuration, the package will automatically look for:

1. A file named `ca.pem` in the current working directory

If found, this will be used for SSL verification.

### Environment-Specific Notes

- In CLI mode, certificate paths are resolved relative to your local filesystem
- Absolute paths must exist on your local system
- Paths with `~` are expanded to your home directory