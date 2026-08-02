"""Alpaca Connect routes for the Oryntra mobile application."""
from __future__ import annotations

import copy
import html
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

from ..alpaca_client import (
    AlpacaAPIError,
    AlpacaConfigurationError,
    build_authorization_url,
    config_status,
    decrypt_token,
    encrypt_token,
    exchange_authorization_code,
    get_account,
    get_asset,
    get_daily_bars,
    normalize_environment,
    state_hash,
    tradingview_symbol,
)
from ..database import get_connection, increment_app_counter
from .analysis import _build_result, _compute_scan_artifacts, _period_to_timeframe
from .auth import require_current_user

router = APIRouter()

PROHIBITED_PUBLIC_KEYS = {
    "bars",
    "candles",
    "ohlcv",
    "history",
    "price_history",
    "mini_history",
    "chart_data",
    "volume_history",
    "timestamps",
    "raw_data",
    "provider_response",
}


class ConnectStartRequest(BaseModel):
    environment: str = "paper"

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        return normalize_environment(value)


class AlpacaScanRequest(BaseModel):
    ticker: str
    period: str = "6mo"
    environment: str | None = None

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, value: str) -> str:
        clean = (value or "").upper().strip()
        if not clean or len(clean) > 15 or not all(ch.isalnum() or ch in {".", "-"} for ch in clean):
            raise ValueError("Enter a valid ticker symbol.")
        return clean

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        if value not in {"1mo", "6mo", "1y", "5y", "all"}:
            raise ValueError("period must be 1mo, 6mo, 1y, 5y, or all")
        return value

    @field_validator("environment")
    @classmethod
    def validate_optional_environment(cls, value: str | None) -> str | None:
        return normalize_environment(value) if value else None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in PROHIBITED_PUBLIC_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _connection_rows(user_id: int) -> list[dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT environment, account_id, account_status, scope, status,
                   connected_at, updated_at, last_validated_at, last_error
            FROM alpaca_connections
            WHERE user_id=?
            ORDER BY CASE environment WHEN 'paper' THEN 0 ELSE 1 END
            """,
            (user_id,),
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            account_id = str(item.pop("account_id", "") or "")
            item["account_last4"] = account_id[-4:] if account_id else ""
            output.append(item)
        return output
    finally:
        conn.close()


def _connection(user_id: int, requested_environment: str | None = None):
    conn = get_connection()
    try:
        if requested_environment:
            row = conn.execute(
                "SELECT * FROM alpaca_connections WHERE user_id=? AND environment=? AND status='CONNECTED'",
                (user_id, requested_environment),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM alpaca_connections
                WHERE user_id=? AND status='CONNECTED'
                ORDER BY CASE environment WHEN 'paper' THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _mark_error(user_id: int, environment: str, message: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE alpaca_connections
               SET status='ERROR', last_error=?, updated_at=datetime('now')
             WHERE user_id=? AND environment=?
            """,
            (message[:500], user_id, environment),
        )
        conn.commit()
    finally:
        conn.close()


@router.get("/config")
async def alpaca_config():
    status = config_status()
    return {
        "provider": "alpaca_connect",
        "ready": status["ready"],
        "redirect_uri": status["redirect_uri"],
        "data_feed": status["data_feed"],
        "requested_scope": "data",
        "raw_market_data_returned": False,
    }


@router.post("/connect/start")
async def connect_start(req: ConnectStartRequest, request: Request):
    user = require_current_user(request)
    try:
        state = secrets.token_urlsafe(48)
        authorization_url = build_authorization_url(
            state=state, environment=req.environment
        )
    except (AlpacaConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    now = datetime.utcnow()
    expires = now + timedelta(minutes=15)
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM alpaca_oauth_states WHERE expires_at < datetime('now') OR consumed_at IS NOT NULL"
        )
        conn.execute(
            """
            INSERT INTO alpaca_oauth_states
                (state_hash, user_id, environment, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state_hash(state),
                user["id"],
                req.environment,
                now.strftime("%Y-%m-%d %H:%M:%S"),
                expires.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "authorization_url": authorization_url,
        "environment": req.environment,
        "expires_in_seconds": 900,
    }


def _callback_page(title: str, message: str, *, ok: bool, environment: str = "") -> HTMLResponse:
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    status = "success" if ok else "error"
    deep_link = f"oryntra://alpaca-connected?status={status}&env={html.escape(environment)}"
    accent = "#38cff3" if ok else "#fb7185"
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title><style>
html,body{{margin:0;min-height:100%;background:#02070d;color:#eef8ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
main{{max-width:560px;margin:0 auto;padding:64px 22px;text-align:center}}.card{{background:#071a2d;border:1px solid rgba(56,207,243,.24);border-radius:24px;padding:30px;box-shadow:0 24px 70px rgba(0,0,0,.45)}}
h1{{margin:0 0 12px;color:{accent}}}p{{line-height:1.6;color:#bfd0df}}a{{display:inline-block;margin-top:18px;padding:13px 18px;border-radius:14px;background:{accent};color:#001018;text-decoration:none;font-weight:800}}
</style></head><body><main><div class="card"><h1>{safe_title}</h1><p>{safe_message}</p><a href="{deep_link}">Return to Oryntra AI</a></div></main>
<script>setTimeout(function(){{window.location.href={deep_link!r};}},700);</script></body></html>"""
    return HTMLResponse(body, status_code=200 if ok else 400, headers={"Cache-Control": "no-store"})


@router.get("/callback", include_in_schema=False)
async def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        return _callback_page(
            "Connection not completed",
            error_description or error,
            ok=False,
        )
    if not code or not state:
        return _callback_page(
            "Invalid callback",
            "The Alpaca authorization response was incomplete.",
            ok=False,
        )

    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM alpaca_oauth_states
            WHERE state_hash=? AND consumed_at IS NULL
              AND expires_at > datetime('now')
            """,
            (state_hash(state),),
        ).fetchone()
        if not row:
            return _callback_page(
                "Authorization expired",
                "Return to Oryntra AI and start the connection again.",
                ok=False,
            )
        state_row = dict(row)
        conn.execute(
            "UPDATE alpaca_oauth_states SET consumed_at=datetime('now') WHERE state_hash=?",
            (state_hash(state),),
        )
        conn.commit()
    finally:
        conn.close()

    environment = state_row["environment"]
    try:
        token_payload = await exchange_authorization_code(code)
        access_token = str(token_payload.get("access_token") or "")
        if not access_token:
            raise AlpacaAPIError("Alpaca did not return an access token.")
        account = await get_account(access_token, environment)
        encrypted = encrypt_token(access_token)
    except (AlpacaAPIError, AlpacaConfigurationError) as exc:
        return _callback_page(
            "Connection failed", str(exc), ok=False, environment=environment
        )

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO alpaca_connections
                (user_id, environment, encrypted_access_token, scope,
                 account_id, account_status, status, connected_at, updated_at,
                 last_validated_at, last_error)
            VALUES (?, ?, ?, ?, ?, ?, 'CONNECTED', datetime('now'), datetime('now'), datetime('now'), NULL)
            ON CONFLICT(user_id, environment) DO UPDATE SET
                encrypted_access_token=excluded.encrypted_access_token,
                scope=excluded.scope,
                account_id=excluded.account_id,
                account_status=excluded.account_status,
                status='CONNECTED',
                connected_at=datetime('now'),
                updated_at=datetime('now'),
                last_validated_at=datetime('now'),
                last_error=NULL
            """,
            (
                state_row["user_id"],
                environment,
                encrypted,
                str(token_payload.get("scope") or "data"),
                str(account.get("id") or account.get("account_number") or ""),
                str(account.get("status") or ""),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return _callback_page(
        "Alpaca connected",
        f"Your {environment} Alpaca account is connected. You can return to Oryntra AI.",
        ok=True,
        environment=environment,
    )


@router.get("/status")
async def connection_status(request: Request):
    user = require_current_user(request)
    rows = _connection_rows(user["id"])
    return {
        "connected": any(row.get("status") == "CONNECTED" for row in rows),
        "connections": rows,
        "preferred_environment": next(
            (row["environment"] for row in rows if row.get("status") == "CONNECTED"),
            None,
        ),
    }


@router.delete("/disconnect/{environment}")
async def disconnect(environment: str, request: Request):
    user = require_current_user(request)
    try:
        env = normalize_environment(environment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM alpaca_connections WHERE user_id=? AND environment=?",
            (user["id"], env),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "environment": env,
        "note": "The local connection was removed. The user may also revoke the app from Alpaca's dashboard.",
    }


@router.post("/scan")
async def alpaca_scan(req: AlpacaScanRequest, request: Request):
    user = require_current_user(request)
    connection = _connection(user["id"], req.environment)
    if not connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ALPACA_NOT_CONNECTED",
                "message": "Connect an Alpaca account from the Account tab before scanning.",
            },
        )
    environment = connection["environment"]
    try:
        token = decrypt_token(connection["encrypted_access_token"])
        bars = await get_daily_bars(token, req.ticker, req.period)
        asset = await get_asset(token, environment, req.ticker)
        analysis_hist, indicators, setup, pattern_report, plan = _compute_scan_artifacts(
            bars, req.ticker, "official"
        )
        result = _build_result(
            req.ticker,
            {
                "company_name": asset.get("name") or req.ticker,
                "exchange": asset.get("exchange") or "",
            },
            "user_authorized_alpaca",
            _period_to_timeframe(req.period),
            indicators,
            setup,
            plan,
            pattern_report,
            {"stored": False, "reason": "raw bars are not persisted for public-user scans"},
            analysis_hist,
        )
        result.pop("price_history", None)
        result["search_counter"] = increment_app_counter("stock_searches", 1)
        result["pattern_engine_mode"] = "official"
        result["alpaca_environment"] = environment
        result["chart"] = {
            "provider": "tradingview",
            "symbol": tradingview_symbol(req.ticker, asset.get("exchange")),
            "interval": "D",
        }
        result["data_policy"] = {
            "user_authorized_provider": "alpaca",
            "raw_bars_returned": False,
            "raw_bars_persisted": False,
            "chart_provider": "tradingview",
        }
        return _sanitize(copy.deepcopy(result))
    except AlpacaConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AlpacaAPIError as exc:
        if exc.status_code in {401, 403}:
            _mark_error(user["id"], environment, str(exc))
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "ALPACA_AUTH_REQUIRED",
                    "message": "Alpaca access is no longer valid. Reconnect the account from the Account tab.",
                },
            ) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Alpaca analysis failed: {type(exc).__name__}: {exc}",
        ) from exc
