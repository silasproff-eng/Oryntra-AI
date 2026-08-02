"""Alpaca Connect OAuth and user-authorized market-data client.

The client secret and OAuth access tokens never leave the backend. Public API
responses must be built from derived analysis only; raw bars remain in memory
for the duration of a scan and are never returned or persisted by this module.
"""
from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import pandas as pd
from cryptography.fernet import Fernet, InvalidToken

ALPACA_AUTHORIZE_URL = "https://app.alpaca.markets/oauth/authorize"
ALPACA_TOKEN_URL = "https://api.alpaca.markets/oauth/token"
ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_LIVE_TRADING_URL = "https://api.alpaca.markets"
ALPACA_PAPER_TRADING_URL = "https://paper-api.alpaca.markets"


class AlpacaConfigurationError(RuntimeError):
    pass


class AlpacaAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def client_id() -> str:
    return _env("ALPACA_OAUTH_CLIENT_ID")


def client_secret() -> str:
    return _env("ALPACA_OAUTH_CLIENT_SECRET")


def redirect_uri() -> str:
    configured = _env("ALPACA_OAUTH_REDIRECT_URI")
    if configured:
        return configured
    base = _env("PUBLIC_API_BASE_URL", _env("PUBLIC_BASE_URL")).rstrip("/")
    return f"{base}/api/alpaca/callback" if base else ""


def data_feed() -> str:
    value = _env("ALPACA_DATA_FEED", "iex").lower()
    return value if value in {"iex", "sip", "delayed_sip", "boats", "overnight", "otc"} else "iex"


def config_status() -> dict[str, Any]:
    return {
        "client_id": bool(client_id()),
        "client_secret": bool(client_secret()),
        "redirect_uri": redirect_uri(),
        "token_encryption_key": bool(_env("ORYNTRA_TOKEN_ENCRYPTION_KEY")),
        "data_feed": data_feed(),
        "ready": bool(client_id() and client_secret() and redirect_uri() and _env("ORYNTRA_TOKEN_ENCRYPTION_KEY")),
    }


def require_configured() -> None:
    status = config_status()
    missing = [name for name in ("client_id", "client_secret", "redirect_uri", "token_encryption_key") if not status[name]]
    if missing:
        raise AlpacaConfigurationError(
            "Alpaca Connect is not configured. Missing: " + ", ".join(missing)
        )


def generate_fernet_key() -> str:
    return Fernet.generate_key().decode("ascii")


def _fernet() -> Fernet:
    raw = _env("ORYNTRA_TOKEN_ENCRYPTION_KEY")
    if not raw:
        raise AlpacaConfigurationError("ORYNTRA_TOKEN_ENCRYPTION_KEY is required.")
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise AlpacaConfigurationError(
            "ORYNTRA_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(encrypted_token: str) -> str:
    try:
        return _fernet().decrypt(encrypted_token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise AlpacaConfigurationError(
            "Stored Alpaca token cannot be decrypted with the configured key."
        ) from exc


def state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def build_authorization_url(*, state: str, environment: str) -> str:
    require_configured()
    env = normalize_environment(environment)
    params = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "state": state,
        "scope": "data",
        "env": env,
    }
    return f"{ALPACA_AUTHORIZE_URL}?{urlencode(params)}"


def normalize_environment(value: str) -> str:
    env = (value or "paper").strip().lower()
    if env not in {"paper", "live"}:
        raise ValueError("environment must be paper or live")
    return env


def trading_base_url(environment: str) -> str:
    return ALPACA_PAPER_TRADING_URL if normalize_environment(environment) == "paper" else ALPACA_LIVE_TRADING_URL


async def _request_json(
    method: str,
    url: str,
    *,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "OryntraAI/0.7.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.request(method, url, headers=headers, params=params, data=data)
    try:
        payload = response.json()
    except Exception:
        payload = {"message": response.text[:500]}
    if response.status_code < 200 or response.status_code >= 300:
        message = payload.get("message") or payload.get("error") or payload.get("detail") or f"Alpaca request failed ({response.status_code})."
        raise AlpacaAPIError(str(message), status_code=response.status_code)
    if not isinstance(payload, dict):
        raise AlpacaAPIError("Alpaca returned an unexpected response.")
    return payload


async def exchange_authorization_code(code: str) -> dict[str, Any]:
    require_configured()
    return await _request_json(
        "POST",
        ALPACA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "redirect_uri": redirect_uri(),
        },
    )


async def get_account(token: str, environment: str) -> dict[str, Any]:
    return await _request_json(
        "GET", f"{trading_base_url(environment)}/v2/account", token=token
    )


async def get_asset(token: str, environment: str, symbol: str) -> dict[str, Any]:
    return await _request_json(
        "GET",
        f"{trading_base_url(environment)}/v2/assets/{symbol.upper()}",
        token=token,
    )


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    days = {
        "1mo": 50,
        "6mo": 230,
        "1y": 390,
        "5y": 1900,
        "all": 3650,
        "5m": 390,
    }.get(period, 230)
    return now - timedelta(days=days)


async def get_daily_bars(token: str, symbol: str, period: str) -> pd.DataFrame:
    symbol = symbol.upper().strip()
    start = _period_start(period)
    end = datetime.now(timezone.utc)
    payload = await _request_json(
        "GET",
        f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars",
        token=token,
        params={
            "timeframe": "1Day",
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "adjustment": "all",
            "feed": data_feed(),
            "sort": "asc",
            "limit": 10000,
        },
        timeout=45,
    )
    bars = payload.get("bars") or []
    if not isinstance(bars, list) or len(bars) < 20:
        raise AlpacaAPIError(
            f"Alpaca returned only {len(bars) if isinstance(bars, list) else 0} daily bars for {symbol}; at least 20 are required."
        )
    rows: list[dict[str, Any]] = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        try:
            rows.append(
                {
                    "timestamp": pd.to_datetime(bar["t"], utc=True),
                    "Open": float(bar["o"]),
                    "High": float(bar["h"]),
                    "Low": float(bar["l"]),
                    "Close": float(bar["c"]),
                    "Volume": float(bar.get("v") or 0),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    if len(rows) < 20:
        raise AlpacaAPIError(f"Alpaca returned insufficient usable history for {symbol}.")
    frame = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return frame


async def get_latest_bars(token: str, symbols: list[str]) -> dict[str, float]:
    clean = sorted({s.upper().strip() for s in symbols if s and s.strip()})
    if not clean:
        return {}
    payload = await _request_json(
        "GET",
        f"{ALPACA_DATA_URL}/v2/stocks/bars/latest",
        token=token,
        params={"symbols": ",".join(clean), "feed": data_feed()},
        timeout=30,
    )
    raw = payload.get("bars") or {}
    result: dict[str, float] = {}
    if isinstance(raw, dict):
        for symbol, bar in raw.items():
            if isinstance(bar, dict) and bar.get("c") is not None:
                try:
                    result[str(symbol).upper()] = float(bar["c"])
                except (TypeError, ValueError):
                    pass
    return result


def tradingview_symbol(symbol: str, exchange: str | None) -> str:
    clean_symbol = symbol.upper().strip().replace("-", "")
    clean_exchange = (exchange or "").upper().strip()
    aliases = {
        "NASDAQ": "NASDAQ",
        "NYSE": "NYSE",
        "AMEX": "AMEX",
        "ARCA": "AMEX",
        "NYSEARCA": "AMEX",
        "BATS": "CBOE",
        "OTC": "OTC",
    }
    prefix = aliases.get(clean_exchange)
    return f"{prefix}:{clean_symbol}" if prefix else clean_symbol
