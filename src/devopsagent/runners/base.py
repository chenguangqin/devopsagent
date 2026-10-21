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
    "Act instead of merely explaining.\n\n"
    "Start with a short plan that lists every requirement in the task and how you "
    "will check it. Revisit the plan when an approach fails instead of starting "
    "over with throwaway experiments; fix the deliverable you already have.\n\n"
    "Each shell tool call runs in a fresh, non-interactive shell: `cd`, `export`, "
    "and `source` do not persist between calls, and the grader will not have them "
    "either. Make results persistent: install binaries to standard locations "
    "(e.g. /usr/local/bin), use absolute paths, and write files exactly where the "
    "task asks.\n\n"
    "Your step budget is limited and tool results report how much is left. When "
    "the budget runs low, stop exploring and make sure the deliverables work.\n\n"
    "Before finishing, verify every requirement in the task as a grader would: in a "
    "fresh shell, without sourcing any setup files, using the exact paths, names, "
    "and commands the task specifies. If a check fails, fix it before finishing.\n\n"
    "Do not attempt to read benchmark tests, verifier files, or reference solutions."
)
SHELL_TOOL_DESCRIPTION = (
    "Run a shell command in the isolated task environment. Each call starts a "
    "fresh non-interactive shell: working directory and environment changes "
    "(cd, export, source) do not carry over to later calls."
)


@dataclass(frozen=True)
class RunnerConfig:
    model_id: str = DEFAULT_MODEL_ID
    region: str = "us-west-2"
    max_steps: int = 12
    max_tokens: int = 4096
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


def budget_note(used: int, max_steps: int) -> str:
    """Step-budget reminder appended to every tool result."""
    remaining = max(max_steps - used, 0)
    note = f"\n\n[step {used}/{max_steps}, {remaining} left]"
    if remaining <= max(3, max_steps // 4):
        note += (
            " Budget is low: stop exploring, fix and verify the existing "
            "deliverables in a fresh shell, then finish."
        )
    return note


class Runner(Protocol):
    async def run(self, instruction: str, tool_client: ToolClient) -> AgentResult: ...
