"""Retriever port for knowledge-retrieval nodes (ADR-0006).

Knowledge-retrieval goes through the ``Retriever`` protocol (a port) rather than a
concrete backend, so the retrieval backend can be swapped without touching node
bodies. The default adapter, ``DifyApiRetriever``, calls Dify's public dataset
Retrieval API, configured via environment variables:

- ``DIFY_API_BASE_URL`` (e.g. ``https://api.dify.ai``)
- ``DIFY_API_KEY`` (a dataset API key)

When those are unset the default adapter is a no-op that returns ``[]`` and logs a
warning, so the generated graph still runs end-to-end before retrieval is wired up.
Depends only on the standard library.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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

    def _retrieve_one(
        self, dataset_id: str, query: str, kwargs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        url = f"{self.base_url}/v1/datasets/{dataset_id}/retrieve"
        payload: dict[str, Any] = {"query": query}
        if "retrieval_model" in kwargs:
            payload["retrieval_model"] = kwargs["retrieval_model"]
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
