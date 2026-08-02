from __future__ import annotations

import os

from fastapi.testclient import TestClient

from backend.main import app
from backend.routes.alpaca import PROHIBITED_PUBLIC_KEYS, _sanitize


def test_recursive_public_sanitizer_removes_raw_market_data():
    payload = {
        "ticker": "AAPL",
        "price": 200,
        "price_history": [{"time": "x", "close": 1}],
        "nested": {
            "bars": [{"o": 1}],
            "provider_response": {"secret": "raw"},
            "analysis": {"quality_score": 88},
        },
    }
    clean = _sanitize(payload)
    assert clean["ticker"] == "AAPL"
    assert clean["nested"]["analysis"]["quality_score"] == 88
    assert "price_history" not in clean
    assert "bars" not in clean["nested"]
    assert "provider_response" not in clean["nested"]


def test_prohibited_keys_cover_known_chart_aliases():
    for key in {
        "ohlcv",
        "candles",
        "bars",
        "history",
        "price_history",
        "mini_history",
        "chart_data",
        "volume_history",
        "timestamps",
        "provider_response",
    }:
        assert key in PROHIBITED_PUBLIC_KEYS


def test_public_app_does_not_mount_legacy_analysis_by_default(monkeypatch):
    monkeypatch.delenv("ORYNTRA_PRIVATE_RESEARCH_ROUTES", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/analysis/scan", json={"ticker": "AAPL"})
        assert response.status_code == 404


def test_alpaca_config_never_returns_secret(monkeypatch):
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("ALPACA_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("ALPACA_OAUTH_REDIRECT_URI", "https://example.test/api/alpaca/callback")
    monkeypatch.setenv("ORYNTRA_TOKEN_ENCRYPTION_KEY", "missing-on-purpose")
    with TestClient(app) as client:
        response = client.get("/api/alpaca/config")
        assert response.status_code == 200
        text = response.text
        assert "client-secret" not in text
        assert "ALPACA_OAUTH_CLIENT_SECRET" not in text
