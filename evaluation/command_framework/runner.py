"""Attempt workspace preparation and Generic Command Adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping

from evaluation.command_framework.models import (
    Variant,
    VariantIdentity,
    resolve_parameters,
    variant_digest,
)

STANDARD_ENV = {
    "AGENT_EVAL_RUN_ID",
    "AGENT_EVAL_INPUT",
    "AGENT_EVAL_RESULT",
    "AGENT_EVAL_ARTIFACT_DIR",
}
BASE_ENV_PASSTHROUGH = {
    "AWS_ACCESS_KEY_ID",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_CONFIG_FILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_PROFILE",
    "AWS_ROLE_ARN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
    "HOME",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "NO_PROXY",
    "PATH",
    "SYSTEMROOT",
    "TMPDIR",
    "USERPROFILE",
    "https_proxy",
    "http_proxy",
    "no_proxy",
}
RESULT_STATUSES = {"completed", "error"}
USAGE_SOURCES = {"agent-reported", "unavailable"}


@dataclass(frozen=True)
class AttemptResult:
    schema_version: str
    run_id: str
    variant_id: str
    variant_digest: str
    task_id: str
    attempt: int
    status: str
    failure_type: str | None
    exit_code: int | None
    runtime_seconds: float
    deadline_seconds: float
    deadline_exceeded: bool
    official_score: float | None
    diagnostic_verifier_result: Mapping[str, Any] | None
    agent_result: Mapping[str, Any] | None
    source: Mapping[str, Any]
    state: Mapping[str, Any]
    paths: Mapping[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PreparedSource:
    path: Path
    commit: str
    source_digest: str
    state_digest: str
    reproducible: bool
    reproducibility_reason: str | None


class CommandEvaluationRunner:
    """Run a fixed command-agent variant in isolated attempt workspaces."""

    def __init__(
        self,
        *,
        variant: Variant,
        run_dir: Path,
        run_id: str,
        verifier: Callable[[Path, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.variant = variant
        self.run_dir = run_dir.resolve()
        self.run_id = run_id
        self.verifier = verifier
        self.parameters = resolve_parameters(variant)
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._prepared = self._prepare_source()
        self.identity = self._build_identity()

    def run_attempt(
        self,
        *,
        task_id: str,
        instruction: str,
        attempt: int,
        deadline_seconds: float | None = None,
    ) -> AttemptResult:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        _safe_identifier(task_id, "task id")
        deadline = deadline_seconds or self.variant.descriptor.launcher.run_timeout_seconds
        if deadline <= 0:
            raise ValueError("deadline_seconds must be positive")
        attempt_dir = (
            self.run_dir / self.variant.id / task_id / f"attempt-{attempt}"
        )
        attempt_dir.mkdir(parents=True, exist_ok=False)
        agent_root = attempt_dir / "agent"
        input_dir = attempt_dir / "input"
        artifacts_dir = attempt_dir / "artifacts"
        logs_dir = attempt_dir / "logs"
        canonical_result_dir = attempt_dir / "result"
        for path in (input_dir, artifacts_dir, logs_dir, canonical_result_dir):
            path.mkdir()
        shutil.copytree(
            self._prepared.path,
            agent_root,
            symlinks=True,
            copy_function=shutil.copy2,
        )
        self._initialize_state(agent_root)
        self._validate_snapshot_symlinks(agent_root)

        declared_result_path = agent_root / self.variant.descriptor.launcher.result_path
        declared_result_path.parent.mkdir(parents=True, exist_ok=True)
        request_path = input_dir / "request.json"
        request = self._build_request(
            task_id=task_id,
            instruction=instruction,
            agent_root=agent_root,
            artifacts_dir=artifacts_dir,
            result_path=declared_result_path,
            deadline=deadline,
        )
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        metadata_path = attempt_dir / "metadata.json"
        self._write_metadata(
            metadata_path,
            {
                "status": "running",
                "request": request,
                "variant_identity": asdict(self.identity),
                "source": self._source_metadata(),
                "state": self._state_metadata(),
            },
        )

        command, environment = self._command_and_environment(
            request_path=request_path,
            declared_result_path=declared_result_path,
            artifacts_dir=artifacts_dir,
        )
        stdout_path = logs_dir / "stdout.log"
        stderr_path = logs_dir / "stderr.log"
        started = time.monotonic()
        exit_code, timed_out = self._run_process(
            command=command,
            cwd=agent_root,
            environment=environment,
            stdin_payload=json.dumps(request, ensure_ascii=False) + "\n",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=deadline,
            max_output_chars=self.variant.descriptor.launcher.max_output_chars,
        )
        runtime = time.monotonic() - started

        agent_result: dict[str, Any] | None = None
        result_error: str | None = None
        try:
            agent_result = self._read_agent_result(declared_result_path)
        except ValueError as exc:
            result_error = str(exc)
        artifact_error: str | None = None
        try:
            self._collect_artifacts(agent_root, artifacts_dir)
        except ValueError as exc:
            artifact_error = str(exc)

        diagnostic: Mapping[str, Any] | None = None
        if self.verifier is not None:
            try:
                diagnostic = dict(self.verifier(artifacts_dir, agent_result or {}))
            except Exception as exc:
                diagnostic = {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }

        status, failure_type = self._classify(
            timed_out=timed_out,
            exit_code=exit_code,
            agent_result=agent_result,
            result_error=result_error,
            artifact_error=artifact_error,
        )
        official_score = self._official_score(
            timed_out=timed_out,
            status=status,
            diagnostic=diagnostic,
        )
        canonical_result_path = canonical_result_dir / "result.json"
        if agent_result is not None:
            canonical_result_path.write_text(
                json.dumps(agent_result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        result = AttemptResult(
            schema_version="0.2",
            run_id=self.run_id,
            variant_id=self.variant.id,
            variant_digest=self.identity.digest,
            task_id=task_id,
            attempt=attempt,
            status=status,
            failure_type=failure_type,
            exit_code=exit_code,
            runtime_seconds=runtime,
            deadline_seconds=deadline,
            deadline_exceeded=timed_out,
            official_score=official_score,
            diagnostic_verifier_result=diagnostic,
            agent_result=agent_result,
            source=self._source_metadata(),
            state=self._state_metadata(),
            paths={
                "attempt": str(attempt_dir),
                "agent_root": str(agent_root),
                "artifact_dir": str(artifacts_dir),
                "result": str(canonical_result_path),
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            },
        )
        metadata = result.to_dict()
        if result_error:
            metadata["result_error"] = result_error
        if artifact_error:
            metadata["artifact_error"] = artifact_error
        self._write_metadata(metadata_path, metadata)
        return result

    def _prepare_source(self) -> _PreparedSource:
        descriptor = self.variant.descriptor
        git_root = Path(
            _git(descriptor.repository, ["rev-parse", "--show-toplevel"]).strip()
        ).resolve()
        if git_root != descriptor.repository:
            raise ValueError(
                "source.repository must resolve to the Git worktree root: "
                f"{git_root}"
            )
        commit = _git(
            descriptor.repository,
            ["rev-parse", "--verify", f"{self.variant.commit}^{{commit}}"],
        ).strip()
        tree = _git(
            descriptor.repository,
            ["rev-parse", "--verify", f"{commit}^{{tree}}"],
        ).strip()
        dirty = bool(
            _git(descriptor.repository, ["status", "--porcelain"], text=True).strip()
        )
        source_dir = self.run_dir / "_source"
        source_dir.mkdir()
        archive = subprocess.run(
            ["git", "-C", str(descriptor.repository), "archive", "--format=tar", commit],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if archive.returncode != 0:
            raise ValueError(
                f"unable to archive source commit {commit}: "
                f"{archive.stderr.decode(errors='replace').strip()}"
            )
        with tempfile.NamedTemporaryFile(suffix=".tar") as target:
            target.write(archive.stdout)
            target.flush()
            with tarfile.open(target.name) as source:
                source.extractall(source_dir, filter="data")
        self._validate_snapshot_symlinks(source_dir)
        return _PreparedSource(
            path=source_dir,
            commit=commit,
            source_digest=f"git-tree:{tree}",
            state_digest=_digest_paths(source_dir, descriptor.state.snapshot_paths),
            reproducible=not dirty,
            reproducibility_reason="dirty-worktree" if dirty else None,
        )

    def _build_identity(self) -> VariantIdentity:
        digest = variant_digest(
            descriptor_digest=self.variant.descriptor.digest,
            source_commit=self._prepared.commit,
            source_digest=self._prepared.source_digest,
            parameters=self.parameters,
            state_snapshot_digest=self._prepared.state_digest,
        )
        return VariantIdentity(
            variant_id=self.variant.id,
            digest=digest,
            descriptor_digest=self.variant.descriptor.digest,
            source_commit=self._prepared.commit,
            source_digest=self._prepared.source_digest,
            state_snapshot_digest=self._prepared.state_digest,
            parameters=dict(self.parameters),
        )

    def _initialize_state(self, agent_root: Path) -> None:
        for relative in self.variant.descriptor.state.empty_paths:
            target = agent_root / relative
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)

    def _build_request(
        self,
        *,
        task_id: str,
        instruction: str,
        agent_root: Path,
        artifacts_dir: Path,
        result_path: Path,
        deadline: float,
    ) -> dict[str, Any]:
        return {
            "schema_version": "0.2",
            "run_id": self.run_id,
            "variant": {
                "id": self.variant.id,
                "digest": self.identity.digest,
            },
            "task": {"id": task_id, "instruction": instruction},
            "agent_config": dict(self.parameters),
            "paths": {
                "agent_root": str(agent_root),
                "artifact_dir": str(artifacts_dir),
                "result_path": str(result_path),
            },
            "constraints": {"deadline_seconds": deadline},
        }

    def _command_and_environment(
        self,
        *,
        request_path: Path,
        declared_result_path: Path,
        artifacts_dir: Path,
    ) -> tuple[list[str], dict[str, str]]:
        command = list(self.variant.descriptor.launcher.command)
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in BASE_ENV_PASSTHROUGH
        }
        environment.update(
            {
                "AGENT_EVAL_RUN_ID": self.run_id,
                "AGENT_EVAL_INPUT": str(request_path),
                "AGENT_EVAL_RESULT": str(declared_result_path),
                "AGENT_EVAL_ARTIFACT_DIR": str(artifacts_dir),
            }
        )
        for name, parameter in self.variant.descriptor.parameters.items():
            value = self.parameters[name]
            formatted = _format_parameter(value)
            if parameter.delivery == "argv":
                assert parameter.flag is not None
                command.extend([parameter.flag, formatted])
            else:
                assert parameter.env_name is not None
                if parameter.env_name in STANDARD_ENV:
                    raise ValueError(
                        f"parameter {name} cannot override reserved environment variable "
                        f"{parameter.env_name}"
                    )
                environment[parameter.env_name] = formatted
        return command, environment

    @staticmethod
    def _run_process(
        *,
        command: list[str],
        cwd: Path,
        environment: Mapping[str, str],
        stdin_payload: str,
        stdout_path: Path,
        stderr_path: Path,
        timeout_seconds: float,
        max_output_chars: int,
    ) -> tuple[int | None, bool]:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=dict(environment),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            stderr_path.write_text(
                f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
            )
            stdout_path.write_bytes(b"")
            return None, False
        assert process.stdin and process.stdout and process.stderr
        stdout_thread = threading.Thread(
            target=_capture_stream,
            args=(process.stdout, stdout_path, max_output_chars),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_capture_stream,
            args=(process.stderr, stderr_path, max_output_chars),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            process.stdin.write(stdin_payload.encode())
            process.stdin.close()
        except BrokenPipeError:
            pass
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process)
        stdout_thread.join()
        stderr_thread.join()
        return process.returncode, timed_out

    @staticmethod
    def _read_agent_result(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ValueError(f"agent result file is missing: {path}")
        if path.is_symlink():
            raise ValueError("agent result file must not be a symbolic link")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"agent result is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("agent result must be a JSON object")
        if str(data.get("schema_version")) != "0.2":
            raise ValueError("agent result schema_version must be '0.2'")
        if data.get("status") not in RESULT_STATUSES:
            raise ValueError("agent result status must be completed or error")
        if not isinstance(data.get("final_text", ""), str):
            raise ValueError("agent result final_text must be a string")
        usage = data.get("usage")
        if not isinstance(usage, dict):
            raise ValueError("agent result usage must be an object")
        if usage.get("source") not in USAGE_SOURCES:
            raise ValueError("agent result usage.source is invalid")
        for name in ("input_tokens", "output_tokens"):
            value = usage.get(name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"agent result usage.{name} must be null or non-negative")
        if usage.get("source") == "unavailable" and any(
            usage.get(name) is not None for name in ("input_tokens", "output_tokens")
        ):
            raise ValueError("unavailable usage values must be null")
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, list) or not all(
            isinstance(item, str) for item in artifacts
        ):
            raise ValueError("agent result artifacts must be a string array")
        return data

    def _collect_artifacts(self, agent_root: Path, artifacts_dir: Path) -> None:
        copied: set[str] = set()
        for pattern in self.variant.descriptor.artifact_paths:
            for source in _artifact_matches(agent_root, pattern):
                if source.is_dir():
                    continue
                resolved = source.resolve()
                if not _is_within(resolved, agent_root):
                    raise ValueError(f"artifact escapes agent root: {source}")
                relative = source.relative_to(agent_root).as_posix()
                if relative in copied:
                    continue
                target = artifacts_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(resolved, target)
                copied.add(relative)

    @staticmethod
    def _classify(
        *,
        timed_out: bool,
        exit_code: int | None,
        agent_result: Mapping[str, Any] | None,
        result_error: str | None,
        artifact_error: str | None,
    ) -> tuple[str, str | None]:
        if timed_out:
            return "deadline_exceeded", "agent_failure"
        if exit_code is None or result_error or artifact_error:
            return "adapter_error", "adapter_failure"
        if exit_code != 0 or agent_result is None or agent_result.get("status") == "error":
            return "agent_error", "agent_failure"
        return "completed", None

    @staticmethod
    def _official_score(
        *,
        timed_out: bool,
        status: str,
        diagnostic: Mapping[str, Any] | None,
    ) -> float | None:
        if timed_out:
            return 0.0
        if status != "completed":
            return 0.0
        if diagnostic is None:
            return None
        score = diagnostic.get("score")
        if isinstance(score, int | float) and not isinstance(score, bool):
            return float(score)
        return None

    def _source_metadata(self) -> dict[str, Any]:
        return {
            "commit": self._prepared.commit,
            "digest": self._prepared.source_digest,
            "descriptor_digest": self.variant.descriptor.digest,
            "reproducible": self._prepared.reproducible,
            "reason": self._prepared.reproducibility_reason,
        }

    def _state_metadata(self) -> dict[str, Any]:
        return {
            "mode": self.variant.descriptor.state.mode,
            "snapshot_digest": self._prepared.state_digest,
            "snapshot_paths": list(self.variant.descriptor.state.snapshot_paths),
            "empty_paths": list(self.variant.descriptor.state.empty_paths),
        }

    @staticmethod
    def _write_metadata(path: Path, data: Mapping[str, Any]) -> None:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _validate_snapshot_symlinks(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_symlink() and not _is_within(path.resolve(), root):
                raise ValueError(f"source contains an external symbolic link: {path}")


def _git(repository: Path, args: list[str], *, text: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode(errors="replace")
        raise ValueError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return completed.stdout


def _digest_paths(root: Path, paths: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        digest.update(f"path:{relative}\0".encode())
        target = root / relative
        if not target.exists() and not target.is_symlink():
            digest.update(b"missing\0")
            continue
        entries = [target]
        if target.is_dir():
            entries.extend(sorted(target.rglob("*"), key=lambda item: item.as_posix()))
        for entry in entries:
            relative_entry = entry.relative_to(root).as_posix()
            if entry.is_symlink():
                kind = "symlink"
                content = os.readlink(entry).encode()
            elif entry.is_dir():
                kind = "directory"
                content = b""
            else:
                kind = "file"
                content = entry.read_bytes()
            digest.update(f"{kind}:{relative_entry}\0".encode())
            digest.update(content)
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _format_parameter(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _artifact_matches(agent_root: Path, pattern: str):
    if pattern.endswith("/**"):
        base = agent_root / pattern[:-3]
        if not base.exists():
            return ()
        return base.rglob("*")
    return agent_root.glob(pattern)


def _capture_stream(stream: BinaryIO, path: Path, limit: int) -> None:
    written = 0
    truncated = False
    with path.open("wb") as target:
        while chunk := stream.read(64 * 1024):
            remaining = max(0, limit - written)
            if remaining:
                target.write(chunk[:remaining])
                written += min(len(chunk), remaining)
            if len(chunk) > remaining:
                truncated = True
        if truncated:
            marker = b"\n[output truncated by evaluation harness]\n"
            if written + len(marker) <= limit:
                target.write(marker)


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait()


def _safe_identifier(value: str, label: str) -> None:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in value):
        raise ValueError(f"{label} contains unsafe characters: {value!r}")


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
