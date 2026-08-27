import unittest

import numpy as np
import pandas as pd

from backend.quant_research import QuantConfig, evaluate_strategies


class QuantResearchTests(unittest.TestCase):
    def test_regime_profile_returns_auditable_diagnostics(self):
        index = pd.bdate_range("2023-01-02", periods=320)
        histories = {}
        for seed, ticker in enumerate(("SPY", "QQQ", "IWM", "GLD"), start=1):
            returns = np.random.default_rng(seed).normal(.0003, .012, len(index))
            histories[ticker] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(returns))}, index=index)
        report = evaluate_strategies(histories, QuantConfig(model="v8_regime_diversified"))
        self.assertEqual(report["validation"]["status"], "chronological_holdout")
        self.assertIn("defensive_low_volatility", [item["id"] for item in report["results"]])
        self.assertTrue(report["portfolio_risk"]["latest_positions"])
        self.assertEqual(len(report["data_quality"]["symbols"]), 4)
        heatmap = report["visual_diagnostics"]["correlation"]
        self.assertEqual(heatmap["symbols"], ["SPY", "QQQ", "IWM", "GLD"])
        self.assertEqual(len(heatmap["values"]), 4)
        self.assertEqual(len(heatmap["values"][0]), 4)
        self.assertTrue(report["visual_diagnostics"]["monthly_returns"]["years"])
        self.assertGreater(len(report["visual_diagnostics"]["performance"]["equity_curve"]), 1)


if __name__ == "__main__":
    unittest.main()
