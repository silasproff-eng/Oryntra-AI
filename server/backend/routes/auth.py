"""
Oryntra lightweight account/session routes.
No external auth dependencies: passwords use PBKDF2-HMAC-SHA256 with per-user salt.
This is suitable for beta/private testing. Add email verification, password reset,
rate limiting, HTTPS-only cookies, and Stripe before a real paid launch.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from ..database import get_connection, init_db

router = APIRouter()
SESSION_DAYS = 90
SESSION_COOKIE_NAME = "oryntra_session"
SESSION_HINT_COOKIE_NAME = "oryntra_logged_in"
SESSION_MAX_AGE = SESSION_DAYS * 24 * 60 * 60



class SignupRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str):
        v = (v or "").lower().strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str):
        if len(v or "") < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str):
        v = (v or "").lower().strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Enter a valid email address.")
        return v


class SubscribeRequest(BaseModel):
    plan_code: str


class DeleteAccountRequest(BaseModel):
    password: str


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _expires_at() -> str:
    return (datetime.utcnow() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")

def _cookie_is_secure(request: Request) -> bool:
    """Use Secure cookies automatically behind HTTPS/Cloudflare, but allow localhost HTTP."""
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _set_session_cookies(response: Response, request: Request, token: str) -> None:
    secure = _cookie_is_secure(request)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=SESSION_HINT_COOKIE_NAME,
        value="1",
        max_age=SESSION_MAX_AGE,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response, request: Request) -> None:
    secure = _cookie_is_secure(request)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", secure=secure, samesite="lax")
    response.delete_cookie(key=SESSION_HINT_COOKIE_NAME, path="/", secure=secure, samesite="lax")


def _hash_password(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return salt.hex(), digest.hex()


def _verify_password(password: str, salt_hex: str, password_hash: str) -> bool:
    _, candidate = _hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, password_hash)


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "created_at": row["created_at"],
    }


def _active_subscription_for(conn, user_id: int) -> Optional[dict]:
    row = conn.execute(
        """
        SELECT * FROM subscriptions
         WHERE user_id=? AND status='ACTIVE'
         ORDER BY started_at DESC LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_auth_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return request.headers.get("x-oryntra-session") or request.cookies.get(SESSION_COOKIE_NAME)


def get_current_user_optional(request: Request) -> Optional[dict]:
    token = get_auth_token(request)
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT users.* FROM user_sessions
            JOIN users ON users.id = user_sessions.user_id
            WHERE user_sessions.token=?
              AND user_sessions.expires_at > datetime('now')
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        user = _public_user(row)
        user["subscription"] = _active_subscription_for(conn, user["id"])
        return user
    finally:
        conn.close()


def require_current_user(request: Request) -> dict:
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def require_active_subscription(request: Request) -> dict:
    user = require_current_user(request)
    if not user.get("subscription"):
        raise HTTPException(status_code=402, detail={"code": "SUBSCRIPTION_REQUIRED", "message": "Choose an Oryntra AI Pro plan to analyze tickers."})
    return user


@router.post("/signup")
async def signup(req: SignupRequest, request: Request, response: Response):
    init_db()
    email = req.email.lower().strip()
    display_name = (req.display_name or email.split("@", 1)[0])[:80]
    salt, password_hash = _hash_password(req.password)
    token = secrets.token_urlsafe(32)
    conn = get_connection()
    try:
        try:
            cur = conn.execute(
                """
                INSERT INTO users (email, display_name, password_salt, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (email, display_name, salt, password_hash),
            )
            user_id = cur.lastrowid
        except Exception:
            raise HTTPException(status_code=409, detail="An account already exists for that email.")
        conn.execute(
            "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, _expires_at()),
        )
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.commit()
        user = _public_user(row)
        user["subscription"] = None
        _set_session_cookies(response, request, token)
        return {"token": token, "user": user}
    finally:
        conn.close()


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    init_db()
    email = req.email.lower().strip()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not _verify_password(req.password, row["password_salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, row["id"], _expires_at()),
        )
        conn.execute("UPDATE users SET last_login_at=datetime('now') WHERE id=?", (row["id"],))
        conn.commit()
        user = _public_user(row)
        user["subscription"] = _active_subscription_for(conn, user["id"])
        _set_session_cookies(response, request, token)
        return {"token": token, "user": user}
    finally:
        conn.close()


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = get_auth_token(request)
    if token:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM user_sessions WHERE token=?", (token,))
            conn.commit()
        finally:
            conn.close()
    _clear_session_cookies(response, request)
    return {"ok": True}


@router.get("/me")
async def me(request: Request, response: Response):
    """Return current user and renew the browser session if valid.

    This makes login persistence much more reliable across refreshes and ZIP
    updates, as long as data/oryntra.db is preserved.
    """
    token = get_auth_token(request)
    user = get_current_user_optional(request)
    if user and token:
        conn = get_connection()
        try:
            conn.execute("UPDATE user_sessions SET expires_at=? WHERE token=?", (_expires_at(), token))
            conn.commit()
        finally:
            conn.close()
        _set_session_cookies(response, request, token)
    return {"authenticated": bool(user), "user": user}


@router.delete("/account")
async def delete_account(req: DeleteAccountRequest, request: Request, response: Response):
    user = require_current_user(request)
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if not row or not _verify_password(req.password, row["password_salt"], row["password_hash"]):
            raise HTTPException(status_code=401, detail="Password confirmation failed.")
        conn.execute("DELETE FROM alpaca_oauth_states WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM alpaca_connections WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM paper_trades WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM user_watchlist WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM user_sessions WHERE user_id=?", (user["id"],))
        conn.execute("DELETE FROM users WHERE id=?", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    _clear_session_cookies(response, request)
    return {"ok": True, "deleted": True}


@router.post("/subscribe")
async def subscribe(request: Request, req: SubscribeRequest):
    """Private-Pro placeholder subscription activator.
    Replace this with Stripe Checkout/webhooks before charging real users.
    """
    user = require_current_user(request)
    plan = req.plan_code.lower().strip()
    allowed = {
        "starter": "Oryntra AI Starter",
        "pro": "Oryntra AI Pro",
    }
    if plan not in allowed:
        raise HTTPException(status_code=400, detail="Unknown plan.")
    conn = get_connection()
    try:
        conn.execute("UPDATE subscriptions SET status='CANCELLED' WHERE user_id=? AND status='ACTIVE'", (user["id"],))
        conn.execute(
            """
            INSERT INTO subscriptions (user_id, plan_code, plan_name, status, started_at)
            VALUES (?, ?, ?, 'ACTIVE', datetime('now'))
            """,
            (user["id"], plan, allowed[plan]),
        )
        conn.commit()
    finally:
        conn.close()
    return await me(request)
