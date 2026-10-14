"""Agent loop built directly on the Bedrock Converse API."""

from __future__ import annotations

from devopsagent.bedrock import BedrockConverseAdapter, ConverseProvider
from devopsagent.loop import AgentLoop, LoopConfig
from devopsagent.protocol import ToolClient
from devopsagent.result import AgentResult
from devopsagent.runners.base import RunnerConfig
from devopsagent.tools import ShellTool


class NativeRunner:
    def __init__(
        self,
        config: RunnerConfig,
        provider: ConverseProvider | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or BedrockConverseAdapter(
            model_id=config.model_id,
            region=config.region,
            max_tokens=config.max_tokens,
        )

    async def run(self, instruction: str, tool_client: ToolClient) -> AgentResult:
        loop = AgentLoop(
            provider=self.provider,
            tools=[ShellTool(client=tool_client)],
            config=LoopConfig(
                max_steps=self.config.max_steps,
                system_prompt=self.config.system_prompt,
            ),
        )
        result = await loop.run(instruction)
        return AgentResult(
            status=result.status,
            final_text=result.final_text,
            steps=result.steps,
            tool_calls=result.tool_calls,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_write_tokens=result.cache_write_tokens,
            trace=result.trace,
        )
