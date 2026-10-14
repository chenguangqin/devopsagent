"""JSONL protocol and local backend for CLI tool execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO


class ToolClient(Protocol):
    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ProtocolError(RuntimeError):
    pass


class JsonlChannel:
    """One JSON object per line; stdout is reserved for protocol messages."""

    def __init__(self, reader: TextIO, writer: TextIO) -> None:
        self.reader = reader
        self.writer = writer
        self._write_lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            self.writer.write(encoded + "\n")
            self.writer.flush()

    def receive(self) -> dict[str, Any]:
        line = self.reader.readline()
        if not line:
            raise ProtocolError("protocol peer closed the stream")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSONL message: {line[:200]!r}") from exc
        if not isinstance(message, dict):
            raise ProtocolError("protocol message must be a JSON object")
        return message


class StdioToolClient:
    def __init__(self, channel: JsonlChannel) -> None:
        self.channel = channel

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        call_id = uuid.uuid4().hex
        self.channel.send(
            {
                "type": "tool_call",
                "id": call_id,
                "name": name,
                "arguments": arguments,
            }
        )
        response = self.channel.receive()
        if response.get("type") != "tool_result" or response.get("id") != call_id:
            raise ProtocolError(f"unexpected tool response: {response!r}")
        return response


@dataclass
class LocalToolClient:
    """Execute the same tool contract without Harbor."""

    workdir: Path
    timeout_seconds: int = 120
    max_output_chars: int = 50_000

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != "shell":
            return self._result("error", f"unknown tool: {name}")

        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return self._result("error", "command must be a non-empty string")

        requested_cwd = arguments.get("cwd")
        if requested_cwd is not None and not isinstance(requested_cwd, str):
            return self._result("error", "cwd must be a string")
        cwd = Path(requested_cwd) if requested_cwd else self.workdir

        try:
            completed = subprocess.run(
                command,
                shell=True,
                executable=os.environ.get("SHELL", "/bin/sh"),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            output = format_exec_result(
                completed.returncode,
                completed.stdout,
                completed.stderr,
                self.max_output_chars,
            )
            status = "success" if completed.returncode == 0 else "error"
            return self._result(status, output)
        except subprocess.TimeoutExpired as exc:
            output = format_exec_result(
                124,
                _decode_timeout_output(exc.stdout),
                _decode_timeout_output(exc.stderr),
                self.max_output_chars,
            )
            return self._result("error", f"command timed out\n{output}")
        except OSError as exc:
            return self._result("error", f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _result(status: str, output: str) -> dict[str, Any]:
        return {"type": "tool_result", "status": status, "output": output}


def format_exec_result(
    return_code: int,
    stdout: str,
    stderr: str,
    max_output_chars: int,
) -> str:
    output = (
        f"exit_code: {return_code}\n"
        f"stdout:\n{stdout or ''}\n"
        f"stderr:\n{stderr or ''}"
    )
    if len(output) > max_output_chars:
        omitted = len(output) - max_output_chars
        output = f"{output[:max_output_chars]}\n... <truncated {omitted} chars>"
    return output


def stderr_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
