"""Amazon Bedrock LLM provider."""

import os
from typing import Any

import boto3

from .base import LLMConfig, LLMProvider, LLMResponse, Message


class BedrockProvider(LLMProvider):
    """Amazon Bedrock LLM provider.

    Supports Claude models via Bedrock Runtime API.

    Example models (geo or global inference profile ids -- the bare
    `anthropic.` form is not served on-demand by bedrock-runtime):
    - global.anthropic.claude-haiku-4-5-20251001-v1:0
    - us.anthropic.claude-haiku-4-5-20251001-v1:0
    """

    def __init__(
        self,
        config: LLMConfig,
        region: str | None = None,
        profile: str | None = None,
    ) -> None:
        """Initialize Bedrock provider.

        Args:
            config: LLM configuration.
            region: AWS region for Bedrock. Falls back to AWS_REGION /
                AWS_DEFAULT_REGION, then to the AWS profile's own region.
            profile: Optional AWS profile name.
        """
        super().__init__(config)

        # botocore only reads AWS_DEFAULT_REGION (configprovider.py); langchain-aws
        # also honours AWS_REGION. Accept both here so one converter invocation
        # behaves the same as the rest of the toolchain. When nothing is set we
        # pass no region_name at all and let boto3 resolve the profile's region --
        # hitting a hardcoded us-east-1 instead is a silent AccessDeniedException.
        self.region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")

        session_kwargs: dict[str, Any] = {}
        if self.region:
            session_kwargs["region_name"] = self.region
        # Only pass profile_name when explicitly asked: naming a profile makes
        # botocore drop EnvProvider from the credential chain, so static
        # AWS_ACCESS_KEY_ID/SECRET env credentials would be ignored.
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        self.client = session.client("bedrock-runtime")

    @property
    def name(self) -> str:
        """Provider name."""
        return "bedrock"

    def generate(self, messages: list[Message]) -> LLMResponse:
        """Generate a response using Bedrock.

        Args:
            messages: List of messages in the conversation.

        Returns:
            LLM response with generated content.
        """
        # Separate system message from conversation
        system_messages = []
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_messages.append({"text": msg.content})
            else:
                conversation.append({
                    "role": msg.role,
                    "content": [{"text": msg.content}],
                })

        # Build request body
        request_body: dict[str, Any] = {
            "messages": conversation,
            "inferenceConfig": {
                "temperature": self.config.temperature,
                "maxTokens": self.config.max_tokens,
            },
        }

        if system_messages:
            request_body["system"] = system_messages

        # Add any extra configuration
        request_body.update(self.config.extra)

        response = self.client.converse(
            modelId=self.config.model,
            **request_body,
        )

        # Extract content from response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        content = ""
        for block in content_blocks:
            if "text" in block:
                content += block["text"]

        # Extract usage information
        usage_info = response.get("usage", {})
        usage = {
            "input_tokens": usage_info.get("inputTokens", 0),
            "output_tokens": usage_info.get("outputTokens", 0),
        }

        return LLMResponse(
            content=content,
            model=self.config.model,
            usage=usage,
            raw=response,
        )


# Convenience model constants. Global inference profiles: `bedrock-runtime` does
# not accept the bare `anthropic.` id for on-demand throughput. Swap `global.`
# for a geo prefix (`us.`, `eu.`, `au.`, `jp.`) to keep requests in one region.
CLAUDE_HAIKU = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
CLAUDE_SONNET = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
