import json
from pathlib import Path

from evaluation.run_matrix import (
    GENERIC_ADAPTER,
    build_jobs,
    build_parser,
    load_preset,
    summarize_result,
)

FIXTURE_VARIANT = (
    Path(__file__).parents[1]
    / "evaluation/fixtures/agents/deterministic-agent/baseline.toml"
)


def test_summarize_result_computes_mean_from_reward_stats(tmp_path: Path):
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "stats": {
                    "n_completed_trials": 3,
                    "n_errored_trials": 0,
                    "n_input_tokens": 100,
                    "n_output_tokens": 20,
                    "evals": {
                        "agent__model__dataset": {
                            "metrics": [],
                            "reward_stats": {
                                "reward": {
                                    "1.0": ["trial-1", "trial-2"],
                                    "0.0": ["trial-3"],
                                }
                            },
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_result("native", result_path, 0)

    assert summary["trials"] == 3
    assert summary["mean_reward"] == 2 / 3
    assert summary["reward_sum"] == 2
    assert summary["full_reward_trials"] == 2
    assert summary["input_tokens"] == 100


def test_matrix_parser_accepts_task_filters_and_tool_timeout():
    args = build_parser().parse_args(
        [
            "--dataset",
            "terminal-bench-sample@2.0",
            "--include-task",
            "sqlite-with-gcov",
            "--include-task",
            "log-*",
            "--tool-timeout-seconds",
            "300",
        ]
    )

    assert args.include_task == ["sqlite-with-gcov", "log-*"]
    assert args.tool_timeout_seconds == 300


def test_load_preset_ignores_comments_and_blank_lines(tmp_path: Path):
    preset = tmp_path / "tasks.txt"
    preset.write_text(
        "# selected tasks\n\nfix-git\n  regex-log  \n",
        encoding="utf-8",
    )

    assert load_preset(preset) == ["fix-git", "regex-log"]


def test_matrix_parser_accepts_multiple_presets():
    args = build_parser().parse_args(
        [
            "--dataset",
            "terminal-bench@2.0",
            "--preset",
            "public.txt",
            "--preset",
            "/secure/hidden.txt",
        ]
    )

    assert args.preset == [Path("public.txt"), Path("/secure/hidden.txt")]


def test_variant_only_runs_generic_adapter_with_shared_filters(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "--dataset",
            "terminal-bench-sample@2.0",
            "--variant",
            str(FIXTURE_VARIANT),
            "--include-task",
            "fix-git",
        ]
    )
    args.engines = []

    jobs = build_jobs(args, tmp_path)

    assert [name for name, _ in jobs] == ["deterministic-baseline"]
    command = jobs[0][1]
    assert command[command.index("--agent") + 1] == GENERIC_ADAPTER
    assert f"variant_path={FIXTURE_VARIANT.resolve()}" in command
    assert "--model" not in command
    assert command[-2:] == ["--include-task-name", "fix-git"]


def test_engines_and_variants_run_side_by_side(tmp_path: Path):
    args = build_parser().parse_args(
        [
            "--path",
            "tasks",
            "--engines",
            "native",
            "--variant",
            str(FIXTURE_VARIANT),
        ]
    )

    jobs = build_jobs(args, tmp_path)

    assert [name for name, _ in jobs] == ["native", "deterministic-baseline"]
    assert all(command[-2:] == ["--path", "tasks"] for _, command in jobs)
