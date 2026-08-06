#!/bin/bash
set -euo pipefail

# conda-build sets these to stop pip from reaching the network. This recipe
# deliberately vendors its Python dependencies from PyPI, so clear them.
unset PIP_NO_INDEX PIP_NO_DEPENDENCIES

# PyPI's linux torch wheel is the CUDA build: ~820 MB of torch plus ~2 GB of
# nvidia-* wheels, all of which ends up inside the package. Install the CPU
# build first, the same way Dockerfile does; the later `pip install .` then
# sees the pins already satisfied. Read the pins from requirements.txt so they
# can't drift out of sync and silently pull CUDA back in.
if [ "$(uname)" = "Linux" ]; then
  torch_pins=$(grep -E '^(torch|torchvision)==' requirements.txt)
  # shellcheck disable=SC2086  # word splitting is intended
  "${PYTHON}" -m pip install --no-cache-dir $torch_pins \
    --index-url https://download.pytorch.org/whl/cpu
fi

"${PYTHON}" -m pip install --no-cache-dir --index-url https://pypi.org/simple .
