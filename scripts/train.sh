#!/usr/bin/env bash
# make train / make train SUBSET=50 / make train-v2
# Installs the CPU-only training libraries into .venv once, then runs training/train.py.
# `bash scripts/train.sh deps` only installs them (used by make test / make eval).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=${1:-v1}; SUBSET=${2:-}
[ -x .venv/bin/python ] || { python3 -m venv .venv; .venv/bin/pip install -q -r requirements-dev.txt; }
if ! .venv/bin/python -c "import torch, transformers" 2>/dev/null; then
  .venv/bin/pip install -q torch==2.4.1+cpu --index-url https://download.pytorch.org/whl/cpu
  .venv/bin/pip install -q -r training/requirements.txt
fi
[ "$VERSION" = deps ] && exit 0   # `scripts/train.sh deps`: only install the libraries
.venv/bin/python training/train.py --version "$VERSION" ${SUBSET:+--subset "$SUBSET"}
