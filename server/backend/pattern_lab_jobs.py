"""Persistent Pattern Lab job files and worker process helpers.

Pattern Lab is deliberately run outside the Uvicorn process.  Status, partial
checkpoints, logs, and final results live under ``data/pattern_lab_jobs`` so a
closed browser never loses the job and a stopped run can still expose partial
results or be resumed.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
JOBS_DIR = BASE_DIR / "data" / "pattern_lab_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

_WRITE_LOCK = threading.Lock()


def _path(job_id: str, suffix: str) -> Path:
    safe = "".join(ch for ch in str(job_id) if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        raise ValueError("Invalid Pattern Lab job ID")
    return JOBS_DIR / f"{safe}.{suffix}"


def status_path(job_id: str) -> Path:
    return _path(job_id, "status.json")


def request_path(job_id: str) -> Path:
    return _path(job_id, "request.json")


def result_path(job_id: str) -> Path:
    return _path(job_id, "result.json")


def checkpoint_path(job_id: str) -> Path:
    return _path(job_id, "checkpoint.pkl")


def log_path(job_id: str) -> Path:
    return _path(job_id, "log")


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    safe = _json_safe(payload)
    _atomic_bytes(path, json.dumps(safe, indent=2, default=str, allow_nan=False).encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_status(job_id: str, status: dict[str, Any]) -> None:
    write_json(status_path(job_id), status)


def read_status(job_id: str) -> dict[str, Any] | None:
    value = read_json(status_path(job_id))
    return value if isinstance(value, dict) else None


def write_request(job_id: str, request: dict[str, Any]) -> None:
    write_json(request_path(job_id), request)


def read_request(job_id: str) -> dict[str, Any] | None:
    value = read_json(request_path(job_id))
    return value if isinstance(value, dict) else None


def write_result(job_id: str, result: dict[str, Any]) -> None:
    write_json(result_path(job_id), result)


def read_result(job_id: str) -> dict[str, Any] | None:
    value = read_json(result_path(job_id))
    return value if isinstance(value, dict) else None


def write_checkpoint(job_id: str, checkpoint: dict[str, Any]) -> None:
    _atomic_bytes(checkpoint_path(job_id), pickle.dumps(checkpoint, protocol=pickle.HIGHEST_PROTOCOL))


def read_checkpoint(job_id: str) -> dict[str, Any] | None:
    try:
        with checkpoint_path(job_id).open("rb") as handle:
            value = pickle.load(handle)
        return value if isinstance(value, dict) else None
    except (FileNotFoundError, OSError, pickle.UnpicklingError, EOFError):
        return None



def summarize_checkpoint(checkpoint: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not checkpoint:
        return []
    summaries = []
    for mode, rows in (checkpoint.get("mode_rows") or {}).items():
        valid = [row for row in rows if not row.get("error")]
        actionable = [row for row in valid if row.get("actionable")]
        returns = [float(row.get("return_pct") or 0.0) for row in actionable]
        wins = sum(value > 0 for value in returns)
        summaries.append({
            "mode": mode,
            "tests": len(valid),
            "actionable": len(actionable),
            "coverage_pct": round(len(actionable) / len(valid) * 100.0, 2) if valid else 0.0,
            "win_rate_pct": round(wins / len(returns) * 100.0, 2) if returns else 0.0,
            "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        })
    return summaries

def pid_is_alive(pid: int | None) -> bool:
    if not pid or int(pid) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def request_stop(job_id: str) -> dict[str, Any]:
    status = read_status(job_id) or {"job_id": job_id, "status": "not_found"}
    if status.get("status") in {"done", "failed", "stopped"}:
        return status
    status.update({
        "status": "stopping",
        "phase": "stop_requested",
        "stop_requested": True,
        "message": "Stop requested; the worker is finalizing partial results.",
        "updated_at": _iso_now(),
    })
    write_status(job_id, status)
    return status


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def launch_worker(job_id: str) -> int:
    """Launch a low-priority Pattern Lab worker and return its PID."""
    env = os.environ.copy()
    # Prevent BLAS libraries from silently using every core.
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("NUMEXPR_NUM_THREADS", "1")
    env.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    env["ORYNTRA_PATTERN_LAB_JOB_ID"] = job_id

    log_file = log_path(job_id).open("ab", buffering=0)
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "backend.pattern_lab_worker", "--job-id", job_id],
            cwd=str(BASE_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_file.close()
    return int(process.pid)


def terminate_worker(job_id: str, *, force: bool = False) -> bool:
    status = read_status(job_id) or {}
    pid = int(status.get("worker_pid") or 0)
    if not pid_is_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        return True
    except OSError:
        return False


def status_with_result(job_id: str) -> dict[str, Any]:
    status = read_status(job_id)
    if not status:
        return {"job_id": job_id, "status": "not_found", "message": "Pattern Lab job not found."}
    pid = int(status.get("worker_pid") or 0)
    if status.get("status") in {"queued", "running", "stopping"} and pid and not pid_is_alive(pid):
        status.update({
            "status": "interrupted",
            "phase": "worker_not_running",
            "message": "The worker stopped unexpectedly. A checkpoint may be resumed.",
            "checkpoint_available": checkpoint_path(job_id).exists(),
            "updated_at": _iso_now(),
        })
        write_status(job_id, status)
    if status.get("status") in {"done", "stopped", "failed"} or status.get("result_available"):
        result = read_result(job_id)
        if result is not None:
            status["result"] = result
    started_at = status.get("started_at")
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
        completed = max(0, int(status.get("completed_checks") or 0))
        total = max(0, int(status.get("total_checks_estimated") or 0))
        rate = completed / elapsed if elapsed > 0 else 0.0
        status["elapsed_seconds"] = round(elapsed, 1)
        status["checks_per_second"] = round(rate, 3)
        status["eta_seconds"] = round((total - completed) / rate, 1) if rate > 0 and total > completed else 0.0
    except Exception:
        pass
    status["checkpoint_available"] = checkpoint_path(job_id).exists()
    if status["checkpoint_available"] and status.get("status") not in {"done", "stopped"}:
        checkpoint = read_checkpoint(job_id)
        status["partial_summary"] = summarize_checkpoint(checkpoint)
        status["checkpointed_tickers"] = len((checkpoint or {}).get("completed_tickers") or [])
    return status


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(JOBS_DIR.glob("*.status.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        value = read_json(path)
        if isinstance(value, dict):
            rows.append(value)
        if len(rows) >= max(1, int(limit)):
            break
    return rows


class PersistentJob(dict):
    """Dict-compatible status sink used by the worker.

    ``run_pattern_lab`` writes to a normal dict very frequently.  This wrapper
    batches those writes so status polling remains cheap while still surviving
    browser closure and web-process restarts.
    """

    def __init__(self, job_id: str, initial: dict[str, Any] | None = None, flush_interval: float = 0.35):
        super().__init__(initial or {})
        self.job_id = job_id
        self.flush_interval = max(0.05, float(flush_interval))
        self._last_flush = 0.0
        self._dirty = True

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._dirty = True
        self.flush(force=key in {"status", "finished_at", "error"})

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._dirty = True
        force = any(key in self for key in ("finished_at", "error")) and self.get("status") in {"done", "stopped", "failed"}
        self.flush(force=force)

    def flush(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not self._dirty or (not force and now - self._last_flush < self.flush_interval):
            return
        payload = dict(self)
        payload.pop("result", None)
        write_status(self.job_id, payload)
        self._last_flush = now
        self._dirty = False


class FileStopEvent:
    def __init__(self, job_id: str, interval: float = 0.25):
        self.job_id = job_id
        self.interval = max(0.05, float(interval))
        self._last_check = 0.0
        self._cached = False

    def is_set(self) -> bool:
        now = time.monotonic()
        if now - self._last_check >= self.interval:
            status = read_status(self.job_id) or {}
            self._cached = bool(status.get("stop_requested"))
            self._last_check = now
        return self._cached
