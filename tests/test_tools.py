from __future__ import annotations

import pytest

from devopsagent.tools import ShellTool


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def call(self, name, arguments):
        self.calls.append({"name": name, "arguments": arguments})
        return {
            "type": "tool_result",
            "status": "success",
            "output": "exit_code: 0\nstdout:\nhello\nstderr:\n",
        }


@pytest.mark.asyncio
async def test_shell_tool_delegates_to_tool_client():
    client = FakeClient()
    tool = ShellTool(client=client)

    output = await tool.execute({"command": "pwd", "cwd": "/app"})

    assert "exit_code: 0" in output
    assert "hello" in output
    assert client.calls == [
        {
            "name": "shell",
            "arguments": {"command": "pwd", "cwd": "/app"},
        }
    ]

