"""Harbor External Agent adapter."""

from __future__ import annotations

import json
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import Field

from devopsagent.bedrock import BedrockConverseAdapter
from devopsagent.loop import AgentLoop, LoopConfig
from devopsagent.tools import ShellTool

DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-5-5"


class DevOpsAgentOptions(AgentOptions):
    region: str = Field(default="us-west-2", description="AWS region for Bedrock Runtime.")
    max_steps: int = Field(default=12, ge=1, le=100)
    max_tokens: int = Field(default=4096, ge=64, le=64_000)
    tool_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    max_tool_output_chars: int = Field(default=50_000, ge=1_000, le=500_000)
    system_prompt: str = Field(
        default=(
            "You are a DevOps agent operating in an isolated benchmark environment. "
            "Use shell commands to inspect the environment and complete the task. "
            "Act instead of merely explaining. Verify your work before finishing. "
            "Do not attempt to read benchmark tests, verifier files, or reference solutions."
        )
    )


class DevOpsAgent(BaseAgent):
    """Minimal Harbor-compatible agent powered by Bedrock Converse."""

    options_model = DevOpsAgentOptions

    @staticmethod
    def name() -> str:
        return "devopsagent"

    def version(self) -> str:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        # External agent: boto3 and the model loop stay on the host. Only tools
        # execute inside the Trial environment through BaseEnvironment.
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        options = self.options
        assert isinstance(options, DevOpsAgentOptions)

        model_id = self.model_name or DEFAULT_MODEL_ID
        provider = BedrockConverseAdapter(
            model_id=model_id,
            region=options.region,
            max_tokens=options.max_tokens,
        )
        shell = ShellTool(
            environment=environment,
            timeout_seconds=options.tool_timeout_seconds,
            max_output_chars=options.max_tool_output_chars,
        )
        loop = AgentLoop(
            provider=provider,
            tools=[shell],
            config=LoopConfig(
                max_steps=options.max_steps,
                system_prompt=options.system_prompt,
            ),
        )

        result = await loop.run(instruction)

        context.n_input_tokens = result.input_tokens
        context.n_output_tokens = result.output_tokens
        context.n_cache_tokens = result.cache_read_tokens
        context.metadata = {
            "status": result.status,
            "steps": result.steps,
            "tool_calls": result.tool_calls,
            "cache_write_tokens": result.cache_write_tokens,
            "model_id": model_id,
            "region": options.region,
            "final_text": result.final_text,
        }

        self._write_json(self.logs_dir / "agent-result.json", {
            **context.metadata,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "trace": result.trace,
        })

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

