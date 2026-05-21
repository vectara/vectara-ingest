"""Pytest config shared across the test suite."""

# YAML files under tests/data/ are fixtures (consumed by parametrised tests),
# not test modules — but pytest picks them up because the filenames start
# with ``test_``. Skipping them at collection time avoids ~12 spurious
# "ERROR collecting" entries that obscure real failures in the summary.
collect_ignore_glob = [
    "data/**/test_*.yml",
    "data/**/test_*.yaml",
]
