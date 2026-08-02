from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from backend.backtest import BacktestRequest, run_backtest
from backend.database import init_db
from backend.market_repository import get_market_repository


def _tickers(text: str) -> list[str]:
    output: list[str] = []
    for raw in str(text or "").replace("\n", ",").split(","):
        ticker = "".join(
            character
            for character in raw.upper().strip()
            if character.isalnum() or character in ".-"
        )
        if ticker and ticker not in output:
            output.append(ticker)
    return output


async def run(args: argparse.Namespace) -> int:
    init_db()
    tickers = _tickers(args.tickers)
    if args.ticker_file:
        tickers.extend(
            ticker
            for ticker in _tickers(Path(args.ticker_file).read_text(encoding="utf-8"))
            if ticker not in tickers
        )
    if args.all_cached:
        tickers = get_market_repository().cached_tickers(minimum_bars=args.min_history)
    elif args.limit > 0:
        tickers = tickers[: args.limit]
    if not tickers:
        raise SystemExit("No tickers selected. Use --tickers, --ticker-file, or --all-cached.")

    request = BacktestRequest(
        tickers=tickers,
        period=args.period,
        min_score=args.min_score,
        setups=_tickers(args.setups),
        engine_mode=args.engine,
        data_source=args.data_source,
        min_history=args.min_history,
        max_hold_candles=args.max_hold,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        target_stop_policy=args.ambiguity_policy,
        position_size_pct=args.position_size_pct,
        max_concurrent_positions=args.max_concurrent,
        bootstrap_samples=args.bootstrap_samples,
        initial_equity=args.initial_equity,
    )
    result = await run_backtest(request)
    output = Path(args.output) if args.output else (
        APP_DIR
        / "data"
        / "training_logs"
        / f"backtest_{args.engine}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "experiment_id": result.get("experiment_id"),
                "tickers_requested": len(tickers),
                "tickers_completed": result.get("tickers_completed"),
                "stats": result.get("stats"),
                "output": str(output),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if result.get("status") in {"done", "partial"} else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run causal, next-session Oryntra backtests from the canonical cache."
    )
    parser.add_argument("--tickers", default="AAPL,MSFT,NVDA,SPY,QQQ")
    parser.add_argument("--ticker-file", default="")
    parser.add_argument("--all-cached", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--period", choices=["1mo", "3mo", "6mo", "1y", "2y", "5y", "all"], default="all")
    parser.add_argument("--engine", choices=["official", "v8", "vai2"], default="official")
    parser.add_argument("--data-source", choices=["cache_only", "cache_first"], default="cache_only")
    parser.add_argument("--min-history", type=int, default=220)
    parser.add_argument("--min-score", type=float, default=55.0)
    parser.add_argument("--setups", default="")
    parser.add_argument("--max-hold", type=int, default=20)
    parser.add_argument("--commission-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=4.0)
    parser.add_argument("--ambiguity-policy", choices=["stop_first", "target_first"], default="stop_first")
    parser.add_argument("--position-size-pct", type=float, default=20.0)
    parser.add_argument("--max-concurrent", type=int, default=5)
    parser.add_argument("--bootstrap-samples", type=int, default=500)
    parser.add_argument("--initial-equity", type=float, default=10000.0)
    parser.add_argument("--output", default="")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
