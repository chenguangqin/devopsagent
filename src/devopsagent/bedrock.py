"""Amazon Bedrock Converse adapter."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import boto3
from botocore.config import Config

# Error codes Bedrock returns for transient server-side failures, including
# errors raised mid-stream by ConverseStream that botocore cannot retry itself.
TRANSIENT_ERROR_CODES = frozenset(
    {
        "internalserverexception",
        "serviceunavailableexception",
        "modelstreamerrorexception",
        "throttlingexception",
    }
)


def bedrock_client_config() -> Config:
    """Shared botocore config for every Bedrock client the agents create."""
    return Config(
        connect_timeout=10,
        read_timeout=300,
        retries={"max_attempts": 8, "mode": "adaptive"},
    )


class ConverseProvider(Protocol):
    """Model interface consumed by the agent loop."""

    async def converse(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> dict[str, Any]: ...


class BedrockConverseAdapter:
    """Thin async wrapper over the synchronous Bedrock Converse API."""

    def __init__(
        self,
        *,
        model_id: str,
        region: str,
        max_tokens: int = 4096,
        client: Any | None = None,
    ) -> None:
        self.model_id = model_id
        self.region = region
        self.max_tokens = max_tokens
        self._client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=bedrock_client_config(),
        )

    async def converse(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": messages,
            "system": [{"text": system_prompt}],
            # Claude Haiku 5.5 rejects temperature; keep inference config minimal.
            "inferenceConfig": {"maxTokens": self.max_tokens},
        }
        if tools:
            request["toolConfig"] = {"tools": tools}

        return await asyncio.to_thread(self._client.converse, **request)

