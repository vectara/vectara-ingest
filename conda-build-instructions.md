# Building vectara-ingest as a Conda Package

This document outlines how to build and use the vectara-ingest conda package.

## Prerequisites

- Install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/download/)
- Install conda-build: `conda install conda-build conda-verify`

## Building the Package Locally

1. Clone the repository and navigate to its root directory:
   ```bash
   git clone https://github.com/vectara/vectara-ingest.git
   cd vectara-ingest
   ```

2. Build the conda package:
   ```bash
   conda build .
   ```

3. Install the locally built package:
   ```bash
   conda install --use-local vectara-ingest
   ```

## Dependency Management

The conda package includes:

- **All core dependencies** from `requirements.txt`
- **All extra dependencies** from `requirements-extra.txt` (included by default)
- **System dependencies** defined directly in `meta.yaml`

When updating dependencies:
1. Update `requirements.txt` for core Python packages
2. Update `requirements-extra.txt` for optional features
3. The conda build will automatically include both sets of dependencies

## Building for Different Python Versions

To build for a specific Python version:

```bash
conda build . --python 3.9
```

## Uploading to Anaconda.org or Conda-Forge

### Option 1: Upload to your Anaconda.org account

1. Install anaconda-client:
   ```bash
   conda install anaconda-client
   ```

2. Login to your Anaconda.org account:
   ```bash
   anaconda login
   ```

3. Upload your package:
   ```bash
   anaconda upload /path/to/conda-package.tar.bz2
   ```

### Option 2: Contributing to conda-forge

To add your package to conda-forge:

1. Fork the [staged-recipes](https://github.com/conda-forge/staged-recipes) repository
2. Add your recipe to the recipes folder
3. Submit a pull request

## Using the Package

Once installed, users can use vectara-ingest with:

```bash
vectara-ingest --config your_config.yaml
```

## Why Use Conda Instead of Pip

Using conda offers several advantages for vectara-ingest:

1. **Seamless system dependency management**: Conda handles Linux, macOS, and Windows system libraries in one consistent way
2. **No root/sudo required**: Users don't need administrator privileges to install system dependencies
3. **Reproducible environments**: Ensures all users have identical environments
4. **Cross-platform compatibility**: Works the same way on all major platforms

## For Users: Installing from Conda

Once the package is available on Anaconda.org or conda-forge, users can install it with:

```bash
# From your personal channel
conda install -c yourusername vectara-ingest

# Or from conda-forge (once accepted)
conda install -c conda-forge vectara-ingest
``` 