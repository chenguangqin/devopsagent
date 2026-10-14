"""Unified command-line interface for all agent implementations."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Sequence

from devopsagent.protocol import (
    JsonlChannel,
    LocalToolClient,
    ProtocolError,
    StdioToolClient,
    stderr_log,
)
from devopsagent.runners.base import (
    DEFAULT_MODEL_ID,
    DEFAULT_SYSTEM_PROMPT,
    Runner,
    RunnerConfig,
)


def build_parser(default_engine: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        choices=("native", "langchain", "strands"),
        default=default_engine or "native",
    )
    parser.add_argument("--protocol", choices=("local", "stdio"), default="local")
    parser.add_argument("--instruction")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    return parser


def create_runner(engine: str, config: RunnerConfig) -> Runner:
    if engine == "native":
        from devopsagent.runners.native import NativeRunner

        return NativeRunner(config)
    if engine == "langchain":
        from devopsagent.runners.langchain import LangChainRunner

        return LangChainRunner(config)
    if engine == "strands":
        from devopsagent.runners.strands import StrandsRunner

        return StrandsRunner(config)
    raise ValueError(f"unknown engine: {engine}")


async def run_cli(args: argparse.Namespace) -> int:
    config = RunnerConfig(
        model_id=args.model_id,
        region=args.region,
        max_steps=args.max_steps,
        max_tokens=args.max_tokens,
        system_prompt=args.system_prompt,
    )
    runner = create_runner(args.engine, config)

    if args.protocol == "stdio":
        channel = JsonlChannel(sys.stdin, sys.stdout)
        start = channel.receive()
        if start.get("type") != "start" or not isinstance(start.get("instruction"), str):
            raise ProtocolError("first stdio message must be a start instruction")
        instruction = start["instruction"]
        client = StdioToolClient(channel)
    else:
        instruction = args.instruction
        if not instruction:
            raise ProtocolError("--instruction is required with --protocol local")
        client = LocalToolClient(workdir=args.workdir.resolve())

    try:
        result = await runner.run(instruction, client)
    except Exception as exc:
        if args.protocol == "stdio":
            channel.send(
                {
                    "type": "finish",
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        raise

    if args.protocol == "stdio":
        channel.send({"type": "finish", "engine": args.engine, **result.to_dict()})
    else:
        print(result.final_text)
        stderr_log(
            f"status={result.status} steps={result.steps} "
            f"tool_calls={result.tool_calls} "
            f"tokens={result.input_tokens + result.output_tokens}"
        )
    return 0


def _main(argv: Sequence[str] | None, default_engine: str | None = None) -> int:
    args = build_parser(default_engine).parse_args(argv)
    try:
        return asyncio.run(run_cli(args))
    except (ProtocolError, ValueError) as exc:
        stderr_log(f"error: {exc}")
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    return _main(argv)


def main_native(argv: Sequence[str] | None = None) -> int:
    return _main(argv, "native")


def main_langchain(argv: Sequence[str] | None = None) -> int:
    return _main(argv, "langchain")


def main_strands(argv: Sequence[str] | None = None) -> int:
    return _main(argv, "strands")


if __name__ == "__main__":
    raise SystemExit(main())
