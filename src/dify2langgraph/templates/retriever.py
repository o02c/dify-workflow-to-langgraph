"""Retriever port for knowledge-retrieval nodes (ADR-0006).

Knowledge-retrieval goes through the ``Retriever`` protocol (a port) rather than a
concrete backend, so the retrieval backend can be swapped without touching node
bodies. The default adapter, ``DifyApiRetriever``, calls Dify's public dataset
Retrieval API, configured via environment variables:

- ``DIFY_API_BASE_URL`` (e.g. ``https://api.dify.ai``)
- ``DIFY_API_KEY`` (a dataset API key)
- ``DIFY_RETRIEVAL_SEARCH_METHOD`` (default ``semantic_search``; the Dify
  ``/retrieve`` API requires a search method, and the Node DSL does not carry one
  -- it is a dataset/deploy concern. Use ``keyword_search`` / ``full_text_search``
  / ``hybrid_search`` for datasets without an embedding model.)
- ``DIFY_RETRIEVAL_TOP_K`` (default ``4``)

When ``DIFY_API_BASE_URL`` / ``DIFY_API_KEY`` are unset the default adapter is a
no-op that returns ``[]`` and logs a warning, so the generated graph still runs
end-to-end before retrieval is wired up. Depends only on the standard library.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def _env_top_k(default: int = 4) -> int:
    """Parse DIFY_RETRIEVAL_TOP_K, warning (not silently failing) on a bad value."""
    raw = os.getenv("DIFY_RETRIEVAL_TOP_K")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid DIFY_RETRIEVAL_TOP_K=%r; using %d", raw, default)
        return default


@runtime_checkable
class Retriever(Protocol):
    """Port: retrieve records for a query from one or more datasets."""

    def retrieve(
        self, query: str, dataset_ids: list[str], **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Return a list of retrieved records (each a dict)."""
        ...


class DifyApiRetriever:
    """Default adapter: Dify's public dataset Retrieval API.

    Unconfigured (missing base URL or API key) -> returns ``[]`` so generated code
    runs without credentials.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("DIFY_API_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("DIFY_API_KEY", "")
        self.timeout = timeout

    def retrieve(
        self, query: str, dataset_ids: list[str], **kwargs: Any
    ) -> list[dict[str, Any]]:
        if not self.base_url or not self.api_key:
            logger.warning(
                "DifyApiRetriever is not configured (set DIFY_API_BASE_URL and "
                "DIFY_API_KEY); returning no records."
            )
            return []

        records: list[dict[str, Any]] = []
        for dataset_id in dataset_ids:
            records.extend(self._retrieve_one(dataset_id, query, kwargs))
        return records

    def _retrieval_model(self, override: dict[str, Any] | None) -> dict[str, Any]:
        """Build a complete retrieval_model for the /retrieve API.

        The API requires ``search_method`` / ``reranking_enable`` / ``top_k`` /
        ``score_threshold_enabled`` together, but the Node DSL only carries a subset
        (top_k, score_threshold). We default the rest here -- ``search_method`` from
        the environment, since it is a dataset/deploy concern -- and overlay whatever
        the Node config provided.
        """
        model: dict[str, Any] = {
            "search_method": os.getenv("DIFY_RETRIEVAL_SEARCH_METHOD", "semantic_search"),
            "reranking_enable": False,
            "top_k": _env_top_k(),
            "score_threshold_enabled": False,
        }
        if override:
            model.update({k: v for k, v in override.items() if v is not None})
        return model

    def _retrieve_one(
        self, dataset_id: str, query: str, kwargs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/v1/datasets/{dataset_id}/retrieve"
        payload: dict[str, Any] = {
            "query": query,
            "retrieval_model": self._retrieval_model(kwargs.get("retrieval_model")),
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.error("Retrieval failed for dataset %s: %s", dataset_id, exc)
            return []
        return body.get("records", [])


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    """Return the process-wide Retriever (the default Dify API adapter).

    Swap the retrieval backend by reassigning this function or replacing the
    module-level singleton with another ``Retriever`` implementation.
    """
    global _retriever
    if _retriever is None:
        _retriever = DifyApiRetriever()
    return _retriever
