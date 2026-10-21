"""Command Adapter entry point for the demomcp Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent import ROOT_DIR, build_agent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "skill"), required=True)
    return parser


def final_text(result: Any) -> str:
    message = getattr(result, "message", None)
    if not isinstance(message, dict):
        return str(result)
    parts = message.get("content", [])
    return "\n".join(
        item["text"]
        for item in parts
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )


def report_artifacts() -> list[str]:
    reports_dir = ROOT_DIR / "reports"
    if not reports_dir.exists():
        return []
    return [
        path.relative_to(ROOT_DIR).as_posix()
        for path in sorted(reports_dir.rglob("*"))
        if path.is_file()
    ]


def write_result(result_path: Path, data: dict[str, Any]) -> None:
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT_DIR / ".env", override=False)
    args = build_parser().parse_args(argv)
    result_path = Path(os.environ["AGENT_EVAL_RESULT"])
    try:
        request = json.loads(sys.stdin.readline())
        requested_mode = request["agent_config"]["mode"]
        if requested_mode != args.mode:
            raise ValueError(
                f"mode mismatch: argv={args.mode!r}, request={requested_mode!r}"
            )
        result = build_agent(args.mode)(request["task"]["instruction"])
        write_result(
            result_path,
            {
                "schema_version": "0.2",
                "status": "completed",
                "final_text": final_text(result),
                "structured_output": None,
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "source": "unavailable",
                },
                "artifacts": report_artifacts(),
            },
        )
        return 0
    except Exception as exc:
        write_result(
            result_path,
            {
                "schema_version": "0.2",
                "status": "error",
                "final_text": "",
                "structured_output": None,
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "source": "unavailable",
                },
                "artifacts": report_artifacts(),
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
