# Per-node-type logic lives in a handler registry

All knowledge about a given Dify Node type is consolidated into one **Node Handler** registered by type, instead of being scattered across the state, node, and graph generators as parallel `if/elif` chains. Each handler exposes a small common interface: `output_fields()` (the Node Output TypedDict), `generate_body()` (the Node Body, either a real implementation or a Stub), and `routing()` (a single Edge, or Router info for a Branching Node). The generators become thin orchestrators that call handlers; an unknown type falls back to a default handler that emits a generic typed Stub so the output still compiles.

Adding support for a new Node type is therefore adding one handler, which directly matches the intent to grow Node-type coverage incrementally. v1 implements handlers for `start`, `llm`, `end`, `question-classifier`, and `if-else`; everything else uses the fallback.

## Consequences

- Handlers are the unit of testing, aligning with the deterministic core (docs/adr/0001).
- `iteration` (loop) handling is an open question: an iteration Node appears as a single Node but contains a sub-graph of child Nodes, so how it maps to a handler (single node vs. compiled subgraph) must be settled after inspecting real iteration DSL before committing to a shape.

## Status

Implemented. `codegen/handlers.py` holds the registry: a `NodeHandler` base (generic-Stub
fallback) with per-type subclasses exposing `output_fields()` and `stub_output()`, plus
`is_branching` / `decision_field` for Branching Nodes. `get_handler(type)` resolves the handler;
unknown types fall back. The generators are now thin orchestrators — `state_generator` and
`node_generator` delegate output fields and Stub bodies to the handler, and `graph_generator`
reads `is_branching` / `decision_field` from it (structural branch-map derivation stays in
`codegen/routing.py`). v1 handlers: `start`, `llm`, `end`, `knowledge-retrieval`, `code`, `tool`,
`template-transform`, `variable-aggregator`, `answer`, `agent`, `question-classifier`, `if-else`.
Inspected against the real `json_translate.yml` fixture, an `iteration` container currently maps
to the fallback Stub (its child sub-graph is left unwired) — consistent with iteration being
deferred. `tests/test_handlers.py` covers the registry.

## Amendment: the LLM handler's outputs

A Stub's declared output fields are a contract downstream selectors read through, so a
missing one is a run-time `KeyError` in the generated package rather than a cosmetic gap.
Three were missing.

- **`structured_output`** was not declared at all, so a real export using structured output
  crashed the moment the End node read through it. It is declared when
  `structured_output_enabled` is set, and the Stub is *shaped from the DSL's own schema* so a
  selector into a declared field resolves.
- That shaping was flat at first, which fixed the crash only at depth 1: a nested object was
  emitted as a bare `{}`, so `[<llm>, structured_output, person, name]` raised the identical
  `KeyError` one level down. It recurses now, and an `array` of objects gets one element so an
  indexed read resolves. A fragment whose type cannot be read (`$ref`, `anyOf`, no `type`)
  becomes `None` — visibly a placeholder rather than a wrong shape.
- **`reasoning_content`** is part of Dify's LLM node output and was absent, so a selector into
  it failed the same way. `usage` is typed `dict[str, Any]`: Dify's usage carries floats and a
  currency string, not only ints.
