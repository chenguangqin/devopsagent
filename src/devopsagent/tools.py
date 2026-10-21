"""Framework-neutral tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from devopsagent.protocol import ToolClient
from devopsagent.runners.base import SHELL_TOOL_DESCRIPTION


class Tool(Protocol):
    name: str

    def bedrock_spec(self) -> dict[str, Any]: ...

    async def execute(self, arguments: dict[str, Any]) -> str: ...


@dataclass
class ShellTool:
    """Shell tool delegated to a local or remote tool client."""

    client: ToolClient
    name: str = "shell"

    def bedrock_spec(self) -> dict[str, Any]:
        return {
            "toolSpec": {
                "name": self.name,
                "description": SHELL_TOOL_DESCRIPTION,
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

        result = await asyncio.to_thread(
            self.client.call,
            self.name,
            {"command": command, **({"cwd": cwd} if cwd else {})},
        )
        output = result.get("output", "")
        if result.get("status") == "error" and not output.startswith("Error:"):
            return f"Error: {output}"
        return output

