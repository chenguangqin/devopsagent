"""Agent implemented with LangChain."""

from __future__ import annotations

import asyncio
from typing import Any

from devopsagent.protocol import ToolClient
from devopsagent.result import AgentResult
from devopsagent.runners.base import RunnerConfig


class LangChainRunner:
    def __init__(self, config: RunnerConfig, model: Any | None = None) -> None:
        self.config = config
        self.model = model

    async def run(self, instruction: str, tool_client: ToolClient) -> AgentResult:
        return await asyncio.to_thread(self._run_sync, instruction, tool_client)

    def _run_sync(self, instruction: str, tool_client: ToolClient) -> AgentResult:
        try:
            from langchain.agents import create_agent
            from langchain_aws import ChatBedrockConverse
            from langchain_core.messages import AIMessage
            from langchain_core.tools import tool
            from langgraph.errors import GraphRecursionError
        except ImportError as exc:
            raise RuntimeError(
                "LangChain dependencies are missing; install devopsagent[langchain]"
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

        model = self.model or ChatBedrockConverse(
            model=self.config.model_id,
            region_name=self.config.region,
            max_tokens=self.config.max_tokens,
        )
        agent = create_agent(
            model=model,
            tools=[shell],
            system_prompt=self.config.system_prompt,
            name="devopsagent-langchain",
        )
        try:
            state = agent.invoke(
                {"messages": [{"role": "user", "content": instruction}]},
                config={"recursion_limit": self.config.max_steps * 2 + 2},
            )
        except GraphRecursionError:
            return AgentResult(
                status="max_steps",
                steps=self.config.max_steps,
                tool_calls=len(calls),
                trace=[{"tool_calls": calls}],
            )

        input_tokens = output_tokens = cache_read = cache_write = 0
        final_text = ""
        ai_steps = 0
        trace: list[dict[str, Any]] = []
        for message in state.get("messages", []):
            if not isinstance(message, AIMessage):
                continue
            ai_steps += 1
            usage = message.usage_metadata or {}
            input_tokens += int(usage.get("input_tokens", 0))
            output_tokens += int(usage.get("output_tokens", 0))
            details = usage.get("input_token_details") or {}
            cache_read += int(details.get("cache_read", 0))
            cache_write += int(details.get("cache_creation", 0))
            text = _message_text(message.content)
            if text:
                final_text = text
            trace.append(
                {
                    "step": ai_steps,
                    "text": text,
                    "tool_names": [
                        call.get("name") for call in getattr(message, "tool_calls", [])
                    ],
                }
            )

        return AgentResult(
            status="completed",
            final_text=final_text,
            steps=ai_steps,
            tool_calls=len(calls),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            trace=trace,
        )


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
        return "\n".join(texts).strip()
    return ""
