from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from devopsagent.loop import AgentLoop, LoopConfig


class ScriptedProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def converse(self, messages, tools, system_prompt):
        self.requests.append(
            {
                "messages": deepcopy(messages),
                "tools": deepcopy(tools),
                "system_prompt": system_prompt,
            }
        )
        return self.responses.pop(0)


class RecordingTool:
    name = "shell"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def bedrock_spec(self):
        return {
            "toolSpec": {
                "name": "shell",
                "description": "Run shell.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    }
                },
            }
        }

    async def execute(self, arguments):
        self.calls.append(arguments)
        return "exit_code: 0\nstdout:\ndone\nstderr:\n"


@pytest.mark.asyncio
async def test_loop_executes_tool_and_returns_final_text():
    provider = ScriptedProvider(
        [
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "toolUse": {
                                    "toolUseId": "tool-1",
                                    "name": "shell",
                                    "input": {"command": "touch /app/hello.txt"},
                                }
                            }
                        ],
                    }
                },
                "stopReason": "tool_use",
                "usage": {"inputTokens": 20, "outputTokens": 10},
            },
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": "Task completed and verified."}],
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 30, "outputTokens": 8},
            },
        ]
    )
    tool = RecordingTool()
    loop = AgentLoop(
        provider=provider,
        tools=[tool],
        config=LoopConfig(max_steps=4),
    )

    result = await loop.run("Create /app/hello.txt")

    assert result.status == "completed"
    assert result.steps == 2
    assert result.tool_calls == 1
    assert result.final_text == "Task completed and verified."
    assert result.input_tokens == 50
    assert result.output_tokens == 18
    assert tool.calls == [{"command": "touch /app/hello.txt"}]

    second_request_messages = provider.requests[1]["messages"]
    assert second_request_messages[-1]["content"][0]["toolResult"]["status"] == "success"


@pytest.mark.asyncio
async def test_loop_stops_at_max_steps():
    responses = [
        {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": f"tool-{index}",
                                "name": "shell",
                                "input": {"command": "true"},
                            }
                        }
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {},
        }
        for index in range(2)
    ]
    loop = AgentLoop(
        provider=ScriptedProvider(responses),
        tools=[RecordingTool()],
        config=LoopConfig(max_steps=2),
    )

    result = await loop.run("Keep working")

    assert result.status == "max_steps"
    assert result.steps == 2
    assert result.tool_calls == 2

