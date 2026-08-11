"""OpenAI LLM provider."""

import os

from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

from .base import LLMConfig, LLMProvider, LLMResponse, Message

load_dotenv(find_dotenv())


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider.

    Supports GPT models via OpenAI API.

    Example models:
    - gpt-4o
    - gpt-4o-mini
    - gpt-4-turbo
    - o1
    - o1-mini
    """

    def __init__(
        self,
        config: LLMConfig,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize OpenAI provider.

        Args:
            config: LLM configuration.
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            base_url: Optional base URL for API (for compatible endpoints).
        """
        super().__init__(config)

        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    @property
    def name(self) -> str:
        """Provider name."""
        return "openai"

    def generate(self, messages: list[Message]) -> LLMResponse:
        """Generate a response using OpenAI.

        Args:
            messages: List of messages in the conversation.

        Returns:
            LLM response with generated content.
        """
        # Convert messages to OpenAI format
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=openai_messages,  # type: ignore[arg-type]
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            **self.config.extra,
        )

        # Extract content from response
        content = response.choices[0].message.content or ""

        # Extract usage information
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            raw=response,
        )


# Convenience model constants
GPT_4O = "gpt-4o"
GPT_4O_MINI = "gpt-4o-mini"
O1 = "o1"
O1_MINI = "o1-mini"
