"""Descriptor v0.2, Variant v0.2, and variant comparison."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "0.2"
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PARAMETER_TYPES = {"string", "integer", "number", "boolean", "enum"}
DELIVERY_TYPES = {"argv", "env"}


@dataclass(frozen=True)
class Launcher:
    command: tuple[str, ...]
    input: str
    result: str
    result_path: str
    startup_timeout_seconds: float
    run_timeout_seconds: float
    max_output_chars: int = 1_000_000


@dataclass(frozen=True)
class State:
    mode: str
    snapshot_paths: tuple[str, ...]
    empty_paths: tuple[str, ...]


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    default: str | int | float | bool
    delivery: str
    flag: str | None = None
    env_name: str | None = None
    values: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: Any) -> str | int | float | bool:
        if self.type == "string":
            valid = isinstance(value, str)
        elif self.type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif self.type == "number":
            valid = isinstance(value, int | float) and not isinstance(value, bool)
        elif self.type == "boolean":
            valid = isinstance(value, bool)
        else:
            valid = isinstance(value, str) and value in self.values
        if not valid:
            raise ValueError(f"invalid value for parameter {self.name}: {value!r}")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"parameter {self.name} must be >= {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"parameter {self.name} must be <= {self.maximum}")
        return value


@dataclass(frozen=True)
class AgentDescriptor:
    path: Path
    id: str
    title: str
    repository: Path
    source_revision: str
    launcher: Launcher
    state: State
    artifact_paths: tuple[str, ...]
    capabilities: Mapping[str, Any]
    parameters: Mapping[str, Parameter]
    digest: str


@dataclass(frozen=True)
class Variant:
    path: Path
    id: str
    descriptor: AgentDescriptor
    commit: str
    parameter_overrides: Mapping[str, Any]


@dataclass(frozen=True)
class VariantIdentity:
    variant_id: str
    digest: str
    descriptor_digest: str
    source_commit: str
    source_digest: str
    state_snapshot_digest: str
    parameters: Mapping[str, str | int | float | bool]


@dataclass(frozen=True)
class ParameterDiff:
    classification: str
    differences: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    reason: str | None = None


def load_descriptor(path: Path) -> AgentDescriptor:
    path = path.resolve()
    data = _load_toml(path)
    agent = _require_table(data, "agent")
    _require_schema(agent, path)
    agent_id = _identifier(agent.get("id"), f"agent id in {path}")
    source = _require_table(data, "source")
    repository_value = _relative_string(source.get("repository"), "source.repository")
    repository = (path.parent / repository_value).resolve()
    if not repository.is_dir():
        raise ValueError(f"agent repository does not exist: {repository}")
    if not _is_within(path, repository):
        raise ValueError("descriptor must be stored inside source.repository")
    source_revision = source.get("revision", "git")
    if source_revision != "git":
        raise ValueError(f"unsupported source revision: {source_revision!r}")

    launcher_data = _require_table(data, "launcher")
    if launcher_data.get("adapter") != "command":
        raise ValueError("MVP only supports launcher.adapter = 'command'")
    command = launcher_data.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise ValueError("launcher.command must be a non-empty argv array")
    input_mode = launcher_data.get("input")
    result_mode = launcher_data.get("result")
    if input_mode != "jsonl-stdin":
        raise ValueError("MVP only supports launcher.input = 'jsonl-stdin'")
    if result_mode != "json-file":
        raise ValueError("MVP only supports launcher.result = 'json-file'")
    result_path = _repository_path(
        repository,
        launcher_data.get("result_path", "result/result.json"),
        "launcher.result_path",
    )
    launcher = Launcher(
        command=tuple(command),
        input=input_mode,
        result=result_mode,
        result_path=result_path,
        startup_timeout_seconds=_positive_number(
            launcher_data.get("startup_timeout_seconds", 30),
            "launcher.startup_timeout_seconds",
        ),
        run_timeout_seconds=_positive_number(
            launcher_data.get("run_timeout_seconds", 600),
            "launcher.run_timeout_seconds",
        ),
        max_output_chars=_positive_integer(
            launcher_data.get("max_output_chars", 1_000_000),
            "launcher.max_output_chars",
        ),
    )

    state_data = _require_table(data, "state")
    state_mode = state_data.get("mode")
    if state_mode != "isolated-copy":
        raise ValueError("MVP only supports state.mode = 'isolated-copy'")
    snapshot_paths = _path_list(
        repository, state_data.get("snapshot_paths", []), "state.snapshot_paths"
    )
    empty_paths = _path_list(
        repository, state_data.get("empty_paths", []), "state.empty_paths"
    )
    overlap = set(snapshot_paths) & set(empty_paths)
    if overlap:
        raise ValueError(f"state paths cannot be both snapshot and empty: {sorted(overlap)}")

    artifacts_data = data.get("artifacts", {})
    if not isinstance(artifacts_data, dict):
        raise ValueError("[artifacts] must be a table")
    artifact_paths = _glob_list(artifacts_data.get("paths", []), "artifacts.paths")

    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise ValueError("[capabilities] must be a table")
    parameters = _load_parameters(data.get("parameters", {}))
    descriptor_digest = _sha256(path.read_bytes())
    return AgentDescriptor(
        path=path,
        id=agent_id,
        title=str(agent.get("title", agent_id)),
        repository=repository,
        source_revision=source_revision,
        launcher=launcher,
        state=State(
            mode=state_mode,
            snapshot_paths=snapshot_paths,
            empty_paths=empty_paths,
        ),
        artifact_paths=artifact_paths,
        capabilities=dict(capabilities),
        parameters=parameters,
        digest=descriptor_digest,
    )


def load_variant(path: Path) -> Variant:
    path = path.resolve()
    data = _load_toml(path)
    item = _require_table(data, "variant")
    _require_schema(item, path)
    variant_id = _identifier(item.get("id"), f"variant id in {path}")
    agent_path_value = _relative_string(item.get("agent"), "variant.agent")
    descriptor = load_descriptor(path.parent / agent_path_value)
    source = _require_table(data, "source")
    commit = source.get("commit")
    if not isinstance(commit, str) or not commit.strip():
        raise ValueError("source.commit must be a non-empty Git revision")
    overrides = data.get("parameters", {})
    if not isinstance(overrides, dict):
        raise ValueError("[parameters] must be a table")
    unknown = set(overrides) - set(descriptor.parameters)
    if unknown:
        raise ValueError(f"variant contains undeclared parameters: {sorted(unknown)}")
    for name, value in overrides.items():
        descriptor.parameters[name].validate(value)
    return Variant(
        path=path,
        id=variant_id,
        descriptor=descriptor,
        commit=commit,
        parameter_overrides=dict(overrides),
    )


def resolve_parameters(variant: Variant) -> dict[str, str | int | float | bool]:
    resolved: dict[str, str | int | float | bool] = {}
    for name, parameter in variant.descriptor.parameters.items():
        value = variant.parameter_overrides.get(name, parameter.default)
        resolved[name] = parameter.validate(value)
    return resolved


def variant_digest(
    *,
    descriptor_digest: str,
    source_commit: str,
    source_digest: str,
    parameters: Mapping[str, Any],
    state_snapshot_digest: str,
) -> str:
    payload = {
        "descriptor_digest": descriptor_digest,
        "source_commit": source_commit,
        "source_digest": source_digest,
        "parameters": dict(sorted(parameters.items())),
        "state_snapshot_digest": state_snapshot_digest,
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()
    return _sha256(encoded)


def compare_variant_identities(
    before: VariantIdentity, after: VariantIdentity
) -> ParameterDiff:
    if before.descriptor_digest != after.descriptor_digest:
        return ParameterDiff(
            classification="INCOMPARABLE_DESCRIPTOR_CHANGE",
            reason="agent descriptor digest differs",
        )
    if (
        before.source_commit != after.source_commit
        or before.source_digest != after.source_digest
    ):
        return ParameterDiff(
            classification="UNCLASSIFIED_CODE_CHANGE",
            reason="source commit or source digest differs",
        )
    if before.state_snapshot_digest != after.state_snapshot_digest:
        return ParameterDiff(
            classification="INCOMPARABLE_STATE_CHANGE",
            reason="initial state snapshot digest differs",
        )
    names = sorted(set(before.parameters) | set(after.parameters))
    differences = {
        name: {
            "before": before.parameters.get(name),
            "after": after.parameters.get(name),
        }
        for name in names
        if before.parameters.get(name) != after.parameters.get(name)
    }
    if len(differences) == 1:
        classification = "SINGLE_PARAMETER_CHANGE"
    elif not differences:
        classification = "NO_PARAMETER_CHANGE"
    else:
        classification = "MULTIPLE_PARAMETER_CHANGE"
    return ParameterDiff(classification=classification, differences=differences)


def _load_parameters(data: Any) -> dict[str, Parameter]:
    if not isinstance(data, dict):
        raise ValueError("[parameters] must contain parameter tables")
    parameters: dict[str, Parameter] = {}
    for name, item in data.items():
        _identifier(name, "parameter name")
        if not isinstance(item, dict):
            raise ValueError(f"parameters.{name} must be a table")
        parameter_type = item.get("type")
        if parameter_type not in PARAMETER_TYPES:
            raise ValueError(f"invalid parameter type for {name}: {parameter_type!r}")
        delivery = item.get("delivery")
        if delivery not in DELIVERY_TYPES:
            raise ValueError(f"invalid parameter delivery for {name}: {delivery!r}")
        flag = item.get("flag")
        env_name = item.get("name")
        if delivery == "argv" and (not isinstance(flag, str) or not flag.startswith("-")):
            raise ValueError(f"argv parameter {name} requires a flag")
        if delivery == "env" and (
            not isinstance(env_name, str)
            or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", env_name)
        ):
            raise ValueError(f"env parameter {name} requires an uppercase environment name")
        values = item.get("values", [])
        if parameter_type == "enum" and (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) for value in values)
        ):
            raise ValueError(f"enum parameter {name} requires string values")
        if "default" not in item:
            raise ValueError(f"parameter {name} requires a default")
        parameter = Parameter(
            name=name,
            type=parameter_type,
            default=item["default"],
            delivery=delivery,
            flag=flag,
            env_name=env_name,
            values=tuple(values),
            minimum=_optional_number(item.get("minimum"), f"parameters.{name}.minimum"),
            maximum=_optional_number(item.get("maximum"), f"parameters.{name}.maximum"),
        )
        parameter.validate(parameter.default)
        parameters[name] = parameter
    return parameters


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as source:
            return tomllib.load(source)
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file does not exist: {path}") from exc


def _require_table(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"missing or invalid [{name}] table")
    return value


def _require_schema(item: Mapping[str, Any], path: Path) -> None:
    version = item.get("schema_version", SCHEMA_VERSION)
    if str(version) != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema version in {path}: {version!r}")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must match {IDENTIFIER_PATTERN.pattern}")
    return value


def _relative_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    if Path(value).is_absolute():
        raise ValueError(f"{label} must be relative")
    return value


def _repository_path(repository: Path, value: Any, label: str) -> str:
    relative = _relative_string(value, label)
    resolved = (repository / relative).resolve()
    if not _is_within(resolved, repository):
        raise ValueError(f"{label} escapes source.repository")
    return resolved.relative_to(repository).as_posix()


def _path_list(repository: Path, value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(_repository_path(repository, item, label) for item in value)


def _glob_list(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    for pattern in value:
        path = Path(pattern)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{label} contains an unsafe pattern: {pattern!r}")
    return tuple(value)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _positive_number(value: Any, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be positive")
    return float(value)


def _positive_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _optional_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _sha256(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
