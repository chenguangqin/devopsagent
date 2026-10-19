"""Run benchmark-aware Agent Engineering suites without changing DevOps evaluation."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from evaluation.run_matrix import summarize_result


@dataclass(frozen=True)
class Track:
    id: str
    benchmark: str
    dataset: str
    status: str
    purpose: str
    tasks: tuple[str, ...]
    weight: float = 1.0
    attempts: int | None = None
    n_concurrent: int | None = None


@dataclass(frozen=True)
class Suite:
    id: str
    title: str
    version: str
    tracks: tuple[Track, ...]


@dataclass(frozen=True)
class Variant:
    id: str
    title: str
    status: str
    agent: str
    model: str | None = None
    agent_kwargs: dict[str, str | int | float | bool] = field(default_factory=dict)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path("evaluation/suites/agent-engineering-core.toml"),
    )
    parser.add_argument(
        "--variant",
        type=Path,
        action="append",
        default=[],
        help="Variant TOML; repeat to compare multiple control/context strategies.",
    )
    parser.add_argument("--include-track", action="append", default=[])
    parser.add_argument(
        "--include-status",
        action="append",
        choices=("ready", "spike", "planned"),
        default=[],
        help="Track maturity to include. Defaults to ready only.",
    )
    parser.add_argument("--model-id", default="global.anthropic.claude-haiku-5-5")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--tool-timeout-seconds", type=int, default=300)
    parser.add_argument("--max-tool-output-chars", type=int, default=50_000)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--environment", default="docker")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/agent-jobs"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="List the resolved experiment matrix.")
    return parser


def load_suite(path: Path) -> Suite:
    data = _load_toml(path)
    tracks = tuple(
        Track(
            id=item["id"],
            benchmark=item["benchmark"],
            dataset=item["dataset"],
            status=item["status"],
            purpose=item["purpose"],
            tasks=tuple(item.get("tasks", [])),
            weight=float(item.get("weight", 1.0)),
            attempts=item.get("attempts"),
            n_concurrent=item.get("n_concurrent"),
        )
        for item in data.get("tracks", [])
    )
    suite = Suite(
        id=data["suite"]["id"],
        title=data["suite"]["title"],
        version=str(data["suite"]["version"]),
        tracks=tracks,
    )
    _validate_suite(suite, path)
    return suite


def load_variant(path: Path) -> Variant:
    data = _load_toml(path)
    item = data["variant"]
    variant = Variant(
        id=item["id"],
        title=item["title"],
        status=item["status"],
        agent=item["agent"],
        model=item.get("model"),
        agent_kwargs=dict(data.get("agent_kwargs", {})),
    )
    if variant.status not in {"ready", "planned"}:
        raise ValueError(f"invalid variant status in {path}: {variant.status}")
    return variant


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def _validate_suite(suite: Suite, path: Path) -> None:
    if not suite.tracks:
        raise ValueError(f"suite contains no tracks: {path}")
    ids = [track.id for track in suite.tracks]
    if len(ids) != len(set(ids)):
        raise ValueError(f"suite contains duplicate track ids: {path}")
    for track in suite.tracks:
        if track.status not in {"ready", "spike", "planned"}:
            raise ValueError(f"invalid track status for {track.id}: {track.status}")
        if not track.tasks:
            raise ValueError(f"track contains no tasks: {track.id}")
        if track.weight <= 0:
            raise ValueError(f"track weight must be positive: {track.id}")


def select_tracks(
    suite: Suite,
    included_ids: Sequence[str],
    included_statuses: Sequence[str],
) -> list[Track]:
    statuses = set(included_statuses or ["ready"])
    selected = [
        track
        for track in suite.tracks
        if track.status in statuses and (not included_ids or track.id in included_ids)
    ]
    missing = set(included_ids) - {track.id for track in suite.tracks}
    if missing:
        raise ValueError(f"unknown track ids: {', '.join(sorted(missing))}")
    return selected


def build_command(
    *,
    track: Track,
    variant: Variant,
    args: argparse.Namespace,
    jobs_dir: Path,
) -> list[str]:
    command = [
        "harbor",
        "run",
        "--jobs-dir",
        str(jobs_dir),
        "--job-name",
        track.id,
        "--dataset",
        track.dataset,
        "--agent",
        variant.agent,
        "--model",
        variant.model or args.model_id,
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
        str(track.attempts or args.attempts),
        "--n-concurrent",
        str(track.n_concurrent or args.n_concurrent),
        "--env",
        args.environment,
        "--yes",
    ]
    for key, value in variant.agent_kwargs.items():
        command.extend(["--ak", f"{key}={_format_value(value)}"])
    for task in track.tasks:
        command.extend(["--include-task-name", task])
    return command


def _format_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite = load_suite(args.suite)
    variant_paths = args.variant or [
        Path("evaluation/variants/react-baseline.toml")
    ]
    variants = [load_variant(path) for path in variant_paths]
    planned = [variant.id for variant in variants if variant.status != "ready"]
    if planned and not (args.list or args.dry_run):
        raise ValueError(
            "planned variants can only be listed or dry-run until their adapter exists: "
            + ", ".join(planned)
        )
    tracks = select_tracks(suite, args.include_track, args.include_status)
    if not tracks:
        raise ValueError("no tracks selected")

    print_matrix(suite, tracks, variants)
    if args.list:
        return 0

    run_name = datetime.now().strftime("%Y-%m-%d__%H-%M-%S")
    run_dir = args.output_dir / run_name
    summaries: list[dict[str, Any]] = []
    if not args.dry_run:
        run_dir.mkdir(parents=True, exist_ok=False)

    for variant in variants:
        for track in tracks:
            variant_jobs = run_dir / variant.id
            command = build_command(
                track=track,
                variant=variant,
                args=args,
                jobs_dir=variant_jobs,
            )
            print(f"\n=== {variant.id} / {track.id} ===", flush=True)
            if args.dry_run:
                print(shlex.join(command))
                continue
            completed = subprocess.run(command, check=False)
            result_path = variant_jobs / track.id / "result.json"
            item = summarize_result(
                f"{variant.id}/{track.id}",
                result_path,
                completed.returncode,
            )
            item.update(
                {
                    "variant": variant.id,
                    "track": track.id,
                    "benchmark": track.benchmark,
                    "dataset": track.dataset,
                    "weight": track.weight,
                }
            )
            summaries.append(item)

    if args.dry_run:
        return 0

    aggregates = aggregate_summaries(summaries)
    report = {
        "suite": suite.id,
        "suite_version": suite.version,
        "summaries": summaries,
        "aggregates": aggregates,
    }
    (run_dir / "agent-engineering-summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print_aggregates(aggregates)
    print(f"\nResults: {run_dir}")
    failed = any(item["return_code"] != 0 or item["errors"] > 0 for item in summaries)
    return 1 if failed else 0


def print_matrix(suite: Suite, tracks: Sequence[Track], variants: Sequence[Variant]) -> None:
    print(f"{suite.title} ({suite.id}@{suite.version})")
    print("Tracks:")
    for track in tracks:
        print(
            f"  {track.id:<20} {track.dataset:<30} "
            f"{len(track.tasks):>2} tasks  [{track.status}]"
        )
    print("Variants:")
    for variant in variants:
        print(f"  {variant.id:<20} {variant.title} [{variant.status}]")


def aggregate_summaries(summaries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in summaries:
        grouped.setdefault(item["variant"], []).append(item)

    aggregates = []
    for variant, items in grouped.items():
        scored = [item for item in items if item["mean_reward"] is not None]
        weight_sum = sum(float(item["weight"]) for item in scored)
        weighted_mean = (
            sum(float(item["mean_reward"]) * float(item["weight"]) for item in scored)
            / weight_sum
            if weight_sum
            else None
        )
        aggregates.append(
            {
                "variant": variant,
                "weighted_mean": weighted_mean,
                "tracks": len(items),
                "trials": sum(int(item["trials"]) for item in items),
                "errors": sum(int(item["errors"]) for item in items),
                "input_tokens": _sum_optional(items, "input_tokens"),
                "output_tokens": _sum_optional(items, "output_tokens"),
            }
        )
    return aggregates


def _sum_optional(items: Sequence[dict[str, Any]], key: str) -> int | None:
    values = [item[key] for item in items]
    return None if any(value is None for value in values) else sum(int(value) for value in values)


def print_aggregates(aggregates: Sequence[dict[str, Any]]) -> None:
    print("\n=== cross-benchmark comparison ===")
    print(f"{'variant':<22} {'mean':>8} {'tracks':>8} {'trials':>8} {'errors':>8}")
    for item in aggregates:
        mean = (
            "-"
            if item["weighted_mean"] is None
            else f"{item['weighted_mean']:.3f}"
        )
        print(
            f"{item['variant']:<22} {mean:>8} {item['tracks']:>8} "
            f"{item['trials']:>8} {item['errors']:>8}"
        )


if __name__ == "__main__":
    sys.exit(main())
