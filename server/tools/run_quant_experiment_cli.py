#!/usr/bin/env python3
"""Run one reproducible, declarative Quant Lab strategy experiment from daily CSV data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from backend.database import init_db
from backend.quant_experiments import histories_from_rows, run_manifest_experiment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a fixed Quant Lab manifest from daily date,ticker,close,volume CSV rows. No orders are created."
    )
    parser.add_argument("--bars-csv", required=True, help="CSV with date,ticker,close,volume columns.")
    parser.add_argument("--manifest", required=True, help="JSON manifest containing a hypothesis, selected sleeves, and fixed assumptions.")
    parser.add_argument("--output", required=True, help="Path to the JSON report to create.")
    args = parser.parse_args()

    bars_path, manifest_path, output_path = Path(args.bars_csv), Path(args.manifest), Path(args.output)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be a JSON object.")
        histories = histories_from_rows(pd.read_csv(bars_path))
        init_db()
        report = run_manifest_experiment(histories, manifest)
    except (OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        parser.error(str(exc))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": "recorded_research_only",
        "experiment_id": report["experiment_id"],
        "dataset_fingerprint": report["dataset_fingerprint"],
        "output": str(output_path),
        "holdout": report.get("validation", {}).get("holdout", {}),
        "benchmark": report.get("benchmark", {}),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
