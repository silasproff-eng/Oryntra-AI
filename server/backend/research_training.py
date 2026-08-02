"""Validated training orchestration for Oryntra research models.

Pattern Lab is responsible for causal observations.  This module audits those
observations, records reproducibility metadata, and only then invokes the
existing model learners.  It keeps model code isolated from data-loading and
prevents training on malformed, duplicated, or future-leaking rows.
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .research_experiments import (
    chronological_split,
    fingerprint,
    record_experiment,
    rows_fingerprint,
)
from .vai2_model import train_vai2_from_lab_rows

_REQUIRED_FIELDS = {
    "ticker",
    "date",
    "signal_date",
    "entry_date",
    "entry_price",
    "future_close",
    "future_high",
    "future_low",
    "raw_long_return_pct",
    "raw_long_mfe_pct",
    "raw_long_mae_pct",
    "horizon_days",
}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def audit_training_rows(rows: list[dict[str, Any]], *, minimum_rows: int = 1) -> dict[str, Any]:
    clean: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    duplicate_keys: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for index, original in enumerate(rows or []):
        row = dict(original or {})
        missing = sorted(field for field in _REQUIRED_FIELDS if row.get(field) in {None, ""})
        if row.get("error"):
            errors.append({"index": index, "reason": "row_error", "detail": str(row.get("error"))})
            continue
        if missing:
            errors.append({"index": index, "reason": "missing_fields", "fields": missing})
            continue
        key = (str(row.get("ticker") or "").upper(), str(row.get("date") or ""))
        if key in seen:
            duplicate_keys.append(key)
            continue
        seen.add(key)
        if str(row.get("entry_date")) <= str(row.get("signal_date")):
            errors.append({"index": index, "reason": "non_future_entry", "key": key})
            continue
        numeric_fields = (
            "entry_price",
            "future_close",
            "future_high",
            "future_low",
            "raw_long_return_pct",
            "raw_long_mfe_pct",
            "raw_long_mae_pct",
            "horizon_days",
        )
        if not all(_finite(row.get(field)) for field in numeric_fields):
            errors.append({"index": index, "reason": "non_finite_numeric", "key": key})
            continue
        if min(float(row["entry_price"]), float(row["future_close"]), float(row["future_high"]), float(row["future_low"])) <= 0:
            errors.append({"index": index, "reason": "non_positive_price", "key": key})
            continue
        clean.append(row)

    clean.sort(key=lambda row: (str(row.get("date")), str(row.get("ticker"))))
    dates = [str(row.get("date")) for row in clean]
    tickers = [str(row.get("ticker")).upper() for row in clean]
    horizon = max((int(float(row.get("horizon_days") or 0)) for row in clean), default=0)
    splits = chronological_split(clean, purge_days=max(0, horizon)) if clean else {"train": [], "validation": [], "test": []}
    split_date_ranges: dict[str, dict[str, str | None]] = {}
    for name, indexes in splits.items():
        split_dates = [str(clean[index].get("date")) for index in indexes]
        split_date_ranges[name] = {
            "first": min(split_dates) if split_dates else None,
            "last": max(split_dates) if split_dates else None,
            "rows": len(indexes),
        }

    valid = len(clean) >= max(1, int(minimum_rows)) and not duplicate_keys
    return {
        "valid": valid,
        "rows_received": len(rows or []),
        "rows_accepted": len(clean),
        "rows_rejected": len(errors),
        "duplicate_keys": duplicate_keys[:100],
        "duplicate_count": len(duplicate_keys),
        "errors": errors[:100],
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "unique_tickers": len(set(tickers)),
        "ticker_counts": dict(Counter(tickers).most_common(25)),
        "horizon_days": horizon,
        "dataset_fingerprint": rows_fingerprint(clean),
        "chronological_split": split_date_ranges,
        "clean_rows": clean,
    }


def train_vai2_research(
    rows: list[dict[str, Any]],
    *,
    horizon_days: int,
    min_samples: int,
    force_promote: bool = False,
    run_label: str | None = None,
) -> dict[str, Any]:
    audit = audit_training_rows(rows, minimum_rows=max(40, int(min_samples)))
    config = {
        "variant": "vai2",
        "horizon_days": horizon_days,
        "min_samples": min_samples,
        "force_promote": force_promote,
        "run_label": run_label,
        "code_version": "research-training-v3",
    }
    experiment_id = record_experiment(
        experiment_type="training",
        status="running",
        config=config,
        dataset_fingerprint=audit["dataset_fingerprint"],
        dataset_start=audit["first_date"],
        dataset_end=audit["last_date"],
        symbols=list(audit["ticker_counts"]),
        sample_count=audit["rows_accepted"],
    )
    if not audit["valid"]:
        result = {
            "ok": False,
            "status": "dataset_audit_failed",
            "experiment_id": experiment_id,
            "dataset_audit": {key: value for key, value in audit.items() if key != "clean_rows"},
        }
    else:
        result = train_vai2_from_lab_rows(
            audit["clean_rows"],
            horizon_days=horizon_days,
            min_samples=min_samples,
            force_promote=force_promote,
            run_label=run_label,
        )
        result = {
            **result,
            "experiment_id": experiment_id,
            "dataset_audit": {key: value for key, value in audit.items() if key != "clean_rows"},
        }
    record_experiment(
        experiment_type="training",
        status="done" if result.get("ok") else "failed",
        config=config,
        dataset_fingerprint=audit["dataset_fingerprint"],
        dataset_start=audit["first_date"],
        dataset_end=audit["last_date"],
        symbols=list(audit["ticker_counts"]),
        sample_count=audit["rows_accepted"],
        metrics={"status": result.get("status"), "promotion": result.get("promotion")},
        experiment_id=experiment_id,
    )
    return result
