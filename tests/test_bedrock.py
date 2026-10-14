from __future__ import annotations

import pytest

from devopsagent.bedrock import BedrockConverseAdapter


class RecordingClient:
    def __init__(self) -> None:
        self.request = None

    def converse(self, **request):
        self.request = request
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "ok"}],
                }
            },
            "stopReason": "end_turn",
            "usage": {},
        }


@pytest.mark.asyncio
async def test_bedrock_request_uses_haiku_compatible_inference_config():
    client = RecordingClient()
    adapter = BedrockConverseAdapter(
        model_id="global.anthropic.claude-haiku-5-5",
        region="us-west-2",
        max_tokens=256,
        client=client,
    )

    await adapter.converse(
        messages=[{"role": "user", "content": [{"text": "hello"}]}],
        tools=[],
        system_prompt="system",
    )

    assert client.request["modelId"] == "global.anthropic.claude-haiku-5-5"
    assert client.request["inferenceConfig"] == {"maxTokens": 256}
    assert "temperature" not in client.request["inferenceConfig"]
    assert "toolConfig" not in client.request

