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
