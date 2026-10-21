"""Run an external command Agent through the v0.2 evaluation boundary."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from evaluation.command_framework.models import load_variant
from evaluation.command_framework.runner import CommandEvaluationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--deadline-seconds", type=float)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("evaluation/command-jobs")
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.attempts < 1 or args.n_concurrent < 1:
        raise ValueError("attempts and n-concurrent must be positive")
    variant = load_variant(args.variant)
    run_id = datetime.now().strftime("%Y-%m-%d__%H-%M-%S-%f")
    runner = CommandEvaluationRunner(
        variant=variant,
        run_dir=args.output_dir / run_id,
        run_id=run_id,
    )

    def run(attempt: int):
        return runner.run_attempt(
            task_id=args.task_id,
            instruction=args.instruction,
            attempt=attempt,
            deadline_seconds=args.deadline_seconds,
        )

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(args.n_concurrent, args.attempts)
    ) as executor:
        results = list(executor.map(run, range(1, args.attempts + 1)))
    summary = {
        "schema_version": "0.2",
        "run_id": run_id,
        "variant_identity": runner.identity.__dict__,
        "attempts": [result.to_dict() for result in results],
    }
    summary_path = runner.run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(summary_path)
    return 1 if any(result.status != "completed" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
