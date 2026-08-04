from __future__ import annotations

import asyncio
import json
import math
import operator
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from ..database import get_connection, init_db, load_ohlcv_bars
from .analysis import ScanRequest, _run_scan_pipeline
from .auth import get_current_user_optional
from .pro_live import configuration as live_configuration, fetch_live

router = APIRouter()


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _scope(request: Request) -> int:
    user = get_current_user_optional(request)
    return int(user["id"]) if user else 0


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def ensure_pro_tables() -> None:
    init_db()
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pro_alerts (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL DEFAULT 0,
                ticker              TEXT NOT NULL COLLATE NOCASE,
                name                TEXT NOT NULL,
                metric              TEXT NOT NULL,
                operator            TEXT NOT NULL,
                threshold           REAL NOT NULL,
                enabled             INTEGER NOT NULL DEFAULT 1,
                cooldown_minutes    INTEGER NOT NULL DEFAULT 30,
                last_value          REAL,
                last_triggered_at   TEXT,
                created_at          TEXT DEFAULT (datetime('now')),
                updated_at          TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_pro_alerts_scope
                ON pro_alerts(user_id, ticker, enabled);

            CREATE TABLE IF NOT EXISTS pro_alert_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL DEFAULT 0,
                ticker          TEXT NOT NULL COLLATE NOCASE,
                metric          TEXT NOT NULL,
                observed_value  REAL,
                threshold       REAL,
                message         TEXT NOT NULL,
                payload_json    TEXT DEFAULT '{}',
                triggered_at    TEXT DEFAULT (datetime('now')),
                acknowledged_at TEXT,
                FOREIGN KEY(alert_id) REFERENCES pro_alerts(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_pro_alert_events_scope
                ON pro_alert_events(user_id, triggered_at DESC);

            CREATE TABLE IF NOT EXISTS pro_paper_trades (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL DEFAULT 0,
                ticker              TEXT NOT NULL COLLATE NOCASE,
                direction           TEXT NOT NULL CHECK(direction IN ('LONG','SHORT')),
                strategy            TEXT NOT NULL,
                catalyst            TEXT DEFAULT '',
                entry_price         REAL NOT NULL,
                stop_price          REAL NOT NULL,
                target_1            REAL NOT NULL,
                target_2            REAL,
                target_3            REAL,
                quantity            REAL NOT NULL,
                planned_risk        REAL NOT NULL,
                planned_reward      REAL,
                reward_risk         REAL,
                status              TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','CLOSED','CANCELLED')),
                opened_at           TEXT DEFAULT (datetime('now')),
                closed_at           TEXT,
                close_price         REAL,
                realized_pnl        REAL,
                realized_r          REAL,
                notes               TEXT DEFAULT '',
                ai_snapshot_json    TEXT DEFAULT '{}',
                pattern_snapshot_json TEXT DEFAULT '[]',
                rule_score          REAL,
                review              TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_pro_paper_scope
                ON pro_paper_trades(user_id, status, opened_at DESC);
            """
        )
        conn.commit()
    finally:
        conn.close()


ensure_pro_tables()


def _cache_summary(ticker: str) -> dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS rows,
                   MIN(timestamp) AS oldest,
                   MAX(timestamp) AS newest,
                   MAX(fetched_at) AS last_fetched,
                   GROUP_CONCAT(DISTINCT provider) AS providers
              FROM ohlcv_bars
             WHERE ticker=? AND timeframe='1d'
            """,
            (ticker,),
        ).fetchone()
        latest = conn.execute(
            """SELECT close, volume, vwap, transactions, provider, timestamp
                 FROM ohlcv_bars WHERE ticker=? AND timeframe='1d'
                 ORDER BY timestamp DESC LIMIT 1""",
            (ticker,),
        ).fetchone()
        return {
            "ticker": ticker,
            "rows": int(row["rows"] or 0),
            "oldest": row["oldest"],
            "newest": row["newest"],
            "last_fetched": row["last_fetched"],
            "providers": [value for value in (row["providers"] or "").split(",") if value] if row else [],
            "latest_bar": dict(latest) if latest else None,
            "status": "healthy" if row and int(row["rows"] or 0) >= 20 else "limited",
        }
    finally:
        conn.close()


def _chart_bars(ticker: str, period: str = "1y") -> list[dict[str, Any]]:
    frame = load_ohlcv_bars(ticker, timeframe="1d", period=period)
    if frame is None or frame.empty:
        return []
    bars: list[dict[str, Any]] = []
    for index, row in frame.tail(1200).iterrows():
        bars.append(
            {
                "time": str(index),
                "open": _safe_float(row.get("Open"), 0),
                "high": _safe_float(row.get("High"), 0),
                "low": _safe_float(row.get("Low"), 0),
                "close": _safe_float(row.get("Close"), 0),
                "volume": _safe_float(row.get("Volume"), 0),
                "vwap": _safe_float(row.get("VWAP")),
                "transactions": _safe_float(row.get("Transactions")),
            }
        )
    return bars


def _mean(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    return sum(clean) / len(clean) if clean else None


def _pct_change(current: float | None, reference: float | None) -> float | None:
    if current is None or reference in (None, 0):
        return None
    return (current / reference - 1.0) * 100.0


def _bar_statistics(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not bars:
        return {}
    valid = [bar for bar in bars if (_safe_float(bar.get("close")) or 0) > 0]
    if not valid:
        return {}
    latest = valid[-1]
    prior = valid[-2] if len(valid) > 1 else latest
    closes = [_safe_float(bar.get("close"), 0) or 0 for bar in valid]
    highs = [_safe_float(bar.get("high"), 0) or 0 for bar in valid]
    lows = [_safe_float(bar.get("low"), 0) or 0 for bar in valid]
    opens = [_safe_float(bar.get("open"), 0) or 0 for bar in valid]
    volumes = [_safe_float(bar.get("volume"), 0) or 0 for bar in valid]
    recent_252 = valid[-252:]
    closes_252 = [_safe_float(bar.get("close"), 0) or 0 for bar in recent_252]
    highs_252 = [_safe_float(bar.get("high"), 0) or 0 for bar in recent_252]
    lows_252 = [_safe_float(bar.get("low"), 0) or 0 for bar in recent_252]
    volumes_252 = [_safe_float(bar.get("volume"), 0) or 0 for bar in recent_252]
    current = closes[-1]
    high_52w = max(highs_252) if highs_252 else None
    low_52w = min(lows_252) if lows_252 else None
    avg_close_52w = _mean(closes_252)
    avg_volume_52w = _mean(volumes_252)
    range_52w = (high_52w - low_52w) if high_52w is not None and low_52w is not None else None
    position_52w = ((current - low_52w) / range_52w * 100.0) if range_52w and low_52w is not None else None

    def sma(window: int) -> float | None:
        values = closes[-window:]
        return _mean(values) if len(values) >= min(window, 5) else None

    def avg_volume(window: int) -> float | None:
        values = volumes[-window:]
        return _mean(values) if values else None

    avg20 = avg_volume(20)
    avg50 = avg_volume(50)
    current_volume = volumes[-1]
    rvol20 = current_volume / avg20 if avg20 else None
    rvol50 = current_volume / avg50 if avg50 else None

    true_ranges: list[float] = []
    for index, bar in enumerate(valid):
        high = _safe_float(bar.get("high"), 0) or 0
        low = _safe_float(bar.get("low"), 0) or 0
        prev_close = _safe_float(valid[index - 1].get("close"), high) if index else high
        true_ranges.append(max(high - low, abs(high - (prev_close or high)), abs(low - (prev_close or low))))
    atr14 = _mean(true_ranges[-14:])
    daily_range = (highs[-1] - lows[-1]) if highs and lows else None
    gap_pct = _pct_change(opens[-1], _safe_float(prior.get("close")))

    returns: list[float] = []
    for index in range(1, len(closes)):
        if closes[index - 1] > 0:
            returns.append(closes[index] / closes[index - 1] - 1.0)
    vol20 = None
    if len(returns) >= 2:
        sample = returns[-20:]
        mean_return = sum(sample) / len(sample)
        variance = sum((value - mean_return) ** 2 for value in sample) / max(1, len(sample) - 1)
        vol20 = math.sqrt(variance) * math.sqrt(252) * 100.0

    return {
        "price": current,
        "previous_close": _safe_float(prior.get("close")),
        "open": opens[-1],
        "day_high": highs[-1],
        "day_low": lows[-1],
        "daily_range": daily_range,
        "gap_pct": gap_pct,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "midpoint_52w": ((high_52w + low_52w) / 2.0) if high_52w is not None and low_52w is not None else None,
        "avg_close_52w": avg_close_52w,
        "avg_volume_52w": avg_volume_52w,
        "position_52w": position_52w,
        "distance_high_52w": _pct_change(current, high_52w),
        "distance_low_52w": _pct_change(current, low_52w),
        "distance_avg_52w": _pct_change(current, avg_close_52w),
        "sma5": sma(5),
        "sma10": sma(10),
        "sma20": sma(20),
        "sma50": sma(50),
        "sma100": sma(100),
        "sma200": sma(200),
        "volume_current": current_volume,
        "volume_avg_20d": avg20,
        "volume_avg_50d": avg50,
        "rvol20": rvol20,
        "rvol50": rvol50,
        "atr14_from_bars": atr14,
        "atr_pct_from_bars": (atr14 / current * 100.0) if atr14 and current else None,
        "volatility_20d": vol20,
        "bar_count": len(valid),
    }


def _candle_pattern_items(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(bars) < 2:
        return []
    detected: list[dict[str, Any]] = []
    start = max(1, len(bars) - 45)

    def add(index: int, name: str, direction: str, confidence: float, description: str, *, family: str = "Candlestick") -> None:
        bar = bars[index]
        trigger = _safe_float(bar.get("high") if direction == "BULLISH" else bar.get("low"), _safe_float(bar.get("close")))
        detected.append({
            "pattern_name": name,
            "pattern_family": family,
            "category": family,
            "direction": direction,
            "confidence": confidence,
            "raw_confidence": confidence,
            "quality_score": confidence,
            "status": "CONFIRMED" if confidence >= 72 else "WATCH",
            "timestamp": bar.get("time"),
            "candle_index": index,
            "trigger_price": trigger,
            "description": description,
            "evidence": ["Detected directly from cached OHLC candle geometry"],
            "conflicts": [],
            "source": "oryntra_pro_fallback",
        })

    for index in range(start, len(bars)):
        current = bars[index]
        previous = bars[index - 1]
        o = _safe_float(current.get("open"), 0) or 0
        h = _safe_float(current.get("high"), 0) or 0
        l = _safe_float(current.get("low"), 0) or 0
        c = _safe_float(current.get("close"), 0) or 0
        po = _safe_float(previous.get("open"), 0) or 0
        ph = _safe_float(previous.get("high"), 0) or 0
        pl = _safe_float(previous.get("low"), 0) or 0
        pc = _safe_float(previous.get("close"), 0) or 0
        candle_range = max(h - l, 1e-9)
        body = abs(c - o)
        upper = h - max(o, c)
        lower = min(o, c) - l
        body_ratio = body / candle_range

        if body_ratio <= 0.10:
            add(index, "Doji", "NEUTRAL", 58, "Open and close are nearly equal, showing indecision that needs confirmation.")
        if lower >= body * 2.2 and upper <= max(body * 0.8, candle_range * .12) and body_ratio <= .45:
            add(index, "Hammer", "BULLISH", 67, "Long lower wick shows rejection of lower prices; strongest near support after a decline.")
        if upper >= body * 2.2 and lower <= max(body * 0.8, candle_range * .12) and body_ratio <= .45:
            add(index, "Shooting Star", "BEARISH", 67, "Long upper wick shows rejection of higher prices; strongest near resistance after a rise.")
        if pc < po and c > o and o <= pc and c >= po:
            add(index, "Bullish Engulfing", "BULLISH", 74, "The current bullish real body engulfs the prior bearish body.")
        if pc > po and c < o and o >= pc and c <= po:
            add(index, "Bearish Engulfing", "BEARISH", 74, "The current bearish real body engulfs the prior bullish body.")
        if h < ph and l > pl:
            add(index, "Inside Bar", "NEUTRAL", 63, "The candle is contained inside the prior range, signaling compression before expansion.")
        if h > ph and l < pl:
            direction = "BULLISH" if c >= o else "BEARISH"
            add(index, "Outside Bar", direction, 66, "The candle expands beyond both sides of the prior range.")
        if body_ratio >= .82:
            direction = "BULLISH" if c > o else "BEARISH"
            add(index, "Bullish Marubozu" if direction == "BULLISH" else "Bearish Marubozu", direction, 69, "Large real body with limited wicks indicates decisive directional control.")

        if index >= 2:
            first = bars[index - 2]
            fo = _safe_float(first.get("open"), 0) or 0
            fc = _safe_float(first.get("close"), 0) or 0
            middle = previous
            mo = _safe_float(middle.get("open"), 0) or 0
            mc = _safe_float(middle.get("close"), 0) or 0
            first_body = abs(fc - fo)
            middle_body = abs(mc - mo)
            if fc < fo and first_body > 0 and middle_body <= first_body * .45 and c > o and c >= (fo + fc) / 2:
                add(index, "Morning Star", "BULLISH", 77, "Three-candle reversal: strong decline, indecision, then recovery through the first candle midpoint.")
            if fc > fo and first_body > 0 and middle_body <= first_body * .45 and c < o and c <= (fo + fc) / 2:
                add(index, "Evening Star", "BEARISH", 77, "Three-candle reversal: strong advance, indecision, then decline through the first candle midpoint.")


    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in detected:
        unique[(str(item.get("pattern_name")), str(item.get("timestamp")))] = item
    results = list(unique.values())
    results.sort(key=lambda item: (str(item.get("timestamp") or ""), float(item.get("quality_score") or 0)), reverse=True)
    return results[:30]


def _pattern_items(scan: dict[str, Any], bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw = list(((scan.get("patterns") or {}).get("recent") or []))
    raw.extend(_candle_pattern_items(bars))
    trend = str(scan.get("trend") or "").upper()
    stats = _bar_statistics(bars)
    rvol = _safe_float((scan.get("volume") or {}).get("ratio"), _safe_float(stats.get("rvol20"), 1)) or 1
    price = _safe_float(scan.get("price"), _safe_float(stats.get("price"), 0)) or 0
    support = _safe_float((scan.get("levels") or {}).get("support_1"))
    resistance = _safe_float((scan.get("levels") or {}).get("resist_1"))
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            item = {"pattern_name": str(item)}
        q = dict(item)
        name = str(q.get("pattern_name") or q.get("name") or "Pattern")
        q["pattern_name"] = name
        q.setdefault("pattern_family", q.get("category") or "Chart pattern")
        timestamp = str(q.get("timestamp") or q.get("time") or "")
        identity = (name, timestamp)
        if identity in seen:
            continue
        seen.add(identity)
        direction = str(q.get("direction") or "NEUTRAL").upper()
        base = _safe_float(q.get("quality_score"), _safe_float(q.get("confidence"), 55)) or 55
        evidence = [str(value) for value in (q.get("evidence") or [])]
        conflicts = [str(value) for value in (q.get("conflicts") or [])]
        adjustment = 0.0
        if rvol >= 1.5:
            adjustment += 5
            evidence.append(f"RVOL {rvol:.2f} confirms participation")
        elif rvol < 0.75:
            adjustment -= 6
            conflicts.append("Below-average volume")
        aligned = (direction == "BULLISH" and "UP" in trend) or (direction == "BEARISH" and "DOWN" in trend)
        if aligned:
            adjustment += 5
            evidence.append("Aligned with current trend")
        elif direction != "NEUTRAL" and trend:
            adjustment -= 4
            conflicts.append("Conflicts with current trend")
        if direction == "BULLISH" and support and price and abs(price - support) / price <= 0.03:
            adjustment += 3
            evidence.append("Near first support")
        if direction == "BEARISH" and resistance and price and abs(resistance - price) / price <= 0.03:
            adjustment += 3
            evidence.append("Near first resistance")
        adjusted = max(0.0, min(99.0, round(base + adjustment, 1)))
        q["raw_confidence"] = round(base, 1)
        q["quality_score"] = adjusted
        q["confidence"] = _safe_float(q.get("confidence"), base)
        q["evidence"] = list(dict.fromkeys(evidence))[:6]
        q["conflicts"] = list(dict.fromkeys(conflicts))[:6]
        q["status"] = "CONFIRMED" if adjusted >= 72 else "WATCH" if adjusted >= 55 else "WEAK"
        items.append(q)
    items.sort(key=lambda x: (float(x.get("quality_score") or 0), str(x.get("timestamp") or "")), reverse=True)
    return items[:40]


def _ai_view(scan: dict[str, Any], patterns: list[dict[str, Any]], stats: dict[str, Any]) -> dict[str, Any]:
    plan = scan.get("trade_plan") or {}
    setup = scan.get("setup") or {}
    signal = str(plan.get("signal") or "HOLD").upper()
    quality = _safe_float(plan.get("quality_score"), 0) or 0
    grade = scan.get("lab_based_grade") or {}
    grade_score = _safe_float(grade.get("score") if isinstance(grade, dict) else None)
    confidence = max(quality, grade_score or 0)
    if signal in {"BUY", "LONG", "BULLISH"}:
        stance = "BULLISH"
    elif signal in {"SELL", "SHORT", "BEARISH"}:
        stance = "BEARISH"
    else:
        stance = "NO TRADE" if confidence < 55 else "NEUTRAL"

    reasons: list[str] = []
    conflicts: list[str] = []
    trend = str(scan.get("trend") or "Unknown")
    rvol = _safe_float((scan.get("volume") or {}).get("ratio"), _safe_float(stats.get("rvol20"), 0)) or 0
    rsi = _safe_float(scan.get("rsi14"))
    above_vwap = scan.get("above_vwap")
    macd_cross = str((scan.get("macd") or {}).get("cross") or "")
    top = patterns[0] if patterns else None
    if trend:
        reasons.append(f"Trend: {trend}")
    if rvol >= 1.25:
        reasons.append(f"Relative volume is elevated at {rvol:.2f}×")
    elif rvol < 0.75:
        conflicts.append(f"Relative volume is weak at {rvol:.2f}×")
    if above_vwap is True:
        reasons.append("Price is above the 20-day VWAP")
    elif above_vwap is False:
        conflicts.append("Price is below the 20-day VWAP")
    if macd_cross and "BULL" in macd_cross.upper():
        reasons.append("MACD is bullish")
    elif macd_cross and "BEAR" in macd_cross.upper():
        conflicts.append("MACD is bearish")
    if rsi is not None:
        if rsi >= 75:
            conflicts.append(f"RSI {rsi:.1f} is extended")
        elif rsi <= 25:
            conflicts.append(f"RSI {rsi:.1f} is deeply oversold")
        else:
            reasons.append(f"RSI {rsi:.1f} is not at an extreme")
    position = _safe_float(stats.get("position_52w"))
    avg_distance = _safe_float(stats.get("distance_avg_52w"))
    if position is not None:
        reasons.append(f"Price is at {position:.1f}% of its 52-week range")
    if avg_distance is not None and abs(avg_distance) >= 15:
        conflicts.append(f"Price is {avg_distance:+.1f}% from its 52-week average close")
    if top:
        reasons.append(f"Top pattern: {top.get('pattern_name', 'Pattern')} ({top.get('quality_score', 0):.0f}%)")
        conflicts.extend(str(x) for x in (top.get("conflicts") or [])[:2])
    setup_type = str(setup.get("setup_type") or "No named setup")
    if setup_type and setup_type != "No named setup":
        reasons.append(f"Setup engine: {setup_type}")
    action = "WAIT"
    if stance == "BULLISH" and confidence >= 70:
        action = "PLAN LONG"
    elif stance == "BEARISH" and confidence >= 70:
        action = "PLAN SHORT"
    elif stance == "NO TRADE":
        action = "AVOID / RECHECK LATER"
    elif confidence >= 55:
        action = "WATCH FOR CONFIRMATION"
    plan_entry = _safe_float(plan.get("entry_price") or plan.get("entry") or plan.get("entry_ideal"))
    plan_stop = _safe_float(plan.get("stop_price") or plan.get("stop_loss") or plan.get("stop"))
    targets = plan.get("targets") or plan.get("target_price") or plan.get("target")
    if targets is None:
        targets = []
    elif not isinstance(targets, list):
        targets = [targets]
    return {
        "stance": stance,
        "confidence": round(confidence, 1),
        "action": action,
        "horizon": str((plan.get("predictions") or {}).get("horizon") or "1–10 trading days"),
        "summary": str(plan.get("reasoning") or plan.get("summary") or setup_type),
        "reasons": reasons[:10],
        "conflicts": conflicts[:10],
        "entry": plan_entry,
        "invalidation": plan_stop,
        "targets": targets,
        "engine": "Oryntra V7/VAI composite",
        "model_version": "pro-0.4",
        "data_freshness": scan.get("scanned_at"),
    }


def _metric(label: str, value: Any, *, key: str, suffix: str = "", description: str = "", favorable: str = "neutral") -> dict[str, Any]:
    number = _safe_float(value)
    if number is None:
        display = "Unavailable"
    elif suffix == "%":
        display = f"{number:.2f}%"
    elif suffix == "×":
        display = f"{number:.2f}×"
    elif suffix == "$":
        display = f"${number:,.2f}"
    elif suffix == "int":
        display = f"{number:,.0f}"
    else:
        display = f"{number:,.2f}"
    return {"key": key, "label": label, "value": number, "display": display, "description": description, "favorable": favorable, "available": number is not None}


def _metrics(scan: dict[str, Any], stats: dict[str, Any], live: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    volume = scan.get("volume") or {}
    macd = scan.get("macd") or {}
    adx = scan.get("adx") or {}
    stochastic = scan.get("stochastic") or {}
    momentum = scan.get("momentum") or {}
    levels = scan.get("levels") or {}
    bollinger = scan.get("bollinger") or {}
    ichimoku = scan.get("ichimoku") or {}
    obv = scan.get("obv") or {}
    live = live or {}
    live_available = live.get("available") is True
    price = _safe_float(live.get("price")) if live_available else None
    price = price if price is not None else (_safe_float(scan.get("price"), _safe_float(stats.get("price"), 0)) or 0)
    atr = _safe_float(scan.get("atr14"), _safe_float(stats.get("atr14_from_bars"), 0)) or 0
    atr_pct = _safe_float(scan.get("atr_pct"), _safe_float(stats.get("atr_pct_from_bars")))
    day_change = _safe_float(live.get("change_pct")) if live_available else None
    day_change = day_change if day_change is not None else (_safe_float(scan.get("day_change"), _pct_change(price, stats.get("previous_close"))) or 0)
    atr_used = abs(day_change) / atr_pct * 100 if atr_pct else None
    rvol = _safe_float(live.get("volume_pace")) if live_available else None
    rvol = rvol if rvol is not None else _safe_float(volume.get("ratio"), _safe_float(stats.get("rvol20")))
    live_group = {"name": "Intraday tape & VWAP", "items": [
        _metric("Live price", live.get("price"), key="live_price", suffix="$", description="Latest Twelve Data intraday close available to the configured plan."),
        _metric("Session VWAP", live.get("session_vwap"), key="session_vwap", suffix="$", description="Cumulative session VWAP computed locally from returned OHLCV bars."),
        _metric("VWAP delta", live.get("vwap_delta"), key="vwap_delta", suffix="$"),
        _metric("From VWAP", live.get("distance_vwap_pct"), key="distance_vwap_pct", suffix="%"),
        _metric("VWAP slope (5 bars)", live.get("vwap_slope_pct"), key="vwap_slope_pct", suffix="%"),
        _metric("VWAP z-score", live.get("vwap_zscore"), key="vwap_zscore"),
        _metric("VWAP upper 1σ", live.get("vwap_upper_1"), key="vwap_upper_1", suffix="$"),
        _metric("VWAP lower 1σ", live.get("vwap_lower_1"), key="vwap_lower_1", suffix="$"),
        _metric("VWAP upper 2σ", live.get("vwap_upper_2"), key="vwap_upper_2", suffix="$"),
        _metric("VWAP lower 2σ", live.get("vwap_lower_2"), key="vwap_lower_2", suffix="$"),
        _metric("Rolling VWAP 20", live.get("rolling_vwap_20"), key="rolling_vwap_20", suffix="$"),
        _metric("VWAP crosses", live.get("vwap_crosses"), key="vwap_crosses", suffix="int"),
        _metric("Bars above VWAP", live.get("bars_above_vwap_pct"), key="bars_above_vwap_pct", suffix="%"),
        _metric("From open", live.get("from_open_pct"), key="from_open_pct", suffix="%"),
        _metric("Volume pace", live.get("volume_pace"), key="live_volume_pace", suffix="×", description="Current session volume divided by expected volume at this point in the regular session."),
        _metric("Session progress", live.get("session_progress"), key="session_progress", suffix="%"),
        _metric("5-minute momentum", live.get("momentum_5m"), key="live_momentum_5m", suffix="%"),
        _metric("15-minute momentum", live.get("momentum_15m"), key="live_momentum_15m", suffix="%"),
        _metric("Opening range high", live.get("opening_range_high"), key="opening_range_high", suffix="$"),
        _metric("Opening range low", live.get("opening_range_low"), key="opening_range_low", suffix="$"),
        _metric("Opening range position", live.get("opening_range_position"), key="opening_range_position", suffix="%"),
    ]}
    groups = [
        {"name": "Price, range & 52-week context", "items": [
            _metric("Price", price, key="price", suffix="$", description="Latest Twelve Data intraday value when configured; otherwise the latest daily close."),
            _metric("Day change", day_change, key="day_change", suffix="%"),
            _metric("Open", live.get("session_open") if live_available else stats.get("open"), key="open", suffix="$"),
            _metric("Day high", live.get("session_high") if live_available else stats.get("day_high"), key="day_high", suffix="$"),
            _metric("Day low", live.get("session_low") if live_available else stats.get("day_low"), key="day_low", suffix="$"),
            _metric("Gap", stats.get("gap_pct"), key="gap_pct", suffix="%"),
            _metric("52W average close", stats.get("avg_close_52w"), key="avg_close_52w", suffix="$", description="Arithmetic average of available daily closing prices over the latest 252 sessions."),
            _metric("52W midpoint", stats.get("midpoint_52w"), key="midpoint_52w", suffix="$"),
            _metric("52W high", stats.get("high_52w") or scan.get("high_52w"), key="high_52w", suffix="$"),
            _metric("52W low", stats.get("low_52w") or scan.get("low_52w"), key="low_52w", suffix="$"),
            _metric("52W range position", stats.get("position_52w"), key="position_52w", suffix="%", description="0% is the 52-week low and 100% is the 52-week high."),
            _metric("From 52W average", stats.get("distance_avg_52w"), key="distance_avg_52w", suffix="%"),
            _metric("From 52W high", stats.get("distance_high_52w"), key="distance_high_52w", suffix="%"),
            _metric("From 52W low", stats.get("distance_low_52w"), key="distance_low_52w", suffix="%"),
            _metric("20-day high", scan.get("high_20d"), key="high_20d", suffix="$"),
            _metric("20-day low", scan.get("low_20d"), key="low_20d", suffix="$"),
        ]},
        {"name": "Trend & moving averages", "items": [
            _metric("Trend strength", scan.get("trend_strength"), key="trend_strength"),
            _metric("SMA 5", stats.get("sma5"), key="sma5", suffix="$"),
            _metric("SMA 10", stats.get("sma10"), key="sma10", suffix="$"),
            _metric("SMA 20", scan.get("ma20") or stats.get("sma20"), key="sma20", suffix="$"),
            _metric("SMA 50", scan.get("ma50") or stats.get("sma50"), key="sma50", suffix="$"),
            _metric("SMA 100", stats.get("sma100"), key="sma100", suffix="$"),
            _metric("SMA 200", scan.get("ma200") or stats.get("sma200"), key="sma200", suffix="$"),
            _metric("EMA 9", scan.get("ema9"), key="ema9", suffix="$"),
            _metric("EMA 21", scan.get("ema21"), key="ema21", suffix="$"),
            _metric("EMA 50", scan.get("ema50"), key="ema50", suffix="$"),
            _metric("5-day momentum", momentum.get("5d"), key="momentum_5d", suffix="%"),
            _metric("20-day momentum", momentum.get("20d"), key="momentum_20d", suffix="%"),
            _metric("60-day momentum", momentum.get("60d"), key="momentum_60d", suffix="%"),
        ]},
        {"name": "Volume & participation", "items": [
            _metric("Live volume pace" if live_available else "RVOL 20D", rvol, key="rvol", suffix="×", description="Intraday volume pace when live data is configured; otherwise current daily volume divided by the 20-day average."),
            _metric("RVOL 50D", stats.get("rvol50"), key="rvol50", suffix="×"),
            _metric("Current volume", live.get("session_volume") if live_available else (volume.get("current") or stats.get("volume_current")), key="volume_current", suffix="int"),
            _metric("20D average volume", volume.get("avg_20d") or stats.get("volume_avg_20d"), key="volume_avg_20d", suffix="int"),
            _metric("50D average volume", stats.get("volume_avg_50d"), key="volume_avg_50d", suffix="int"),
            _metric("52W average volume", stats.get("avg_volume_52w"), key="volume_avg_52w", suffix="int"),
            _metric("VWAP 20D", scan.get("vwap_20d"), key="vwap_20d", suffix="$"),
            _metric("OBV", obv.get("value"), key="obv", suffix="int"),
        ]},
        {"name": "Momentum & trend quality", "items": [
            _metric("RSI 14", scan.get("rsi14"), key="rsi14"),
            _metric("RSI 7", scan.get("rsi7"), key="rsi7"),
            _metric("MACD line", macd.get("line"), key="macd_line"),
            _metric("MACD signal", macd.get("signal"), key="macd_signal"),
            _metric("MACD histogram", macd.get("hist"), key="macd_hist"),
            _metric("Stochastic K", stochastic.get("k"), key="stoch_k"),
            _metric("Stochastic D", stochastic.get("d"), key="stoch_d"),
            _metric("Williams %R", scan.get("williams_r"), key="williams_r"),
            _metric("ADX", adx.get("value"), key="adx"),
            _metric("DI+", adx.get("di_plus"), key="di_plus"),
            _metric("DI-", adx.get("di_minus"), key="di_minus"),
        ]},
        {"name": "Volatility & bands", "items": [
            _metric("ATR 14", atr, key="atr14", suffix="$"),
            _metric("ATR %", atr_pct, key="atr_pct", suffix="%"),
            _metric("ATR traveled", atr_used, key="atr_used", suffix="%"),
            _metric("20D annualized volatility", stats.get("volatility_20d"), key="volatility_20d", suffix="%"),
            _metric("Bollinger upper", bollinger.get("upper"), key="bb_upper", suffix="$"),
            _metric("Bollinger middle", bollinger.get("mid"), key="bb_mid", suffix="$"),
            _metric("Bollinger lower", bollinger.get("lower"), key="bb_lower", suffix="$"),
            _metric("Bollinger %B", bollinger.get("pct"), key="bb_pct"),
            _metric("Bollinger width", bollinger.get("width"), key="bb_width"),
        ]},
        {"name": "Key levels & structure", "items": [
            _metric("Pivot", levels.get("pivot"), key="pivot", suffix="$"),
            _metric("Support 1", levels.get("support_1"), key="support_1", suffix="$"),
            _metric("Support 2", levels.get("support_2"), key="support_2", suffix="$"),
            _metric("Resistance 1", levels.get("resist_1"), key="resistance_1", suffix="$"),
            _metric("Resistance 2", levels.get("resist_2"), key="resistance_2", suffix="$"),
            _metric("Ichimoku Tenkan", ichimoku.get("tenkan"), key="ichi_tenkan", suffix="$"),
            _metric("Ichimoku Kijun", ichimoku.get("kijun"), key="ichi_kijun", suffix="$"),
            _metric("Ichimoku Span A", ichimoku.get("senkou_a"), key="ichi_span_a", suffix="$"),
            _metric("Ichimoku Span B", ichimoku.get("senkou_b"), key="ichi_span_b", suffix="$"),
        ]},
    ]
    if live_available:
        groups.insert(0, live_group)
    return groups


def _metric_map(snapshot: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    scan = snapshot.get("raw_scan") or {}
    stats = snapshot.get("bar_statistics") or {}
    live = snapshot.get("live") or {}
    values["price"] = _safe_float(live.get("price"), _safe_float(scan.get("price"), _safe_float(stats.get("price"), 0))) or 0
    values["day_change"] = _safe_float(live.get("change_pct"), _safe_float(scan.get("day_change"), 0)) or 0
    values["rvol"] = _safe_float(live.get("volume_pace"), _safe_float((scan.get("volume") or {}).get("ratio"), _safe_float(stats.get("rvol20"), 0))) or 0
    values["rsi14"] = _safe_float(scan.get("rsi14"), 0) or 0
    values["atr_pct"] = _safe_float(scan.get("atr_pct"), _safe_float(stats.get("atr_pct_from_bars"), 0)) or 0
    values["ai_confidence"] = _safe_float((snapshot.get("ai_view") or {}).get("confidence"), 0) or 0
    values["pattern_confidence"] = _safe_float(((snapshot.get("patterns") or [{}])[0]).get("quality_score"), 0) or 0
    values["quality_score"] = _safe_float((scan.get("trade_plan") or {}).get("quality_score"), 0) or 0
    values["above_vwap"] = 1.0 if scan.get("above_vwap") is True else 0.0
    values["rvol50"] = _safe_float(stats.get("rvol50"), 0) or 0
    values["position_52w"] = _safe_float(stats.get("position_52w"), 0) or 0
    values["distance_avg_52w"] = _safe_float(stats.get("distance_avg_52w"), 0) or 0
    values["distance_high_52w"] = _safe_float(stats.get("distance_high_52w"), 0) or 0
    values["volatility_20d"] = _safe_float(stats.get("volatility_20d"), 0) or 0
    values["volume_current"] = _safe_float(stats.get("volume_current"), 0) or 0
    values["distance_vwap_pct"] = _safe_float(live.get("distance_vwap_pct"), 0) or 0
    values["vwap_zscore"] = _safe_float(live.get("vwap_zscore"), 0) or 0
    values["vwap_slope_pct"] = _safe_float(live.get("vwap_slope_pct"), 0) or 0
    values["live_volume_pace"] = _safe_float(live.get("volume_pace"), 0) or 0
    values["opening_range_position"] = _safe_float(live.get("opening_range_position"), 0) or 0
    return values


def _snapshot_from_scan(scan: dict[str, Any], period: str, live: dict[str, Any] | None = None) -> dict[str, Any]:
    ticker = str(scan.get("ticker") or "").upper()
    chart_bars = _chart_bars(ticker, period)
    stats = _bar_statistics(chart_bars)
    patterns = _pattern_items(scan, chart_bars)
    summary = dict((scan.get("patterns") or {}).get("summary") or {})
    summary.update({
        "displayed_patterns": len(patterns),
        "fallback_candle_patterns": sum(1 for item in patterns if item.get("source") == "oryntra_pro_fallback"),
    })
    snapshot = {
        "ticker": ticker,
        "company_name": (live or {}).get("company_name") or scan.get("company_name") or ticker,
        "exchange": (live or {}).get("exchange") or scan.get("exchange") or "",
        "scanned_at": scan.get("scanned_at") or _utc_now(),
        "timeframe": scan.get("timeframe") or "1d",
        "period": period,
        "patterns": patterns,
        "pattern_summary": summary,
        "metrics": _metrics(scan, stats, live),
        "cache": _cache_summary(ticker),
        "chart_bars": chart_bars,
        "bar_statistics": stats,
        "trade_plan": scan.get("trade_plan") or {},
        "setup": scan.get("setup") or {},
        "data_provider": scan.get("data_provider") or "unknown",
        "data_sources": [
            {"name": "Massive", "role": "daily history", "status": "active"},
            {"name": "Twelve Data", "role": "live intraday and VWAP", "status": "active" if live and live.get("available") else (live or {}).get("status", "not configured")},
        ],
        "raw_scan": scan,
        "live": live or {**live_configuration(), "available": False, "status": "not_loaded", "bars": []},
        "availability": {
            "daily_cache": True,
            "intraday_stream": bool(live and live.get("available")),
            "bid_ask": bool(live and live.get("available") and live.get("bid") is not None),
            "news_feed": False,
            "fundamentals": False,
            "message": (live or {}).get("message") or "Massive daily cache and full daily analytics are active. Configure Twelve Data for intraday bars and VWAP analytics.",
        },
    }
    snapshot["ai_view"] = _ai_view(scan, patterns, stats)
    if live and live.get("available") and live.get("updated_at"):
        snapshot["ai_view"]["data_freshness"] = live.get("updated_at")
    return snapshot


@router.get("/snapshot/{ticker}")
async def pro_snapshot(
    ticker: str,
    period: str = Query("6mo", pattern="^(1mo|6mo|1y|5y|all)$"),
    pattern_mode: str = Query("official"),
):
    clean = ticker.upper().strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Ticker is required.")
    scan, live = await asyncio.gather(
        _run_scan_pipeline(ScanRequest(ticker=clean, period=period, pattern_mode=pattern_mode)),
        fetch_live(clean, timeframe="5Min", limit=420),
    )
    snapshot = _snapshot_from_scan(scan, period, live)
    _evaluate_alerts_for_snapshot(snapshot, user_id=None)
    return snapshot


@router.get("/live/{ticker}")
async def pro_live(
    ticker: str,
    timeframe: str = Query("5Min", pattern="^(1Min|5Min|15Min|1Hour)$"),
    limit: int = Query(420, ge=20, le=1000),
):
    clean = ticker.upper().strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Ticker is required.")
    return await fetch_live(clean, timeframe=timeframe, limit=limit)


@router.get("/chart/{ticker}")
async def pro_chart(ticker: str, period: str = "1y"):
    clean = ticker.upper().strip()
    return {"ticker": clean, "period": period, "cache": _cache_summary(clean), "bars": _chart_bars(clean, period)}


@router.get("/cache/{ticker}")
async def pro_cache(ticker: str):
    return _cache_summary(ticker.upper().strip())


class AlertCreate(BaseModel):
    ticker: str
    name: str = ""
    metric: Literal["price", "day_change", "rvol", "rvol50", "rsi14", "atr_pct", "ai_confidence", "pattern_confidence", "quality_score", "above_vwap", "position_52w", "distance_avg_52w", "distance_high_52w", "volatility_20d", "volume_current", "distance_vwap_pct", "vwap_zscore", "vwap_slope_pct", "live_volume_pace", "opening_range_position"]
    operator: Literal[">", ">=", "<", "<=", "=="] = ">="
    threshold: float
    cooldown_minutes: int = Field(30, ge=1, le=10080)
    enabled: bool = True

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, value: str) -> str:
        return value.upper().strip()


class AlertUpdate(BaseModel):
    name: str | None = None
    operator: Literal[">", ">=", "<", "<=", "=="] | None = None
    threshold: float | None = None
    cooldown_minutes: int | None = Field(None, ge=1, le=10080)
    enabled: bool | None = None


@router.get("/alerts")
async def list_alerts(request: Request, ticker: str | None = None):
    user_id = _scope(request)
    conn = get_connection()
    try:
        if ticker:
            rows = conn.execute("SELECT * FROM pro_alerts WHERE user_id=? AND ticker=? ORDER BY created_at DESC", (user_id, ticker.upper().strip())).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pro_alerts WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/alerts")
async def create_alert(req: AlertCreate, request: Request):
    user_id = _scope(request)
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO pro_alerts
               (user_id,ticker,name,metric,operator,threshold,enabled,cooldown_minutes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, req.ticker, req.name or f"{req.ticker} {req.metric} {req.operator} {req.threshold}", req.metric, req.operator, req.threshold, int(req.enabled), req.cooldown_minutes),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM pro_alerts WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.patch("/alerts/{alert_id}")
async def update_alert(alert_id: int, req: AlertUpdate, request: Request):
    user_id = _scope(request)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    columns = []
    values: list[Any] = []
    for key, value in updates.items():
        columns.append(f"{key}=?")
        values.append(int(value) if key == "enabled" else value)
    values.extend([alert_id, user_id])
    conn = get_connection()
    try:
        cur = conn.execute(f"UPDATE pro_alerts SET {', '.join(columns)}, updated_at=datetime('now') WHERE id=? AND user_id=?", values)
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found.")
        row = conn.execute("SELECT * FROM pro_alerts WHERE id=?", (alert_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, request: Request):
    user_id = _scope(request)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM pro_alerts WHERE id=? AND user_id=?", (alert_id, user_id))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/alert-events")
async def alert_events(request: Request, limit: int = Query(100, ge=1, le=500)):
    user_id = _scope(request)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM pro_alert_events WHERE user_id=? ORDER BY triggered_at DESC LIMIT ?", (user_id, limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


_OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": lambda a, b: abs(a - b) < 1e-9}


def _evaluate_alerts_for_snapshot(snapshot: dict[str, Any], user_id: int | None) -> list[dict[str, Any]]:
    ticker = snapshot["ticker"]
    values = _metric_map(snapshot)
    conn = get_connection()
    triggered: list[dict[str, Any]] = []
    try:
        if user_id is None:
            rows = conn.execute("SELECT * FROM pro_alerts WHERE ticker=? AND enabled=1", (ticker,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pro_alerts WHERE user_id=? AND ticker=? AND enabled=1", (user_id, ticker)).fetchall()
        now = datetime.utcnow()
        for row in rows:
            metric = row["metric"]
            if metric not in values:
                continue
            observed = values[metric]
            threshold = float(row["threshold"])
            predicate = _OPERATORS.get(row["operator"])
            if predicate is None or not predicate(observed, threshold):
                conn.execute("UPDATE pro_alerts SET last_value=?, updated_at=datetime('now') WHERE id=?", (observed, row["id"]))
                continue
            last = row["last_triggered_at"]
            if last:
                try:
                    last_dt = datetime.fromisoformat(str(last).replace("Z", ""))
                    if now - last_dt < timedelta(minutes=int(row["cooldown_minutes"] or 30)):
                        continue
                except ValueError:
                    pass
            message = f"{ticker}: {metric} is {observed:.2f}, meeting {row['operator']} {threshold:.2f}"
            payload = {"ai_view": snapshot.get("ai_view"), "top_pattern": (snapshot.get("patterns") or [None])[0]}
            cur = conn.execute(
                """INSERT INTO pro_alert_events
                   (alert_id,user_id,ticker,metric,observed_value,threshold,message,payload_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (row["id"], row["user_id"], ticker, metric, observed, threshold, message, _json(payload)),
            )
            conn.execute("UPDATE pro_alerts SET last_value=?, last_triggered_at=?, updated_at=datetime('now') WHERE id=?", (observed, _utc_now(), row["id"]))
            triggered.append({"id": cur.lastrowid, "alert_id": row["id"], "ticker": ticker, "message": message, "observed_value": observed})
        conn.commit()
        return triggered
    finally:
        conn.close()


@router.post("/alerts/evaluate/{ticker}")
async def evaluate_alerts(ticker: str, request: Request, period: str = "6mo"):
    clean = ticker.upper().strip()
    scan = await _run_scan_pipeline(ScanRequest(ticker=clean, period=period, pattern_mode="official"))
    snapshot = _snapshot_from_scan(scan, period)
    return {"ticker": clean, "events": _evaluate_alerts_for_snapshot(snapshot, _scope(request)), "snapshot": snapshot}


class PaperTradeOpen(BaseModel):
    ticker: str
    direction: Literal["LONG", "SHORT"] = "LONG"
    strategy: str
    catalyst: str = ""
    entry_price: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    target_1: float = Field(gt=0)
    target_2: float | None = Field(None, gt=0)
    target_3: float | None = Field(None, gt=0)
    quantity: float = Field(gt=0)
    notes: str = ""
    ai_snapshot: dict[str, Any] = Field(default_factory=dict)
    pattern_snapshot: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, value: str) -> str:
        return value.upper().strip()


class PaperTradeClose(BaseModel):
    close_price: float = Field(gt=0)
    rule_score: float | None = Field(None, ge=0, le=100)
    review: str = ""


@router.get("/paper/trades")
async def pro_paper_trades(request: Request, status: str | None = None):
    user_id = _scope(request)
    conn = get_connection()
    try:
        if status:
            rows = conn.execute("SELECT * FROM pro_paper_trades WHERE user_id=? AND status=? ORDER BY opened_at DESC", (user_id, status.upper())).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pro_paper_trades WHERE user_id=? ORDER BY opened_at DESC", (user_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["ai_snapshot"] = json.loads(item.pop("ai_snapshot_json") or "{}")
            item["pattern_snapshot"] = json.loads(item.pop("pattern_snapshot_json") or "[]")
            result.append(item)
        return result
    finally:
        conn.close()


@router.post("/paper/open")
async def pro_paper_open(req: PaperTradeOpen, request: Request):
    if req.direction == "LONG" and not (req.stop_price < req.entry_price < req.target_1):
        raise HTTPException(status_code=400, detail="Long trade requires stop < entry < target 1.")
    if req.direction == "SHORT" and not (req.target_1 < req.entry_price < req.stop_price):
        raise HTTPException(status_code=400, detail="Short trade requires target 1 < entry < stop.")
    risk_per_share = abs(req.entry_price - req.stop_price)
    reward_per_share = abs(req.target_1 - req.entry_price)
    planned_risk = risk_per_share * req.quantity
    planned_reward = reward_per_share * req.quantity
    rr = planned_reward / planned_risk if planned_risk else 0
    user_id = _scope(request)
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO pro_paper_trades
               (user_id,ticker,direction,strategy,catalyst,entry_price,stop_price,target_1,target_2,target_3,
                quantity,planned_risk,planned_reward,reward_risk,notes,ai_snapshot_json,pattern_snapshot_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, req.ticker, req.direction, req.strategy[:120], req.catalyst[:500], req.entry_price, req.stop_price,
             req.target_1, req.target_2, req.target_3, req.quantity, planned_risk, planned_reward, rr, req.notes[:2000],
             _json(req.ai_snapshot), _json(req.pattern_snapshot)),
        )
        conn.commit()
        return {"ok": True, "trade_id": cur.lastrowid, "planned_risk": round(planned_risk, 2), "planned_reward": round(planned_reward, 2), "reward_risk": round(rr, 2)}
    finally:
        conn.close()


@router.post("/paper/{trade_id}/close")
async def pro_paper_close(trade_id: int, req: PaperTradeClose, request: Request):
    user_id = _scope(request)
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM pro_paper_trades WHERE id=? AND user_id=?", (trade_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trade not found.")
        if row["status"] != "OPEN":
            raise HTTPException(status_code=400, detail="Trade is not open.")
        sign = 1 if row["direction"] == "LONG" else -1
        pnl = (req.close_price - float(row["entry_price"])) * float(row["quantity"]) * sign
        realized_r = pnl / float(row["planned_risk"]) if row["planned_risk"] else 0
        conn.execute(
            """UPDATE pro_paper_trades SET status='CLOSED', closed_at=datetime('now'), close_price=?,
               realized_pnl=?, realized_r=?, rule_score=?, review=? WHERE id=? AND user_id=?""",
            (req.close_price, pnl, realized_r, req.rule_score, req.review[:4000], trade_id, user_id),
        )
        conn.commit()
        return {"ok": True, "trade_id": trade_id, "realized_pnl": round(pnl, 2), "realized_r": round(realized_r, 3)}
    finally:
        conn.close()


@router.get("/paper/stats")
async def pro_paper_stats(request: Request):
    user_id = _scope(request)
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM pro_paper_trades WHERE user_id=? AND status='CLOSED'", (user_id,)).fetchall()
        pnls = [float(row["realized_pnl"] or 0) for row in rows]
        rs = [float(row["realized_r"] or 0) for row in rows]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        total = len(rows)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        return {
            "closed_trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / total * 100, 2) if total else 0,
            "net_pnl": round(sum(pnls), 2),
            "average_win": round(gross_profit / len(wins), 2) if wins else 0,
            "average_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "expectancy_r": round(sum(rs) / total, 3) if total else 0,
            "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        }
    finally:
        conn.close()

@router.post("/alerts/evaluate-all")
async def evaluate_all_alerts(request: Request, period: str = "6mo"):
    import asyncio
    user_id = _scope(request)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM pro_alerts WHERE user_id=? AND enabled=1 ORDER BY ticker LIMIT 50",
            (user_id,),
        ).fetchall()
        tickers = [str(row["ticker"]).upper() for row in rows]
    finally:
        conn.close()
    semaphore = asyncio.Semaphore(3)

    async def evaluate_one(ticker: str):
        async with semaphore:
            try:
                scan = await _run_scan_pipeline(ScanRequest(ticker=ticker, period=period, pattern_mode="official"))
                snapshot = _snapshot_from_scan(scan, period)
                events = await asyncio.to_thread(_evaluate_alerts_for_snapshot, snapshot, user_id)
                return ticker, events, None
            except Exception as exc:
                return ticker, [], str(exc)

    rows = await asyncio.gather(*(evaluate_one(ticker) for ticker in tickers))
    all_events = [event for _, events, _ in rows for event in events]
    errors = [{"ticker": ticker, "error": error} for ticker, _, error in rows if error]
    return {"evaluated": tickers, "events": all_events, "errors": errors, "evaluated_at": _utc_now()}


def _env_bool(name: str, default: bool = False) -> bool:
    import os
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _server_alert_worker() -> None:
    import asyncio
    import os
    import threading
    import time
    if getattr(_server_alert_worker, "started", False):
        return
    _server_alert_worker.started = True
    interval = max(60, int(os.getenv("ORYNTRA_PRO_ALERTS_INTERVAL_SECONDS", "300") or 300))

    def loop() -> None:
        while True:
            try:
                conn = get_connection()
                try:
                    rows = conn.execute(
                        "SELECT DISTINCT user_id, ticker FROM pro_alerts WHERE enabled=1 ORDER BY ticker LIMIT 100"
                    ).fetchall()
                    jobs = [(int(row["user_id"]), str(row["ticker"]).upper()) for row in rows]
                finally:
                    conn.close()
                for user_id, ticker in jobs:
                    try:
                        scan = asyncio.run(_run_scan_pipeline(ScanRequest(ticker=ticker, period="6mo", pattern_mode="official")))
                        snapshot = _snapshot_from_scan(scan, "6mo")
                        _evaluate_alerts_for_snapshot(snapshot, user_id)
                    except Exception as exc:
                        print(f"[Oryntra Pro] alert worker failed for {ticker}: {exc}")
                    time.sleep(0.25)
            except Exception as exc:
                print(f"[Oryntra Pro] alert worker cycle failed: {exc}")
            time.sleep(interval)

    threading.Thread(target=loop, name="oryntra-pro-alerts", daemon=True).start()


if _env_bool("ORYNTRA_PRO_ALERTS_AUTO_START", False):
    _server_alert_worker()

