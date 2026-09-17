@echo off
:: conda-build sets these to stop pip from reaching the network. This recipe
:: deliberately vendors its Python dependencies from PyPI, so clear them.
:: `unset` is a shell builtin and does not exist in cmd.exe -- calling it here
:: left both variables set, so pip installed the project with no dependencies
:: and win-64 shipped ~0.9 MB packages instead of ~600 MB ones.
set PIP_NO_INDEX=
set PIP_NO_DEPENDENCIES=
set PIP_IGNORE_INSTALLED=

:: Windows torch wheels on PyPI are already CPU-only, so no separate index.
"%PYTHON%" -m pip install --no-cache-dir --index-url https://pypi.org/simple .
if errorlevel 1 exit /b 1

:: unstructured (>=0.24) tokenizes with spaCy's en_core_web_sm and downloads it from
:: GitHub on first use when it is missing, so an offline or egress-restricted conda
:: install fails on the first document it parses. This is the wheel unstructured pins;
:: URL and sha256 are the ones unstructured pins in unstructured/nlp/tokenize.py, and
:: the version has to track _SPACY_MODEL_VERSION there.
"%PYTHON%" -m pip install --no-cache-dir "en_core_web_sm @ https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl#sha256=1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
if errorlevel 1 exit /b 1
"%PYTHON%" -c "import spacy; spacy.load('en_core_web_sm')"
if errorlevel 1 exit /b 1
