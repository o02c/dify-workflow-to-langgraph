# Conditional branching via generated router functions in graph.py

Branching Nodes (`question-classifier`, `if-else`) are wired with `add_conditional_edges` and a generated `route_<node>(state)` function whose branch-key→target mapping is derived deterministically from the DSL edge `sourceHandle`. The router reads the branching Node's output field (e.g. `class_id` for question-classifier, `selected_branch` for if-else) and returns the matching branch key.

We keep routing in graph.py rather than having node bodies return `Command(goto=...)` so the graph structure stays visible and deterministic in one place; only the branch *decision* lives in the (possibly LLM-backed) node body, while the *wiring* is deterministic.

## Consequences

- Each branching Node type needs a type-specific rule for which output field drives the route — the Structure is not uniform across Node types.
- `iteration` (loop / subgraph) is deliberately out of scope for now; its Structure differs fundamentally from single-successor and conditional-branch Nodes.
- The earlier output that emitted plain `add_edge` for every branch (causing all branches to fire) was a bug this decision replaces.

## Status

Implemented. `codegen/routing.py` holds the deterministic rules (per-type `decision_field`, `branch_map` from `sourceHandle`). `graph_generator.py` emits a
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
(`合并`, `isInIteration: true`). Nodes the DSL places inside a container are
therefore excluded — and that includes `loop`, whose `loop_id` was not checked at all,
so a loop body's last step was wired straight to `END`.

Container membership follows the order Dify itself resolves it in
(`graph/scoping.py::resolve_container_id`): the newer canonical `data.container_id`,
then the top-level `parentId`, then the legacy `data.iteration_id` / `data.loop_id`.
`isInIteration` / `isInLoop` come last: Dify does not use them for scoping at all,
they are flags the editor derives. `parentId` sits at the *top level* of a DSL node
rather than under `data`, so the parser keeps it as `NodeInfo.parent_id` — a check
against `data["parentId"]` could never fire.

This was silent: langgraph's `StateGraph.validate` rejects neither dead ends nor
unreachable nodes, so nothing downstream would have reported it. It is inert today
only because the iteration sub-graph has no incoming edge; it becomes a premature-
termination bug the moment `iteration` is implemented.

`END` is imported only when something reaches it, since an unused import is a lint
failure in the generated package (ADR-0007).

## Amendment: error handling turns a node into a branch

`error_strategy: fail-branch` on any node makes Dify export a **second** outgoing edge
with `sourceHandle: fail-branch`, beside the ordinary `source` one, and promotes the
node to a branch. The generator emitted both as unconditional `add_edge` calls, so
**the failure path ran even when the node succeeded** — the exact bug this ADR was
written to replace, arriving through a different door. Dify offers the setting on
`llm`, `tool`, `http-request`, `code`, `agent` and `agent-v2`.

The router does not need an invented output field. Dify carries the chosen branch out
of band (`NodeRunResult.edge_source_handle`), but it also injects `error_message` and
`error_type` into the node's outputs on the failure path *only* — so presence of
`error_message` is equivalent, and it is a real Dify output:

```python
def route_http_node(state: GraphState) -> str:
    return "fail-branch" if state["http_node"].get("error_message") else "source"
```

`branch_map` already keys on the DSL's `sourceHandle`, so no extra mapping is needed,
and a Stub that leaves `error_message` unset takes the success branch — keeping the
rule that a stubbed graph resolves to exactly one successor.

Retries and the `default-value` strategy are a separate concern and remain unhandled
(see TODO.md).

## Amendment: `if-else` routes on Dify's own field name

The decision field was `selected_branch`, a name this generator invented. Dify calls
it `selected_case_id`, and routes with `selected_case_id or "false"` — an unmatched
condition leaves the output unset and means the false branch. Both are now mirrored,
so whoever implements the body (a person, or the opt-in LLM pass) computes the value
under the name everything else uses.
