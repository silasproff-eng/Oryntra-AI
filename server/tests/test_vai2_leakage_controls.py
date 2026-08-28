import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.vai2_model import train_vai2_from_lab_rows


class Vai2LeakageControlTests(unittest.TestCase):
    def test_train_validation_test_are_chronological_and_purged(self):
        rows = []
        for day in range(120):
            date = f"2024-{(day // 28) + 1:02d}-{(day % 28) + 1:02d}"
            for number, ticker in enumerate(("AAA", "BBB", "CCC", "DDD")):
                winner = (day + number) % 2 == 0
                rows.append({
                    "date": date, "ticker": ticker, "direction": "LONG", "actionable": True,
                    "return_pct": 2.5 if winner else -2.0, "mfe_pct": 3.0 if winner else .5,
                    "mae_pct": -.5 if winner else -2.5, "target_hit": winner, "stop_hit": not winner,
                    "rsi14": 65 if winner else 35, "adx14": 28, "di_plus": 20 if winner else 8,
                    "di_minus": 8 if winner else 20, "vol_ratio": 1.1, "atr_pct": 2.0,
                    "momentum_5d": 3 if winner else -3, "momentum_20d": 8 if winner else -8,
                    "momentum_60d": 12 if winner else -12, "above_ma20": winner,
                    "above_ma50": winner, "above_ma200": winner, "regime": "BULL_TREND",
                    "top_pattern": "TEST", "setup_type": "TREND", "confidence": 99 if not winner else 1,
                })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "models"
            with patch("backend.vai2_model.MODEL_ROOT", root), patch("backend.vai2_model.RUNS_DIR", root / "runs"), patch("backend.vai2_model.PROMOTED_MODEL_PATH", root / "model.json"), patch("backend.vai2_model.PROMOTED_META_PATH", root / "metadata.json"):
                outcome = train_vai2_from_lab_rows(rows, horizon_days=1, min_samples=80, force_promote=True, run_label="leakage_test")
        self.assertTrue(outcome["ok"], outcome)
        model = outcome["model"]
        self.assertEqual(model["split"]["method"], "chronological_dates_with_horizon_purge")
        self.assertGreater(model["test_samples"], 0)
        self.assertNotIn("confidence", model["feature_names"])
        self.assertFalse(any(name.startswith("ticker=") for name in model["feature_names"]))
        self.assertIn("promotion_score", model["test"])


if __name__ == "__main__":
    unittest.main()
