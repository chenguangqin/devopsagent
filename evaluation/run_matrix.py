"""Run the same Harbor task or dataset against multiple CLI agent implementations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ADAPTERS = {
    "native": "evaluation.harbor_adapter:NativeCliHarborAgent",
    "langchain": "evaluation.harbor_adapter:LangChainCliHarborAgent",
    "strands": "evaluation.harbor_adapter:StrandsCliHarborAgent",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path, help="Local Harbor task or dataset path.")
    source.add_argument("--dataset", help="Harbor registry dataset name and version.")
    parser.add_argument(
        "--engines",
        nargs="+",
        choices=tuple(ADAPTERS),
        default=list(ADAPTERS),
    )
    parser.add_argument("--model-id", default="global.anthropic.claude-haiku-5-5")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--environment", default="docker")
    parser.add_argument(
        "--include-task",
        action="append",
        default=[],
        help="Task name or glob to include; repeat for multiple selections.",
    )
    parser.add_argument(
        "--exclude-task",
        action="append",
        default=[],
        help="Task name or glob to exclude; repeat for multiple selections.",
    )
    parser.add_argument("--tool-timeout-seconds", type=int, default=120)
    parser.add_argument("--max-tool-output-chars", type=int, default=50_000)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/jobs"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_name = datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    run_dir = args.output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    summaries = []

    for engine in args.engines:
        command = [
            "harbor",
            "run",
            "--jobs-dir",
            str(run_dir),
            "--job-name",
            engine,
            "--agent",
            ADAPTERS[engine],
            "--model",
            args.model_id,
            "--ak",
            f"region={args.region}",
            "--ak",
            f"max_steps={args.max_steps}",
            "--ak",
            f"max_tokens={args.max_tokens}",
            "--ak",
            f"tool_timeout_seconds={args.tool_timeout_seconds}",
            "--ak",
            f"max_tool_output_chars={args.max_tool_output_chars}",
            "--n-attempts",
            str(args.attempts),
            "--n-concurrent",
            str(args.n_concurrent),
            "--env",
            args.environment,
            "--yes",
        ]
        if args.path:
            command.extend(["--path", str(args.path)])
        else:
            command.extend(["--dataset", args.dataset])
        for task_name in args.include_task:
            command.extend(["--include-task-name", task_name])
        for task_name in args.exclude_task:
            command.extend(["--exclude-task-name", task_name])

        print(f"\n=== {engine} ===", flush=True)
        completed = subprocess.run(command, check=False)
        result_path = run_dir / engine / "result.json"
        summaries.append(summarize_result(engine, result_path, completed.returncode))

    summary_path = run_dir / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print_summary(summaries)
    print(f"\nResults: {run_dir}")
    failed = any(
        item["return_code"] != 0 or item["errors"] > 0 for item in summaries
    )
    return 1 if failed else 0


def summarize_result(
    engine: str,
    result_path: Path,
    return_code: int,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "engine": engine,
        "return_code": return_code,
        "mean_reward": None,
        "trials": 0,
        "errors": 0,
        "input_tokens": None,
        "output_tokens": None,
        "result_path": str(result_path),
    }
    if not result_path.exists():
        return summary

    data = json.loads(result_path.read_text(encoding="utf-8"))
    stats = data.get("stats", {})
    summary["trials"] = int(stats.get("n_completed_trials", 0))
    summary["errors"] = int(stats.get("n_errored_trials", 0))
    summary["input_tokens"] = stats.get("n_input_tokens")
    summary["output_tokens"] = stats.get("n_output_tokens")
    summary["mean_reward"] = _mean_reward(stats.get("evals", {}))
    return summary


def _mean_reward(evals: dict[str, Any]) -> float | None:
    values: list[float] = []
    for eval_stats in evals.values():
        eval_values: list[float] = []
        metrics = eval_stats.get("metrics", [])
        for metric in metrics:
            value = metric.get("reward")
            if isinstance(value, int | float):
                eval_values.append(float(value))
        if eval_values:
            values.extend(eval_values)
            continue
        rewards = eval_stats.get("reward_stats", {}).get("reward", {})
        for reward, trial_names in rewards.items():
            try:
                numeric_reward = float(reward)
            except (TypeError, ValueError):
                continue
            values.extend([numeric_reward] * len(trial_names))
    return sum(values) / len(values) if values else None


def print_summary(summaries: list[dict[str, Any]]) -> None:
    print("\n=== comparison ===")
    print(f"{'engine':<12} {'mean':>8} {'trials':>8} {'errors':>8} {'tokens':>12}")
    for item in summaries:
        mean = "-" if item["mean_reward"] is None else f"{item['mean_reward']:.3f}"
        token_values = (item["input_tokens"], item["output_tokens"])
        tokens = (
            "-"
            if any(value is None for value in token_values)
            else str(sum(int(value) for value in token_values))
        )
        print(
            f"{item['engine']:<12} {mean:>8} {item['trials']:>8} "
            f"{item['errors']:>8} {tokens:>12}"
        )


if __name__ == "__main__":
    sys.exit(main())
