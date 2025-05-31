"""
vectara_ingest package

This package provides a proper namespace for the vectara-ingest conda package.
Instead of importing directly from 'ingest', this namespace allows for more 
intuitive imports when using vectara-ingest in other applications:

    from vectara_ingest import run_ingest
"""

# Import and re-export the run_ingest function
from ingest import run_ingest