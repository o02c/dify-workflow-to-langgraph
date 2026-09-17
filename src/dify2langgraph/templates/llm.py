"""Shared LLM configuration for workflow nodes.

This module provides a unified interface to get chat models.
Configure via environment variables.
"""

import os

from dotenv import find_dotenv, load_dotenv
from langchain_core.language_models import BaseChatModel

load_dotenv(find_dotenv())

# Default configuration
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "google")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")


def get_chat_model(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """Get a configured chat model instance.

    Args:
        provider: LLM provider (google, openai, anthropic, bedrock). Defaults to LLM_PROVIDER env var.
        model: Model name. Defaults to LLM_MODEL env var.
        **kwargs: Additional arguments passed to the model constructor.

    Returns:
        Configured LangChain chat model.

    Examples:
        >>> llm = get_chat_model()  # Uses defaults from env (gemini-2.5-flash)
        >>> llm = get_chat_model("openai", "gpt-4o-mini")
        >>> llm = get_chat_model("anthropic", "claude-3-5-sonnet-20241022")
        >>> llm = get_chat_model("bedrock", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    """
    provider = provider or DEFAULT_PROVIDER
    model = model or DEFAULT_MODEL

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, **kwargs)

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, **kwargs)

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, **kwargs)

    elif provider == "bedrock":
        from langchain_aws import ChatBedrock

        return ChatBedrock(model_id=model, **kwargs)

    else:
        raise ValueError(f"Unknown provider: {provider}")
