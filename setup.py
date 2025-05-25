from setuptools import setup, find_packages
import os
import sys

# Add the current directory to the path so that ingest.py can be imported
sys.path.insert(0, os.path.abspath("."))

# Read requirements from requirements.txt
def read_requirements():
    with open("requirements.txt") as req:
        return req.read().splitlines()

# Read optional requirements
def read_requirements_extra():
    with open("requirements-extra.txt") as req:
        return req.read().splitlines()

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
    install_requires=read_requirements(),
    extras_require={
        "all": read_requirements_extra(),
    },
    entry_points={
        "console_scripts": [
            "vectara-ingest=ingest:app",
        ],
    },
) 