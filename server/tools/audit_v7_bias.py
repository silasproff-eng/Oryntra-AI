from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from backend.database import DB_PATH, load_ohlcv_bars
from backend.indicators import calculate_all_indicators
from backend.setup_detector import detect_setup


PRESET_TICKERS = {
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD", "AVGO",
    "JPM", "V", "XOM", "CVX", "UNH", "LLY", "JNJ", "WMT", "COST", "HD",
    "MCD", "NKE", "CAT", "BA", "RTX", "NEE", "PLTR", "CRWD", "SPY", "QQQ",
    "SMH",
}


def _finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _cached_tickers(db_path: str) -> list[str]:
    uri = f"file:{Path(db_path).resolve()}?immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            "SELECT ticker FROM ohlcv_bars WHERE timeframe = '1d' "
            "GROUP BY ticker HAVING COUNT(*) >= 240 ORDER BY ticker"
        ).fetchall()
    return [str(row[0]).upper() for row in rows]


def _candidate_indexes(length: int, horizon: int, max_tests: int, seed: int, ticker: str) -> list[int]:
    candidates = np.arange(220, max(220, length - horizon), dtype=int)
    if not len(candidates):
        return []
    ticker_seed = seed + sum((i + 1) * ord(ch) for i, ch in enumerate(ticker))
    rng = np.random.default_rng(ticker_seed)
    count = min(max_tests, len(candidates))
    return sorted(int(value) for value in rng.choice(candidates, size=count, replace=False))


def _evaluate_ticker(ticker: str, horizon: int, max_tests: int, seed: int) -> list[dict]:
    hist = load_ohlcv_bars(ticker, "1d", "all")
    if hist is None or hist.empty:
        return []
    rows: list[dict] = []
    for idx in _candidate_indexes(len(hist), horizon, max_tests, seed, ticker):
        future = hist.iloc[idx + 1:idx + 1 + horizon]
        if future.empty:
            continue
        train = hist.iloc[:idx + 1]
        entry = _finite(hist["Close"].iloc[idx])
        if entry <= 0:
            continue
        try:
            indicators = calculate_all_indicators(train)
            setup = detect_setup(indicators, train, pattern_mode="official")
        except Exception:
            continue
        direction = str(setup.get("direction") or "NEUTRAL").upper()
        actionable = direction in {"LONG", "SHORT"} and setup.get("setup_type") != "NO_TRADE"
        end_price = _finite(future["Close"].iloc[-1], entry)
        long_return = ((end_price - entry) / entry) * 100.0
        signed_return = long_return if direction == "LONG" else (-long_return if direction == "SHORT" else 0.0)
        timestamp = hist.index[idx]
        rows.append(
            {
                "ticker": ticker,
                "preset": ticker in PRESET_TICKERS,
                "date": str(timestamp.date() if hasattr(timestamp, "date") else timestamp),
                "direction": direction,
                "actionable": actionable,
                "confidence": _finite(setup.get("confidence")),
                "return_pct": signed_return if actionable else 0.0,
                "net_return_pct": signed_return - 0.10 if actionable else 0.0,
            }
        )
    return rows


def _summary(rows: list[dict]) -> dict:
    actionable = [row for row in rows if row["actionable"]]
    returns = np.asarray([row["net_return_pct"] for row in actionable], dtype=float)
    directions = Counter(row["direction"] for row in actionable)
    return {
        "tests": len(rows),
        "actionable": len(actionable),
        "coverage_pct": round(len(actionable) / max(1, len(rows)) * 100.0, 3),
        "win_rate_pct": round(float((returns > 0).mean() * 100.0), 3) if len(returns) else 0.0,
        "avg_net_return_pct": round(float(returns.mean()), 4) if len(returns) else 0.0,
        "median_net_return_pct": round(float(np.median(returns)), 4) if len(returns) else 0.0,
        "long_signals": int(directions.get("LONG", 0)),
        "short_signals": int(directions.get("SHORT", 0)),
        "no_trade_pct": round((len(rows) - len(actionable)) / max(1, len(rows)) * 100.0, 3),
    }


def _temporal_summaries(rows: list[dict]) -> list[dict]:
    dates = sorted({row["date"] for row in rows})
    if not dates:
        return []
    cut1 = dates[max(0, len(dates) // 3 - 1)]
    cut2 = dates[max(0, (len(dates) * 2) // 3 - 1)]
    groups = {"early": [], "middle": [], "late": []}
    for row in rows:
        label = "early" if row["date"] <= cut1 else ("middle" if row["date"] <= cut2 else "late")
        groups[label].append(row)
    return [{"time_block": name, **_summary(group)} for name, group in groups.items()]


def _ticker_concentration(rows: list[dict]) -> dict:
    counts = Counter(row["ticker"] for row in rows if row["actionable"])
    total = sum(counts.values())
    ranked = counts.most_common()
    return {
        "tickers_with_signals": len(counts),
        "top_5_signal_share_pct": round(sum(value for _, value in ranked[:5]) / max(1, total) * 100.0, 3),
        "top_10_signal_share_pct": round(sum(value for _, value in ranked[:10]) / max(1, total) * 100.0, 3),
        "top_tickers": [{"ticker": ticker, "signals": count} for ticker, count in ranked[:15]],
    }


def run_audit(horizon: int, max_tests: int, seed: int, sample_per_group: int = 0) -> dict:
    cached = _cached_tickers(DB_PATH)
    if sample_per_group > 0:
        preset = [ticker for ticker in cached if ticker in PRESET_TICKERS]
        nonpreset = [ticker for ticker in cached if ticker not in PRESET_TICKERS]
        rng = np.random.default_rng(seed)
        preset = list(rng.choice(preset, size=min(sample_per_group, len(preset)), replace=False))
        nonpreset = list(rng.choice(nonpreset, size=min(sample_per_group, len(nonpreset)), replace=False))
        tickers = sorted(preset + nonpreset)
    else:
        tickers = cached
    rows: list[dict] = []
    failures: list[str] = []
    workers = min(6, max(1, (os.cpu_count() or 2) - 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_evaluate_ticker, ticker, horizon, max_tests, seed): ticker
            for ticker in tickers
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            ticker = futures[future]
            try:
                evaluated = future.result()
            except Exception:
                evaluated = []
            if evaluated:
                rows.extend(evaluated)
            else:
                failures.append(ticker)
            if completed % 10 == 0 or completed == len(tickers):
                print(f"Audited {completed}/{len(tickers)} tickers", file=sys.stderr, flush=True)
    preset_rows = [row for row in rows if row["preset"]]
    nonpreset_rows = [row for row in rows if not row["preset"]]
    preset_summary = _summary(preset_rows)
    nonpreset_summary = _summary(nonpreset_rows)
    temporal = _temporal_summaries(rows)
    coverage_gap = preset_summary["coverage_pct"] - nonpreset_summary["coverage_pct"]
    return_gap = preset_summary["avg_net_return_pct"] - nonpreset_summary["avg_net_return_pct"]
    time_returns = [item["avg_net_return_pct"] for item in temporal]
    actionable = [row for row in rows if row["actionable"]]
    long_share = sum(row["direction"] == "LONG" for row in actionable) / max(1, len(actionable)) * 100.0
    findings = {
        "ticker_identity_leakage_risk": True,
        "ticker_feature_live_mismatch": True,
        "long_direction_share_pct": round(long_share, 3),
        "preset_vs_nonpreset_coverage_gap_pp": round(coverage_gap, 3),
        "preset_vs_nonpreset_return_gap_pct": round(return_gap, 4),
        "time_block_return_range_pct": round(max(time_returns) - min(time_returns), 4) if time_returns else 0.0,
        "passes_direction_balance": long_share <= 80.0,
        "passes_preset_generalization": abs(coverage_gap) <= 8.0 and abs(return_gap) <= 0.35,
        "passes_time_stability": (max(time_returns) - min(time_returns) <= 0.75) if time_returns else False,
    }
    findings["audit_passed"] = all(
        findings[key]
        for key in ("passes_direction_balance", "passes_preset_generalization", "passes_time_stability")
    ) and not findings["ticker_feature_live_mismatch"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "official",
        "label": "V7 Official Momentum",
        "database": str(DB_PATH),
        "parameters": {"horizon_days": horizon, "max_tests_per_ticker": max_tests, "seed": seed, "round_trip_cost_pct": 0.10},
        "universe": {
            "cached_tickers_tested": len(tickers) - len(failures),
            "preset_tickers_tested": len({row["ticker"] for row in preset_rows}),
            "nonpreset_tickers_tested": len({row["ticker"] for row in nonpreset_rows}),
            "failures": failures,
        },
        "overall": _summary(rows),
        "preset": preset_summary,
        "nonpreset": nonpreset_summary,
        "temporal": temporal,
        "ticker_concentration": _ticker_concentration(rows),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--max-tests-per-ticker", type=int, default=18)
    parser.add_argument("--sample-per-group", type=int, default=0)
    parser.add_argument("--seed", type=int, default=73021)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = run_audit(
        horizon=max(1, min(args.horizon, 60)),
        max_tests=max(3, min(args.max_tests_per_ticker, 200)),
        seed=args.seed,
        sample_per_group=max(0, args.sample_per_group),
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["findings"]["audit_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

