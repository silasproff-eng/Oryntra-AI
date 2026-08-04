from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend import database
from backend.market_cache import (
    latest_completed_trading_day,
    trading_days,
)


class MarketCalendarTests(unittest.TestCase):
    def test_weekends_and_major_holidays_are_excluded(self):
        days = trading_days(date(2026, 7, 3), date(2026, 7, 6))
        self.assertEqual(days, [date(2026, 7, 6)])

    def test_before_eod_cutoff_uses_previous_session(self):
        value = latest_completed_trading_day(
            datetime(2026, 7, 30, 17, 30, tzinfo=timezone.utc),
            ready_hour_et=18,
        )
        self.assertEqual(value, date(2026, 7, 29))


class GroupedDailyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = str(Path(self.temp.name) / "oryntra-test.db")
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temp.cleanup()

    def _bars(self, close_a: float = 101.0):
        timestamp = int(pd.Timestamp("2026-07-29T04:00:00Z").timestamp() * 1000)
        return [
            {"T": "AAPL", "o": 100, "h": 102, "l": 99, "c": close_a, "v": 1234, "vw": 100.5, "n": 88, "t": timestamp},
            {"T": "MSFT", "o": 200, "h": 205, "l": 198, "c": 204, "v": 4321, "vw": 202.5, "n": 77, "t": timestamp},
        ]

    def test_grouped_store_is_atomic_and_idempotent(self):
        first = database.store_grouped_daily_bars(
            "2026-07-29",
            self._bars(),
            minimum_rows=2,
            request_id="request-1",
        )
        second = database.store_grouped_daily_bars(
            "2026-07-29",
            self._bars(close_a=103.0),
            minimum_rows=2,
            request_id="request-2",
        )
        self.assertEqual(first["rows_stored"], 2)
        self.assertEqual(second["rows_stored"], 2)

        with database.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM ohlcv_bars").fetchone()[0]
            aapl = conn.execute(
                "SELECT close, vwap, transactions FROM ohlcv_bars WHERE ticker='AAPL'"
            ).fetchone()
            run = conn.execute(
                "SELECT status, request_id, rows_stored FROM market_ingest_runs WHERE trading_date='2026-07-29'"
            ).fetchone()
        self.assertEqual(count, 2)
        self.assertEqual(float(aapl["close"]), 103.0)
        self.assertEqual(float(aapl["vwap"]), 100.5)
        self.assertEqual(int(aapl["transactions"]), 88)
        self.assertEqual(run["status"], "SUCCESS")
        self.assertEqual(run["request_id"], "request-2")

    def test_undersized_payload_does_not_change_existing_rows(self):
        database.store_grouped_daily_bars(
            "2026-07-29", self._bars(), minimum_rows=2
        )
        with self.assertRaises(ValueError):
            database.store_grouped_daily_bars(
                "2026-07-30", self._bars()[:1], minimum_rows=2
            )
        with database.get_connection() as conn:
            dates = conn.execute(
                "SELECT COUNT(DISTINCT substr(timestamp,1,10)) FROM ohlcv_bars"
            ).fetchone()[0]
        self.assertEqual(dates, 1)


if __name__ == "__main__":
    unittest.main()

