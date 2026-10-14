from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from devopsagent.runners.base import RunnerConfig
from devopsagent.runners.langchain import LangChainRunner


class ToolAwareFakeModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class RecordingClient:
    def __init__(self) -> None:
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"status": "success", "output": "exit_code: 0\nstdout:\ndone\nstderr:\n"}


@pytest.mark.asyncio
async def test_langchain_runner_uses_shared_tool_client():
    model = ToolAwareFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "shell",
                        "args": {"command": "touch /tmp/example"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            ),
            AIMessage(
                content="completed",
                usage_metadata={"input_tokens": 20, "output_tokens": 4, "total_tokens": 24},
            ),
        ]
    )
    client = RecordingClient()
    runner = LangChainRunner(RunnerConfig(max_steps=4), model=model)

    result = await runner.run("create a file", client)

    assert result.status == "completed"
    assert result.final_text == "completed"
    assert result.tool_calls == 1
    assert result.input_tokens == 30
    assert client.calls == [("shell", {"command": "touch /tmp/example"})]
