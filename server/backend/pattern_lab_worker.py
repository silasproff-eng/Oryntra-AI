from __future__ import annotations

import argparse
import asyncio
import math
import os
import signal
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configure_resources() -> dict[str, Any]:
    details: dict[str, Any] = {}
    try:
        nice_value = int(os.getenv("ORYNTRA_PATTERN_LAB_NICE", "12"))
        if nice_value > 0:
            os.nice(min(19, nice_value))
        details["nice"] = nice_value
    except Exception as exc:
        details["nice_error"] = str(exc)

    try:
        available = (
            sorted(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else list(range(max(1, os.cpu_count() or 1)))
        )
        total = max(1, len(available))
        share = max(0.05, min(float(os.getenv("ORYNTRA_PATTERN_LAB_CPU_SHARE", "0.30")), 1.0))
        allowed_count = max(1, min(total, int(round(total * share))))

        allowed = set(available[-allowed_count:])
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, allowed)
        details.update({"cpu_total": total, "cpu_share": share, "cpu_affinity": sorted(allowed)})
    except Exception as exc:
        details["cpu_affinity_error"] = str(exc)
    return details


async def _run(job_id: str) -> int:
    from .database import init_db
    from .pattern_lab import run_pattern_lab


    init_db()
    from .pattern_lab_jobs import (
        FileStopEvent,
        PersistentJob,
        read_checkpoint,
        read_request,
        read_status,
        write_checkpoint,
        write_result,
        summarize_checkpoint,
    )

    request = read_request(job_id)
    if not request:
        raise RuntimeError("Pattern Lab request file is missing.")
    initial = read_status(job_id) or {"job_id": job_id, "status": "queued"}
    initial.update({
        "worker_pid": os.getpid(),
        "status": "running",
        "phase": "worker_starting",
        "updated_at": _now(),
        "resource_policy": _configure_resources(),
    })
    job = PersistentJob(job_id, initial)
    job.flush(force=True)
    stop_event = FileStopEvent(job_id)

    resume_from = str(request.pop("resume_from_job_id", "") or "")
    resume_state = read_checkpoint(resume_from) if resume_from else None
    if resume_from and not resume_state:
        job.update({"message": f"Resume checkpoint {resume_from} was unavailable; starting from the beginning."})

    checkpoint_every = max(1, int(os.getenv("ORYNTRA_PATTERN_LAB_CHECKPOINT_TICKERS", "5")))
    checkpoint_counter = {"count": 0}

    def checkpoint_callback(state: dict[str, Any]) -> None:
        checkpoint_counter["count"] += 1
        if checkpoint_counter["count"] % checkpoint_every == 0 or state.get("stopped"):
            write_checkpoint(job_id, state)
            job["checkpoint_available"] = True
            job["checkpointed_tickers"] = len(state.get("completed_tickers") or [])
            job["partial_summary"] = summarize_checkpoint(state)
            job.flush(force=True)

    result = await run_pattern_lab(
        request,
        job=job,
        stop_event=stop_event,
        checkpoint_callback=checkpoint_callback,
        resume_state=resume_state,
    )
    write_result(job_id, result)
    job.update({
        "status": result.get("status", "done"),
        "phase": "complete" if result.get("status") == "done" else result.get("status", "complete"),
        "result_available": True,
        "summary": result.get("summary", []),
        "best_mode": result.get("best_mode"),
        "ticker_errors": result.get("ticker_errors", []),
        "message": result.get("message", "Pattern Lab complete."),
        "finished_at": _now(),
        "updated_at": _now(),
    })
    job.flush(force=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args.job_id))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        try:
            from .pattern_lab_jobs import PersistentJob, read_status
            job = PersistentJob(args.job_id, read_status(args.job_id) or {"job_id": args.job_id})
            job.update({
                "status": "failed",
                "phase": "failed",
                "message": str(exc),
                "error": str(exc),
                "finished_at": _now(),
                "updated_at": _now(),
            })
            job.flush(force=True)
        except Exception:
            pass
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

