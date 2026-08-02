# Per-node-type logic lives in a handler registry

All knowledge about a given Dify Node type is consolidated into one **Node Handler** registered by type, instead of being scattered across the state, node, and graph generators as parallel `if/elif` chains. Each handler exposes a small common interface: `output_fields()` (the Node Output TypedDict), `generate_body()` (the Node Body, either a real implementation or a Stub), and `routing()` (a single Edge, or Router info for a Branching Node). The generators become thin orchestrators that call handlers; an unknown type falls back to a default handler that emits a generic typed Stub so the output still compiles.

Adding support for a new Node type is therefore adding one handler, which directly matches the intent to grow Node-type coverage incrementally. v1 implements handlers for `start`, `llm`, `end`, `question-classifier`, and `if-else`; everything else uses the fallback.

## Consequences

- Handlers are the unit of testing, aligning with the deterministic core (docs/adr/0001).
- `iteration` (loop) handling is an open question: an iteration Node appears as a single Node but contains a sub-graph of child Nodes, so how it maps to a handler (single node vs. compiled subgraph) must be settled after inspecting real iteration DSL before committing to a shape.
