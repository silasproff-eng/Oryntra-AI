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
LOCK_PATH = DATA_DIR / "polygon_api.lock"
STATE_PATH = DATA_DIR / "polygon_api_rate_state.json"

try:
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")
except Exception:
    pass

POLYGON_BASE_URL = os.getenv("POLYGON_BASE_URL", "https://api.polygon.io").rstrip("/")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("ORYNTRA_HTTP_TIMEOUT", "20"))
MAX_CALLS_PER_MINUTE = max(1.0, float(os.getenv("ORYNTRA_POLYGON_CALLS_PER_MINUTE", "5")))

MIN_GAP_SECONDS = max(
    60.0 / MAX_CALLS_PER_MINUTE,
    float(os.getenv("ORYNTRA_POLYGON_MIN_GAP", "12.5")),
)
MAX_RETRIES = max(0, int(os.getenv("ORYNTRA_POLYGON_MAX_RETRIES", "4")))

_THREAD_LOCK = threading.Lock()
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "OryntraAI/0.5.2 market-cache"})


class PolygonAPIError(ValueError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _redact_secret(value: Any) -> str:
    text = str(value)
    key = os.getenv("POLYGON_API_KEY", "").strip()
    if key:
        text = text.replace(key, "[REDACTED]")
    return text


def _read_rate_state() -> dict[str, Any]:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_rate_state(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temp, STATE_PATH)


def reserve_polygon_slot() -> float:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _THREAD_LOCK:
        with LOCK_PATH.open("a+") as lock_file:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                state = _read_rate_state()
                now = time.time()
                next_allowed = float(state.get("next_allowed_at") or 0.0)
                scheduled_at = max(now, next_allowed)
                _write_rate_state({
                    "next_allowed_at": scheduled_at + MIN_GAP_SECONDS,
                    "last_reserved_at": now,
                    "min_gap_seconds": MIN_GAP_SECONDS,
                })
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return max(0.0, scheduled_at - time.time())


def _api_key() -> str:
    key = os.getenv("POLYGON_API_KEY", "").strip()
    if not key or key == "your_polygon_key_here":
        raise PolygonAPIError("POLYGON_API_KEY is not set.")
    return key


def _safe_message(response: requests.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return str(payload.get("error") or payload.get("message") or payload.get("status") or "")
    except Exception:
        pass
    return ""


def polygon_get(
    path_or_url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    session: requests.Session | None = None,
) -> tuple[dict[str, Any], requests.Response]:

    url = path_or_url if path_or_url.startswith("http") else f"{POLYGON_BASE_URL}/{path_or_url.lstrip('/')}"
    query = dict(params or {})
    query.setdefault("apiKey", _api_key())
    attempts = MAX_RETRIES if max_retries is None else max(0, int(max_retries))
    client = session or _SESSION

    for attempt in range(attempts + 1):
        wait_seconds = reserve_polygon_slot()
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            response = client.get(url, params=query, timeout=timeout or DEFAULT_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            if attempt >= attempts:
                raise PolygonAPIError(f"Polygon network error: {_redact_secret(exc)}") from exc
            time.sleep(min(60.0, 2.0 ** attempt))
            continue

        if response.status_code == 200:
            try:
                payload = response.json()
            except Exception as exc:
                raise PolygonAPIError("Polygon returned invalid JSON.", status_code=200) from exc
            if not isinstance(payload, dict):
                raise PolygonAPIError("Polygon returned an unexpected response.", status_code=200)
            return payload, response

        detail = _safe_message(response)
        if response.status_code == 401:
            raise PolygonAPIError("Polygon API key is invalid.", status_code=401)
        if response.status_code == 403:
            suffix = f" {detail}" if detail else ""
            raise PolygonAPIError(
                f"Polygon plan does not allow this endpoint or date range.{suffix}",
                status_code=403,
            )

        retryable = response.status_code == 429 or 500 <= response.status_code < 600
        if retryable and attempt < attempts:
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = float(retry_after)
            except Exception:
                delay = min(90.0, 2.0 ** (attempt + 1))
            time.sleep(max(delay, MIN_GAP_SECONDS if response.status_code == 429 else delay))
            continue

        suffix = f": {detail}" if detail else ""
        raise PolygonAPIError(
            f"Polygon error {response.status_code}{suffix}",
            status_code=response.status_code,
        )

    raise PolygonAPIError("Polygon request failed after retries.")


def rate_limit_info() -> dict[str, Any]:
    state = _read_rate_state()
    return {
        "max_calls_per_minute": MAX_CALLS_PER_MINUTE,
        "minimum_gap_seconds": MIN_GAP_SECONDS,
        "next_allowed_at": state.get("next_allowed_at"),
    }

