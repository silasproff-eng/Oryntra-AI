#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv-mac"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "Creating Mac Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.oryntra_requirements_installed" ] || [ requirements.txt -nt "$VENV_DIR/.oryntra_requirements_installed" ]; then
  echo "Installing Oryntra requirements..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch "$VENV_DIR/.oryntra_requirements_installed"
fi

echo "Checking local market cache..."
python tools/market_cache_cli.py status || true

echo "Starting Oryntra at http://localhost:${PORT:-8000}"
echo "The full-market backfill will resume automatically in the background."
python run.py
