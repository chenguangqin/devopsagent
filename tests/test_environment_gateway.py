from pathlib import Path

import httpx2
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from evaluation.environment_gateway import EnvironmentMCPGateway, ToolRegistry
from evaluation.host_environment import TrustedHostEnvironment


def make_environment(tmp_path: Path) -> TrustedHostEnvironment:
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    trial_paths = TrialPaths(tmp_path / "trial")
    trial_paths.mkdir()
    return TrustedHostEnvironment(
        environment_dir=environment_dir,
        environment_name="gateway-test",
        session_id="gateway-test-session",
        trial_paths=trial_paths,
        task_env_config=EnvironmentConfig(workdir="/workspace"),
    )


async def test_mcp_gateway_executes_in_harbor_environment(tmp_path: Path):
    environment = make_environment(tmp_path)
    await environment.start(force_build=False)
    registry = ToolRegistry(
        environment=environment,
        allowed_tools=("environment_exec",),
        timeout_seconds=30,
        max_output_chars=4000,
        trace_path=tmp_path / "tool-calls.jsonl",
    )
    gateway = EnvironmentMCPGateway(registry)
    await gateway.start()
    assert gateway.url is not None

    http_client = httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {gateway.token}"}
    )
    try:
        async with (
            http_client,
            streamable_http_client(
                gateway.url, http_client=http_client
            ) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(
                "environment_exec",
                {"command": "printf 'MCP_OK\\n' > gateway.txt"},
            )
    finally:
        await gateway.stop()

    assert [tool.name for tool in tools.tools] == ["environment_exec"]
    assert result.is_error is False
    assert (environment.workspace / "gateway.txt").read_text() == "MCP_OK\n"
    trace = (tmp_path / "tool-calls.jsonl").read_text()
    assert '"name":"environment_exec"' in trace
    assert '"status":"success"' in trace


async def test_mcp_gateway_rejects_missing_token(tmp_path: Path):
    environment = make_environment(tmp_path)
    await environment.start(force_build=False)
    registry = ToolRegistry(
        environment=environment,
        allowed_tools=("environment_exec",),
        timeout_seconds=30,
        max_output_chars=4000,
        trace_path=tmp_path / "tool-calls.jsonl",
    )
    gateway = EnvironmentMCPGateway(registry)
    await gateway.start()
    assert gateway.url is not None

    try:
        async with httpx2.AsyncClient() as client:
            response = await client.post(gateway.url, json={})
    finally:
        await gateway.stop()

    assert response.status_code == 401


async def test_tool_trace_redacts_secret_values(
    tmp_path: Path, monkeypatch
):
    secret = "workshop-secret-value"
    monkeypatch.setenv("WORKSHOP_SECRET_TOKEN", secret)
    environment = make_environment(tmp_path)
    await environment.start(force_build=False)
    trace_path = tmp_path / "tool-calls.jsonl"
    registry = ToolRegistry(
        environment=environment,
        allowed_tools=("environment_exec",),
        timeout_seconds=30,
        max_output_chars=4000,
        trace_path=trace_path,
    )

    await registry.call(
        "environment_exec",
        {"command": f"printf '%s' '{secret}' >/dev/null"},
    )

    trace = trace_path.read_text()
    assert secret not in trace
    assert "[REDACTED]" in trace
