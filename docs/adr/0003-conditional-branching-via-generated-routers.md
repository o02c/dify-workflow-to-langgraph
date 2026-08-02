# Conditional branching via generated router functions in graph.py

Branching Nodes (`question-classifier`, `if-else`) are wired with `add_conditional_edges` and a generated `route_<node>(state)` function whose branch-key→target mapping is derived deterministically from the DSL edge `sourceHandle`. The router reads the branching Node's output field (e.g. `class_id` for question-classifier, `selected_branch` for if-else) and returns the matching branch key.

We keep routing in graph.py rather than having node bodies return `Command(goto=...)` so the graph structure stays visible and deterministic in one place; only the branch *decision* lives in the (possibly LLM-backed) node body, while the *wiring* is deterministic.

## Consequences

- Each branching Node type needs a type-specific rule for which output field drives the route — the Structure is not uniform across Node types.
- `iteration` (loop / subgraph) is deliberately out of scope for now; its Structure differs fundamentally from single-successor and conditional-branch Nodes.
- The current output that emits plain `add_edge` for every branch (causing all branches to fire) is a bug this decision replaces.
