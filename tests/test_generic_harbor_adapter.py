from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harbor.models.agent.context import AgentContext
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from evaluation.generic_harbor_adapter import GenericCommandHarborAgent
from evaluation.host_environment import TrustedHostEnvironment


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def make_external_agent(tmp_path: Path) -> Path:
    repository = tmp_path / "external-agent"
    repository.mkdir()
    (repository / "agent.py").write_text(
        """
import asyncio
import json
import os
from pathlib import Path

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    request = json.loads(input())
    headers = json.loads(os.environ["AGENT_EVAL_MCP_HEADERS"])
    async with httpx2.AsyncClient(headers=headers) as http_client:
        async with streamable_http_client(
            os.environ["AGENT_EVAL_MCP_URL"], http_client=http_client
        ) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                result = await session.call_tool(
                    "environment_exec",
                    {"command": "printf 'HOST_OK\\\\n' > answer.txt"},
                )
                if result.is_error:
                    raise RuntimeError(str(result))
    result_path = Path(os.environ["AGENT_EVAL_RESULT"])
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({
        "schema_version": "0.2",
        "status": "completed",
        "final_text": request["task"]["instruction"],
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "source": "unavailable"
        },
        "artifacts": []
    }))


asyncio.run(main())
""".lstrip(),
        encoding="utf-8",
    )
    (repository / "agent.toml").write_text(
        f"""
[agent]
schema_version = "0.2"
id = "external-mcp-agent"
title = "External MCP Agent"

[source]
repository = "."
revision = "git"

[launcher]
adapter = "command"
command = [{json.dumps(sys.executable)}, "agent.py"]
input = "jsonl-stdin"
result = "json-file"
result_path = "run/result.json"
startup_timeout_seconds = 30
run_timeout_seconds = 30

[environment]
access = "mcp"
tools = ["environment_exec"]
tool_timeout_seconds = 20
max_output_chars = 4000

[state]
mode = "isolated-copy"
snapshot_paths = []
empty_paths = ["run"]

[artifacts]
paths = ["run/**"]

[capabilities]
structured_result = true
""".lstrip(),
        encoding="utf-8",
    )
    git(repository, "init", "-q")
    git(repository, "config", "user.email", "evaluation@example.invalid")
    git(repository, "config", "user.name", "Evaluation Test")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "external agent")
    commit = git(repository, "rev-parse", "HEAD")
    variant = repository / "baseline.toml"
    variant.write_text(
        f"""
[variant]
schema_version = "0.2"
id = "external-mcp-baseline"
agent = "agent.toml"

[source]
commit = "{commit}"
""".lstrip(),
        encoding="utf-8",
    )
    return variant


async def test_external_command_agent_operates_harbor_environment_via_mcp(
    tmp_path: Path,
):
    variant_path = make_external_agent(tmp_path)
    trial_paths = TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    environment = TrustedHostEnvironment(
        environment_dir=environment_dir,
        environment_name="external-agent-test",
        session_id="external-agent-session",
        trial_paths=trial_paths,
        task_env_config=EnvironmentConfig(workdir="/workspace"),
    )
    await environment.start(force_build=False)
    agent = GenericCommandHarborAgent(
        logs_dir=trial_paths.agent_dir,
        trial_paths=trial_paths,
        variant_path=str(variant_path),
    )
    context = AgentContext()

    await agent.setup(environment)
    await agent.run("write the required answer", environment, context)

    assert (environment.workspace / "answer.txt").read_text() == "HOST_OK\n"
    assert context.metadata is not None
    assert context.metadata["environment_access"] == "mcp"
    assert (trial_paths.agent_dir / "tool-calls.jsonl").exists()
    metadata = json.loads(
        (trial_paths.agent_dir / "agent-result.json").read_text()
    )
    assert metadata["exit_code"] == 0
    assert metadata["environment_tools"] == ["environment_exec"]


def test_harbor_runs_external_command_agent_through_mcp_gateway(tmp_path: Path):
    variant_path = make_external_agent(tmp_path)
    harbor = Path(sys.executable).with_name("harbor")
    jobs_dir = tmp_path / "jobs"

    completed = subprocess.run(
        [
            str(harbor),
            "run",
            "--path",
            "examples/tasks/hello-host-harbor",
            "--agent",
            "evaluation.generic_harbor_adapter:GenericCommandHarborAgent",
            "--ak",
            f"variant_path={variant_path}",
            "--env",
            "evaluation.host_environment:TrustedHostEnvironment",
            "--jobs-dir",
            str(jobs_dir),
            "--n-concurrent",
            "1",
            "--yes",
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(next(jobs_dir.glob("*/result.json")).read_text())
    assert result["stats"]["n_errored_trials"] == 0
    evaluation = next(iter(result["stats"]["evals"].values()))
    assert evaluation["metrics"][0]["mean"] == 1.0
