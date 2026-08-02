"""Oryntra V8 evidence engine.

V8 is a deterministic, ticker-agnostic extension of the V7 setup framework.
It does not train on Pattern Lab output and it does not use ticker identity.
Long and short candidates are judged by the same formula with the sign reversed.

Directional evidence and risk are deliberately separated:

* trend, moving averages, momentum, MACD, VWAP and price levels contribute
  directional evidence;
* relative volume confirms or weakens an existing move but is never a direction
  by itself;
* ATR is a risk/positioning input and never becomes bullish or bearish;
* stochastic and RSI are timing/context inputs, not standalone reversal calls;
* support/resistance and pivots are low-weight location inputs.

The methodology references are documented in ``V8_METHODOLOGY.md``.  The
weights are hypotheses to be validated out of sample, not claims of predictive
certainty.
"""
from __future__ import annotations

import math
from typing import Any

V8_VERSION = "8.0-evidence-v1"

FACTOR_WEIGHTS: dict[str, float] = {
    "trend_structure": 22.0,
    "trend_strength": 10.0,
    "momentum": 16.0,
    "macd": 10.0,
    "vwap": 10.0,
    "relative_volume": 8.0,
    "stochastic": 5.0,
    "price_levels": 11.0,
    "rsi_context": 5.0,
    "pattern_confirmation": 3.0,
}


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def canonical_direction(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"LONG", "BUY", "BULL", "BULLISH", "UP"}:
        return "LONG"
    if raw in {"SHORT", "SELL", "BEAR", "BEARISH", "DOWN"}:
        return "SHORT"
    return "NEUTRAL"


def _signed(candidate_direction: str, market_value: float) -> float:
    """Convert an observed market direction to candidate-alignment space."""
    sign = 1.0 if canonical_direction(candidate_direction) == "LONG" else -1.0
    return clamp(sign * market_value)


def _pct_distance(price: float, level: float | None) -> float:
    level_value = finite(level, 0.0)
    return ((price - level_value) / level_value * 100.0) if price > 0 and level_value > 0 else 0.0


def _squash(value: float, scale: float) -> float:
    return clamp(math.tanh(value / max(1e-9, scale)))


def _factor(
    name: str,
    alignment: float,
    confidence: float,
    explanation: str,
    *,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weight = FACTOR_WEIGHTS[name]
    bounded_alignment = clamp(alignment)
    bounded_confidence = clamp(confidence, 0.0, 1.0)
    contribution = weight * bounded_alignment * bounded_confidence
    return {
        "name": name,
        "weight": weight,
        "alignment": round(bounded_alignment, 4),
        "confidence": round(bounded_confidence, 4),
        "contribution": round(contribution, 4),
        "explanation": explanation,
        "raw": raw or {},
    }


def _trend_structure(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    price = finite(ind.get("price"))
    levels = [
        ("SMA20", finite(ind.get("ma20")), 0.20),
        ("SMA50", finite(ind.get("ma50")), 0.28),
        ("SMA200", finite(ind.get("ma200")), 0.24),
        ("EMA9", finite(ind.get("ema9")), 0.08),
        ("EMA21", finite(ind.get("ema21")), 0.12),
        ("EMA50", finite(ind.get("ema50")), 0.08),
    ]
    observed = 0.0
    available_weight = 0.0
    for _, level, weight in levels:
        if price > 0 and level > 0:
            observed += weight * _squash(_pct_distance(price, level), 2.5)
            available_weight += weight
    if available_weight:
        observed /= available_weight

    ma20, ma50, ma200 = finite(ind.get("ma20")), finite(ind.get("ma50")), finite(ind.get("ma200"))
    ema9, ema21, ema50 = finite(ind.get("ema9")), finite(ind.get("ema21")), finite(ind.get("ema50"))
    stack = 0.0
    stack_parts = 0
    if min(ma20, ma50, ma200) > 0:
        stack += 1.0 if ma20 > ma50 > ma200 else (-1.0 if ma20 < ma50 < ma200 else 0.0)
        stack_parts += 1
    if min(ema9, ema21, ema50) > 0:
        stack += 1.0 if ema9 > ema21 > ema50 else (-1.0 if ema9 < ema21 < ema50 else 0.0)
        stack_parts += 1
    if stack_parts:
        observed = 0.72 * observed + 0.28 * (stack / stack_parts)

    trend_label = str(ind.get("trend") or "").upper()
    if "UPTREND" in trend_label:
        observed = 0.82 * observed + 0.18
    elif "DOWNTREND" in trend_label:
        observed = 0.82 * observed - 0.18

    alignment = _signed(direction, observed)
    explanation = "Price and moving-average structure align with the candidate." if alignment > 0.15 else (
        "Price and moving-average structure conflict with the candidate." if alignment < -0.15 else
        "Moving-average structure is mixed or flat."
    )
    return _factor(
        "trend_structure",
        alignment,
        min(1.0, 0.45 + available_weight),
        explanation,
        raw={"price": price, "trend": trend_label, "observed_direction": round(observed, 4)},
    )


def _trend_strength(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    adx = finite(ind.get("adx14"))
    di_plus = finite(ind.get("di_plus"))
    di_minus = finite(ind.get("di_minus"))
    di_total = max(1.0, di_plus + di_minus)
    observed = clamp((di_plus - di_minus) / di_total * 2.0)
    confidence = clamp((adx - 12.0) / 28.0, 0.0, 1.0)
    alignment = _signed(direction, observed)
    explanation = (
        "ADX/DI confirm the candidate direction."
        if alignment > 0.15 and confidence >= 0.25
        else "ADX/DI oppose the candidate direction."
        if alignment < -0.15 and confidence >= 0.25
        else "ADX is weak; trend direction receives little weight."
    )
    return _factor(
        "trend_strength",
        alignment,
        confidence,
        explanation,
        raw={"adx14": adx, "di_plus": di_plus, "di_minus": di_minus},
    )


def _momentum(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    m5 = finite(ind.get("momentum_5d"))
    m20 = finite(ind.get("momentum_20d"))
    m60 = finite(ind.get("momentum_60d"))
    observed = 0.20 * _squash(m5, 5.0) + 0.45 * _squash(m20, 9.0) + 0.35 * _squash(m60, 18.0)
    alignment = _signed(direction, observed)
    explanation = "Multi-horizon momentum supports the candidate." if alignment > 0.15 else (
        "Multi-horizon momentum opposes the candidate." if alignment < -0.15 else
        "Momentum is mixed across horizons."
    )
    return _factor(
        "momentum",
        alignment,
        1.0,
        explanation,
        raw={"momentum_5d": m5, "momentum_20d": m20, "momentum_60d": m60},
    )


def _macd(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    price = max(1e-9, finite(ind.get("price"), 1.0))
    line = finite(ind.get("macd_line"))
    signal = finite(ind.get("macd_signal"))
    hist = finite(ind.get("macd_hist"))
    observed = 0.65 * _squash(hist / price * 100.0, 0.45) + 0.35 * _squash((line - signal) / price * 100.0, 0.35)
    cross = str(ind.get("macd_cross") or "").upper()
    if cross == "BULLISH":
        observed = clamp(observed + 0.20)
    elif cross == "BEARISH":
        observed = clamp(observed - 0.20)
    alignment = _signed(direction, observed)
    explanation = "MACD momentum supports the candidate." if alignment > 0.12 else (
        "MACD momentum conflicts with the candidate." if alignment < -0.12 else
        "MACD is neutral or close to its signal line."
    )
    return _factor(
        "macd",
        alignment,
        0.9,
        explanation,
        raw={"macd_line": line, "macd_signal": signal, "macd_hist": hist, "macd_cross": cross},
    )


def _vwap(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    price = finite(ind.get("price"))
    vwap = finite(ind.get("vwap_20d") or ind.get("vwap"))
    distance = _pct_distance(price, vwap)
    observed = _squash(distance, 2.0)
    alignment = _signed(direction, observed)
    explanation = "Price location relative to VWAP supports the candidate." if alignment > 0.12 else (
        "Price is on the wrong side of VWAP for the candidate." if alignment < -0.12 else
        "Price is close to VWAP; control is not clear."
    )
    return _factor(
        "vwap",
        alignment,
        1.0 if vwap > 0 else 0.0,
        explanation,
        raw={"vwap": vwap, "pct_from_vwap": round(distance, 4)},
    )


def _relative_volume(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    rvol = max(0.0, finite(ind.get("rvol_20d"), finite(ind.get("vol_ratio"), 1.0)))
    day_change = finite(ind.get("day_change"))
    m5 = finite(ind.get("momentum_5d"))
    observed_direction = _squash(0.65 * day_change + 0.35 * m5, 4.0)
    participation = clamp((rvol - 0.55) / 1.45, 0.0, 1.0)
    alignment = _signed(direction, observed_direction)
    explanation = (
        "Elevated relative volume confirms movement in the candidate direction."
        if alignment > 0.12 and participation >= 0.35
        else "Elevated relative volume confirms movement against the candidate."
        if alignment < -0.12 and participation >= 0.35
        else "Relative volume is low or directionally inconclusive."
    )
    return _factor(
        "relative_volume",
        alignment,
        participation,
        explanation,
        raw={"rvol": rvol, "day_change": day_change, "momentum_5d": m5},
    )


def _stochastic(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    k = finite(ind.get("stoch_k"), 50.0)
    d = finite(ind.get("stoch_d"), 50.0)
    observed = _squash(k - d, 18.0)
    # Extremes are timing cautions, not automatic reversals.
    if k >= 90 and observed > 0:
        observed *= 0.45
    elif k <= 10 and observed < 0:
        observed *= 0.45
    alignment = _signed(direction, observed)
    explanation = "Stochastic timing supports the candidate." if alignment > 0.15 else (
        "Stochastic timing opposes the candidate." if alignment < -0.15 else
        "Stochastic is neutral or at an extreme where standalone signals are unreliable."
    )
    return _factor(
        "stochastic",
        alignment,
        0.75,
        explanation,
        raw={"stoch_k": k, "stoch_d": d, "stoch_signal": ind.get("stoch_signal")},
    )


def _price_levels(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    price = finite(ind.get("price"))
    pivot = finite(ind.get("pivot"))
    r1 = finite(ind.get("resist_1"))
    r2 = finite(ind.get("resist_2"))
    s1 = finite(ind.get("support_1"))
    s2 = finite(ind.get("support_2"))
    rvol = finite(ind.get("rvol_20d"), finite(ind.get("vol_ratio"), 1.0))

    observed = 0.0
    available = 0.0
    if pivot > 0:
        observed += 0.55 * _squash(_pct_distance(price, pivot), 1.5)
        available += 0.55
    if min(r1, s1) > 0:
        if price > r1:
            observed += 0.30 * (0.8 if rvol >= 1.0 else 0.45)
        elif price < s1:
            observed -= 0.30 * (0.8 if rvol >= 1.0 else 0.45)
        else:
            room_up = (r1 - price) / max(price, 1e-9) * 100.0
            room_down = (price - s1) / max(price, 1e-9) * 100.0
            observed += 0.30 * clamp((room_up - room_down) / max(1.0, room_up + room_down))
        available += 0.30
    if min(r2, s2) > 0:
        observed += 0.15 * clamp((_pct_distance(price, (r2 + s2) / 2.0)) / 5.0)
        available += 0.15
    if available:
        observed /= available
    alignment = _signed(direction, observed)
    explanation = "Pivot/support/resistance location supports the candidate." if alignment > 0.12 else (
        "Nearby pivot/support/resistance location works against the candidate." if alignment < -0.12 else
        "Price is balanced between nearby support and resistance."
    )
    return _factor(
        "price_levels",
        alignment,
        min(1.0, available),
        explanation,
        raw={"price": price, "pivot": pivot, "r1": r1, "r2": r2, "s1": s1, "s2": s2},
    )


def _rsi_context(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    rsi = finite(ind.get("rsi14"), 50.0)
    observed = _squash(rsi - 50.0, 18.0)
    # Reduce the directional contribution at chase-risk extremes.
    if rsi > 78:
        observed = min(observed, 0.25)
    elif rsi < 22:
        observed = max(observed, -0.25)
    alignment = _signed(direction, observed)
    explanation = "RSI context supports the candidate without being extreme." if alignment > 0.12 else (
        "RSI context conflicts with the candidate or indicates chase risk." if alignment < -0.12 else
        "RSI is neutral or extreme enough to receive limited weight."
    )
    return _factor("rsi_context", alignment, 0.8, explanation, raw={"rsi14": rsi})


def _pattern_confirmation(
    direction: str,
    pattern_direction: str | None,
    pattern_confidence: float | None,
) -> dict[str, Any]:
    candidate = canonical_direction(direction)
    pattern = canonical_direction(pattern_direction)
    confidence = clamp(finite(pattern_confidence) / 100.0, 0.0, 1.0)
    if pattern == "NEUTRAL":
        alignment = 0.0
        confidence *= 0.25
    else:
        alignment = 1.0 if pattern == candidate else -1.0
    explanation = "Top pattern confirms the candidate." if alignment > 0 else (
        "Top pattern conflicts with the candidate." if alignment < 0 else
        "No reliable directional pattern confirmation."
    )
    return _factor(
        "pattern_confirmation",
        alignment,
        confidence,
        explanation,
        raw={"pattern_direction": pattern_direction, "pattern_confidence": pattern_confidence},
    )


def _atr_penalty(ind: dict[str, Any], direction: str) -> dict[str, Any]:
    atr_pct = max(0.0, finite(ind.get("atr_pct")))
    percentile = clamp(finite(ind.get("atr_percentile_252"), 50.0) / 100.0, 0.0, 1.0)
    penalty = 0.0
    if atr_pct > 8.0:
        penalty += 13.0
    elif atr_pct > 6.0:
        penalty += 9.0
    elif atr_pct > 4.0:
        penalty += 5.0
    elif atr_pct > 2.5:
        penalty += 2.0
    if percentile >= 0.90:
        penalty += 3.0
    elif percentile >= 0.80:
        penalty += 1.5
    return {
        "name": "atr_risk",
        "directional": False,
        "penalty": round(min(16.0, penalty), 4),
        "explanation": "ATR changes risk and sizing, not trade direction.",
        "raw": {"atr_pct": atr_pct, "atr_percentile_252": round(percentile * 100.0, 2)},
    }


def directional_alignment(
    indicators: dict[str, Any] | None,
    direction: str,
    *,
    pattern_direction: str | None = None,
    pattern_confidence: float | None = None,
) -> dict[str, Any]:
    ind = dict(indicators or {})
    side = canonical_direction(direction)
    if side == "NEUTRAL":
        return {
            "score": 0.0,
            "direction": "NEUTRAL",
            "weighted_alignment": 0.0,
            "factor_breakdown": [],
            "risk": _atr_penalty(ind, side),
            "evidence": [],
            "warnings": ["Candidate has no directional side."],
        }

    factors = [
        _trend_structure(ind, side),
        _trend_strength(ind, side),
        _momentum(ind, side),
        _macd(ind, side),
        _vwap(ind, side),
        _relative_volume(ind, side),
        _stochastic(ind, side),
        _price_levels(ind, side),
        _rsi_context(ind, side),
        _pattern_confirmation(side, pattern_direction, pattern_confidence),
    ]
    total_weight = sum(FACTOR_WEIGHTS.values())
    contribution = sum(factor["contribution"] for factor in factors)
    weighted_alignment = contribution / max(1e-9, total_weight)
    evidence_score = 50.0 + weighted_alignment * 50.0
    risk = _atr_penalty(ind, side)
    evidence_score -= finite(risk.get("penalty"))
    evidence_score = max(0.0, min(100.0, evidence_score))

    positives = [factor for factor in factors if factor["alignment"] * factor["confidence"] >= 0.12]
    negatives = [factor for factor in factors if factor["alignment"] * factor["confidence"] <= -0.12]
    return {
        "score": round(evidence_score, 2),
        "direction": side,
        "weighted_alignment": round(weighted_alignment, 5),
        "factor_breakdown": factors,
        "risk": risk,
        "positive_factor_count": len(positives),
        "negative_factor_count": len(negatives),
        "evidence": [factor["explanation"] for factor in positives],
        "warnings": [factor["explanation"] for factor in negatives] + ([risk["explanation"]] if risk["penalty"] else []),
        "symmetry": {
            "ticker_identity_used": False,
            "long_short_formula_shared": True,
            "risk_separate_from_direction": True,
        },
    }


def v8_candidate_score(
    base_score: float,
    indicators: dict[str, Any] | None,
    direction: str,
    *,
    pattern_direction: str | None = None,
    pattern_confidence: float | None = None,
) -> dict[str, Any]:
    """Blend the V7-derived setup score with the new evidence model.

    The candidate setup contributes 35%; analytics evidence contributes 65%.
    A candidate must also have enough independent positive factors to avoid a
    high score from one duplicated family of indicators.
    """
    alignment = directional_alignment(
        indicators,
        direction,
        pattern_direction=pattern_direction,
        pattern_confidence=pattern_confidence,
    )
    base = clamp(finite(base_score), 0.0, 100.0)
    evidence = finite(alignment.get("score"), 50.0)
    blended = base * 0.35 + evidence * 0.65

    if alignment.get("positive_factor_count", 0) < 3:
        blended = min(blended, 64.0)
    if alignment.get("weighted_alignment", 0.0) < 0.10:
        blended = min(blended, 60.0)
    if alignment.get("negative_factor_count", 0) >= 5:
        blended -= 8.0

    return {
        "score": round(max(0.0, min(100.0, blended)), 2),
        "alignment": alignment,
        "version": V8_VERSION,
    }
