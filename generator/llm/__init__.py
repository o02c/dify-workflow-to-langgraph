"""LLM providers for code generation.

This module provides a unified interface for multiple LLM providers:
- Amazon Bedrock (Claude via AWS)
- OpenAI (GPT models)
- Anthropic (Claude via direct API)

Example usage:
    from generator.llm import create_provider, LLMConfig

    # Using Bedrock
    config = LLMConfig(model="anthropic.claude-3-5-sonnet-20241022-v2:0")
    provider = create_provider("bedrock", config, region="us-east-1")

    # Using OpenAI
    config = LLMConfig(model="gpt-4o")
    provider = create_provider("openai", config)

    # Using Anthropic
    config = LLMConfig(model="claude-sonnet-4-20250514")
    provider = create_provider("anthropic", config)

    # Generate text
    response = provider.generate_text("Write a hello world function")
"""

from typing import Any

from .base import LLMConfig, LLMProvider, LLMResponse, Message

# Provider implementations (lazy imports to avoid missing dependency errors)
_PROVIDERS: dict[str, type[LLMProvider]] = {}


def _load_providers() -> None:
    """Lazily load provider implementations."""
    global _PROVIDERS
    if _PROVIDERS:
        return

    try:
        from .bedrock import BedrockProvider
        _PROVIDERS["bedrock"] = BedrockProvider
    except ImportError:
        pass

    try:
        from .openai import OpenAIProvider
        _PROVIDERS["openai"] = OpenAIProvider
    except ImportError:
        pass

    try:
        from .anthropic import AnthropicProvider
        _PROVIDERS["anthropic"] = AnthropicProvider
    except ImportError:
        pass


def create_provider(
    provider_name: str,
    config: LLMConfig,
    **kwargs: Any,
) -> LLMProvider:
    """Create an LLM provider instance.

    Args:
        provider_name: Name of the provider ('bedrock', 'openai', 'anthropic').
        config: LLM configuration.
        **kwargs: Provider-specific arguments.

    Returns:
        Configured LLM provider instance.

    Raises:
        ValueError: If provider is not supported or not installed.
    """
    _load_providers()

    if provider_name not in _PROVIDERS:
        available = list(_PROVIDERS.keys())
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Available providers: {available}. "
            f"Make sure the required package is installed."
        )

    provider_class = _PROVIDERS[provider_name]
    return provider_class(config, **kwargs)


def available_providers() -> list[str]:
    """Get list of available provider names.

    Returns:
        List of provider names that can be used.
    """
    _load_providers()
    return list(_PROVIDERS.keys())


__all__ = [
    "LLMConfig",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "create_provider",
    "available_providers",
]
