from argparse import Namespace
from pathlib import Path

import pytest

from evaluation.agent_engineering import (
    Track,
    Variant,
    aggregate_summaries,
    build_command,
    load_suite,
    load_variant,
    select_tracks,
)


def test_load_core_suite_keeps_devops_preset_separate():
    suite = load_suite(Path("evaluation/suites/agent-engineering-core.toml"))

    assert suite.id == "agent-engineering-core"
    assert {track.benchmark for track in suite.tracks} == {
        "Terminal-Bench",
        "DABstep",
        "BFCL Parity",
        "SWE-Atlas QnA",
    }
    assert all("competition" not in task for track in suite.tracks for task in track.tasks)


def test_select_tracks_defaults_to_ready_only():
    suite = load_suite(Path("evaluation/suites/agent-engineering-core.toml"))

    selected = select_tracks(suite, [], [])

    assert [track.id for track in selected] == ["terminal"]


def test_unknown_track_is_rejected():
    suite = load_suite(Path("evaluation/suites/agent-engineering-core.toml"))

    with pytest.raises(ValueError, match="unknown track"):
        select_tracks(suite, ["missing"], ["ready"])


def test_load_react_variant_is_ready():
    variant = load_variant(Path("evaluation/variants/react-baseline.toml"))

    assert variant.id == "react-baseline"
    assert variant.status == "ready"


def test_build_command_uses_separate_job_and_dataset():
    track = Track(
        id="data",
        benchmark="DABstep",
        dataset="dabstep@1.0",
        status="spike",
        purpose="data",
        tasks=("dabstep-1",),
    )
    variant = Variant(
        id="react",
        title="React",
        status="ready",
        agent="evaluation.harbor_adapter:NativeCliHarborAgent",
    )
    args = Namespace(
        model_id="model",
        region="us-west-2",
        max_steps=20,
        max_tokens=1000,
        tool_timeout_seconds=30,
        max_tool_output_chars=5000,
        attempts=2,
        n_concurrent=1,
        environment="docker",
    )

    command = build_command(
        track=track,
        variant=variant,
        args=args,
        jobs_dir=Path("jobs/react"),
    )

    assert command[command.index("--dataset") + 1] == "dabstep@1.0"
    assert command[command.index("--job-name") + 1] == "data"
    assert "dabstep-1" in command


def test_aggregate_summaries_uses_track_weights():
    summaries = [
        {
            "variant": "react",
            "mean_reward": 1.0,
            "weight": 1.0,
            "trials": 2,
            "errors": 0,
            "input_tokens": 10,
            "output_tokens": 2,
        },
        {
            "variant": "react",
            "mean_reward": 0.0,
            "weight": 3.0,
            "trials": 2,
            "errors": 0,
            "input_tokens": 20,
            "output_tokens": 4,
        },
    ]

    result = aggregate_summaries(summaries)

    assert result[0]["weighted_mean"] == 0.25
    assert result[0]["trials"] == 4
    assert result[0]["input_tokens"] == 30
