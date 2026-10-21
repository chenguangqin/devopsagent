"""The minimal model → tool → result agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devopsagent.bedrock import ConverseProvider
from devopsagent.runners.base import budget_note
from devopsagent.tools import Tool


@dataclass(frozen=True)
class LoopConfig:
    max_steps: int = 12
    system_prompt: str = (
        "You are a DevOps agent operating in an isolated benchmark environment. "
        "Use the available tools to inspect the environment and complete the task. "
        "Act on the environment instead of merely explaining. Verify your work before finishing."
    )


@dataclass
class LoopResult:
    status: str
    steps: int
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_calls: int = 0
    trace: list[dict[str, Any]] = field(default_factory=list)


class AgentLoop:
    def __init__(
        self,
        *,
        provider: ConverseProvider,
        tools: list[Tool],
        config: LoopConfig,
    ) -> None:
        self.provider = provider
        self.tools = {tool.name: tool for tool in tools}
        self.config = config

    async def run(self, instruction: str) -> LoopResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": instruction}]}
        ]
        result = LoopResult(status="running", steps=0)
        tool_specs = [tool.bedrock_spec() for tool in self.tools.values()]

        for step in range(1, self.config.max_steps + 1):
            response = await self.provider.converse(
                messages=messages,
                tools=tool_specs,
                system_prompt=self.config.system_prompt,
            )
            result.steps = step
            self._accumulate_usage(result, response.get("usage", {}))

            message = response["output"]["message"]
            content = message.get("content", [])
            messages.append({"role": "assistant", "content": content})

            text = "\n".join(
                block["text"] for block in content if isinstance(block.get("text"), str)
            ).strip()
            if text:
                result.final_text = text

            tool_uses = [
                block["toolUse"]
                for block in content
                if isinstance(block.get("toolUse"), dict)
            ]
            result.trace.append(
                {
                    "step": step,
                    "stop_reason": response.get("stopReason"),
                    "text": text,
                    "tool_names": [call.get("name") for call in tool_uses],
                }
            )

            if response.get("stopReason") != "tool_use" or not tool_uses:
                result.status = "completed"
                return result

            tool_results = []
            for call in tool_uses:
                result.tool_calls += 1
                tool_name = call.get("name", "")
                tool = self.tools.get(tool_name)
                if tool is None:
                    output = f"Error: unknown tool {tool_name!r}"
                    status = "error"
                else:
                    try:
                        output = await tool.execute(call.get("input", {}))
                        status = "error" if output.startswith("Error:") else "success"
                    except Exception as exc:  # keep the loop alive on tool failure
                        output = f"Error: {type(exc).__name__}: {exc}"
                        status = "error"
                output += budget_note(step, self.config.max_steps)

                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": call["toolUseId"],
                            "content": [{"text": output}],
                            "status": status,
                        }
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        result.status = "max_steps"
        return result

    @staticmethod
    def _accumulate_usage(result: LoopResult, usage: dict[str, Any]) -> None:
        result.input_tokens += int(usage.get("inputTokens", 0))
        result.output_tokens += int(usage.get("outputTokens", 0))
        result.cache_read_tokens += int(usage.get("cacheReadInputTokens", 0))
        result.cache_write_tokens += int(usage.get("cacheWriteInputTokens", 0))

