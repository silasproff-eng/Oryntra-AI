from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import backend.database as database
import backend.routes.backtest as backtest_routes
from backend.main import app


def _bars(count=222):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "timestamp": (start + timedelta(days=index)).isoformat(),
            "open": 100 + index * 0.1,
            "high": 101 + index * 0.1,
            "low": 99 + index * 0.1,
            "close": 100.5 + index * 0.1,
            "volume": 1_000_000 + index,
        }
        for index in range(count)
    ]


def test_browser_backtest_route_is_authenticated_and_receives_bars_without_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "backtest.db"))

    async def fake_run(request, histories, source):
        assert request.ticker == "AAPL"
        assert source == "browser_polygon"
        assert len(histories["AAPL"]) == 222
        return {"status": "done", "ticker": "AAPL", "trades": [], "stats": {}}

    monkeypatch.setattr(backtest_routes, "run_backtest_from_histories", fake_run)
    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={"email": "backtest@example.com", "password": "strong-password", "accept_legal": True},
        )
        response = client.post(
            "/api/backtest/run-upload",
            headers={"Authorization": f"Bearer {signup.json()['token']}"},
            json={"ticker": "AAPL", "period": "1y", "provider": "polygon", "bars": _bars()},
        )

    assert response.status_code == 200, response.text
    assert response.json()["data_source"] == "browser_direct"
    assert response.json()["raw_market_data_persisted"] is False


def test_public_backtest_route_is_mounted():
    paths = {route.path for route in app.routes}
    assert "/api/backtest/run-upload" in paths
