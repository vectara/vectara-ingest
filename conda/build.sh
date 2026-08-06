#!/bin/bash
set -euo pipefail

# conda-build sets these to stop pip from reaching the network and to force a
# clean install. This recipe deliberately vendors its Python dependencies from
# PyPI, so clear them. PIP_IGNORE_INSTALLED matters as much as the other two:
# left set, pip ignores the CPU torch installed below and re-resolves
# torch==2.7.1 from PyPI, which is the CUDA build.
unset PIP_NO_INDEX PIP_NO_DEPENDENCIES PIP_IGNORE_INSTALLED

# PyPI's linux torch wheel is the CUDA build: ~820 MB of torch plus ~2 GB of
# nvidia-* wheels, all of which ends up inside the package. Install the CPU
# build first, the same way Dockerfile does; the later `pip install .` then
# sees the pins already satisfied. Read the pins from requirements.txt so they
# can't drift out of sync and silently pull CUDA back in.
if [ "$(uname)" = "Linux" ]; then
  torch_pins=$(grep -E '^(torch|torchvision)==' requirements.txt) || true
  if [ -z "$torch_pins" ]; then
    echo "ERROR: no torch/torchvision== pins found in requirements.txt." >&2
    echo "       Without them pip resolves torch from PyPI and bundles the" >&2
    echo "       CUDA stack, adding ~2.8 GB to the package. Refusing to build." >&2
    exit 1
  fi
  # shellcheck disable=SC2086  # word splitting is intended
  "${PYTHON}" -m pip install --no-cache-dir $torch_pins \
    --index-url https://download.pytorch.org/whl/cpu
fi

"${PYTHON}" -m pip install --no-cache-dir --index-url https://pypi.org/simple .

# The CPU install above only holds if nothing re-resolved torch on the way
# through the project's own dependencies. Assert it here: a silent fallback to
# the CUDA wheels adds ~2.8 GB and is otherwise not visible until the upload
# fails, an hour later.
# Read the list fully before filtering: `pip list | grep -q` makes grep exit on
# the first match, pip then dies flushing to a closed pipe (exit 120), and with
# `pipefail` the whole test reads false -- skipping the guard in exactly the
# case it exists to catch.
installed=$("${PYTHON}" -m pip list --format=freeze)
cuda_wheels=$(printf '%s\n' "$installed" | grep '^nvidia-' || true)
if [ -n "$cuda_wheels" ]; then
  echo "ERROR: CUDA wheels present after install -- CPU torch was overridden:" >&2
  printf '%s\n' "$cuda_wheels" >&2
  exit 1
fi
