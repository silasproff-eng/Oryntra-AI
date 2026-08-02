from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backend.backtest import BacktestRequest, _run_one
from backend.pattern_lab import _base_observation
from backend.research_experiments import compare_engine_inputs, chronological_split
from backend.research_training import audit_training_rows


def _history(rows: int = 320) -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=rows, freq="B")
    trend = np.linspace(80.0, 140.0, rows)
    wave = np.sin(np.arange(rows) / 7.0) * 2.0
    close = trend + wave
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.012,
            "Low": close * 0.988,
            "Close": close,
            "Volume": 1_000_000 + np.arange(rows) * 1000,
            "VWAP": close * 0.999,
            "Transactions": 500 + np.arange(rows),
        },
        index=index,
    )


def _training_row(ticker: str, signal: date, *, bad_entry: bool = False) -> dict:
    entry = signal if bad_entry else signal + timedelta(days=1)
    return {
        "ticker": ticker,
        "date": signal.isoformat(),
        "signal_date": signal.isoformat(),
        "entry_date": entry.isoformat(),
        "entry_price": 100.0,
        "future_close": 103.0,
        "future_high": 105.0,
        "future_low": 98.0,
        "raw_long_return_pct": 3.0,
        "raw_long_mfe_pct": 5.0,
        "raw_long_mae_pct": -2.0,
        "horizon_days": 10,
        "direction": "LONG",
        "actionable": True,
        "return_pct": 2.9,
        "mfe_pct": 5.0,
        "mae_pct": -2.0,
    }


class ResearchPipelineTests(unittest.TestCase):
    def test_pattern_features_do_not_look_into_future(self) -> None:
        original = _history()
        index = 250
        first = _base_observation(
            "TEST",
            original,
            index,
            horizon_days=10,
            source="test",
            window={"start": "", "end": ""},
        )
        changed = original.copy()
        changed.iloc[index + 1 :, changed.columns.get_loc("Close")] *= 10.0
        changed.iloc[index + 1 :, changed.columns.get_loc("High")] *= 10.0
        changed.iloc[index + 1 :, changed.columns.get_loc("Low")] *= 0.1
        second = _base_observation(
            "TEST",
            changed,
            index,
            horizon_days=10,
            source="test",
            window={"start": "", "end": ""},
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        first_observation, first_indicators, first_signal_history = first
        second_observation, second_indicators, second_signal_history = second
        self.assertEqual(first_observation["signal_date"], second_observation["signal_date"])
        self.assertGreater(first_observation["entry_date"], first_observation["signal_date"])
        pd.testing.assert_frame_equal(first_signal_history, second_signal_history)
        self.assertEqual(first_indicators, second_indicators)
        self.assertNotEqual(first_observation["future_close"], second_observation["future_close"])

    def test_engine_comparison_requires_identical_observations(self) -> None:
        common = [
            {"ticker": "AAPL", "date": "2026-01-02"},
            {"ticker": "MSFT", "date": "2026-01-02"},
        ]
        same = compare_engine_inputs({"official": common, "v8": [dict(row) for row in common]})
        self.assertTrue(same["comparable"])
        different = compare_engine_inputs(
            {"official": common, "v8": [common[0]]}
        )
        self.assertFalse(different["comparable"])
        self.assertEqual(different["differences"]["v8"]["missing_count"], 1)

    def test_training_audit_rejects_non_future_and_duplicate_rows(self) -> None:
        start = date(2025, 1, 1)
        valid = [_training_row("AAPL", start + timedelta(days=i * 2)) for i in range(20)]
        invalid = _training_row("MSFT", start + timedelta(days=50), bad_entry=True)
        duplicate = dict(valid[0])
        audit = audit_training_rows(valid + [invalid, duplicate], minimum_rows=10)
        self.assertFalse(audit["valid"])
        self.assertEqual(audit["rows_accepted"], 20)
        self.assertEqual(audit["duplicate_count"], 1)
        self.assertTrue(any(error["reason"] == "non_future_entry" for error in audit["errors"]))

    def test_chronological_split_has_ordered_non_overlapping_dates(self) -> None:
        start = date(2020, 1, 1)
        rows = [_training_row("AAPL", start + timedelta(days=i)) for i in range(200)]
        split = chronological_split(rows, purge_days=5)
        train_dates = [rows[index]["date"] for index in split["train"]]
        validation_dates = [rows[index]["date"] for index in split["validation"]]
        test_dates = [rows[index]["date"] for index in split["test"]]
        self.assertTrue(train_dates and validation_dates and test_dates)
        self.assertLess(max(train_dates), min(validation_dates))
        self.assertLess(max(validation_dates), min(test_dates))
        self.assertFalse(set(train_dates) & set(validation_dates))
        self.assertFalse(set(validation_dates) & set(test_dates))

    def test_backtest_is_deterministic_and_enters_after_signal(self) -> None:
        history = _history()
        request = BacktestRequest(
            ticker="TEST",
            period="all",
            min_score=0,
            engine_mode="official",
            min_history=90,
            max_hold_candles=10,
            commission_bps=2,
            slippage_bps=4,
        )
        first = _run_one("TEST", history, request, source="unit_test")
        second = _run_one("TEST", history, request, source="unit_test")
        self.assertEqual(first, second)
        for trade in first["trades"]:
            self.assertGreater(trade["date_in"], trade["signal_date"])


if __name__ == "__main__":
    unittest.main()
