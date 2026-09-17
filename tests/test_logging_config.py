"""Tests for console log formatting, focused on cross-platform behaviour."""

from dify2langgraph import logging_config
from dify2langgraph.logging_config import ConsoleFormatter, supports_ansi_colors


class _FakeStderr:
    """Minimal stderr stand-in with a controllable isatty()."""

    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class TestSupportsAnsiColors:
    """Color codes must only be emitted where the terminal interprets them."""

    def test_false_when_not_a_tty(self, monkeypatch):
        """Redirected output gets no escape codes, on any platform."""
        monkeypatch.setattr(logging_config.sys, "stderr", _FakeStderr(tty=False))
        monkeypatch.setattr(logging_config.os, "name", "posix")

        assert supports_ansi_colors() is False

    def test_true_on_posix_tty(self, monkeypatch):
        """POSIX terminals interpret ANSI escapes unconditionally."""
        monkeypatch.setattr(logging_config.sys, "stderr", _FakeStderr(tty=True))
        monkeypatch.setattr(logging_config.os, "name", "posix")

        assert supports_ansi_colors() is True

    def test_false_on_windows_console_without_vt_markers(self, monkeypatch):
        """A legacy Windows console would render escapes as literal noise."""
        monkeypatch.setattr(logging_config.sys, "stderr", _FakeStderr(tty=True))
        monkeypatch.setattr(logging_config.os, "name", "nt")
        for var in ("WT_SESSION", "ANSICON", "TERM"):
            monkeypatch.delenv(var, raising=False)

        assert supports_ansi_colors() is False

    def test_true_on_windows_terminal(self, monkeypatch):
        """Windows Terminal advertises itself and does handle escapes."""
        monkeypatch.setattr(logging_config.sys, "stderr", _FakeStderr(tty=True))
        monkeypatch.setattr(logging_config.os, "name", "nt")
        monkeypatch.setenv("WT_SESSION", "abc-123")

        assert supports_ansi_colors() is True


class TestConsoleFormatter:
    """The formatter defers to supports_ansi_colors() for coloring."""

    def test_omits_escape_codes_on_legacy_windows_console(self, monkeypatch):
        """No stray ``\\x1b[32m`` in front of log lines on cmd.exe."""
        monkeypatch.setattr(logging_config, "supports_ansi_colors", lambda: False)

        formatter = ConsoleFormatter()
        record = logging_config.logging.LogRecord(
            "dify2langgraph", logging_config.logging.INFO, __file__, 1, "hello", None, None
        )

        assert "\x1b[" not in formatter.format(record)
