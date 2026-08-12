# Variable reference normalization and homes for special namespaces

Dify expresses inter-Node data flow in two syntaxes — value_selector arrays (`['<id>', 'field']`) in structured config and template strings (`{{#<id>.field#}}`) in prompt text. Both normalize to the single canonical access `state["node_<id>"]["field"]` (template strings become f-strings); this keeps translation deterministic and consistent with docs/adr/0002.

Non-Node namespaces get fixed homes decided up front so the state shape doesn't change later:

- `sys.*` (runtime inputs: query/files/user_id) → a **reserved `sys` key in GraphState** (`sys: SysInputs`), populated at invoke time, so every read uses the same `state[...]` pattern and stays typed.
- `env.*` (DSL `environment_variables`, which are constants) → module-level constants in a generated `env.py`, **not** in mutable state.
- `{{#context#}}` → resolved via the LLM Node's `context.variable_selector` to the referenced knowledge-retrieval `result` (a per-Node-type rule).
- `conversation.*` → out of scope (chatflow only).

The `sys`-in-state / `env`-as-constants asymmetry is deliberate: `sys` values vary per run and belong in state; `env` values are static and don't.

## Consequences

- `sys` and `env` homes are reserved now, but their implementation is deferred; v1 prioritizes Node references and `context`.

## Status

Node-reference normalization implemented. `VariableReference.to_state_access` and
`replace_variable_references` (`parser/dsl_parser.py`) now emit the canonical
`state["node_<id>"]["field"]` for both syntaxes — using `sanitize_function_name` so numeric
Dify IDs map to the same key as `GraphState` (ADR-0002), and honoring an LLM name map when
present. The shared name logic moved to a dependency-free leaf module `dify2langgraph/naming.py`
(re-exported by `codegen/naming.py`) so the parser and generators agree on one key without an
import cycle.

First deterministic consumer: the **End node** (`EndHandler`, ADR-0005) forwards each declared
output's `value_selector` as a normalized access (e.g. `"result": state["llm_node"]["text"]`)
instead of a placeholder — a real body, not a Stub. Selectors into `sys`/`env` or unknown nodes
fall back to a placeholder (those namespaces remain deferred). `tests/test_parser.py`,
`tests/test_handlers.py`, and `tests/test_generated.py` (End output equals the upstream value)
cover this.

Still deferred: `sys.*` / `env.*` homes, `{{#context#}}` resolution, and wiring normalized
inputs into non-End node bodies (arrives with LLM opt-in body generation, ADR-0001).
