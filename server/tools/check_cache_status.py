from __future__ import annotations
import sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from tools.cache_guard import main
raise SystemExit(main())

