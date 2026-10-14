"""Agent implemented with the Strands Agents SDK."""

from __future__ import annotations

import asyncio
from typing import Any

from devopsagent.protocol import ToolClient
from devopsagent.result import AgentResult
from devopsagent.runners.base import RunnerConfig


class StrandsRunner:
    def __init__(self, config: RunnerConfig, model: Any | None = None) -> None:
        self.config = config
        self.model = model

    async def run(self, instruction: str, tool_client: ToolClient) -> AgentResult:
        return await asyncio.to_thread(self._run_sync, instruction, tool_client)

    def _run_sync(self, instruction: str, tool_client: ToolClient) -> AgentResult:
        try:
            from strands import Agent, tool
            from strands.models import BedrockModel
            from strands.types.agent import Limits
        except ImportError as exc:
            raise RuntimeError(
                "Strands dependencies are missing; install devopsagent[strands]"
            ) from exc

        calls: list[dict[str, Any]] = []

        @tool
        def shell(command: str, cwd: str | None = None) -> str:
            """Run a shell command in the task environment."""
            arguments = {"command": command, **({"cwd": cwd} if cwd else {})}
            response = tool_client.call("shell", arguments)
            calls.append({"name": "shell", "arguments": arguments})
            output = str(response.get("output", ""))
            return f"Error: {output}" if response.get("status") == "error" else output

        model = self.model or BedrockModel(
            model_id=self.config.model_id,
            region_name=self.config.region,
            max_tokens=self.config.max_tokens,
        )
        agent = Agent(
            model=model,
            tools=[shell],
            system_prompt=self.config.system_prompt,
            callback_handler=None,
            name="devopsagent-strands",
        )
        sdk_result = agent(
            instruction,
            limits=Limits(turns=self.config.max_steps),
        )

        metrics = getattr(sdk_result, "metrics", None)
        usage = getattr(metrics, "accumulated_usage", {}) if metrics else {}
        stop_reason = str(getattr(sdk_result, "stop_reason", "end_turn"))
        status = "max_steps" if stop_reason.startswith("limit_") else "completed"
        return AgentResult(
            status=status,
            final_text=str(sdk_result).strip(),
            steps=int(getattr(metrics, "cycle_count", 0) or 0),
            tool_calls=len(calls),
            input_tokens=int(_usage_value(usage, "inputTokens", "input_tokens")),
            output_tokens=int(_usage_value(usage, "outputTokens", "output_tokens")),
            cache_read_tokens=int(
                _usage_value(usage, "cacheReadInputTokens", "cache_read_input_tokens")
            ),
            cache_write_tokens=int(
                _usage_value(usage, "cacheWriteInputTokens", "cache_write_input_tokens")
            ),
            trace=[{"stop_reason": stop_reason, "tool_calls": calls}],
        )


def _usage_value(usage: Any, *names: str) -> int:
    for name in names:
        if isinstance(usage, dict) and name in usage:
            return int(usage[name] or 0)
        value = getattr(usage, name, None)
        if value is not None:
            return int(value)
    return 0
