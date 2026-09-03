from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backend import database
import backend.market_repository as market_repository


class MarketRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = str(Path(self.temp.name) / "oryntra-market-repository.db")
        database.init_db()
        market_repository._REPOSITORY = None
        self.repository = market_repository.get_market_repository()

    def tearDown(self) -> None:
        market_repository._REPOSITORY = None
        database.DB_PATH = self.original_path
        self.temp.cleanup()

    @staticmethod
    def _frame(rows: int = 12) -> pd.DataFrame:
        index = pd.date_range("2026-07-13", periods=rows, freq="B")
        close = pd.Series(range(100, 100 + rows), index=index, dtype=float)
        return pd.DataFrame(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.0,
                "Close": close,
                "Volume": 1_000_000.0,
                "VWAP": close - 0.1,
                "Transactions": 500,
            },
            index=index,
        )

    def test_cache_hit_does_not_call_provider(self) -> None:
        database.store_ohlcv_bars(
            "AAPL",
            "1d",
            self._frame(),
            provider="polygon_grouped_daily",
            adjusted=True,
        )
        with patch("backend.market_repository.polygon_get") as provider:
            result = self.repository.get_history(
                "AAPL",
                period="1mo",
                minimum_bars=5,
                max_stale_days=3650,
                allow_api=True,
            )
        provider.assert_not_called()
        self.assertEqual(result.metadata.source, "local_grouped_cache")
        self.assertTrue(result.metadata.from_cache)
        self.assertFalse(result.metadata.fallback_used)
        self.assertGreaterEqual(len(result.history), 5)

    def test_missing_ticker_uses_one_fallback_then_persists(self) -> None:
        frame = self._frame()
        results = []
        for timestamp, row in frame.iterrows():
            results.append(
                {
                    "t": int(pd.Timestamp(timestamp, tz="UTC").timestamp() * 1000),
                    "o": float(row["Open"]),
                    "h": float(row["High"]),
                    "l": float(row["Low"]),
                    "c": float(row["Close"]),
                    "v": float(row["Volume"]),
                    "vw": float(row["VWAP"]),
                    "n": int(row["Transactions"]),
                }
            )
        response = SimpleNamespace(headers={"X-Request-Id": "fallback-test"})
        with patch(
            "backend.market_repository.polygon_get",
            return_value=({"results": results}, response),
        ) as provider:
            first = self.repository.get_history(
                "ZZZZ",
                period="1mo",
                minimum_bars=5,
                max_stale_days=3650,
                allow_api=True,
                provider_preference="polygon",
                provider_api_keys={"polygon": "polygon-user-key"},
                allow_platform_provider_keys=False,
            )
            second = self.repository.get_history(
                "ZZZZ",
                period="1mo",
                minimum_bars=5,
                max_stale_days=3650,
                allow_api=True,
                provider_preference="polygon",
                provider_api_keys={"polygon": "polygon-user-key"},
                allow_platform_provider_keys=False,
            )
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(provider.call_args.kwargs["api_key"], "polygon-user-key")
        self.assertTrue(first.metadata.fallback_used)
        self.assertEqual(first.metadata.source, "ticker_api_fallback_cached")
        self.assertTrue(second.metadata.from_cache)
        self.assertFalse(second.metadata.fallback_used)
        conn = database.get_connection()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM ohlcv_bars WHERE ticker='ZZZZ' AND timeframe='1d'"
            ).fetchone()[0]
            provider_name = conn.execute(
                "SELECT provider FROM ohlcv_bars WHERE ticker='ZZZZ' LIMIT 1"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, len(results))
        self.assertEqual(provider_name, "polygon_ticker_fallback")

    def test_explicit_twelve_data_selection_uses_only_that_users_key(self) -> None:
        values = []
        for timestamp, row in self._frame().iterrows():
            values.append(
                {
                    "datetime": pd.Timestamp(timestamp).strftime("%Y-%m-%d"),
                    "open": str(row["Open"]),
                    "high": str(row["High"]),
                    "low": str(row["Low"]),
                    "close": str(row["Close"]),
                    "volume": str(row["Volume"]),
                }
            )
        with patch("backend.market_repository.polygon_get") as polygon, patch(
            "backend.market_repository.twelvedata_available", return_value=True
        ), patch(
            "backend.market_repository.twelvedata_get", return_value=({"values": values}, SimpleNamespace())
        ) as twelve:
            result = self.repository.get_history(
                "TDAT",
                period="1mo",
                minimum_bars=5,
                max_stale_days=3650,
                allow_api=True,
                provider_preference="twelvedata",
                provider_api_keys={"twelvedata": "twelve-user-key"},
                allow_platform_provider_keys=False,
            )
        polygon.assert_not_called()
        twelve.assert_called_once()
        self.assertEqual(twelve.call_args.kwargs["api_key"], "twelve-user-key")
        self.assertEqual(twelve.call_args.kwargs["params"]["interval"], "1day")
        self.assertEqual(result.metadata.provider, "twelvedata_ticker_fallback")

    def test_cache_only_never_calls_provider(self) -> None:
        with patch("backend.market_repository.polygon_get") as provider:
            with self.assertRaises(ValueError):
                self.repository.get_history(
                    "MISSING",
                    period="1y",
                    minimum_bars=20,
                    allow_api=False,
                )
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
