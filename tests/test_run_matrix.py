import json
from pathlib import Path

from evaluation.run_matrix import summarize_result


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
    assert summary["input_tokens"] == 100
