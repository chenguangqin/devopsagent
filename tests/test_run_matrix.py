import json
from pathlib import Path

from evaluation.run_matrix import build_parser, load_preset, summarize_result


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
