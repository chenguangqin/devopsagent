"""Harbor adapter for black-box DevOps Agent CLI processes."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import Field

from devopsagent.protocol import format_exec_result
from devopsagent.runners.base import DEFAULT_MODEL_ID, DEFAULT_SYSTEM_PROMPT

PROTOCOL_LINE_LIMIT = 64 * 1024 * 1024


class CliAgentOptions(AgentOptions):
    region: str = Field(default="us-west-2")
    max_steps: int = Field(default=12, ge=1, le=100)
    max_tokens: int = Field(default=4096, ge=64, le=64_000)
    tool_timeout_seconds: int = Field(default=120, ge=1, le=3600)
    max_tool_output_chars: int = Field(default=50_000, ge=1_000, le=500_000)
    system_prompt: str = Field(default=DEFAULT_SYSTEM_PROMPT)


class CliHarborAgent(BaseAgent):
    """Translate Harbor's environment API to the agent's JSONL CLI protocol."""

    options_model = CliAgentOptions
    engine = "native"

    @staticmethod
    def name() -> str:
        return "devopsagent-cli"

    def version(self) -> str:
        return "0.2.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        options = self.options
        assert isinstance(options, CliAgentOptions)
        model_id = self.model_name or DEFAULT_MODEL_ID
        command = [
            sys.executable,
            "-m",
            "devopsagent.cli",
            "--engine",
            self.engine,
            "--protocol",
            "stdio",
            "--model-id",
            model_id,
            "--region",
            options.region,
            "--max-steps",
            str(options.max_steps),
            "--max-tokens",
            str(options.max_tokens),
            "--system-prompt",
            options.system_prompt,
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Protocol messages are single JSON lines; tool calls and the final
            # trace can exceed asyncio's 64 KiB default line limit.
            limit=PROTOCOL_LINE_LIMIT,
        )
        assert process.stdin and process.stdout and process.stderr
        stderr_task = asyncio.create_task(self._capture_stderr(process.stderr))

        try:
            await self._send(process.stdin, {"type": "start", "instruction": instruction})
            result = await self._protocol_loop(
                process,
                environment,
                options,
            )
            return_code = await process.wait()
            if return_code != 0 and result.get("status") != "error":
                raise RuntimeError(f"agent CLI exited with status {return_code}")
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            await stderr_task

        self._update_context(context, result, model_id, options.region)
        self._write_json(self.logs_dir / "agent-result.json", result)
        if result.get("status") == "error":
            raise RuntimeError(str(result.get("error", "agent CLI failed")))

    async def _protocol_loop(
        self,
        process: asyncio.subprocess.Process,
        environment: BaseEnvironment,
        options: CliAgentOptions,
    ) -> dict[str, Any]:
        assert process.stdin and process.stdout
        while True:
            message = await self._receive(process.stdout)
            message_type = message.get("type")
            if message_type == "finish":
                return message
            if message_type != "tool_call":
                raise RuntimeError(f"unexpected agent protocol message: {message!r}")

            call_id = message.get("id")
            name = message.get("name")
            arguments = message.get("arguments", {})
            if name != "shell" or not isinstance(arguments, dict):
                response = {
                    "type": "tool_result",
                    "id": call_id,
                    "status": "error",
                    "output": f"unsupported tool call: {name!r}",
                }
            else:
                response = await self._execute_shell(
                    call_id,
                    arguments,
                    environment,
                    options,
                )
            await self._send(process.stdin, response)

    async def _execute_shell(
        self,
        call_id: Any,
        arguments: dict[str, Any],
        environment: BaseEnvironment,
        options: CliAgentOptions,
    ) -> dict[str, Any]:
        command = arguments.get("command")
        cwd = arguments.get("cwd")
        if not isinstance(command, str) or not command.strip():
            return self._tool_error(call_id, "command must be a non-empty string")
        if cwd is not None and not isinstance(cwd, str):
            return self._tool_error(call_id, "cwd must be a string")
        try:
            result = await environment.exec(
                command=command,
                cwd=cwd,
                timeout_sec=options.tool_timeout_seconds,
            )
            output = format_exec_result(
                result.return_code,
                result.stdout or "",
                result.stderr or "",
                options.max_tool_output_chars,
            )
            return {
                "type": "tool_result",
                "id": call_id,
                "status": "success" if result.return_code == 0 else "error",
                "output": output,
            }
        except Exception as exc:
            return self._tool_error(call_id, f"{type(exc).__name__}: {exc}")

    async def _capture_stderr(self, stream: asyncio.StreamReader) -> None:
        path = self.logs_dir / "agent-stderr.log"
        with path.open("wb") as target:
            while line := await stream.readline():
                target.write(line)
                target.flush()

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write(
            json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
            + b"\n"
        )
        await writer.drain()

    @staticmethod
    async def _receive(reader: asyncio.StreamReader) -> dict[str, Any]:
        line = await reader.readline()
        if not line:
            raise RuntimeError("agent CLI closed stdout before finish")
        message = json.loads(line)
        if not isinstance(message, dict):
            raise RuntimeError("agent protocol message must be an object")
        return message

    @staticmethod
    def _tool_error(call_id: Any, output: str) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "id": call_id,
            "status": "error",
            "output": output,
        }

    @staticmethod
    def _update_context(
        context: AgentContext,
        result: dict[str, Any],
        model_id: str,
        region: str,
    ) -> None:
        context.n_input_tokens = int(result.get("input_tokens", 0))
        context.n_output_tokens = int(result.get("output_tokens", 0))
        context.n_cache_tokens = int(result.get("cache_read_tokens", 0))
        context.metadata = {
            "engine": result.get("engine"),
            "status": result.get("status"),
            "steps": result.get("steps", 0),
            "tool_calls": result.get("tool_calls", 0),
            "cache_write_tokens": result.get("cache_write_tokens", 0),
            "model_id": model_id,
            "region": region,
            "final_text": result.get("final_text", ""),
        }

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class NativeCliHarborAgent(CliHarborAgent):
    engine = "native"

    @staticmethod
    def name() -> str:
        return "devopsagent-native-cli"


class LangChainCliHarborAgent(CliHarborAgent):
    engine = "langchain"

    @staticmethod
    def name() -> str:
        return "devopsagent-langchain-cli"


class StrandsCliHarborAgent(CliHarborAgent):
    engine = "strands"

    @staticmethod
    def name() -> str:
        return "devopsagent-strands-cli"
