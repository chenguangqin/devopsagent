#!/usr/bin/env python3
"""Verify that the configured Bedrock Claude model can answer a minimal request."""

from __future__ import annotations

import argparse
import asyncio

from devopsagent.bedrock import BedrockConverseAdapter


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-id",
        default="global.anthropic.claude-haiku-5-5",
    )
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args()

    adapter = BedrockConverseAdapter(
        model_id=args.model_id,
        region=args.region,
        max_tokens=32,
    )
    response = await adapter.converse(
        messages=[
            {
                "role": "user",
                "content": [{"text": "Reply with exactly: Bedrock connection works"}],
            }
        ],
        tools=[],
        system_prompt="Follow the user's output instruction exactly.",
    )
    content = response["output"]["message"]["content"]
    text = "".join(block.get("text", "") for block in content)
    usage = response.get("usage", {})
    print(text)
    print(
        f"input_tokens={usage.get('inputTokens', 0)} "
        f"output_tokens={usage.get('outputTokens', 0)}"
    )


if __name__ == "__main__":
    asyncio.run(main())

