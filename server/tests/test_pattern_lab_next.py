from __future__ import annotations

import unittest

from backend.pattern_lab import _candidate_indexes, _cluster_bootstrap_ci, _walk_forward_report
import numpy as np
import pandas as pd


class PatternLabNextTests(unittest.TestCase):
    def test_candidate_indexes_do_not_overlap_holding_windows(self):
        index = pd.date_range("2020-01-01", periods=320, freq="B")
        close = np.linspace(50, 100, len(index))
        history = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * .99, "Close": close, "Volume": 1000}, index=index)
        candidates, meta = _candidate_indexes(
            history, ticker="TEST", min_history=80, horizon_days=10, step=1,
            max_tests=200, sampling_mode="even", seed=1, random_window_bars=180,
            start_date="", end_date="",
        )
        self.assertTrue(candidates)
        self.assertTrue(all(b - a >= 11 for a, b in zip(candidates, candidates[1:])))
        self.assertEqual(meta["overlap_policy"], "one_position_per_ticker")

    def test_walk_forward_selects_threshold_on_prior_dates(self):
        rows = []
        dates = pd.date_range("2020-01-01", periods=100, freq="B")
        for i, date in enumerate(dates):
            rows.append({"ticker": "AAPL", "date": date.date().isoformat(), "actionable": True, "confidence": 80, "return_pct": 1 if i % 3 else -0.5, "mfe_pct": 2, "mae_pct": -1, "winner": i % 3 != 0})
        report = _walk_forward_report(rows, folds=4, purge_days=10)
        self.assertEqual(report["method"], "expanding_purged_walk_forward")
        self.assertTrue(report["folds"])
        for fold in report["folds"]:
            if fold["train_end"]:
                self.assertLess(fold["train_end"], fold["test_start"])

    def test_cluster_bootstrap_returns_intervals(self):
        rows = []
        for ticker in ("A", "B", "C"):
            for i in range(10):
                rows.append({"ticker": ticker, "actionable": True, "return_pct": 1 if i % 2 else -0.25, "mfe_pct": 2, "mae_pct": -1, "winner": i % 2 == 1})
        report = _cluster_bootstrap_ci(rows, samples=50, seed=3)
        self.assertEqual(report["samples"], 50)
        self.assertEqual(len(report["expectancy_95_ci_pct"]), 2)


if __name__ == "__main__":
    unittest.main()
