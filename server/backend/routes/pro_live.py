"""Twelve Data live/intraday adapter for private Oryntra Pro use.

The adapter keeps API credentials on the Ubuntu server, uses Twelve Data REST
endpoints, caches aggressively for the free credit limits, and derives the
VWAP analytics locally from returned OHLCV bars. Massive remains Oryntra's
source for broad daily history and 52-week analysis.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TWELVE_DATA_BASE = os.getenv("TWELVE_DATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
_LIVE_CACHE_TTL = timedelta(seconds=max(45, int(os.getenv("ORYNTRA_PRO_LIVE_CACHE_SECONDS", "55") or 55)))
_QUOTE_CACHE_TTL = timedelta(minutes=max(5, int(os.getenv("ORYNTRA_PRO_QUOTE_CACHE_MINUTES", "15") or 15)))
_LIVE_CACHE: dict[tuple[str, str, int], tuple[datetime, dict[str, Any]]] = {}
_QUOTE_CACHE: dict[str, tuple[datetime, dict[str, Any], dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_FETCH_LOCK = threading.Lock()


class LiveDataError(RuntimeError):
    pass


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _api_key() -> str:
    return (
        os.getenv("TWELVE_DATA_API_KEY")
        or os.getenv("TWELVEDATA_API_KEY")
        or os.getenv("TD_API_KEY")
        or ""
    ).strip()


def configuration() -> dict[str, Any]:
    key = _api_key()
    configured = bool(key)
    return {
        "configured": configured,
        "provider": "Twelve Data",
        "feed": "REST intraday",
        "coverage": "eligible real-time US equities/ETFs; venue subset" if configured else "not configured",
        "key_present": configured,
        "secret_present": False,
        "recommended_refresh_seconds": 60,
        "display_rights_note": "Check the display rights included with your Twelve Data plan before showing market data in an app.",
    }


def _request_json(path: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    key = _api_key()
    if not key:
        raise LiveDataError("Twelve Data is not configured. Add TWELVE_DATA_API_KEY to the Oryntra server .env.")
    query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{TWELVE_DATA_BASE}{path}" + (f"?{query}" if query else "")
    request = Request(
        url,
        headers={
            "Authorization": f"apikey {key}",
            "Accept": "application/json",
            "User-Agent": "Oryntra-Pro/0.4",
        },
    )
    try:
        with urlopen(request, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            usage = {
                "api_credits_used": response.headers.get("api-credits-used"),
                "api_credits_left": response.headers.get("api-credits-left"),
            }
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            message = parsed.get("message") or parsed.get("detail") or detail
        except json.JSONDecodeError:
            message = detail
        raise LiveDataError(f"Twelve Data returned HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise LiveDataError(f"Could not reach Twelve Data: {exc.reason}") from exc
    if payload.get("status") == "error" or payload.get("code"):
        raise LiveDataError(str(payload.get("message") or payload))
    return payload, usage


def _parse_exchange_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed


def _normalized_bar(raw: dict[str, Any]) -> dict[str, Any]:
    stamp = _parse_exchange_time(raw.get("datetime"))
    return {
        "time": stamp.isoformat() if stamp else raw.get("datetime"),
        "open": _safe_float(raw.get("open"), 0),
        "high": _safe_float(raw.get("high"), 0),
        "low": _safe_float(raw.get("low"), 0),
        "close": _safe_float(raw.get("close"), 0),
        "volume": _safe_float(raw.get("volume"), 0),
        "vwap": None,
        "provider": "twelve_data",
    }


def _market_state(now_et: datetime, is_market_open: Any = None) -> str:
    if is_market_open is True:
        return "OPEN"
    if now_et.weekday() >= 5:
        return "CLOSED"
    minute = now_et.hour * 60 + now_et.minute
    if 4 * 60 <= minute < 9 * 60 + 30:
        return "PRE-MARKET"
    if 9 * 60 + 30 <= minute < 16 * 60:
        return "OPEN" if is_market_open is not False else "CLOSED"
    if 16 * 60 <= minute < 20 * 60:
        return "AFTER HOURS"
    return "CLOSED"


def _session_progress(now_et: datetime) -> float:
    if now_et.weekday() >= 5:
        return 1.0
    minute = now_et.hour * 60 + now_et.minute
    start = 9 * 60 + 30
    end = 16 * 60
    if minute <= start:
        return 0.0
    if minute >= end:
        return 1.0
    return (minute - start) / (end - start)


def _pct_change(current: float | None, reference: float | None) -> float | None:
    if current is None or reference in (None, 0):
        return None
    return (current / reference - 1.0) * 100.0


def _momentum_minutes(bars: list[dict[str, Any]], minutes: int) -> float | None:
    if len(bars) < 2:
        return None
    latest_time = _parse_exchange_time(bars[-1].get("time"))
    latest_close = _safe_float(bars[-1].get("close"))
    if latest_time is None or latest_close is None:
        return None
    target = latest_time - timedelta(minutes=minutes)
    reference = None
    for bar in reversed(bars[:-1]):
        stamp = _parse_exchange_time(bar.get("time"))
        if stamp is not None and stamp <= target:
            reference = _safe_float(bar.get("close"))
            break
    return _pct_change(latest_close, reference)


def _rolling_vwap(bars: list[dict[str, Any]], count: int) -> float | None:
    selected = bars[-count:]
    numerator = 0.0
    denominator = 0.0
    for bar in selected:
        volume = _safe_float(bar.get("volume"), 0) or 0
        high = _safe_float(bar.get("high"), 0) or 0
        low = _safe_float(bar.get("low"), 0) or 0
        close = _safe_float(bar.get("close"), 0) or 0
        typical = (high + low + close) / 3 if close else None
        if typical is not None and volume > 0:
            numerator += typical * volume
            denominator += volume
    return numerator / denominator if denominator else None


def _apply_cumulative_vwap(bars: list[dict[str, Any]]) -> dict[str, Any]:
    numerator = 0.0
    denominator = 0.0
    weighted_prices: list[tuple[float, float]] = []
    signs: list[int] = []
    above_count = 0
    for bar in bars:
        volume = _safe_float(bar.get("volume"), 0) or 0
        high = _safe_float(bar.get("high"), 0) or 0
        low = _safe_float(bar.get("low"), 0) or 0
        close = _safe_float(bar.get("close"), 0) or 0
        typical = (high + low + close) / 3 if close else None
        if typical is not None and volume > 0:
            numerator += typical * volume
            denominator += volume
            weighted_prices.append((typical, volume))
        vwap = numerator / denominator if denominator else None
        bar["vwap"] = vwap
        if vwap is not None and close:
            sign = 1 if close > vwap else -1 if close < vwap else 0
            signs.append(sign)
            if sign > 0:
                above_count += 1

    session_vwap = numerator / denominator if denominator else None
    variance = None
    if session_vwap is not None and denominator:
        variance = sum(volume * ((price - session_vwap) ** 2) for price, volume in weighted_prices) / denominator
    std = math.sqrt(variance) if variance is not None and variance >= 0 else None
    crosses = 0
    previous = 0
    for sign in signs:
        if sign and previous and sign != previous:
            crosses += 1
        if sign:
            previous = sign
    return {
        "session_vwap": session_vwap,
        "vwap_std": std,
        "vwap_crosses": crosses,
        "bars_above_vwap_pct": (above_count / len(signs) * 100.0) if signs else None,
    }


def _opening_range(session_bars: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    first_30 = []
    for bar in session_bars:
        stamp = _parse_exchange_time(bar.get("time"))
        if stamp is None:
            continue
        local = stamp.astimezone(ET)
        minute = local.hour * 60 + local.minute
        if 9 * 60 + 30 <= minute < 10 * 60:
            first_30.append(bar)
    if not first_30:
        return None, None
    return (
        max((_safe_float(bar.get("high"), 0) or 0) for bar in first_30),
        min((_safe_float(bar.get("low"), 0) or 0) for bar in first_30),
    )


def _vwap_state(price: float | None, vwap: float | None, upper: float | None, lower: float | None, bars: list[dict[str, Any]]) -> str:
    if price is None or vwap is None:
        return "UNAVAILABLE"
    if len(bars) >= 2:
        previous_close = _safe_float(bars[-2].get("close"))
        previous_vwap = _safe_float(bars[-2].get("vwap"))
        if previous_close is not None and previous_vwap is not None:
            if previous_close <= previous_vwap and price > vwap:
                return "VWAP RECLAIM"
            if previous_close >= previous_vwap and price < vwap:
                return "VWAP LOSS"
    if upper is not None and price > upper:
        return "EXTENDED ABOVE VWAP"
    if lower is not None and price < lower:
        return "EXTENDED BELOW VWAP"
    return "ABOVE VWAP" if price > vwap else "BELOW VWAP" if price < vwap else "AT VWAP"


def _cached_quote(ticker: str, now_utc: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    with _CACHE_LOCK:
        cached = _QUOTE_CACHE.get(ticker)
        if cached and now_utc - cached[0] <= _QUOTE_CACHE_TTL:
            return dict(cached[1]), dict(cached[2])
    payload, usage = _request_json("/quote", {"symbol": ticker})
    with _CACHE_LOCK:
        _QUOTE_CACHE[ticker] = (now_utc, dict(payload), dict(usage))
    return payload, usage


def _fetch_live_sync(ticker: str, timeframe: str, limit: int) -> dict[str, Any]:
    clean = ticker.upper().strip()
    config = configuration()
    if not config["configured"]:
        return {
            **config,
            "available": False,
            "status": "not_configured",
            "ticker": clean,
            "message": "Add TWELVE_DATA_API_KEY to the server .env. A Twelve Data key is not interchangeable with Alpaca credentials.",
            "bars": [],
        }

    interval_map = {"1Min": "1min", "5Min": "5min", "15Min": "15min", "1Hour": "1h"}
    interval = interval_map.get(timeframe, "5min")
    outputsize = max(80, min(int(limit), 1000))
    cache_key = (clean, interval, outputsize)
    now_utc = datetime.now(timezone.utc)
    with _CACHE_LOCK:
        cached = _LIVE_CACHE.get(cache_key)
        if cached and now_utc - cached[0] <= _LIVE_CACHE_TTL:
            result = dict(cached[1])
            result["cache_hit"] = True
            result["cache_age_seconds"] = round((now_utc - cached[0]).total_seconds(), 1)
            return result

    series, series_usage = _request_json(
        "/time_series",
        {
            "symbol": clean,
            "interval": interval,
            "outputsize": outputsize,
            "order": "asc",
            "timezone": "America/New_York",
            "previous_close": "true",
        },
    )
    quote, quote_usage = _cached_quote(clean, now_utc)
    bars = [_normalized_bar(item) for item in series.get("values", []) if isinstance(item, dict)]
    bars = [bar for bar in bars if (_safe_float(bar.get("close"), 0) or 0) > 0]
    now_et = now_utc.astimezone(ET)
    today = now_et.date()
    session_bars = [
        bar for bar in bars
        if (stamp := _parse_exchange_time(bar.get("time"))) is not None and stamp.astimezone(ET).date() == today
    ]
    if not session_bars:
        latest_date = None
        for bar in reversed(bars):
            stamp = _parse_exchange_time(bar.get("time"))
            if stamp is not None:
                latest_date = stamp.astimezone(ET).date()
                break
        if latest_date is not None:
            session_bars = [
                bar for bar in bars
                if (stamp := _parse_exchange_time(bar.get("time"))) is not None and stamp.astimezone(ET).date() == latest_date
            ]

    vwap_stats = _apply_cumulative_vwap(session_bars)
    # Copy computed session VWAP values back into the matching chart bars.
    session_by_time = {bar.get("time"): bar for bar in session_bars}
    for bar in bars:
        enriched = session_by_time.get(bar.get("time"))
        if enriched is not None:
            bar["vwap"] = enriched.get("vwap")

    price = _safe_float(session_bars[-1].get("close")) if session_bars else _safe_float(quote.get("close"))
    previous_close = _safe_float(quote.get("previous_close"))
    change = price - previous_close if price is not None and previous_close is not None else _safe_float(quote.get("change"))
    change_pct = _pct_change(price, previous_close)
    if change_pct is None:
        change_pct = _safe_float(quote.get("percent_change"))

    session_open = _safe_float(session_bars[0].get("open")) if session_bars else _safe_float(quote.get("open"))
    session_high = max((_safe_float(bar.get("high"), 0) or 0) for bar in session_bars) if session_bars else _safe_float(quote.get("high"))
    session_low = min((_safe_float(bar.get("low"), 0) or 0) for bar in session_bars) if session_bars else _safe_float(quote.get("low"))
    session_volume = sum((_safe_float(bar.get("volume"), 0) or 0) for bar in session_bars)
    if not session_volume:
        session_volume = _safe_float(quote.get("volume"), 0) or 0
    average_daily_volume = _safe_float(quote.get("average_volume"))
    progress = _session_progress(now_et)
    expected_volume = average_daily_volume * max(progress, 0.05) if average_daily_volume else None
    volume_pace = session_volume / expected_volume if expected_volume else None

    session_vwap = _safe_float(vwap_stats.get("session_vwap"))
    vwap_std = _safe_float(vwap_stats.get("vwap_std"))
    upper_1 = session_vwap + vwap_std if session_vwap is not None and vwap_std is not None else None
    lower_1 = session_vwap - vwap_std if session_vwap is not None and vwap_std is not None else None
    upper_2 = session_vwap + 2 * vwap_std if session_vwap is not None and vwap_std is not None else None
    lower_2 = session_vwap - 2 * vwap_std if session_vwap is not None and vwap_std is not None else None
    vwap_delta = price - session_vwap if price is not None and session_vwap is not None else None
    vwap_zscore = vwap_delta / vwap_std if vwap_delta is not None and vwap_std not in (None, 0) else None
    latest_vwap = _safe_float(session_bars[-1].get("vwap")) if session_bars else None
    prior_vwap = _safe_float(session_bars[-6].get("vwap")) if len(session_bars) >= 6 else None
    vwap_slope_pct = _pct_change(latest_vwap, prior_vwap)
    rolling_vwap_20 = _rolling_vwap(session_bars, 20)
    opening_range_high, opening_range_low = _opening_range(session_bars)
    opening_range_position = None
    if price is not None and opening_range_high is not None and opening_range_low is not None and opening_range_high > opening_range_low:
        opening_range_position = (price - opening_range_low) / (opening_range_high - opening_range_low) * 100.0

    meta = series.get("meta") if isinstance(series.get("meta"), dict) else {}
    last_time = session_bars[-1].get("time") if session_bars else quote.get("datetime")
    state = _market_state(now_et, quote.get("is_market_open"))
    result = {
        **config,
        "available": bool(bars),
        "status": "ok" if bars else "no_data",
        "ticker": clean,
        "company_name": quote.get("name") or clean,
        "exchange": quote.get("exchange") or meta.get("exchange") or "",
        "mic_code": quote.get("mic_code") or meta.get("mic_code") or "",
        "currency": quote.get("currency") or meta.get("currency") or "USD",
        "timeframe": timeframe,
        "interval": interval,
        "bars": bars,
        "daily_bars": [],
        "price": price,
        "previous_close": previous_close,
        "change": change,
        "change_pct": change_pct,
        "bid": None,
        "ask": None,
        "bid_size": None,
        "ask_size": None,
        "midpoint": None,
        "spread": None,
        "spread_pct": None,
        "session_open": session_open,
        "session_high": session_high,
        "session_low": session_low,
        "session_volume": session_volume,
        "average_daily_volume_20": average_daily_volume,
        "volume_pace": volume_pace,
        "session_progress": progress * 100.0,
        "session_vwap": session_vwap,
        "vwap_delta": vwap_delta,
        "distance_vwap_pct": _pct_change(price, session_vwap),
        "vwap_std": vwap_std,
        "vwap_zscore": vwap_zscore,
        "vwap_upper_1": upper_1,
        "vwap_lower_1": lower_1,
        "vwap_upper_2": upper_2,
        "vwap_lower_2": lower_2,
        "vwap_slope_pct": vwap_slope_pct,
        "rolling_vwap_20": rolling_vwap_20,
        "vwap_crosses": vwap_stats.get("vwap_crosses"),
        "bars_above_vwap_pct": vwap_stats.get("bars_above_vwap_pct"),
        "vwap_state": _vwap_state(price, session_vwap, upper_1, lower_1, session_bars),
        "from_open_pct": _pct_change(price, session_open),
        "momentum_5m": _momentum_minutes(session_bars, 5),
        "momentum_15m": _momentum_minutes(session_bars, 15),
        "opening_range_high": opening_range_high,
        "opening_range_low": opening_range_low,
        "opening_range_position": opening_range_position,
        "market_state": state,
        "market_time": now_et.isoformat(timespec="seconds"),
        "updated_at": last_time or now_utc.isoformat(timespec="seconds"),
        "cache_hit": False,
        "api_usage": {
            "series": series_usage,
            "quote": quote_usage,
        },
        "message": "Twelve Data REST intraday bars with Oryntra-computed VWAP analytics. The default US feed may represent a subset of total US trading volume; check your plan's display rights.",
    }
    with _CACHE_LOCK:
        _LIVE_CACHE[cache_key] = (now_utc, dict(result))
    return result


def _locked_fetch(ticker: str, timeframe: str, limit: int) -> dict[str, Any]:
    # Prevent simultaneous snapshot and timer refreshes from spending duplicate
    # API credits for the same private workstation.
    with _FETCH_LOCK:
        return _fetch_live_sync(ticker, timeframe, limit)


async def fetch_live(ticker: str, timeframe: str = "5Min", limit: int = 420) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_locked_fetch, ticker, timeframe, limit)
    except LiveDataError as exc:
        return {
            **configuration(),
            "available": False,
            "status": "error",
            "ticker": ticker.upper().strip(),
            "message": str(exc),
            "bars": [],
        }
