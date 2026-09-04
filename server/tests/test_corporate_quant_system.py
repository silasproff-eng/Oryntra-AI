import os
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend import database
from backend.corporate_repository import CorporateRepository
from backend.quant_research import QuantConfig, evaluate_strategies
from backend.quant_experiments import histories_from_rows, run_manifest_experiment
from backend.quant_system import liquidity_execution_costs, probabilistic_regimes, regime_conditioned_weights


class CorporateQuantSystemTests(unittest.TestCase):
    def test_point_in_time_corporate_and_macro_records_do_not_arrive_early(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(database, "DB_PATH", os.path.join(directory, "research.db")):
            repository = CorporateRepository()
            facts = []
            for ticker, margin in (("AAA", 11), ("BBB", 17), ("CCC", 23), ("DDD", 29)):
                facts.extend([
                    {"ticker": ticker, "metric": "operating_margin", "value": margin, "available_at": "2024-03-01T12:00:00Z", "source_class": "sec_filing", "source_url": f"https://example.com/{ticker}/margin"},
                    {"ticker": ticker, "metric": "revenue_growth_yoy", "value": margin / 2, "available_at": "2024-03-01T12:00:00Z", "source_class": "sec_filing", "source_url": f"https://example.com/{ticker}/growth"},
                ])
            repository.import_facts(facts)
            repository.import_macro([{"metric": "yield_10y", "value": 4.2, "observation_at": "2024-02-29", "available_at": "2024-03-01T12:00:00Z", "source_class": "regulator_correspondence", "source_url": "https://example.com/y10"}])
            index = pd.DatetimeIndex(["2024-02-29", "2024-03-01", "2024-03-04"])
            corporate, _ = repository.factor_panel(["AAA", "BBB", "CCC", "DDD"], index)
            macro, _ = repository.macro_panel(index)
            self.assertEqual(float(corporate.iloc[0].abs().sum()), 0.0)
            self.assertGreater(float(corporate.iloc[-1].abs().sum()), 0.0)
            self.assertTrue(pd.isna(macro.loc[index[0], "yield_10y"]))
            self.assertEqual(float(macro.loc[index[-1], "yield_10y"]), 4.2)

    def test_regime_cost_and_full_system_outputs_are_structured(self):
        index = pd.bdate_range("2023-01-02", periods=320)
        histories, scores = {}, pd.DataFrame(index=index)
        for seed, ticker in enumerate(("AAA", "BBB", "CCC", "DDD"), 1):
            random = np.random.default_rng(seed)
            closes = 100 * np.exp(np.cumsum(random.normal(.0004, .012, len(index))))
            histories[ticker] = pd.DataFrame({"Close": closes, "Volume": np.full(len(index), 2_000_000)}, index=index)
            scores[ticker] = np.sin(np.arange(len(index)) / 17 + seed)
        macro = pd.DataFrame({"yield_2y": 4.0, "yield_10y": 4.3, "credit_spread_bps": 120.0, "inflation_yoy": 3.0, "policy_rate": 5.0}, index=index)
        regimes = probabilistic_regimes(pd.Series(.0002, index=index), macro)
        weights = regime_conditioned_weights({"time_series_trend": 60, "corporate_quality": 40}, regimes)
        self.assertTrue(np.allclose(weights.sum(axis=1).tail(20), 1.0))
        costs, execution = liquidity_execution_costs(pd.DataFrame(.1, index=index, columns=["AAA"]), pd.DataFrame(100.0, index=index, columns=["AAA"]), pd.DataFrame(1_000.0, index=index, columns=["AAA"]), base_cost_bps=10)
        self.assertGreaterEqual(float(costs.sum()), 0.0)
        self.assertIn("participation_limit_breaches", execution)
        report = evaluate_strategies(histories, QuantConfig(model="v1_corporate_quant_system"), scores, macro)
        self.assertIn("execution", report)
        self.assertEqual(report["assumption_ledger"]["timing"][0]["value"], "Session close t; holdings begin in session t+1")
        self.assertEqual(report["assumption_ledger"]["execution"][1]["value"], "Base cost plus square-root ADV-participation proxy")
        self.assertEqual(len(report["assumption_ledger"]["omissions"]), 4)
        self.assertEqual([row["portfolio_value_multiple"] for row in report["execution"]["capacity_sensitivity"]["scenarios"]], [1.0, 2.0, 5.0])
        self.assertIn("factor_attribution", report)
        self.assertEqual(report["benchmark"]["label"], "Equal-weight buy-and-hold reference")
        self.assertIn("strategy_health", report)
        self.assertEqual(report["macro_data"]["status"], "available")

    def test_manifest_experiment_is_declarative_reproducible_and_recorded(self):
        index = pd.bdate_range("2023-01-02", periods=320)
        rows = []
        for seed, ticker in enumerate(("AAA", "BBB", "CCC", "DDD"), 1):
            closes = 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(.0003, .01, len(index))))
            rows.extend({"date": day.isoformat(), "ticker": ticker, "close": close, "volume": 1_500_000} for day, close in zip(index, closes))
        manifest = {
            "label": "Fixed test",
            "hypothesis": "A fixed rule must be compared with its declared reference.",
            "strategies": ["time_series_trend", "cross_sectional_momentum"],
            "model": "v8_balanced",
            "strategy_weights": {"time_series_trend": 60, "cross_sectional_momentum": 40},
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(database, "DB_PATH", os.path.join(directory, "research.db")):
            report = run_manifest_experiment(histories_from_rows(pd.DataFrame(rows)), manifest)
        self.assertTrue(report["experiment_id"])
        self.assertEqual(report["manifest"]["label"], "Fixed test")
        self.assertEqual(report["benchmark"]["label"], "Equal-weight buy-and-hold reference")


if __name__ == "__main__":
    unittest.main()
