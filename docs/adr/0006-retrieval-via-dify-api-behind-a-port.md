# RAG via Dify's public Retrieval API, behind a swappable Retriever port

Knowledge-retrieval uses Dify's **public dataset Retrieval API** as the default backend, accessed through a `Retriever` protocol (port) in the generated `retriever.py`; the default adapter is `DifyApiRetriever` (configured with a Dify API base URL and API key via env). The knowledge-retrieval Node Handler generates calls against the `Retriever` interface, not a concrete backend, so the retrieval backend can later be swapped — e.g. to point at the export destination's own vector DB — without touching generated Node bodies.

**This supersedes the original requirement Goal #2** ("connect directly to Dify's existing RDS/PGVector"): requirements changed, and direct DB access coupled the tool to Dify's internal, undocumented schema and forced the generated code to re-match Dify's per-dataset embedding model. Going through the API decouples us from Dify's schema and moves embedding/search server-side, eliminating the embedding-model-matching problem.

## Considered Options

- **Direct SQL against Dify's internal PGVector schema** (the original implementation, `db_retriever.py`) — rejected: tight coupling to undocumented tables that change across Dify versions, plus the embedding-model-matching gap.
- **Dify public Retrieval API behind a port** (chosen) — schema-independent, loosely coupled, swappable backend.

## Consequences

- The generated code depends on a running Dify instance reachable via API for the default adapter; swapping to another backend is an adapter implementation.
- The existing `core/db_retriever.py` (direct SQL) is superseded and should be removed or reduced to an optional alternate adapter.
- requirement.md Goal #2 must be updated to reflect this decision.

## Status

Implemented. The `Retriever` port + default `DifyApiRetriever` adapter ship as a
dependency-free template (`templates/retriever.py`, stdlib `urllib`) copied into every
generated package as `retriever.py`. `KnowledgeRetrievalHandler` emits a real body that calls
`get_retriever().retrieve(query=<normalized selector>, dataset_ids=[...])` (ADR-0004 for the
query normalization) and imports the port via `from ..retriever import get_retriever`. The
adapter reads `DIFY_API_BASE_URL` / `DIFY_API_KEY` from the environment; when unset it logs a
warning and returns `[]`, so the generated graph runs end-to-end without credentials. Swap the
backend by replacing the module-level singleton in `get_retriever()` with another `Retriever`.
`core/db_retriever.py` was already removed in the redesign cleanup. Covered by
`tests/test_retriever.py`, `tests/test_handlers.py`, and `tests/test_generated.py`.
