from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import backend.database as database
import backend.routes.intelligence as intelligence
from backend.main import app


def test_authenticated_owner_scan_returns_only_derived_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "route.db"))
    monkeypatch.setenv("ORYNTRA_MARKET_DATA_LICENSE_MODE", "personal_research")
    monkeypatch.setenv("ORYNTRA_OWNER_EMAILS", "owner@example.com")
    monkeypatch.setenv("ORYNTRA_DAILY_ANALYSIS_LIMIT", "100")

    async def fake_scan(_request, **_kwargs):
        return {
            "ticker": "AAPL",
            "price": 200.0,
            "open": 198.0,
            "high": 202.0,
            "low": 197.0,
            "close": 200.0,
            "volume": {"current": 10, "avg_20d": 8, "ratio": 1.25, "trend": "INCREASING"},
            "price_history": [{"open": 1, "high": 2, "low": 0, "close": 1.5}],
            "rsi14": 55.0,
            "ema9": 199.5,
            "levels": {"support": 195.0, "resistance": 205.0},
            "patterns": {"recent": [{"name": "Bull flag", "timestamp": "2026-08-01", "confidence": 78}]},
            "trade_plan": {"direction": "LONG", "entry_ideal": 200.0, "stop": 196.0, "target": 208.0, "quality_score": 80},
        }

    monkeypatch.setattr(intelligence, "_run_scan_pipeline", fake_scan)

    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": "owner@example.com",
                "password": "strong-password",
                "display_name": "Owner",
                "accept_legal": True,
            },
        )
        assert signup.status_code == 200, signup.text
        token = signup.json()["token"]
        response = client.post(
            "/api/intelligence/scan",
            headers={"Authorization": f"Bearer {token}"},
            json={"ticker": "AAPL", "period": "6mo"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["rsi14"] == 55.0
        assert payload["trade_plan"]["entry_ideal"] == 200.0
        assert payload["patterns"]["recent"][0]["timestamp"] == "2026-08-01"
        assert payload["data_policy"]["market_history_included"] is False
        text = response.text.lower()
        for forbidden in ("price_history", '"open"', '"high"', '"low"', '"close"'):
            assert forbidden not in text


def test_legacy_public_analysis_route_is_not_mounted():
    with TestClient(app) as client:
        response = client.post("/api/analysis/scan", json={"ticker": "AAPL"})
        assert response.status_code == 404


def test_browser_uploaded_bars_are_processed_without_raw_response_or_persistence(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "route.db"))
    monkeypatch.setenv("ORYNTRA_MARKET_DATA_LICENSE_MODE", "personal_research")
    monkeypatch.setenv("ORYNTRA_OWNER_EMAILS", "owner@example.com")

    async def fake_uploaded(_request, bars, provider):
        assert provider == "polygon"
        assert len(bars) == 320
        return {
            "ticker": "AAPL", "rsi14": 52.0, "ema9": 201.0, "ma20": 198.0,
            "patterns": {"recent": []}, "trade_plan": {"quality_score": 74},
            "volume": {"ratio": 1.1, "trend": "STABLE"},
        }

    monkeypatch.setattr(intelligence, "_run_uploaded_scan_pipeline", fake_uploaded)
    bars = [{"timestamp": f"2025-01-{(index % 28) + 1:02d}T00:00:00Z", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000} for index in range(320)]
    # The route validates timestamps in the implementation; use distinct years here for the mocked route's payload contract.
    bars = [{**bar, "timestamp": f"{2025 + index // 365}-01-{(index % 28) + 1:02d}T00:00:00Z"} for index, bar in enumerate(bars)]
    with TestClient(app) as client:
        signup = client.post("/api/auth/signup", json={"email": "owner@example.com", "password": "strong-password", "accept_legal": True})
        response = client.post("/api/intelligence/scan-upload", headers={"Authorization": f"Bearer {signup.json()['token']}"}, json={"ticker": "AAPL", "period": "6mo", "provider": "polygon", "bars": bars})
    assert response.status_code == 200, response.text
    assert "\"open\"" not in response.text.lower()
    assert response.json()["data_policy"]["market_history_included"] is False


def test_browser_uploaded_bars_run_the_real_pipeline_and_clean_nonfinite_values(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "direct.db"))
    monkeypatch.setenv("ORYNTRA_BROWSER_DIRECT_ANALYSIS_ENABLED", "true")
    monkeypatch.setenv("ORYNTRA_MARKET_DATA_LICENSE_MODE", "personal_research")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for index in range(330):
        base = 100 + index * .12
        bars.append({"timestamp": (start + timedelta(days=index)).isoformat(), "open": base, "high": base + 1.4, "low": base - 1.1, "close": base + .4, "volume": 1_000_000 + index})
    with TestClient(app) as client:
        signup = client.post("/api/auth/signup", json={"email": "direct@example.com", "password": "strong-password", "accept_legal": True})
        response = client.post("/api/intelligence/scan-upload", headers={"Authorization": f"Bearer {signup.json()['token']}"}, json={"ticker": "AAPL", "period": "6mo", "provider": "polygon", "bars": bars})
    assert response.status_code == 200, response.text
    assert response.json()["ticker"] == "AAPL"
    assert response.json()["data_policy"]["market_history_included"] is False
    assert "NaN" not in response.text
