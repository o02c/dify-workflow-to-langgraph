"""Logging configuration for dify2langgraph.

This module provides centralized logging configuration with support for:
- JSON structured logging for production
- Colored console output for development
- Configuration via environment variables

Environment Variables:
    LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO
    LOG_FORMAT: Output format ("json" or "console"). Default: console
"""

import io
import json
import logging
import logging.config
import os
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging in production environments."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        extra_data = getattr(record, "extra_data", None)
        if extra_data is not None:
            log_data.update(extra_data)

        return json.dumps(log_data, ensure_ascii=False)


def supports_ansi_colors() -> bool:
    """Whether stderr renders ANSI escape codes.

    Windows consoles only interpret them when virtual-terminal processing is
    enabled; where it is not, colored output degrades into literal ``[32m``
    noise in front of every log line. Trust the marker variables set by the
    terminals that do handle it.

    Returns:
        True if color codes are safe to emit.
    """
    if not sys.stderr.isatty():
        return False
    if os.name != "nt":
        return True
    return bool(
        os.environ.get("WT_SESSION")
        or os.environ.get("ANSICON")
        or os.environ.get("TERM")
    )


class ConsoleFormatter(logging.Formatter):
    """Console formatter with optional color support for development."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize console formatter.

        Args:
            use_colors: Whether to use ANSI color codes.
        """
        super().__init__()
        self.use_colors = use_colors and supports_ansi_colors()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output.

        Args:
            record: Log record to format.

        Returns:
            Formatted log string.
        """
        level = record.levelname
        message = record.getMessage()

        if self.use_colors:
            color = self.COLORS.get(level, "")
            formatted = f"{color}{level:8}{self.RESET} {record.name}: {message}"
        else:
            formatted = f"{level:8} {record.name}: {message}"

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


def get_log_level() -> int:
    """Get log level from environment variable.

    Returns:
        Logging level integer.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def get_log_format() -> str:
    """Get log format from environment variable.

    Returns:
        Format string ("json" or "console").
    """
    return os.environ.get("LOG_FORMAT", "console").lower()


def configure_logging() -> None:
    """Configure logging based on environment variables.

    This function should be called once at application startup.
    It configures the root logger and the dify2langgraph logger.
    """
    log_level = get_log_level()
    log_format = get_log_format()

    # Log records carry non-ASCII text (node titles, prompts, file paths such as
    # C:\\Users\\<name>\\workflow.yml). On Windows stderr uses the console codepage,
    # and a record it cannot encode makes logging drop the line and emit an
    # internal error instead -- escape those characters and keep the line.
    if isinstance(sys.stderr, io.TextIOWrapper):
        try:
            sys.stderr.reconfigure(errors="backslashreplace")
        except (OSError, ValueError):  # pragma: no cover - stream not reconfigurable
            pass

    # Create handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)

    # Set formatter based on format preference
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    # Configure dify2langgraph logger
    logger = logging.getLogger("dify2langgraph")
    logger.setLevel(log_level)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance for the dify2langgraph package.

    Args:
        name: Optional module name to append to the base logger name.

    Returns:
        Logger instance.

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing file")
    """
    base_name = "dify2langgraph"
    if name:
        # Strip common prefixes to keep logger names clean
        if name.startswith("src.dify2langgraph."):
            name = name[len("src.dify2langgraph.") :]
        elif name.startswith("dify2langgraph."):
            name = name[len("dify2langgraph.") :]
        return logging.getLogger(f"{base_name}.{name}")
    return logging.getLogger(base_name)


# Configure logging on module import
configure_logging()
