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
        # The /retrieve API requires a complete retrieval_model; the adapter fills
        # the required fields (search_method from env, defaulting to semantic_search).
        assert captured["body"] == {
            "query": "my query",
            "retrieval_model": {
                "search_method": "semantic_search",
                "reranking_enable": False,
                "top_k": 4,
                "score_threshold_enabled": False,
            },
        }

    def test_search_method_and_top_k_from_env(self, monkeypatch):
        """search_method / top_k are dataset/deploy concerns, driven by env."""
        monkeypatch.setenv("DIFY_RETRIEVAL_SEARCH_METHOD", "keyword_search")
        monkeypatch.setenv("DIFY_RETRIEVAL_TOP_K", "7")
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"records": []})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        DifyApiRetriever(base_url="https://api.dify.ai", api_key="k").retrieve("q", ["d"])
        assert captured["body"]["retrieval_model"]["search_method"] == "keyword_search"
        assert captured["body"]["retrieval_model"]["top_k"] == 7

    def test_node_retrieval_model_overrides_defaults(self, monkeypatch):
        """A retrieval_model passed by the node overlays the adapter defaults."""
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"records": []})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        DifyApiRetriever(base_url="https://api.dify.ai", api_key="k").retrieve(
            "q", ["d"], retrieval_model={"top_k": 2, "score_threshold_enabled": True}
        )
        model = captured["body"]["retrieval_model"]
        assert model["top_k"] == 2  # node override wins
        assert model["score_threshold_enabled"] is True
        assert model["search_method"] == "semantic_search"  # default kept

    def test_zero_valued_overrides_survive(self, monkeypatch):
        """top_k=0 / score_threshold=0.0 overlay (merge uses `is not None`, not truthiness)."""
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"records": []})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        DifyApiRetriever(base_url="https://api.dify.ai", api_key="k").retrieve(
            "q", ["d"], retrieval_model={"top_k": 0, "score_threshold": 0.0}
        )
        model = captured["body"]["retrieval_model"]
        assert model["top_k"] == 0
        assert model["score_threshold"] == 0.0

    def test_invalid_top_k_env_falls_back_with_warning(self, monkeypatch):
        """A non-int DIFY_RETRIEVAL_TOP_K falls back to 4 rather than crashing to []."""
        monkeypatch.setenv("DIFY_RETRIEVAL_TOP_K", "not-a-number")
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse({"records": [{"segment": {"content": "x"}}]})

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        records = DifyApiRetriever(base_url="https://api.dify.ai", api_key="k").retrieve(
            "q", ["d"]
        )
        assert records == [{"segment": {"content": "x"}}]  # not swallowed to []
        assert captured["body"]["retrieval_model"]["top_k"] == 4

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
