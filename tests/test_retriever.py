"""Tests for the Retriever port template (ADR-0006).

The template is copied verbatim into every generated package; here we import it
in place and check the default adapter's unconfigured behavior.
"""

from dify2langgraph.templates.retriever import (
    DifyApiRetriever,
    Retriever,
    get_retriever,
)


class TestDifyApiRetriever:
    def test_unconfigured_returns_empty(self):
        """With no base URL / API key the adapter is a no-op returning []."""
        retriever = DifyApiRetriever(base_url="", api_key="")
        assert retriever.retrieve("any query", ["dataset-1"]) == []

    def test_partial_config_still_unconfigured(self):
        """A base URL without an API key is still unconfigured."""
        retriever = DifyApiRetriever(base_url="https://api.dify.ai", api_key="")
        assert retriever.retrieve("q", ["d"]) == []

    def test_satisfies_retriever_protocol(self):
        assert isinstance(DifyApiRetriever(), Retriever)


class TestGetRetriever:
    def test_returns_a_retriever(self):
        retriever = get_retriever()
        assert isinstance(retriever, Retriever)

    def test_is_cached(self):
        assert get_retriever() is get_retriever()
