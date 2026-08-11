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
