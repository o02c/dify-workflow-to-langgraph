# State is keyed by Dify node ID, not by readable names

The generated `GraphState` is a `TypedDict(total=False)` with **one key per Node**, and the canonical key is `node_<dify_node_id>` (e.g. `node_1722391426202`), each mapping to that Node's own output `TypedDict`. A Variable Reference `{{#<id>.field#}}` therefore maps mechanically and uniquely to `state["node_<id>"]["field"]`, and the linter flags any access to a key that doesn't exist.

We use the raw Dify node ID rather than a readable snake_case name derived from the Node title because titles are non-unique (a workflow can have two "終了" end nodes) and frequently non-ASCII (Japanese), so deriving a stable, collision-free, deterministic identifier from them is unreliable — whereas node IDs are already unique and stable. Human-readable renaming is left to the opt-in LLM pass (see docs/adr/0001).

## Consequences

- Generated code is correct and deterministic but not very readable by default; readability is an opt-in LLM concern.
- The per-Node output `TypedDict` model is what makes static, linter-detectable type safety possible — this is a core requirement, not incidental.
