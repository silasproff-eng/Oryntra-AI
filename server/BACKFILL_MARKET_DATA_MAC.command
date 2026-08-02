#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv-mac/bin/python" ]; then
  echo "Run START_ORYNTRA_MAC.command once first so the Mac environment is installed."
  exit 1
fi

source .venv-mac/bin/activate
python tools/market_cache_cli.py backfill
