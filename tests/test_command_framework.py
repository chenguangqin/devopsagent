from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from evaluation.command_framework import (
    CommandEvaluationRunner,
    compare_variant_identities,
    load_descriptor,
    load_variant,
)

FIXTURE = (
    Path(__file__).parents[1]
    / "evaluation"
    / "fixtures"
    / "agents"
    / "deterministic-agent"
)


def _git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _make_agent_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "agent-repository"
    shutil.copytree(FIXTURE, repository)
    descriptor_path = repository / "agent.toml"
    descriptor_path.write_text(
        descriptor_path.read_text(encoding="utf-8").replace(
            'repository = "../../../.."', 'repository = "."'
        ).replace("evaluation/fixtures/agents/deterministic-agent/", ""),
        encoding="utf-8",
    )
    agent_path = repository / "agent.py"
    agent_path.write_text(
        agent_path.read_text(encoding="utf-8").replace(
            '"evaluation/fixtures/agents/deterministic-agent/reports/report.json"',
            '"reports/report.json"',
        ),
        encoding="utf-8",
    )
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "evaluation@example.invalid")
    _git(repository, "config", "user.name", "Evaluation Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "fixture")
    commit = _git(repository, "rev-parse", "HEAD")
    return repository, commit


def _variant(repository: Path, name: str = "baseline.toml"):
    return load_variant(repository / name)


def test_descriptor_rejects_absolute_repository(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    descriptor = repository / "agent.toml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            'repository = "."', f'repository = "{repository}"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be relative"):
        load_descriptor(descriptor)


def test_descriptor_rejects_path_escape(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    descriptor = repository / "agent.toml"
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(
            'result_path = "run/result.json"',
            'result_path = "../result.json"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes"):
        load_descriptor(descriptor)


def test_variant_rejects_undeclared_parameter(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    variant_path = repository / "baseline.toml"
    variant_path.write_text(
        variant_path.read_text(encoding="utf-8") + "\nunknown = 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="undeclared"):
        load_variant(variant_path)


def test_attempt_uses_fixed_commit_and_does_not_modify_source(tmp_path: Path):
    repository, commit = _make_agent_repository(tmp_path)
    source_memory = repository / "memory"
    runner = CommandEvaluationRunner(
        variant=_variant(repository),
        run_dir=tmp_path / "jobs",
        run_id="run-fixed",
    )

    result = runner.run_attempt(
        task_id="case", instruction="hello", attempt=1
    )

    assert result.status == "completed"
    assert result.source["commit"] == commit
    assert result.agent_result is not None
    assert result.agent_result["usage"] == {
        "input_tokens": None,
        "output_tokens": None,
        "source": "unavailable",
    }
    assert list(source_memory.glob("runtime-*.txt")) == []
    assert not (repository / "reports").exists()
    report = Path(result.paths["artifact_dir"]) / "reports" / "report.json"
    assert report.exists()


def test_serial_attempts_do_not_share_memory_or_reports(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    runner = CommandEvaluationRunner(
        variant=_variant(repository),
        run_dir=tmp_path / "jobs",
        run_id="run-serial",
    )

    first = runner.run_attempt(task_id="case", instruction="one", attempt=1)
    second = runner.run_attempt(task_id="case", instruction="two", attempt=2)

    for result in (first, second):
        structured = result.agent_result["structured_output"]
        assert structured["initial_runtime_markers"] == []
    assert first.paths["agent_root"] != second.paths["agent_root"]
    assert first.paths["artifact_dir"] != second.paths["artifact_dir"]
    assert Path(first.paths["result"]) != Path(second.paths["result"])


def test_concurrent_attempts_have_independent_workspaces(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    runner = CommandEvaluationRunner(
        variant=_variant(repository),
        run_dir=tmp_path / "jobs",
        run_id="run-concurrent",
    )

    def run(attempt: int):
        return runner.run_attempt(
            task_id="case", instruction=str(attempt), attempt=attempt
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, (1, 2)))

    assert all(result.status == "completed" for result in results)
    assert len({result.paths["agent_root"] for result in results}) == 2
    assert all(
        result.agent_result["structured_output"]["initial_runtime_markers"] == []
        for result in results
    )


def test_parameter_overlay_and_single_variable_diff(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    baseline_runner = CommandEvaluationRunner(
        variant=_variant(repository, "baseline.toml"),
        run_dir=tmp_path / "baseline-jobs",
        run_id="baseline",
    )
    experiment_runner = CommandEvaluationRunner(
        variant=_variant(repository, "experiment.toml"),
        run_dir=tmp_path / "experiment-jobs",
        run_id="experiment",
    )

    diff = compare_variant_identities(
        baseline_runner.identity, experiment_runner.identity
    )
    result = experiment_runner.run_attempt(
        task_id="case", instruction="compare", attempt=1
    )

    assert diff.classification == "SINGLE_PARAMETER_CHANGE"
    assert diff.differences == {
        "mode": {"before": "baseline", "after": "experiment"}
    }
    assert result.agent_result["structured_output"]["mode"] == "experiment"
    assert result.agent_result["structured_output"]["agent_config"]["mode"] == "experiment"


def test_code_change_is_not_reported_as_parameter_only(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    baseline_runner = CommandEvaluationRunner(
        variant=_variant(repository),
        run_dir=tmp_path / "baseline-jobs",
        run_id="baseline",
    )
    changed = replace(
        baseline_runner.identity,
        source_commit="different",
        parameters={**baseline_runner.identity.parameters, "mode": "experiment"},
    )

    diff = compare_variant_identities(baseline_runner.identity, changed)

    assert diff.classification == "UNCLASSIFIED_CODE_CHANGE"


def test_deadline_is_enforced_and_partial_artifacts_are_diagnostic_only(
    tmp_path: Path,
):
    repository, _ = _make_agent_repository(tmp_path)
    variant_path = repository / "baseline.toml"
    variant_path.write_text(
        variant_path.read_text(encoding="utf-8")
        + "\nmarker = \"timeout\"\nsleep_seconds = 2\n",
        encoding="utf-8",
    )
    runner = CommandEvaluationRunner(
        variant=load_variant(variant_path),
        run_dir=tmp_path / "jobs",
        run_id="run-timeout",
        verifier=lambda artifacts, result: {
            "score": 1.0,
            "report_exists": (artifacts / "reports" / "report.json").exists(),
        },
    )

    result = runner.run_attempt(
        task_id="case",
        instruction="timeout",
        attempt=1,
        deadline_seconds=0.1,
    )

    assert result.status == "deadline_exceeded"
    assert result.deadline_exceeded is True
    assert result.official_score == 0.0
    assert result.diagnostic_verifier_result == {
        "score": 1.0,
        "report_exists": True,
    }
    assert Path(result.paths["artifact_dir"], "reports", "report.json").exists()


def test_request_and_metadata_include_state_and_variant_identity(tmp_path: Path):
    repository, _ = _make_agent_repository(tmp_path)
    runner = CommandEvaluationRunner(
        variant=_variant(repository),
        run_dir=tmp_path / "jobs",
        run_id="run-metadata",
    )
    result = runner.run_attempt(
        task_id="case", instruction="metadata", attempt=1
    )
    attempt_path = Path(result.paths["attempt"])
    request = json.loads((attempt_path / "input" / "request.json").read_text())
    metadata = json.loads((attempt_path / "metadata.json").read_text())

    assert request["variant"]["digest"] == runner.identity.digest
    assert request["agent_config"]["mode"] == "baseline"
    assert metadata["state"]["snapshot_digest"].startswith("sha256:")
    assert metadata["source"]["descriptor_digest"].startswith("sha256:")


def test_demomcp_shim_preserves_harness_environment():
    shim = (
        Path(__file__).parents[1]
        / "evaluation"
        / "spikes"
        / "demomcp"
        / "agent_eval_entry.py"
    ).read_text(encoding="utf-8")

    assert "load_dotenv(ROOT_DIR / \".env\", override=False)" in shim
    assert "from agent import ROOT_DIR, build_agent" in shim
    assert "from strands" not in shim
