"""Observability configuration for LangSmith tracing.

This module provides utilities for configuring LangSmith tracing
in LangGraph workflows.

Environment Variables:
    LANGSMITH_API_KEY: Your LangSmith API key
    LANGSMITH_PROJECT: Project name for tracing (default: dify2langgraph)
    LANGSMITH_TRACING: Enable tracing ("true" or "false", default: "false")
"""

import os
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled.

    Returns:
        True if tracing is enabled and configured.
    """
    tracing = os.environ.get("LANGSMITH_TRACING", "false").lower()
    api_key = os.environ.get("LANGSMITH_API_KEY", "")

    if tracing == "true" and not api_key:
        logger.warning("LANGSMITH_TRACING is enabled but LANGSMITH_API_KEY is not set")
        return False

    return tracing == "true" and bool(api_key)


def get_project_name() -> str:
    """Get the LangSmith project name.

    Returns:
        Project name from environment or default.
    """
    return os.environ.get("LANGSMITH_PROJECT", "dify2langgraph")


def configure_tracing() -> None:
    """Configure LangSmith tracing based on environment variables.

    This function should be called at application startup if you want
    to enable tracing for all LangGraph operations.

    Example:
        >>> from dify2langgraph.observability import configure_tracing
        >>> configure_tracing()
    """
    if not is_tracing_enabled():
        logger.debug("LangSmith tracing is disabled")
        return

    project = get_project_name()
    logger.info("LangSmith tracing enabled for project: %s", project)

    # LangSmith tracing is automatically enabled when LANGSMITH_TRACING=true
    # and LANGSMITH_API_KEY is set. This function just logs the configuration.


def with_tracing(name: str | None = None) -> Callable[[F], F]:
    """Decorator to add tracing to a function.

    This decorator wraps a function with LangSmith tracing context
    if tracing is enabled.

    Args:
        name: Optional name for the traced operation.

    Returns:
        Decorated function.

    Example:
        >>> @with_tracing("process_data")
        ... def process_data(input_text: str) -> str:
        ...     return input_text.upper()
    """

    def decorator(func: F) -> F:
        if not is_tracing_enabled():
            return func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # LangSmith automatically traces langchain/langgraph operations
            # For custom functions, we can add metadata
            # Not every callable has __name__ (partials, callable instances),
            # and F is only bound to Callable -- so read it defensively.
            trace_name = name or getattr(func, "__name__", repr(func))
            logger.debug("Tracing: %s", trace_name)
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


def get_run_url(run_id: str) -> str | None:
    """Get the LangSmith URL for a specific run.

    Args:
        run_id: The run ID from LangSmith.

    Returns:
        URL to the run in LangSmith, or None if tracing is disabled.
    """
    if not is_tracing_enabled():
        return None

    project = get_project_name()
    return f"https://smith.langchain.com/o/default/projects/p/{project}/r/{run_id}"
