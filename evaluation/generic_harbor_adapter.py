"""Harbor adapter for complete external command agents using an MCP gateway."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import TrialPaths
from pydantic import Field

from evaluation.command_framework.models import (
    Variant,
    load_variant,
    resolve_parameters,
)
from evaluation.command_framework.runner import (
    BASE_ENV_PASSTHROUGH,
    STANDARD_ENV,
)
from evaluation.environment_gateway import EnvironmentMCPGateway, ToolRegistry


class GenericCommandAgentOptions(AgentOptions):
    variant_path: str = Field(
        description="Absolute or current-working-directory-relative Variant TOML."
    )


class GenericCommandHarborAgent(BaseAgent):
    """Launch a pinned external Agent and bridge its MCP tools to Harbor."""

    options_model = GenericCommandAgentOptions

    @staticmethod
    def name() -> str:
        return "generic-command-agent"

    def version(self) -> str:
        return "0.3.0"

    def __init__(
        self,
        logs_dir: Path,
        trial_paths: TrialPaths | None = None,
        **kwargs: Any,
    ) -> None:
        # Harbor passes paths relative to its --jobs-dir; the external agent runs
        # with cwd=workspace, so every path handed to it must be absolute.
        logs_dir = logs_dir.resolve()
        super().__init__(logs_dir=logs_dir, **kwargs)
        self.trial_paths = trial_paths or TrialPaths(logs_dir.parent)
        self.variant: Variant | None = None
        self.workspace = self.logs_dir / "workspace"

    async def setup(self, environment: BaseEnvironment) -> None:
        options = self.options
        assert isinstance(options, GenericCommandAgentOptions)
        variant_path = Path(options.variant_path)
        if not variant_path.is_absolute():
            variant_path = Path.cwd() / variant_path
        self.variant = load_variant(variant_path)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._prepare_workspace(self.variant)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if self.variant is None:
            raise RuntimeError("generic command agent was not set up")
        variant = self.variant
        descriptor = variant.descriptor
        parameters = resolve_parameters(variant)
        result_path = self.workspace / descriptor.launcher.result_path
        result_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_dir = self.logs_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        request = {
            "schema_version": "0.2",
            "run_id": self.trial_paths.trial_dir.name,
            "variant": {"id": variant.id},
            "task": {"id": self.trial_paths.trial_dir.name, "instruction": instruction},
            "agent_config": parameters,
            "paths": {
                "agent_root": str(self.workspace),
                "artifact_dir": str(artifact_dir),
                "result_path": str(result_path),
            },
            "constraints": {
                "deadline_seconds": descriptor.launcher.run_timeout_seconds
            },
        }
        environment_variables = self._build_environment(
            variant=variant,
            result_path=result_path,
            artifact_dir=artifact_dir,
            parameters=parameters,
        )
        command = self._build_command(variant, parameters)
        gateway: EnvironmentMCPGateway | None = None
        if descriptor.environment.mode == "mcp":
            registry = ToolRegistry(
                environment=environment,
                allowed_tools=descriptor.environment.tools,
                timeout_seconds=descriptor.environment.tool_timeout_seconds,
                max_output_chars=descriptor.environment.max_output_chars,
                trace_path=self.logs_dir / "tool-calls.jsonl",
            )
            gateway = EnvironmentMCPGateway(registry)
            await gateway.start()
            assert gateway.url is not None
            environment_variables.update(
                {
                    "AGENT_EVAL_MCP_TRANSPORT": "streamable-http",
                    "AGENT_EVAL_MCP_URL": gateway.url,
                    "AGENT_EVAL_MCP_TOKEN": gateway.token,
                    "AGENT_EVAL_MCP_HEADERS": json.dumps(
                        {"Authorization": f"Bearer {gateway.token}"}
                    ),
                }
            )

        try:
            exit_code = await self._run_process(
                command=command,
                request=request,
                environment=environment_variables,
                timeout_seconds=descriptor.launcher.run_timeout_seconds,
                max_output_chars=descriptor.launcher.max_output_chars,
            )
        finally:
            if gateway is not None:
                await gateway.stop()

        result = self._read_result(result_path)
        self._collect_artifacts(variant, artifact_dir)
        self._write_metadata(variant, parameters, result, exit_code)
        self._update_context(context, result, variant)
        if exit_code != 0:
            raise RuntimeError(f"external agent exited with status {exit_code}")
        if result.get("status") == "error":
            raise RuntimeError(str(result.get("error", "external agent failed")))

    def _prepare_workspace(self, variant: Variant) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True)
        commit = self._git(
            variant.descriptor.repository,
            ["rev-parse", "--verify", f"{variant.commit}^{{commit}}"],
        ).strip()
        archive = subprocess.run(
            [
                "git",
                "-C",
                str(variant.descriptor.repository),
                "archive",
                "--format=tar",
                commit,
            ],
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
                source.extractall(self.workspace, filter="data")
        self._validate_workspace_symlinks()
        for relative in variant.descriptor.state.empty_paths:
            target_path = self.workspace / relative
            if target_path.is_file() or target_path.is_symlink():
                target_path.unlink()
            elif target_path.exists():
                shutil.rmtree(target_path)
            target_path.mkdir(parents=True)

    @staticmethod
    def _build_command(
        variant: Variant, parameters: dict[str, str | int | float | bool]
    ) -> list[str]:
        command = list(variant.descriptor.launcher.command)
        for name, parameter in variant.descriptor.parameters.items():
            if parameter.delivery == "argv":
                assert parameter.flag is not None
                command.extend([parameter.flag, _format_value(parameters[name])])
        return command

    @staticmethod
    def _build_environment(
        *,
        variant: Variant,
        result_path: Path,
        artifact_dir: Path,
        parameters: dict[str, str | int | float | bool],
    ) -> dict[str, str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in BASE_ENV_PASSTHROUGH
        }
        environment.update(
            {
                "AGENT_EVAL_RUN_ID": variant.id,
                "AGENT_EVAL_RESULT": str(result_path),
                "AGENT_EVAL_ARTIFACT_DIR": str(artifact_dir),
            }
        )
        for name, parameter in variant.descriptor.parameters.items():
            if parameter.delivery != "env":
                continue
            assert parameter.env_name is not None
            if parameter.env_name in STANDARD_ENV:
                raise ValueError(
                    f"parameter {name} overrides reserved environment variable"
                )
            environment[parameter.env_name] = _format_value(parameters[name])
        return environment

    async def _run_process(
        self,
        *,
        command: list[str],
        request: dict[str, Any],
        environment: dict[str, str],
        timeout_seconds: float,
        max_output_chars: int,
    ) -> int:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.workspace,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(
                    json.dumps(request, ensure_ascii=False).encode() + b"\n"
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            raise TimeoutError(
                f"external agent exceeded {timeout_seconds} seconds"
            ) from None
        self._write_capped(self.logs_dir / "stdout.log", stdout, max_output_chars)
        self._write_capped(self.logs_dir / "stderr.log", stderr, max_output_chars)
        return process.returncode or 0

    @staticmethod
    def _read_result(path: Path) -> dict[str, Any]:
        if not path.exists() or path.is_symlink():
            raise ValueError(f"external agent result is missing or unsafe: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != "0.2":
            raise ValueError("external agent result must use schema_version 0.2")
        if data.get("status") not in {"completed", "error"}:
            raise ValueError("external agent result has invalid status")
        return data

    def _collect_artifacts(self, variant: Variant, artifact_dir: Path) -> None:
        for pattern in variant.descriptor.artifact_paths:
            matches = (
                (self.workspace / pattern[:-3]).rglob("*")
                if pattern.endswith("/**")
                else self.workspace.glob(pattern)
            )
            for source in matches:
                if not source.is_file() or source.is_symlink():
                    continue
                relative = source.relative_to(self.workspace)
                target = artifact_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _write_metadata(
        self,
        variant: Variant,
        parameters: dict[str, str | int | float | bool],
        result: dict[str, Any],
        exit_code: int,
    ) -> None:
        metadata = {
            "variant": variant.id,
            "descriptor": str(variant.descriptor.path),
            "source_commit": self._git(
                variant.descriptor.repository,
                ["rev-parse", "--verify", f"{variant.commit}^{{commit}}"],
            ).strip(),
            "environment_access": variant.descriptor.environment.mode,
            "environment_tools": list(variant.descriptor.environment.tools),
            "parameters": parameters,
            "exit_code": exit_code,
            "result": result,
        }
        (self.logs_dir / "agent-result.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _validate_workspace_symlinks(self) -> None:
        root = self.workspace.resolve()
        for path in self.workspace.rglob("*"):
            if not path.is_symlink():
                continue
            try:
                path.resolve().relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"source contains an external symbolic link: {path}"
                ) from exc

    @staticmethod
    def _write_capped(path: Path, content: bytes, limit: int) -> None:
        if len(content) <= limit:
            path.write_bytes(content)
            return
        marker = b"\n[output truncated by evaluation harness]\n"
        retained = max(0, limit - len(marker))
        path.write_bytes(content[:retained] + marker)

    @staticmethod
    def _update_context(
        context: AgentContext, result: dict[str, Any], variant: Variant
    ) -> None:
        usage = result.get("usage", {})
        context.n_input_tokens = usage.get("input_tokens")
        context.n_output_tokens = usage.get("output_tokens")
        context.n_cache_tokens = usage.get("cache_read_tokens")
        context.metadata = {
            "variant": variant.id,
            "status": result.get("status"),
            "final_text": result.get("final_text", ""),
            "environment_access": variant.descriptor.environment.mode,
        }

    @staticmethod
    def _git(repository: Path, args: list[str]) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"git {' '.join(args)} failed: {completed.stderr.strip()}"
            )
        return completed.stdout


def _format_value(value: str | int | float | bool) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
