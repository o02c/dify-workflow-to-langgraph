"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""

    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from LLM provider."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: Any = None  # Original response object


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations should handle:
    - Authentication (API keys, credentials)
    - Request formatting for specific provider
    - Response parsing
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize provider with configuration.

        Args:
            config: LLM configuration.
        """
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'bedrock', 'openai', 'anthropic')."""
        ...

    @abstractmethod
    def generate(self, messages: list[Message]) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            messages: List of messages in the conversation.

        Returns:
            LLM response with generated content.
        """
        ...

    def generate_text(self, prompt: str, system: str | None = None) -> str:
        """Convenience method for simple text generation.

        Args:
            prompt: User prompt.
            system: Optional system message.

        Returns:
            Generated text content.
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        response = self.generate(messages)
        return response.content
