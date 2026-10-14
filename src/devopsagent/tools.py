"""Tools bound to a Harbor Trial environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class Environment(Protocol):
    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
        user: str | int | None = None,
    ) -> Any: ...


class Tool(Protocol):
    name: str

    def bedrock_spec(self) -> dict[str, Any]: ...

    async def execute(self, arguments: dict[str, Any]) -> str: ...


@dataclass
class ShellTool:
    """Execute a shell command inside the current Harbor environment."""

    environment: Environment
    timeout_seconds: int = 120
    max_output_chars: int = 50_000
    name: str = "shell"

    def bedrock_spec(self) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": self.name,
                "description": (
                    "Run a shell command in the isolated benchmark environment. "
                    "Use it to inspect files, execute programs, and modify the environment."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute.",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Optional working directory.",
                            },
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    }
                },
            }
        }

    async def execute(self, arguments: dict[str, Any]) -> str:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return "Error: command must be a non-empty string"

        cwd = arguments.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            return "Error: cwd must be a string"

        result = await self.environment.exec(
            command=command,
            cwd=cwd,
            timeout_sec=self.timeout_seconds,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        output = (
            f"exit_code: {result.return_code}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
        if len(output) > self.max_output_chars:
            omitted = len(output) - self.max_output_chars
            output = f"{output[: self.max_output_chars]}\n... <truncated {omitted} chars>"
        return output

