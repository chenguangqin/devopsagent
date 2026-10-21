"""Deterministic external Agent used to verify the command boundary."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "experiment"), required=True)
    args = parser.parse_args()
    request = json.loads(input())
    marker = os.environ["DETERMINISTIC_MARKER"]
    sleep_seconds = float(os.environ["DETERMINISTIC_SLEEP_SECONDS"])
    result_path = Path(os.environ["AGENT_EVAL_RESULT"])

    memory_dir = ROOT / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    initial_runtime_markers = sorted(
        path.read_text(encoding="utf-8")
        for path in memory_dir.glob("runtime-*.txt")
    )
    runtime_marker = memory_dir / f"runtime-{request['run_id']}-{request['task']['id']}.txt"
    runtime_marker.write_text(marker, encoding="utf-8")

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "report.json"
    report: dict[str, Any] = {
        "mode": args.mode,
        "marker": marker,
        "instruction": request["task"]["instruction"],
        "initial_runtime_markers": initial_runtime_markers,
        "agent_config": request["agent_config"],
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if sleep_seconds:
        time.sleep(sleep_seconds)

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "status": "completed",
                "final_text": json.dumps(report, ensure_ascii=False),
                "structured_output": report,
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "source": "unavailable",
                },
                "artifacts": [
                    "evaluation/fixtures/agents/deterministic-agent/reports/report.json"
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
