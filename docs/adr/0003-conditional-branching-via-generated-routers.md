# Conditional branching via generated router functions in graph.py

Branching Nodes (`question-classifier`, `if-else`) are wired with `add_conditional_edges` and a generated `route_<node>(state)` function whose branch-key→target mapping is derived deterministically from the DSL edge `sourceHandle`. The router reads the branching Node's output field (e.g. `class_id` for question-classifier, `selected_branch` for if-else) and returns the matching branch key.

We keep routing in graph.py rather than having node bodies return `Command(goto=...)` so the graph structure stays visible and deterministic in one place; only the branch *decision* lives in the (possibly LLM-backed) node body, while the *wiring* is deterministic.

## Consequences

- Each branching Node type needs a type-specific rule for which output field drives the route — the Structure is not uniform across Node types.
- `iteration` (loop / subgraph) is deliberately out of scope for now; its Structure differs fundamentally from single-successor and conditional-branch Nodes.
- The earlier output that emitted plain `add_edge` for every branch (causing all branches to fire) was a bug this decision replaces.

## Status

Implemented. `codegen/routing.py` holds the deterministic rules (`BRANCHING_NODE_TYPES`,
per-type `decision_field`, `branch_map` from `sourceHandle`). `graph_generator.py` emits a
`route_<node>` function plus `add_conditional_edges` for each Branching Node; `node_generator.py`
defaults the decision field of a Branching Node's stub to the first branch key so the graph
resolves to a single successor and runs end-to-end before bodies are implemented.
`tests/test_generated.py::test_question_classifier_routes_to_single_branch` guards the behavior.

## Amendment: which nodes reach `END`

Terminal edges were keyed off node **type** `end`. A chatflow declares no `end`
node at all — it finishes on an `answer` node — so its graph had a dangling
terminal and `END` imported but unused. The rule is now **shape**: a node with no
outgoing edge reaches `END`.

Shape alone is not sufficient, though. An iteration's body is a sub-graph whose
last step has no outgoing edge in the DSL's flat edge list, so it looks terminal —
and wiring it to `END` asserts that the whole workflow finishes when one pass of
the loop body does. `tests/fixtures/json_translate.yml` contains exactly that node
(`合并`, `isInIteration: true`). Nodes the DSL marks as inside an iteration are
therefore excluded.

This was silent: langgraph's `StateGraph.validate` rejects neither dead ends nor
unreachable nodes, so nothing downstream would have reported it. It is inert today
only because the iteration sub-graph has no incoming edge; it becomes a premature-
termination bug the moment `iteration` is implemented.

`END` is imported only when something reaches it, since an unused import is a lint
failure in the generated package (ADR-0007).
