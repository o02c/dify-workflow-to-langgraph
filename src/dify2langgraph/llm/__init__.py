"""LLM providers for code generation.

This module provides a unified interface for multiple LLM providers:
- Amazon Bedrock (Claude via AWS)
- OpenAI (GPT models)
- Anthropic (Claude via direct API)
- Google (Gemini models)

Example usage:
    from dify2langgraph.llm import create_provider, LLMConfig

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
        from .google import GoogleProvider
        _PROVIDERS["google"] = GoogleProvider
    except ImportError:
        pass

    try:
        from .anthropic import AnthropicProvider
        _PROVIDERS["anthropic"] = AnthropicProvider
    except ImportError:
        pass


# Each provider names its models differently, so there is no single sensible
# default. Without this, `--llm-provider google` inherits the OpenAI default and
# fails with "models/gpt-4o-mini is not found", which reads like a broken
# provider rather than a missing --llm-model.
# Model ids go stale: the 3.5 generation reached end of life and stopped being
# servable, so a default naming it fails with a 404 that looks like a broken
# provider. Re-check these when bumping SDKs.
#
# Bedrock is the awkward one. This project talks to `bedrock-runtime`, where the
# bare `anthropic.` id is not accepted for on-demand throughput -- it needs a geo
# (`us.`/`eu.`/`au.`/`jp.`) or global inference profile. `global.` is used here
# because it is the only one that works from every region, which is what a
# default has to do; it can route outside the source region, so anyone with data
# residency requirements should pass a geo profile via --llm-model.
_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "bedrock": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "google": "gemini-2.5-flash",
}


def default_model(provider_name: str) -> str | None:
    """Return the default model for a provider.

    Args:
        provider_name: Name of the provider.

    Returns:
        A model identifier, or None if the provider is unknown.
    """
    return _DEFAULT_MODELS.get(provider_name)


def create_provider(
    provider_name: str,
    config: LLMConfig,
    **kwargs: Any,
) -> LLMProvider:
    """Create an LLM provider instance.

    Args:
        provider_name: Name of the provider ('bedrock', 'openai', 'anthropic', 'google').
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
    "default_model",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "create_provider",
    "available_providers",
]
