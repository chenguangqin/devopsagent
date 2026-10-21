"""Inspect the frozen Security Agent dataset portfolio."""

from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_CATALOG = Path("evaluation/security/dataset_catalog.toml")
VALID_STATUSES = {"ready", "spike", "planned"}
VALID_ROLES = {
    "primary",
    "adversarial",
    "software-security",
    "end-to-end-security",
    "calibration",
}


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    role: str
    status: str
    harness: str
    source: str
    revision: str
    commit: str | None
    public_cases: int
    hidden_cases: int
    attempts: int
    requires_docker: bool
    capabilities: tuple[str, ...]
    selected: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    id: str
    title: str
    version: str
    frozen_at: str
    qualification_dataset_ids: tuple[str, ...]
    core_dataset_ids: tuple[str, ...]
    broad_dataset_ids: tuple[str, ...]
    datasets: tuple[Dataset, ...]


def load_catalog(path: Path = DEFAULT_CATALOG) -> Catalog:
    with path.open("rb") as source:
        data = tomllib.load(source)
    catalog_data = data["catalog"]
    selection = data["selection"]
    datasets = tuple(
        Dataset(
            id=item["id"],
            title=item["title"],
            role=item["role"],
            status=item["status"],
            harness=item["harness"],
            source=item["source"],
            revision=item["revision"],
            commit=item.get("commit"),
            public_cases=int(item["public_cases"]),
            hidden_cases=int(item["hidden_cases"]),
            attempts=int(item["attempts"]),
            requires_docker=bool(item["requires_docker"]),
            capabilities=tuple(item["capabilities"]),
            selected=tuple(item["selected"]),
        )
        for item in data["datasets"]
    )
    catalog = Catalog(
        id=catalog_data["id"],
        title=catalog_data["title"],
        version=str(catalog_data["version"]),
        frozen_at=catalog_data["frozen_at"],
        qualification_dataset_ids=tuple(selection["qualification_dataset_ids"]),
        core_dataset_ids=tuple(selection["core_dataset_ids"]),
        broad_dataset_ids=tuple(selection["broad_dataset_ids"]),
        datasets=datasets,
    )
    _validate_catalog(catalog, path)
    return catalog


def _validate_catalog(catalog: Catalog, path: Path) -> None:
    if not catalog.datasets:
        raise ValueError(f"catalog contains no datasets: {path}")
    ids = [dataset.id for dataset in catalog.datasets]
    if len(ids) != len(set(ids)):
        raise ValueError(f"catalog contains duplicate dataset ids: {path}")
    known_ids = set(ids)
    for selection_name, selected_ids in (
        ("qualification", catalog.qualification_dataset_ids),
        ("core", catalog.core_dataset_ids),
        ("broad", catalog.broad_dataset_ids),
    ):
        unknown = set(selected_ids) - known_ids
        if unknown:
            raise ValueError(
                f"{selection_name} selection contains unknown datasets: "
                + ", ".join(sorted(unknown))
            )
    for dataset in catalog.datasets:
        if dataset.status not in VALID_STATUSES:
            raise ValueError(f"invalid status for {dataset.id}: {dataset.status}")
        if dataset.role not in VALID_ROLES:
            raise ValueError(f"invalid role for {dataset.id}: {dataset.role}")
        if dataset.public_cases < 0 or dataset.hidden_cases < 0:
            raise ValueError(f"negative case count for {dataset.id}")
        if dataset.attempts < 1:
            raise ValueError(f"attempts must be positive for {dataset.id}")
        if not dataset.capabilities or not dataset.selected:
            raise ValueError(f"dataset has no capability or selection: {dataset.id}")
        if dataset.source.startswith("https://") and not dataset.commit:
            raise ValueError(f"external repository is not pinned: {dataset.id}")
        if dataset.commit and (
            len(dataset.commit) != 40
            or any(character not in "0123456789abcdef" for character in dataset.commit)
        ):
            raise ValueError(f"invalid commit for {dataset.id}: {dataset.commit}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument(
        "--selection",
        choices=("all", "qualification", "core", "broad"),
        default="all",
    )
    parser.add_argument(
        "--include-status",
        action="append",
        choices=tuple(sorted(VALID_STATUSES)),
        default=[],
    )
    return parser


def select_datasets(
    catalog: Catalog,
    selection: str,
    statuses: Sequence[str],
) -> list[Dataset]:
    selected_ids = {
        "all": tuple(dataset.id for dataset in catalog.datasets),
        "qualification": catalog.qualification_dataset_ids,
        "core": catalog.core_dataset_ids,
        "broad": catalog.broad_dataset_ids,
    }[selection]
    allowed_statuses = set(statuses or VALID_STATUSES)
    by_id = {dataset.id: dataset for dataset in catalog.datasets}
    return [
        by_id[dataset_id]
        for dataset_id in selected_ids
        if by_id[dataset_id].status in allowed_statuses
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    catalog = load_catalog(args.catalog)
    datasets = select_datasets(catalog, args.selection, args.include_status)
    print(f"{catalog.title} ({catalog.id}@{catalog.version}, frozen {catalog.frozen_at})")
    print(
        f"{'dataset':<38} {'role':<21} {'status':<9} "
        f"{'public':>6} {'hidden':>6} {'docker':>7}"
    )
    for dataset in datasets:
        print(
            f"{dataset.id:<38} {dataset.role:<21} {dataset.status:<9} "
            f"{dataset.public_cases:>6} {dataset.hidden_cases:>6} "
            f"{str(dataset.requires_docker).lower():>7}"
        )
        print(f"  harness={dataset.harness} revision={dataset.revision}")
    if args.selection == "qualification":
        print("\nWorkshop command:")
        print(
            "uv run agent-engineering-eval "
            "--suite evaluation/suites/security-agent-qualification.toml "
            "--include-status ready --attempts 1 --n-concurrent 1"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
