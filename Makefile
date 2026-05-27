.PHONY: requirements requirements-extra requirements-all test lint format

PYTHON_VERSION := 3.11

requirements:
	uv pip compile requirements.in -o requirements.txt --universal --python-version $(PYTHON_VERSION)

requirements-extra:
	uv pip compile requirements-extra.in -o requirements-extra.txt --universal --python-version $(PYTHON_VERSION)

requirements-all: requirements requirements-extra

# Run the unit test suite via pytest (declared in requirements-test.txt). The
# tests are unittest-based, so this is equivalent to CI's
# `python -m unittest discover -s tests -p "test_*.py"`.
test:
	python -m pytest tests/

# Lint gate: Ruff with the repo's ruff.toml (E402 ignored). Black is not run —
# the tree isn't black-formatted and CI treats black as informational only.
lint:
	ruff check .

# Apply Ruff's safe autofixes. (Deliberately no `black .`: it would reformat
# nearly the whole tree, which isn't the project's convention.)
format:
	ruff check --fix .
