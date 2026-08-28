from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..analysis_access import (
    policy_status,
    refund_quota,
    require_analysis_user,
    reserve_quota,
    usage_status,
)
from ..public_payload import assert_no_raw_market_data, public_analysis_payload
from ..provider_credentials import decrypted_credentials
from .analysis import ScanRequest, _run_scan_pipeline

router = APIRouter()


class IntelligenceScanRequest(BaseModel):
    ticker: str
    period: str = "6mo"

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned or len(cleaned) > 10:
            raise ValueError("Enter a valid ticker symbol.")
        if any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in cleaned):
            raise ValueError("Ticker contains unsupported characters.")
        return cleaned

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        if value not in {"5m", "1mo", "6mo", "1y", "5y", "all"}:
            raise ValueError("Unsupported analysis period.")
        return value


class IntelligenceMultiScanRequest(BaseModel):
    tickers: list[str]
    period: str = "6mo"

    @field_validator("tickers")
    @classmethod
    def clean_tickers(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for raw in values[:20]:
            ticker = IntelligenceScanRequest.clean_ticker(str(raw))
            if ticker not in output:
                output.append(ticker)
        if not output:
            raise ValueError("Provide at least one ticker.")
        return output

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        return IntelligenceScanRequest.valid_period(value)


def _require_user_provider_keys() -> bool:
    return os.getenv("ORYNTRA_REQUIRE_USER_PROVIDER_KEYS", "true").strip().lower() in {"1", "true", "yes", "on"}


async def _one_scan(ticker: str, period: str, quota: dict, policy: dict, user_id: int) -> dict:
    require_user_keys = _require_user_provider_keys()
    provider_keys = decrypted_credentials(user_id) if os.getenv("ORYNTRA_CREDENTIAL_ENCRYPTION_KEY", "").strip() else {}
    raw = await _run_scan_pipeline(
        ScanRequest(ticker=ticker, period=period, pattern_mode="official"),
        provider_api_keys=provider_keys,
        allow_platform_provider_keys=not require_user_keys,
    )
    payload = public_analysis_payload(raw, quota=quota, policy=policy)
    assert_no_raw_market_data(payload)
    return payload


@router.get("/status")
async def intelligence_status(request: Request):
    user = require_analysis_user(request)
    return {
        "service": "oryntra_market_intelligence",
        "status": "ready",
        "policy": policy_status(user),
        "quota": usage_status(user["id"]),
        "chart_provider": "TradingView",
    }


@router.get("/quota")
async def quota_status(request: Request):
    user = require_analysis_user(request)
    return usage_status(user["id"])


@router.post("/scan")
async def scan(req: IntelligenceScanRequest, request: Request):
    user = require_analysis_user(request)
    quota = reserve_quota(user["id"], 1)
    policy = policy_status(user)
    try:
        return await _one_scan(req.ticker, req.period, quota, policy, user["id"])
    except HTTPException:
        refund_quota(user["id"], 1)
        raise
    except Exception:
        refund_quota(user["id"], 1)
        raise


@router.post("/scan-multiple")
async def scan_multiple(req: IntelligenceMultiScanRequest, request: Request):
    user = require_analysis_user(request)
    cost = len(req.tickers)
    quota = reserve_quota(user["id"], cost)
    policy = policy_status(user)
    semaphore = asyncio.Semaphore(max(1, min(3, len(req.tickers))))

    async def run_one(ticker: str):
        async with semaphore:
            try:
                return ticker, await _one_scan(ticker, req.period, quota, policy, user["id"]), None
            except HTTPException as exc:
                return ticker, None, exc.detail
            except Exception as exc:
                return ticker, None, str(exc)

    rows = await asyncio.gather(*(run_one(ticker) for ticker in req.tickers))
    successful = [payload for _, payload, error in rows if payload is not None]
    failures = [{"ticker": ticker, "error": error} for ticker, payload, error in rows if error is not None]
    failed_count = len(failures)
    if failed_count:
        quota = refund_quota(user["id"], failed_count)
        for payload in successful:
            payload["quota"] = quota
    successful.sort(key=lambda item: item.get("trade_plan", {}).get("quality_score", 0) or 0, reverse=True)
    return {
        "results": successful,
        "errors": failures,
        "count": len(successful),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "quota": quota,
        "data_policy": {
            "market_history_included": False,
            "ohlcv_arrays_included": False,
            "chart_provider": "TradingView",
        },
    }
