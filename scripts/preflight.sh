#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/build_guide.py --check
python3 scripts/check_docs.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/scripts" python3 -m unittest discover -s tests
