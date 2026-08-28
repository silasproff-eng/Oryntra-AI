from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request

from .database import get_connection
from .routes.auth import require_current_user


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str) -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    }


def license_mode() -> str:
    value = os.getenv("ORYNTRA_MARKET_DATA_LICENSE_MODE", "personal_research").strip().lower()
    return value if value in {"personal_research", "business_approved"} else "personal_research"


def daily_limit() -> int:
    return max(1, min(int(os.getenv("ORYNTRA_DAILY_ANALYSIS_LIMIT", "100")), 10000))


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def is_owner(user: dict[str, Any]) -> bool:
    owners = _csv("ORYNTRA_OWNER_EMAILS")
    return bool(user.get("email") and user["email"].lower() in owners)


def policy_status(user: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = license_mode()
    owner = bool(user and is_owner(user))
    public_enabled = env_bool("ORYNTRA_PUBLIC_DERIVED_ANALYSIS_ENABLED", False)
    browser_direct_enabled = env_bool("ORYNTRA_BROWSER_DIRECT_ANALYSIS_ENABLED", False)
    subscriptions_enforced = env_bool("ORYNTRA_SUBSCRIPTIONS_ENFORCED", False)
    permitted = owner or browser_direct_enabled or (mode == "business_approved" and public_enabled)
    return {
        "license_mode": mode,
        "owner_access": owner,
        "public_derived_analysis_enabled": public_enabled,
        "browser_direct_analysis_enabled": browser_direct_enabled,
        "user_provider_keys_required": False,
        "subscriptions_enforced": subscriptions_enforced,
        "analysis_permitted": permitted,
        "daily_limit": daily_limit(),
        "plan": {
            "code": "pro",
            "name": "Oryntra AI Pro",
            "display_price_usd": float(os.getenv("ORYNTRA_PLAN_DISPLAY_PRICE_USD", "3.00")),
            "billing_status": "configuration_only",
        },
        "market_history_included": False,
        "ohlcv_arrays_included": False,
        "chart_provider": "TradingView",
    }


def require_analysis_user(request: Request) -> dict[str, Any]:
    user = require_current_user(request)
    status = policy_status(user)

    if not status["analysis_permitted"]:
        if status["license_mode"] == "personal_research":
            raise HTTPException(
                status_code=451,
                detail={
                    "code": "MARKET_DATA_LICENSE_REQUIRED",
                    "message": (
                        "This server is configured for the account owner's personal research only. "
                        "Public or paid end-user analysis requires a written business market-data agreement."
                    ),
                },
            )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PUBLIC_ANALYSIS_DISABLED",
                "message": "Public derived analysis is disabled until the approved market-data agreement is activated.",
            },
        )

    if (
        status["subscriptions_enforced"]
        and not status["owner_access"]
        and not user.get("subscription")
    ):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "An active Oryntra AI Pro subscription is required for analysis.",
            },
        )
    return user


def usage_status(user_id: int) -> dict[str, Any]:
    today = _today_utc()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT request_count FROM analysis_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        used = int(row["request_count"] if row else 0)
    finally:
        conn.close()
    limit = daily_limit()
    return {
        "date_utc": today,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "resets_at": f"{today}T23:59:59Z",
    }


def reserve_quota(user_id: int, cost: int = 1) -> dict[str, Any]:
    clean_cost = max(1, int(cost))
    today = _today_utc()
    limit = daily_limit()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT request_count FROM analysis_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        used = int(row["request_count"] if row else 0)
        if used + clean_cost > limit:
            conn.rollback()
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "DAILY_ANALYSIS_LIMIT_REACHED",
                    "message": f"Daily analysis limit reached ({limit} ticker requests per UTC day).",
                    "used": used,
                    "limit": limit,
                    "remaining": max(0, limit - used),
                },
            )
        if row:
            conn.execute(
                """UPDATE analysis_usage
                   SET request_count=request_count+?, updated_at=datetime('now')
                   WHERE user_id=? AND usage_date=?""",
                (clean_cost, user_id, today),
            )
        else:
            conn.execute(
                """INSERT INTO analysis_usage
                   (user_id, usage_date, request_count, updated_at)
                   VALUES (?, ?, ?, datetime('now'))""",
                (user_id, today, clean_cost),
            )
        conn.commit()
    finally:
        conn.close()
    return usage_status(user_id)


def refund_quota(user_id: int, cost: int = 1) -> dict[str, Any]:
    clean_cost = max(1, int(cost))
    today = _today_utc()
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """UPDATE analysis_usage
               SET request_count=MAX(0, request_count-?), updated_at=datetime('now')
               WHERE user_id=? AND usage_date=?""",
            (clean_cost, user_id, today),
        )
        conn.commit()
    finally:
        conn.close()
    return usage_status(user_id)
