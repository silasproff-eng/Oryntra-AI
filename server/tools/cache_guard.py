"""Oryntra cache protection helpers for safe updates and headless training."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DB_PATH = APP_DIR / "data" / "oryntra.db"
BACKUP_DIR = APP_DIR / "data_backups"


def cache_counts(db_path: Path = DB_PATH) -> dict:
    if not db_path.exists():
        return {"db_path": str(db_path), "exists": False, "distinct_tickers": 0, "ohlcv_rows": 0, "db_size_bytes": 0}
    conn = sqlite3.connect(db_path)
    try:
        try:
            tickers, rows = conn.execute("select count(distinct ticker), count(*) from ohlcv_bars").fetchone()
        except Exception:
            tickers, rows = 0, 0
    finally:
        conn.close()
    return {"db_path": str(db_path), "exists": True, "distinct_tickers": int(tickers or 0), "ohlcv_rows": int(rows or 0), "db_size_bytes": db_path.stat().st_size}


def backup_db(label: str = "manual") -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"oryntra_db_{label}_{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    for p in APP_DIR.glob("data/oryntra.db*"):
        if p.is_file():
            shutil.copy2(p, dest / p.name)
    (dest / "cache_counts.json").write_text(json.dumps(cache_counts(dest / "oryntra.db"), indent=2), encoding="utf-8")
    return dest


def restore_backup(backup_dir: Path) -> None:
    backup_dir = Path(backup_dir)
    if not (backup_dir / "oryntra.db").exists():
        raise FileNotFoundError(f"Backup does not contain oryntra.db: {backup_dir}")
    (APP_DIR / "data").mkdir(parents=True, exist_ok=True)
    for p in backup_dir.glob("oryntra.db*"):
        shutil.copy2(p, APP_DIR / "data" / p.name)


def assert_not_shrunk(before: dict, after: dict, restore_from: Path | None = None) -> dict:
    ok = after.get("distinct_tickers", 0) >= before.get("distinct_tickers", 0) and after.get("ohlcv_rows", 0) >= before.get("ohlcv_rows", 0)
    result = {"ok": ok, "before": before, "after": after, "restored": False}
    if not ok and restore_from:
        restore_backup(restore_from)
        result["restored"] = True
        result["after_restore"] = cache_counts()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Check/backup/restore Oryntra OHLCV cache.")
    ap.add_argument("action", choices=["status", "backup", "restore", "assert"], nargs="?", default="status")
    ap.add_argument("--backup-dir", default="")
    ap.add_argument("--min-tickers", type=int, default=0)
    ap.add_argument("--min-rows", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.action == "status":
        out = cache_counts()
    elif args.action == "backup":
        b = backup_db("manual")
        out = {"backup_dir": str(b), "counts": cache_counts(b / "oryntra.db")}
    elif args.action == "restore":
        if not args.backup_dir:
            raise SystemExit("--backup-dir required")
        restore_backup(Path(args.backup_dir))
        out = {"restored_from": args.backup_dir, "counts": cache_counts()}
    else:
        out = cache_counts()
        out["ok"] = out["distinct_tickers"] >= args.min_tickers and out["ohlcv_rows"] >= args.min_rows
        if not out["ok"]:
            raise SystemExit(json.dumps(out, indent=2))
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        counts = out.get("counts") or out
        print(f"Cache tickers: {counts.get('distinct_tickers', 0)}")
        print(f"OHLCV rows: {counts.get('ohlcv_rows', 0)}")
        if "backup_dir" in out:
            print(f"Backup: {out['backup_dir']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
