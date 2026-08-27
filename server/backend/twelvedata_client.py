"""Private Twelve Data client with conservative shared rate limiting."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

try:
    import fcntl
except Exception:
    fcntl = None

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
LOCK_PATH = DATA_DIR / "twelvedata_api.lock"
STATE_PATH = DATA_DIR / "twelvedata_api_rate_state.json"

try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except Exception:
    pass

TWELVEDATA_BASE_URL = os.getenv("TWELVEDATA_BASE_URL", "https://api.twelvedata.com").rstrip("/")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("ORYNTRA_HTTP_TIMEOUT", "20"))
MAX_CALLS_PER_MINUTE = max(1.0, float(os.getenv("ORYNTRA_TWELVEDATA_CALLS_PER_MINUTE", "6")))
MIN_GAP_SECONDS = max(60.0 / MAX_CALLS_PER_MINUTE, float(os.getenv("ORYNTRA_TWELVEDATA_MIN_GAP", "10.5")))
MAX_RETRIES = max(0, int(os.getenv("ORYNTRA_TWELVEDATA_MAX_RETRIES", "3")))

_THREAD_LOCK = threading.Lock()
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "OryntraAI/0.9 Quant-Lab"})


class TwelveDataAPIError(ValueError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _redact_secret(value: Any) -> str:
    text = str(value)
    key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    return text.replace(key, "[REDACTED]") if key else text


def _read_rate_state() -> dict[str, Any]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_rate_state(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, STATE_PATH)


def reserve_twelvedata_slot() -> float:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK:
        with LOCK_PATH.open("a+") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                state = _read_rate_state()
                now = time.time()
                scheduled_at = max(now, float(state.get("next_allowed_at") or 0.0))
                _write_rate_state({"next_allowed_at": scheduled_at + MIN_GAP_SECONDS, "last_reserved_at": now})
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return max(0.0, scheduled_at - time.time())


def _api_key() -> str:
    key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not key or key == "your_twelvedata_key_here":
        raise TwelveDataAPIError("TWELVEDATA_API_KEY is not set.")
    return key


def twelvedata_available() -> bool:
    enabled = os.getenv("ORYNTRA_ENABLE_TWELVEDATA_FALLBACK", "1").strip().lower()
    return enabled in {"1", "true", "yes", "on"} and bool(os.getenv("TWELVEDATA_API_KEY", "").strip())


def _safe_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return _redact_secret(payload.get("message") or payload.get("code") or "")
    except Exception:
        pass
    return ""


def twelvedata_get(
    path_or_url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    session: requests.Session | None = None,
) -> tuple[dict[str, Any], requests.Response]:
    url = path_or_url if path_or_url.startswith("http") else f"{TWELVEDATA_BASE_URL}/{path_or_url.lstrip('/')}"
    query = dict(params or {})
    query.setdefault("apikey", _api_key())
    attempts = MAX_RETRIES if max_retries is None else max(0, int(max_retries))
    client = session or _SESSION
    for attempt in range(attempts + 1):
        wait_seconds = reserve_twelvedata_slot()
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        try:
            response = client.get(url, params=query, timeout=timeout or DEFAULT_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            if attempt >= attempts:
                raise TwelveDataAPIError(f"Twelve Data network error: {_redact_secret(exc)}") from exc
            time.sleep(min(60.0, 2.0 ** attempt))
            continue
        detail = _safe_message(response)
        if response.status_code == 200:
            try:
                payload = response.json()
            except Exception as exc:
                raise TwelveDataAPIError("Twelve Data returned invalid JSON.", status_code=200) from exc
            if not isinstance(payload, dict):
                raise TwelveDataAPIError("Twelve Data returned an unexpected response.", status_code=200)
            if str(payload.get("status") or "").lower() == "error" or payload.get("code"):
                message = _redact_secret(payload.get("message") or payload.get("code") or "request failed")
                raise TwelveDataAPIError(f"Twelve Data error: {message}", status_code=200)
            return payload, response
        if response.status_code == 401:
            raise TwelveDataAPIError("Twelve Data API key is invalid.", status_code=401)
        retryable = response.status_code == 429 or 500 <= response.status_code < 600
        if retryable and attempt < attempts:
            try:
                delay = float(response.headers.get("Retry-After", ""))
            except Exception:
                delay = min(90.0, 2.0 ** (attempt + 1))
            time.sleep(max(delay, MIN_GAP_SECONDS if response.status_code == 429 else delay))
            continue
        suffix = f": {detail}" if detail else ""
        raise TwelveDataAPIError(f"Twelve Data error {response.status_code}{suffix}", status_code=response.status_code)
    raise TwelveDataAPIError("Twelve Data request failed after retries.")
