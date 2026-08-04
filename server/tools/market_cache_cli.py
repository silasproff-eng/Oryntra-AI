from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except Exception:
    pass

from backend.database import init_db
from backend.market_cache import (
    apply_retention,
    backfill_market_cache,
    import_grouped_day,
    status,
    sync_ticker_reference,
    update_recent_market_cache,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and maintain Oryntra's local full-market daily cache."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show database and backfill progress.")

    backfill = sub.add_parser("backfill", help="Resume the full historical grouped-daily backfill.")
    backfill.add_argument("--days", type=int, default=None, help="Calendar-day lookback; default from .env.")
    backfill.add_argument("--max-dates", type=int, default=None, help="Stop after this many API calls/dates.")
    backfill.add_argument("--oldest-first", action="store_true")
    backfill.add_argument("--dry-run", action="store_true", help="Plan work without calling Polygon.")

    update = sub.add_parser("update", help="Download recent missing completed sessions.")
    update.add_argument("--sessions", type=int, default=None, help="Recent sessions to check; default ORYNTRA_MARKET_CACHE_UPDATE_SESSIONS.")
    update.add_argument("--max-dates", type=int, default=None)

    one = sub.add_parser("one-day", help="Import one explicit trading date.")
    one.add_argument("trading_date", help="YYYY-MM-DD")
    one.add_argument("--dry-run", action="store_true")

    reference = sub.add_parser("reference", help="Sync active ticker names and security types.")
    reference.add_argument("--max-pages", type=int, default=None)

    retention = sub.add_parser("retention", help="Apply optional age-based retention.")
    retention.add_argument("--days", type=int, required=True, help="0 disables deletion.")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    init_db()

    if args.command == "status":
        result = status()
    elif args.command == "backfill":
        result = backfill_market_cache(
            lookback_calendar_days=args.days,
            max_dates=args.max_dates,
            newest_first=not args.oldest_first,
            dry_run=args.dry_run,
        )
    elif args.command == "update":
        result = update_recent_market_cache(
            lookback_sessions=args.sessions or int(__import__("os").getenv("ORYNTRA_MARKET_CACHE_UPDATE_SESSIONS", "5")),
            max_dates=args.max_dates,
        )
    elif args.command == "one-day":
        result = import_grouped_day(date.fromisoformat(args.trading_date), dry_run=args.dry_run)
    elif args.command == "reference":
        result = sync_ticker_reference(max_pages=args.max_pages)
    else:
        result = apply_retention(args.days)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

