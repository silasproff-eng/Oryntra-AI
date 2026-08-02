from __future__ import annotations

import unittest

from backend.v8_engine import directional_alignment, v8_candidate_score


def bullish_indicators() -> dict:
    return {
        "price": 110.0,
        "ma20": 106.0, "ma50": 102.0, "ma200": 95.0,
        "ema9": 108.0, "ema21": 105.0, "ema50": 101.0,
        "trend": "UPTREND", "adx14": 28.0, "di_plus": 30.0, "di_minus": 14.0,
        "momentum_5d": 3.0, "momentum_20d": 8.0, "momentum_60d": 15.0,
        "macd_line": 2.0, "macd_signal": 1.4, "macd_hist": 0.6, "macd_cross": "BULLISH",
        "vwap_20d": 104.0, "rvol_20d": 1.6, "day_change": 1.8,
        "stoch_k": 67.0, "stoch_d": 58.0, "rsi14": 62.0,
        "pivot": 105.0, "support": 101.0, "resistance": 114.0,
        "atr_pct": 2.0, "atr_percentile_252": 45.0,
    }


class V8EngineTests(unittest.TestCase):
    def test_bullish_analytics_favor_long(self):
        ind = bullish_indicators()
        long_score = directional_alignment(ind, "LONG", pattern_direction="BULLISH", pattern_confidence=80)
        short_score = directional_alignment(ind, "SHORT", pattern_direction="BULLISH", pattern_confidence=80)
        self.assertGreater(long_score["score"], short_score["score"])
        self.assertTrue(long_score["symmetry"]["long_short_formula_shared"])
        self.assertFalse(long_score["symmetry"]["ticker_identity_used"])

    def test_atr_penalty_is_same_for_long_and_short(self):
        ind = bullish_indicators()
        ind["atr_pct"] = 8.5
        long_risk = directional_alignment(ind, "LONG")["risk"]
        short_risk = directional_alignment(ind, "SHORT")["risk"]
        self.assertFalse(long_risk["directional"])
        self.assertEqual(long_risk["penalty"], short_risk["penalty"])

    def test_candidate_requires_multiple_positive_factor_families(self):
        sparse = {"price": 101, "ma20": 100, "atr_pct": 1}
        result = v8_candidate_score(95, sparse, "LONG")
        self.assertLessEqual(result["score"], 64)


class V8SetupIntegrationTests(unittest.TestCase):
    def _base_results(self, preferred_direction: str) -> dict:
        opposite = "SHORT" if preferred_direction == "LONG" else "LONG"
        return {
            "BREAKOUT": {"score": 72.0, "direction": preferred_direction, "rules": []},
            "PULLBACK": {"score": 45.0, "direction": opposite, "rules": []},
            "TREND_CONTINUATION": {"score": 68.0, "direction": preferred_direction, "rules": []},
            "REVERSAL_ATTEMPT": {"score": 35.0, "direction": opposite, "rules": []},
            "OVEREXTENDED": {"score": 20.0, "direction": opposite, "rules": []},
            "NO_TRADE": {"score": 35.0, "direction": "NEUTRAL", "rules": []},
        }

    def test_v8_gate_can_pass_strong_long_candidate(self):
        from backend.setup_detector import _apply_v8_engine_adjustments

        ind = bullish_indicators()
        ind.update({"above_ma20": True, "above_ma50": True, "above_ma200": True, "bb_width": 8.0})
        patterns = {"advanced_patterns": {"top_pattern": {"direction": "BULLISH", "confidence": 90}}}
        adjusted = _apply_v8_engine_adjustments(self._base_results("LONG"), ind, patterns)
        best = max((value for key, value in adjusted.items() if key != "NO_TRADE"), key=lambda value: value["score"])
        self.assertGreaterEqual(best["score"], 65)
        self.assertLess(adjusted["NO_TRADE"]["score"], 58)
        self.assertGreaterEqual(best["v8_alignment"]["positive_factor_count"], 3)

    def test_v8_foundation_is_mirrored_for_strong_short_candidate(self):
        from backend.setup_detector import _apply_v8_engine_adjustments

        ind = bullish_indicators()
        ind.update({
            "price": 90.0,
            "ma20": 94.0, "ma50": 98.0, "ma200": 105.0,
            "ema9": 92.0, "ema21": 95.0, "ema50": 99.0,
            "trend": "DOWNTREND",
            "adx14": 30.0, "di_plus": 12.0, "di_minus": 31.0,
            "momentum_5d": -3.0, "momentum_20d": -8.0, "momentum_60d": -15.0,
            "macd_line": -2.0, "macd_signal": -1.4, "macd_hist": -0.6, "macd_cross": "BEARISH",
            "vwap_20d": 96.0, "day_change": -1.8,
            "stoch_k": 33.0, "stoch_d": 42.0, "rsi14": 38.0,
            "pivot": 95.0, "support_1": 86.0, "support_2": 82.0,
            "resist_1": 99.0, "resist_2": 104.0,
            "above_ma20": False, "above_ma50": False, "above_ma200": False,
            "bb_width": 8.0,
        })
        patterns = {"advanced_patterns": {"top_pattern": {"direction": "BEARISH", "confidence": 90}}}
        adjusted = _apply_v8_engine_adjustments(self._base_results("SHORT"), ind, patterns)
        best = max((value for key, value in adjusted.items() if key != "NO_TRADE"), key=lambda value: value["score"])
        self.assertEqual(best["direction"], "SHORT")
        self.assertGreaterEqual(best["score"], 65)
        self.assertLess(adjusted["NO_TRADE"]["score"], 58)


if __name__ == "__main__":
    unittest.main()
