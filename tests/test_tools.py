from __future__ import annotations

from dataclasses import dataclass

import pytest

from devopsagent.tools import ShellTool


@dataclass
class Result:
    stdout: str | None
    stderr: str | None
    return_code: int


class FakeEnvironment:
    def __init__(self) -> None:
        self.calls = []

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "timeout_sec": timeout_sec,
                "user": user,
            }
        )
        return Result(stdout="hello\n", stderr="", return_code=0)


@pytest.mark.asyncio
async def test_shell_tool_executes_inside_environment():
    environment = FakeEnvironment()
    tool = ShellTool(environment=environment, timeout_seconds=33)

    output = await tool.execute({"command": "pwd", "cwd": "/app"})

    assert "exit_code: 0" in output
    assert "hello" in output
    assert environment.calls == [
        {
            "command": "pwd",
            "cwd": "/app",
            "timeout_sec": 33,
            "user": None,
        }
    ]

