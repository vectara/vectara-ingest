from setuptools import setup, find_packages
import os
import sys

# Add the current directory to the path so that ingest.py can be imported
sys.path.insert(0, os.path.abspath("."))

# Read requirements from requirements files
def read_requirements_from_file(filename):
    requirements = []
    with open(filename) as req:
        for line in req:
            line = line.strip()
            # Skip empty lines, comments, and constraint lines
            if not line or line.startswith('#') or line.startswith('    #'):
                continue
            # Extract just the package name and version, skip lines with indentation (they're comments)
            if not line.startswith(' '):
                requirements.append(line)
    return requirements

# Combine requirements from both files
def get_all_requirements():
    base_reqs = read_requirements_from_file("requirements.txt")
    extra_reqs = read_requirements_from_file("requirements-extra.txt")
    return base_reqs + extra_reqs

setup(
    name="vectara-ingest",
    version="0.1.0",
    description="A tool for ingesting content into Vectara from various sources",
    author="Vectara",
    author_email="support@vectara.com",
    url="https://github.com/vectara/vectara-ingest",
    packages=find_packages(),
    py_modules=["ingest"],  # Include root-level Python modules
    include_package_data=True,
    install_requires=get_all_requirements(),
    entry_points={
        "console_scripts": [
            "vectara-ingest=ingest:app",
        ],
    },
) 