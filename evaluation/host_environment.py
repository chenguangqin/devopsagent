"""Trusted host-process Harbor environment for local smoke tests only."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Mapping

from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities


class TrustedHostEnvironment(BaseEnvironment):
    """Run trusted Harbor task commands in a per-trial host directory.

    This environment intentionally provides no container, resource, or network
    isolation. It is only suitable for repository-owned smoke tests.
    """

    @staticmethod
    def type() -> str:
        return "trusted-host"

    @property
    def capabilities(self) -> EnvironmentCapabilities:
        return EnvironmentCapabilities(mounted=True)

    def _validate_definition(self) -> None:
        forbidden = ("Dockerfile", "docker-compose.yaml", "docker-compose.yml")
        present = [name for name in forbidden if (self.environment_dir / name).exists()]
        if present:
            raise ValueError(
                "TrustedHostEnvironment does not accept container definitions: "
                + ", ".join(present)
            )

    @property
    def root(self) -> Path:
        return self.trial_paths.trial_dir.resolve() / "host-environment"

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    async def start(self, force_build: bool) -> None:
        if force_build:
            self.logger.debug("force_build has no effect for TrustedHostEnvironment")
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.root / "tests").mkdir(parents=True, exist_ok=True)
        (self.root / "solution").mkdir(parents=True, exist_ok=True)
        (self.root / "harbor" / "skills").mkdir(parents=True, exist_ok=True)
        self._link_log_dir("agent", self.trial_paths.agent_dir)
        self._link_log_dir("verifier", self.trial_paths.verifier_dir)
        self._link_log_dir("artifacts", self.trial_paths.artifacts_dir)

    async def stop(self, delete: bool) -> None:
        if delete and self.root.exists():
            shutil.rmtree(self.root)

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        source = Path(source_path)
        target = self._map_path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    async def upload_dir(self, source_dir: Path | str, target_dir: str) -> None:
        source = Path(source_dir)
        target = self._map_path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)

    async def download_file(
        self, source_path: str, target_path: Path | str
    ) -> None:
        source = self._map_path(source_path)
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)

    async def download_dir(
        self, source_dir: str, target_dir: Path | str
    ) -> None:
        source = self._map_path(source_dir)
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            shutil.copytree(source, target, dirs_exist_ok=True)

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> ExecResult:
        if user not in (None, "root", os.getuid(), str(os.getuid())):
            return ExecResult(
                return_code=1,
                stderr=f"TrustedHostEnvironment cannot switch to user {user!r}",
            )
        mapped_command = self._rewrite_virtual_paths(command)
        working_directory = self._map_cwd(cwd)
        process_env = {
            **os.environ,
            **self._persistent_env,
            **self._current_exec_env(),
            **(env or {}),
        }
        process = await asyncio.create_subprocess_shell(
            mapped_command,
            cwd=working_directory,
            env=process_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            executable="/bin/bash",
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_sec
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return ExecResult(
                return_code=124,
                stderr=f"command timed out after {timeout_sec} seconds",
            )
        return ExecResult(
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            return_code=process.returncode or 0,
        )

    def _current_exec_env(self) -> dict[str, str]:
        overlays: Mapping[str, str] = {}
        for overlay in self._exec_env_overlays.get():
            overlays = {**overlays, **overlay}
        return dict(overlays)

    def _map_cwd(self, cwd: str | None) -> Path:
        if cwd is None:
            configured = self.task_env_config.workdir or "/workspace"
            return self._map_path(configured)
        path = PurePosixPath(cwd)
        if path.is_absolute():
            return self._map_path(cwd)
        target = (self.workspace / path.as_posix()).resolve()
        self._require_within(target, self.workspace)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _map_path(self, value: str | Path) -> Path:
        path = PurePosixPath(str(value))
        if not path.is_absolute():
            target = (self.workspace / path.as_posix()).resolve()
            self._require_within(target, self.workspace)
            return target
        mappings = {
            PurePosixPath("/workspace"): self.workspace,
            PurePosixPath("/tests"): self.root / "tests",
            PurePosixPath("/solution"): self.root / "solution",
            PurePosixPath("/harbor"): self.root / "harbor",
            PurePosixPath("/logs/agent"): self.trial_paths.agent_dir.resolve(),
            PurePosixPath("/logs/verifier"): self.trial_paths.verifier_dir.resolve(),
            PurePosixPath("/logs/artifacts"): self.trial_paths.artifacts_dir.resolve(),
        }
        for virtual, host in sorted(
            mappings.items(), key=lambda item: len(item[0].parts), reverse=True
        ):
            try:
                relative = path.relative_to(virtual)
            except ValueError:
                continue
            target = (host / relative.as_posix()).resolve()
            self._require_within(target, host.resolve())
            return target
        raise ValueError(f"unsupported host-environment path: {value}")

    def _rewrite_virtual_paths(self, command: str) -> str:
        replacements = {
            "/logs/artifacts": str(self.trial_paths.artifacts_dir.resolve()),
            "/logs/verifier": str(self.trial_paths.verifier_dir.resolve()),
            "/logs/agent": str(self.trial_paths.agent_dir.resolve()),
            "/workspace": str(self.workspace),
            "/solution": str(self.root / "solution"),
            "/tests": str(self.root / "tests"),
            "/harbor": str(self.root / "harbor"),
        }
        rewritten = command
        for virtual, host in replacements.items():
            rewritten = rewritten.replace(virtual, host)
        return rewritten

    def _link_log_dir(self, name: str, target: Path) -> None:
        target = target.resolve()
        target.mkdir(parents=True, exist_ok=True)
        logs_dir = self.root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        link = logs_dir / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=True)

    @staticmethod
    def _require_within(path: Path, parent: Path) -> None:
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise ValueError(f"path escapes trusted host root: {path}") from exc
