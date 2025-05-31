# Building vectara-ingest as a Conda Package

This document outlines how to build and use the vectara-ingest conda package.

## Prerequisites
- Python 3.11
- Install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/download/)
- Install conda-build: `conda install conda-build conda-verify`

## Building the Package Locally

1. Clone the repository and navigate to its root directory:
   ```bash
   git clone https://github.com/vectara/vectara-ingest.git
   cd vectara-ingest
   switch to branch `add-cli-option`
   ```

2. Activate the conda base environment 
   ```bash
   conda activate base
   ```

3. Build the conda package:
   ```bash
   cd conda 
   conda build . --channel conda-forge
   ```

4. Choose one of the following installation methods:

   **Option A: Install directly in your base environment**
   ```bash
   conda install -c conda-forge -c local vectara-ingest
   ```

   **Option B: Install in a dedicated environment (recommended)**
   ```bash
   # Create a new conda environment
   conda create -n vectara-ingest python=3.11
   
   # Activate the conda environment
   conda activate vectara-ingest
   
   # Install the package
   conda install --use-local vectara-ingest
   ```

## Using the Package

After installing vectara-ingest, you can run it using the command-line interface:

### Basic Usage

```bash
vectara-ingest --config-file your_config.yaml --profile default --secrets-path path/to/secrets.toml
```

### Parameter Explanation

- `--config-file`: Path to your YAML configuration file (required)
- `--profile`: Profile name in your secrets.toml file (required)
- `--secrets-path`: Path to your secrets.toml file (optional, defaults to looking for secrets.toml in current directory)
- `--reset-corpus`: Flag to reset the corpus before indexing (optional)

## SSL Certificate Handling

If your Vectara instance uses custom SSL certificates, the CLI package supports several ways to configure certificate verification:

### Configuration in YAML

In your configuration YAML file, add the `ssl_verify` parameter under the `vectara` section:

```yaml
vectara:
  # Other Vectara settings...
  ssl_verify: /path/to/certificate.pem
```

### SSL Certificate Options

   - You can use absolute paths: `/etc/ssl/certs/mycert.pem`
   - You can use home directory paths: `~/certs/mycert.pem`
   - You can use directory of certificates: `/path/to/certificates/`

### Auto-Detection

If you don't specify `ssl_verify` in your configuration, the package will automatically look for:

1. A file named `ca.pem` in the current working directory
2. A directory named `ssl` in the current working directory

If found, these will be used for SSL verification.

### Environment-Specific Notes

- In CLI mode, certificate paths are resolved relative to your local filesystem
- Absolute paths must exist on your local system
- Paths with `~` are expanded to your home directory
