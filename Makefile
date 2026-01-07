.PHONY: requirements requirements-extra requirements-all

PYTHON_VERSION := 3.11

requirements:
	uv pip compile requirements.in -o requirements.txt --universal --python-version $(PYTHON_VERSION)

requirements-extra:
	uv pip compile requirements-extra.in -o requirements-extra.txt --universal --python-version $(PYTHON_VERSION)

requirements-all: requirements requirements-extra
