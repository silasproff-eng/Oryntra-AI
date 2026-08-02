#!/bin/bash
set -e
cd "$(dirname "$0")"
exec python3 maintenance_site/app.py --host 0.0.0.0 --port "${ORYNTRA_MAINTENANCE_PORT:-8000}"
