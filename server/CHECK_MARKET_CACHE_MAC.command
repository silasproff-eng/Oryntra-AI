#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ".venv-mac/bin/python" ]; then
  source .venv-mac/bin/activate
  python tools/market_cache_cli.py status
else
  python3 tools/market_cache_cli.py status
fi
