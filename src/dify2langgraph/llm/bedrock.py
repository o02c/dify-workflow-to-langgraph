"""Amazon Bedrock LLM provider."""

from typing import Any

import boto3

from .base import LLMConfig, LLMProvider, LLMResponse, Message


class BedrockProvider(LLMProvider):
    """Amazon Bedrock LLM provider.

    Supports Claude models via Bedrock Runtime API.

    Example models:
    - anthropic.claude-3-5-sonnet-20241022-v2:0
    - anthropic.claude-3-5-haiku-20241022-v1:0
    - anthropic.claude-3-opus-20240229-v1:0
    """

    def __init__(
        self,
        config: LLMConfig,
        region: str = "us-east-1",
        profile: str | None = None,
    ) -> None:
        """Initialize Bedrock provider.

        Args:
            config: LLM configuration.
            region: AWS region for Bedrock.
            profile: Optional AWS profile name.
        """
        super().__init__(config)
        self.region = region

        session_kwargs: dict[str, Any] = {"region_name": region}
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


# Convenience model constants
CLAUDE_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"
CLAUDE_HAIKU = "anthropic.claude-3-5-haiku-20241022-v1:0"
CLAUDE_OPUS = "anthropic.claude-3-opus-20240229-v1:0"
