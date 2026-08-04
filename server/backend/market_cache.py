from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar,
    GoodFriday,
    Holiday,
    USLaborDay,
    USMartinLutherKingJr,
    USMemorialDay,
    USPresidentsDay,
    USThanksgivingDay,
    nearest_workday,
)

from .database import (
    get_market_cache_meta,
    get_market_cache_status,
    get_successful_market_dates,
    init_db,
    mark_market_ingest_failed,
    mark_market_ingest_started,
    prune_ohlcv_before,
    set_market_cache_meta,
    store_grouped_daily_bars,
    upsert_market_symbols,
)
from .polygon_client import PolygonAPIError, polygon_get, rate_limit_info

try:
    import fcntl
except Exception:
    fcntl = None

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
WORKER_LOCK_PATH = DATA_DIR / "market_cache_worker.lock"
EASTERN = ZoneInfo("America/New_York")


class NyseHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year's Day", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr,
        USPresidentsDay,
        GoodFriday,
        USMemorialDay,
        Holiday(
            "Juneteenth National Independence Day",
            month=6,
            day=19,
            start_date=pd.Timestamp("2022-06-19"),
            observance=nearest_workday,
        ),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
    ]


SPECIAL_CLOSURES = {
    date(2025, 1, 9),
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MarketCacheConfig:
    lookback_calendar_days: int = 730
    minimum_rows_per_day: int = 1000
    auto_start: bool = False
    auto_backfill: bool = True
    sync_reference: bool = True
    reference_refresh_days: int = 7
    polling_seconds: int = 1800
    initial_delay_seconds: int = 3
    end_of_day_ready_hour_et: int = 18
    retention_days: int = 0
    update_sessions: int = 5

    @classmethod
    def from_env(cls) -> "MarketCacheConfig":
        return cls(
            lookback_calendar_days=max(
                30, int(os.getenv("ORYNTRA_MARKET_CACHE_LOOKBACK_DAYS", "730"))
            ),
            minimum_rows_per_day=max(
                100, int(os.getenv("ORYNTRA_MARKET_CACHE_MIN_ROWS", "1000"))
            ),
            auto_start=_env_bool("ORYNTRA_MARKET_CACHE_AUTO_START", False),
            auto_backfill=_env_bool("ORYNTRA_MARKET_CACHE_AUTO_BACKFILL", True),
            sync_reference=_env_bool("ORYNTRA_MARKET_CACHE_SYNC_REFERENCE", True),
            reference_refresh_days=max(
                1, int(os.getenv("ORYNTRA_MARKET_CACHE_REFERENCE_REFRESH_DAYS", "7"))
            ),
            polling_seconds=max(
                300, int(os.getenv("ORYNTRA_MARKET_CACHE_POLL_SECONDS", "1800"))
            ),
            initial_delay_seconds=max(
                0, int(os.getenv("ORYNTRA_MARKET_CACHE_INITIAL_DELAY_SECONDS", "3"))
            ),
            end_of_day_ready_hour_et=min(
                23, max(16, int(os.getenv("ORYNTRA_MARKET_CACHE_EOD_READY_HOUR_ET", "18")))
            ),
            retention_days=max(
                0, int(os.getenv("ORYNTRA_MARKET_CACHE_RETENTION_DAYS", "0"))
            ),
            update_sessions=max(
                1, min(30, int(os.getenv("ORYNTRA_MARKET_CACHE_UPDATE_SESSIONS", "5")))
            ),
        )


def trading_days(start: date, end: date) -> list[date]:
    if end < start:
        return []
    weekdays = pd.date_range(start=start, end=end, freq="B")
    holidays = NyseHolidayCalendar().holidays(start=start, end=end)
    holiday_dates = {stamp.date() for stamp in holidays}
    return [
        stamp.date()
        for stamp in weekdays
        if stamp.date() not in holiday_dates and stamp.date() not in SPECIAL_CLOSURES
    ]


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while True:
        candidates = trading_days(cursor, cursor)
        if candidates:
            return cursor
        cursor -= timedelta(days=1)


def latest_completed_trading_day(
    now: datetime | None = None,
    *,
    ready_hour_et: int | None = None,
) -> date:

    config = MarketCacheConfig.from_env()
    ready_hour = ready_hour_et if ready_hour_et is not None else config.end_of_day_ready_hour_et
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    eastern_now = current.astimezone(EASTERN)
    today = eastern_now.date()
    is_session = bool(trading_days(today, today))
    if is_session and eastern_now.time() >= dt_time(hour=ready_hour):
        return today
    return previous_trading_day(today)


def planned_backfill_dates(
    *,
    lookback_calendar_days: int | None = None,
    end_date: date | None = None,
    newest_first: bool = True,
) -> list[date]:
    config = MarketCacheConfig.from_env()
    end = end_date or latest_completed_trading_day()
    days = lookback_calendar_days or config.lookback_calendar_days
    start = end - timedelta(days=max(1, int(days)))
    successful = get_successful_market_dates()
    pending = [d for d in trading_days(start, end) if d.isoformat() not in successful]
    return sorted(pending, reverse=newest_first)


def _validate_grouped_payload(payload: dict[str, Any], trading_date: date) -> list[dict[str, Any]]:
    status = str(payload.get("status") or "").upper()
    if status and status not in {"OK", "DELAYED"}:
        raise ValueError(f"Unexpected Polygon status for {trading_date}: {status}")
    results = payload.get("results") or []
    if not isinstance(results, list):
        raise ValueError(f"Polygon grouped response for {trading_date} did not contain a result list.")
    return results


def import_grouped_day(
    trading_date: date | str,
    *,
    minimum_rows: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:

    config = MarketCacheConfig.from_env()
    day = date.fromisoformat(str(trading_date)) if not isinstance(trading_date, date) else trading_date
    min_rows = minimum_rows or config.minimum_rows_per_day
    path = f"/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}"

    if dry_run:
        return {
            "trading_date": day.isoformat(),
            "endpoint": path,
            "dry_run": True,
            "minimum_rows": min_rows,
        }

    mark_market_ingest_started(day.isoformat())
    try:
        payload, response = polygon_get(
            path,
            params={"adjusted": "true"},
            timeout=float(os.getenv("ORYNTRA_MARKET_CACHE_HTTP_TIMEOUT", "45")),
        )
        results = _validate_grouped_payload(payload, day)
        request_id = payload.get("request_id") or response.headers.get("X-Request-Id")
        if not results:
            mark_market_ingest_failed(
                day.isoformat(),
                "Provider returned no grouped rows.",
                status="NO_DATA",
                rows_received=0,
                request_id=request_id,
            )
            return {
                "trading_date": day.isoformat(),
                "status": "NO_DATA",
                "rows_received": 0,
            }
        stored = store_grouped_daily_bars(
            day.isoformat(),
            results,
            provider="polygon_grouped_daily",
            adjusted=True,
            request_id=request_id,
            minimum_rows=min_rows,
        )
        stored["status"] = "SUCCESS"
        print(
            f"[MarketCache] {day.isoformat()}: stored "
            f"{stored['rows_stored']:,} bars from one API call."
        )
        return stored
    except Exception as exc:
        mark_market_ingest_failed(day.isoformat(), str(exc))
        raise


def backfill_market_cache(
    *,
    lookback_calendar_days: int | None = None,
    max_dates: int | None = None,
    newest_first: bool = True,
    dry_run: bool = False,
    stop_event: threading.Event | None = None,
) -> dict[str, Any]:

    init_db()
    pending = planned_backfill_dates(
        lookback_calendar_days=lookback_calendar_days,
        newest_first=newest_first,
    )
    if max_dates is not None:
        pending = pending[: max(0, int(max_dates))]
    summary: dict[str, Any] = {
        "planned_dates": len(pending),
        "completed": 0,
        "failed": 0,
        "no_data": 0,
        "rows_stored": 0,
        "dry_run": dry_run,
        "rate_limit": rate_limit_info(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "errors": [],
    }
    set_market_cache_meta("backfill_state", {**summary, "status": "RUNNING"})

    consecutive_failures = 0
    max_consecutive_failures = max(
        1, int(os.getenv("ORYNTRA_MARKET_CACHE_MAX_CONSECUTIVE_FAILURES", "3"))
    )
    for index, day in enumerate(pending, start=1):
        if stop_event is not None and stop_event.is_set():
            summary["stopped"] = True
            break
        try:
            result = import_grouped_day(day, dry_run=dry_run)
            consecutive_failures = 0
            if result.get("status") == "NO_DATA":
                summary["no_data"] += 1
            else:
                summary["completed"] += 1
                summary["rows_stored"] += int(result.get("rows_stored") or 0)
        except Exception as exc:
            consecutive_failures += 1
            summary["failed"] += 1
            summary["errors"].append({"date": day.isoformat(), "error": str(exc)})
            print(f"[MarketCache] {day.isoformat()} failed: {exc}")
            provider_blocked = isinstance(exc, PolygonAPIError) and exc.status_code in {401, 403}
            if provider_blocked or consecutive_failures >= max_consecutive_failures:
                summary["stopped"] = True
                summary["stop_reason"] = (
                    "Provider rejected the API key or entitlement."
                    if provider_blocked
                    else f"Stopped after {consecutive_failures} consecutive failed dates."
                )
        summary["progress"] = f"{index}/{len(pending)}"
        set_market_cache_meta("backfill_state", {**summary, "status": "RUNNING"})
        if summary.get("stopped"):
            break

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["status"] = "STOPPED" if summary.get("stopped") else "COMPLETE"
    set_market_cache_meta("backfill_state", summary)
    return summary


def update_recent_market_cache(
    *,
    lookback_sessions: int = 10,
    max_dates: int | None = None,
    stop_event: threading.Event | None = None,
) -> dict[str, Any]:

    end = latest_completed_trading_day()
    start = end - timedelta(days=max(20, lookback_sessions * 3))
    successful = get_successful_market_dates()
    candidates = [
        day for day in trading_days(start, end)
        if day.isoformat() not in successful
    ][-max(1, int(lookback_sessions)):]
    candidates.sort(reverse=True)
    if max_dates is not None:
        candidates = candidates[: max(0, int(max_dates))]

    summary = {"planned_dates": len(candidates), "completed": 0, "failed": 0, "rows_stored": 0}
    consecutive_failures = 0
    max_consecutive_failures = max(
        1, int(os.getenv("ORYNTRA_MARKET_CACHE_MAX_CONSECUTIVE_FAILURES", "3"))
    )
    for day in candidates:
        if stop_event is not None and stop_event.is_set():
            summary["stopped"] = True
            break
        try:
            result = import_grouped_day(day)
            consecutive_failures = 0
            if result.get("status") == "SUCCESS":
                summary["completed"] += 1
                summary["rows_stored"] += int(result.get("rows_stored") or 0)
        except Exception as exc:
            consecutive_failures += 1
            summary["failed"] += 1
            print(f"[MarketCache] recent update failed for {day}: {exc}")
            provider_blocked = isinstance(exc, PolygonAPIError) and exc.status_code in {401, 403}
            if provider_blocked or consecutive_failures >= max_consecutive_failures:
                summary["stopped"] = True
                summary["stop_reason"] = (
                    "Provider rejected the API key or entitlement."
                    if provider_blocked
                    else f"Stopped after {consecutive_failures} consecutive failed dates."
                )
                break
    return summary


def _reference_sync_due(refresh_days: int) -> bool:
    state = get_market_cache_meta("reference_sync", {}) or {}
    completed_at = state.get("completed_at") if isinstance(state, dict) else None
    if not completed_at:
        return True
    try:
        previous = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - previous >= timedelta(days=refresh_days)
    except Exception:
        return True


def sync_ticker_reference(
    *,
    max_pages: int | None = None,
    stop_event: threading.Event | None = None,
) -> dict[str, Any]:

    init_db()
    page_limit = max_pages or max(1, int(os.getenv("ORYNTRA_MARKET_CACHE_REFERENCE_MAX_PAGES", "50")))
    next_url: str | None = "/v3/reference/tickers"
    params: dict[str, Any] | None = {
        "market": "stocks",
        "active": "true",
        "limit": 1000,
        "sort": "ticker",
        "order": "asc",
    }
    pages = 0
    rows = 0
    started = datetime.now(timezone.utc).isoformat()
    set_market_cache_meta("reference_sync", {"status": "RUNNING", "started_at": started})

    try:
        while next_url and pages < page_limit:
            if stop_event is not None and stop_event.is_set():
                break
            payload, _response = polygon_get(next_url, params=params, timeout=45)
            page_rows = payload.get("results") or []
            if not isinstance(page_rows, list):
                raise ValueError("Ticker reference response did not contain a result list.")
            stored = upsert_market_symbols(page_rows)
            rows += stored
            pages += 1
            print(f"[MarketCache] reference page {pages}: stored {stored:,} symbols.")
            next_url = payload.get("next_url")
            params = None
    except Exception as exc:
        failed = {
            "status": "FAILED",
            "pages": pages,
            "symbols_stored": rows,
            "started_at": started,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
        set_market_cache_meta("reference_sync", failed)
        raise

    result = {
        "status": "STOPPED" if stop_event is not None and stop_event.is_set() else "COMPLETE",
        "pages": pages,
        "symbols_stored": rows,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    set_market_cache_meta("reference_sync", result)
    return result


def apply_retention(retention_days: int | None = None) -> dict[str, Any]:
    config = MarketCacheConfig.from_env()
    days = config.retention_days if retention_days is None else max(0, int(retention_days))
    if days <= 0:
        return {"enabled": False, "deleted_rows": 0}
    cutoff = date.today() - timedelta(days=days)
    deleted = prune_ohlcv_before(cutoff.isoformat())
    return {"enabled": True, "cutoff": cutoff.isoformat(), "deleted_rows": deleted}


class MarketCacheWorker:
    def __init__(self, config: MarketCacheConfig | None = None):
        self.config = config or MarketCacheConfig.from_env()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._lock_file = None

    def start(self) -> bool:
        if self.thread and self.thread.is_alive():
            return True
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        lock_file = WORKER_LOCK_PATH.open("a+")
        if fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_file.close()
                print("[MarketCache] another cache worker is already running; skipping duplicate.")
                return False
        self._lock_file = lock_file
        self.thread = threading.Thread(
            target=self._run,
            name="oryntra-market-cache",
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
        if self._lock_file:
            try:
                if fcntl is not None:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None

    def _wait(self, seconds: int) -> bool:
        return self.stop_event.wait(max(0, seconds))

    def _run_cycle(self, initial: bool = False) -> None:
        try:
            update_recent_market_cache(lookback_sessions=self.config.update_sessions, stop_event=self.stop_event)
            if self.stop_event.is_set():
                return


            if initial and self.config.auto_backfill:
                backfill_market_cache(
                    lookback_calendar_days=self.config.lookback_calendar_days,
                    newest_first=True,
                    stop_event=self.stop_event,
                )
            if self.stop_event.is_set():
                return

            if self.config.sync_reference and _reference_sync_due(self.config.reference_refresh_days):
                try:
                    sync_ticker_reference(stop_event=self.stop_event)
                except Exception as exc:
                    print(f"[MarketCache] reference sync skipped after error: {type(exc).__name__}: {exc}")

            if not self.stop_event.is_set():
                apply_retention(self.config.retention_days)
        except PolygonAPIError as exc:
            print(f"[MarketCache] provider error: {exc}")
        except Exception as exc:
            print(f"[MarketCache] worker error: {type(exc).__name__}: {exc}")

    def _run(self) -> None:
        init_db()
        if self._wait(self.config.initial_delay_seconds):
            return
        self._run_cycle(initial=True)
        while not self._wait(self.config.polling_seconds):
            self._run_cycle(initial=False)


def start_market_cache_worker() -> MarketCacheWorker | None:
    config = MarketCacheConfig.from_env()
    if not config.auto_start:
        return None
    if not os.getenv("POLYGON_API_KEY", "").strip():
        print("[MarketCache] auto-start skipped because POLYGON_API_KEY is not configured.")
        return None
    worker = MarketCacheWorker(config)
    return worker if worker.start() else None


def status() -> dict[str, Any]:
    state = get_market_cache_status()
    state["rate_limit"] = rate_limit_info()
    state["backfill"] = get_market_cache_meta("backfill_state", {})
    state["reference_sync"] = get_market_cache_meta("reference_sync", {})
    state["config"] = MarketCacheConfig.from_env().__dict__
    return state

