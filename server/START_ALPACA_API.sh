#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and add the approved Alpaca credentials."
  exit 1
fi

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi

source venv/bin/activate
python -m pip install -r requirements.txt
exec python run.py
