"""Tests for the Retriever port template (ADR-0006).

The template is copied verbatim into every generated package; here we import it
in place and check the default adapter's behavior.
"""

import json
import urllib.error
import urllib.request

from dify2langgraph.templates.retriever import (
    DifyApiRetriever,
    Retriever,
    get_retriever,
)


class _FakeResponse:
    """Minimal urlopen() context-manager stand-in."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


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

    def test_configured_builds_request_and_extracts_records(self, monkeypatch):
        """A configured adapter posts to the dataset endpoint and returns records."""
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"records": [{"segment": {"content": "hi"}}]})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        retriever = DifyApiRetriever(base_url="https://api.dify.ai", api_key="secret")
        records = retriever.retrieve("my query", ["ds-1"])

        assert records == [{"segment": {"content": "hi"}}]
        assert captured["url"] == "https://api.dify.ai/v1/datasets/ds-1/retrieve"
        assert captured["method"] == "POST"
        assert captured["auth"] == "Bearer secret"
        assert captured["body"] == {"query": "my query"}

    def test_network_error_returns_empty(self, monkeypatch):
        """A retrieval failure is swallowed so it can't crash the graph."""

        def boom(request, timeout=None):
            raise urllib.error.URLError("down")

        monkeypatch.setattr(urllib.request, "urlopen", boom)

        retriever = DifyApiRetriever(base_url="https://api.dify.ai", api_key="secret")
        assert retriever.retrieve("q", ["ds-1"]) == []


class TestGetRetriever:
    def test_returns_a_retriever(self):
        retriever = get_retriever()
        assert isinstance(retriever, Retriever)

    def test_is_cached(self):
        assert get_retriever() is get_retriever()
