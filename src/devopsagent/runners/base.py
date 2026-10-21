"""Common runner contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from devopsagent.protocol import ToolClient
from devopsagent.result import AgentResult

DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_SYSTEM_PROMPT = (
    "You are a DevOps agent operating in an isolated task environment. "
    "Use shell commands to inspect the environment and complete the task. "
    "Act instead of merely explaining. Verify your work before finishing. "
    "Do not attempt to read benchmark tests, verifier files, or reference solutions."
)


@dataclass(frozen=True)
class RunnerConfig:
    model_id: str = DEFAULT_MODEL_ID
    region: str = "us-west-2"
    max_steps: int = 12
    max_tokens: int = 4096
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class Runner(Protocol):
    async def run(self, instruction: str, tool_client: ToolClient) -> AgentResult: ...
