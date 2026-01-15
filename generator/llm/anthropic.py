"""Anthropic LLM provider."""

import os

import anthropic
from dotenv import find_dotenv, load_dotenv

from .base import LLMConfig, LLMProvider, LLMResponse, Message

load_dotenv(find_dotenv())


class AnthropicProvider(LLMProvider):
    """Anthropic LLM provider.

    Supports Claude models via Anthropic API directly.

    Example models:
    - claude-sonnet-4-20250514
    - claude-opus-4-20250514
    - claude-3-5-sonnet-20241022
    - claude-3-5-haiku-20241022
    """

    def __init__(
        self,
        config: LLMConfig,
        api_key: str | None = None,
    ) -> None:
        """Initialize Anthropic provider.

        Args:
            config: LLM configuration.
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        """
        super().__init__(config)

        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )

    @property
    def name(self) -> str:
        """Provider name."""
        return "anthropic"

    def generate(self, messages: list[Message]) -> LLMResponse:
        """Generate a response using Anthropic API.

        Args:
            messages: List of messages in the conversation.

        Returns:
            LLM response with generated content.
        """
        # Separate system message from conversation
        system_content = ""
        conversation = []

        for msg in messages:
            if msg.role == "system":
                system_content = msg.content
            else:
                conversation.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Build request kwargs
        kwargs = {
            "model": self.config.model,
            "messages": conversation,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            **self.config.extra,
        }

        if system_content:
            kwargs["system"] = system_content

        response = self.client.messages.create(**kwargs)

        # Extract content from response
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        # Extract usage information
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            raw=response,
        )


# Convenience model constants
CLAUDE_SONNET_4 = "claude-sonnet-4-20250514"
CLAUDE_OPUS_4 = "claude-opus-4-20250514"
CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20241022"
CLAUDE_3_5_HAIKU = "claude-3-5-haiku-20241022"
