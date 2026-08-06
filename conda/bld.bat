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
