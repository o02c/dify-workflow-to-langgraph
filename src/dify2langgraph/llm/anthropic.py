"""Anthropic LLM provider."""

import inspect
import os

import anthropic
from anthropic.resources.messages import Messages
from dotenv import find_dotenv, load_dotenv

from dify2langgraph.logging_config import get_logger

from .base import LLMConfig, LLMProvider, LLMResponse, Message

# usecwd=True: search upward from the working directory, not from this file.
# Once installed (uv sync / pip install) this module lives inside the venv,
# so the default file-relative search never reaches the user's .env.
load_dotenv(find_dotenv(usecwd=True))

logger = get_logger(__name__)

# anthropic 1.x dropped temperature and top_p from messages.create(). The declared
# floor (anthropic>=0.75.0) still admits versions that accept them, so ask the
# installed SDK rather than assuming either shape -- passing temperature to 1.x
# fails the whole call with "unexpected keyword argument 'temperature'".
_CREATE_PARAMS = frozenset(inspect.signature(Messages.create).parameters)


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
            **self.config.extra,
        }

        if "temperature" in _CREATE_PARAMS:
            kwargs["temperature"] = self.config.temperature
        else:
            logger.debug(
                "anthropic %s does not accept temperature; sending without it",
                anthropic.__version__,
            )

        if system_content:
            kwargs["system"] = system_content

        # The request is assembled dynamically (config.extra is open-ended), so a
        # type checker cannot match it against the SDK's overloads; the shapes are
        # enforced by the API at call time instead.
        response = self.client.messages.create(**kwargs)  # ty: ignore[no-matching-overload]

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
