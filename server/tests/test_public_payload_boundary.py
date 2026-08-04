from __future__ import annotations

from backend.public_payload import assert_no_raw_market_data, public_analysis_payload


def test_public_payload_removes_raw_market_data_and_keeps_derived_analysis():
    raw = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "price": 201.25,
        "open": 199.0,
        "high": 203.0,
        "low": 198.0,
        "close": 201.25,
        "volume": {"current": 50_000_000, "avg_20d": 40_000_000, "ratio": 1.25, "trend": "INCREASING"},
        "price_history": [{"timestamp": "2026-08-03", "open": 1, "high": 2, "low": 0, "close": 1.5}],
        "provider_response": {"results": [{"o": 1, "h": 2, "l": 0, "c": 1.5}]},
        "rsi14": 58.2,
        "ema9": 200.4,
        "ma20": 198.8,
        "vwap_20d": 199.7,
        "above_vwap": True,
        "volume_price_divergence": "NONE",
        "levels": {"support": 196.5, "resistance": 205.2},
        "patterns": {
            "recent": [
                {
                    "name": "Liquidity sweep",
                    "bias": "BULLISH",
                    "confidence": 81,
                    "timestamp": "2026-08-01",
                    "zone_low": 197.2,
                    "zone_high": 198.4,
                    "raw_bars": [{"open": 1}],
                }
            ]
        },
        "trade_plan": {
            "direction": "LONG",
            "entry_ideal": 200.0,
            "stop": 196.0,
            "target": 208.0,
            "quality_score": 84,
        },
    }
    payload = public_analysis_payload(
        raw,
        quota={"used": 1, "limit": 100, "remaining": 99},
        policy={"license_mode": "personal_research", "public_derived_analysis_enabled": False},
    )
    assert payload["rsi14"] == 58.2
    assert payload["ema9"] == 200.4
    assert payload["patterns"]["recent"][0]["timestamp"] == "2026-08-01"
    assert payload["trade_plan"]["entry_ideal"] == 200.0
    assert payload["volume_context"]["relative_ratio"] == 1.25
    assert payload["data_policy"]["ohlcv_arrays_included"] is False
    text = repr(payload).lower()
    for forbidden in ("price_history", "provider_response", "'open'", "'high'", "'low'", "'close'", "raw_bars"):
        assert forbidden not in text
    assert_no_raw_market_data(payload)

