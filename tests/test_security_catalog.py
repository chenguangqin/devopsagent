from pathlib import Path

from evaluation.agent_engineering import load_suite, select_tracks
from evaluation.security_catalog import load_catalog, select_datasets


CATALOG_PATH = Path("evaluation/security/dataset_catalog.toml")


def test_security_catalog_freezes_complementary_dataset_portfolio():
    catalog = load_catalog(CATALOG_PATH)

    assert catalog.id == "aws-security-agent"
    assert {dataset.id for dataset in catalog.datasets} == {
        "aws-security-arena",
        "agentdojo",
        "sec-bench",
        "bountybench",
        "terminal-bench-security-calibration",
    }
    assert catalog.core_dataset_ids == (
        "aws-security-arena",
        "agentdojo",
        "sec-bench",
        "terminal-bench-security-calibration",
    )
    primary = next(dataset for dataset in catalog.datasets if dataset.role == "primary")
    assert primary.id == "aws-security-arena"


def test_external_security_datasets_are_pinned_to_commits():
    catalog = load_catalog(CATALOG_PATH)
    external = [
        dataset
        for dataset in catalog.datasets
        if dataset.source.startswith("https://")
    ]

    assert external
    assert all(dataset.commit and len(dataset.commit) == 40 for dataset in external)
    assert all("latest" not in dataset.revision.lower() for dataset in external)


def test_security_portfolio_covers_utility_attack_and_boundary_axes():
    catalog = load_catalog(CATALOG_PATH)
    capabilities = {
        capability
        for dataset in catalog.datasets
        for capability in dataset.capabilities
    }

    assert {
        "iam-least-privilege",
        "prompt-injection-resistance",
        "authorization-boundary",
        "security-patching",
        "verification-discipline",
    } <= capabilities


def test_qualification_selection_contains_only_ready_dataset():
    catalog = load_catalog(CATALOG_PATH)

    selected = select_datasets(catalog, "qualification", [])

    assert [dataset.id for dataset in selected] == [
        "terminal-bench-security-calibration"
    ]
    assert selected[0].status == "ready"


def test_security_qualification_suite_is_directly_runnable():
    suite = load_suite(
        Path("evaluation/suites/security-agent-qualification.toml")
    )

    selected = select_tracks(suite, [], [])

    assert suite.id == "security-agent-qualification"
    assert [track.id for track in selected] == [
        "vulnerability-remediation",
        "repository-security",
    ]
    assert sum(len(track.tasks) for track in selected) == 3
