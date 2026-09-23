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

**`sys.*` is now implemented.** The generator declares a `SysInputs` TypedDict holding
exactly the fields the DSL references and adds `sys: SysInputs` to `GraphState`; the caller
supplies them at invoke time alongside the workflow inputs (ADR-0009). Selectors and template
strings both resolve to `state["sys"]["<field>"]` — the parser already normalised the two
syntaxes into one `VariableReference`, so only the declaration and the End/knowledge-retrieval
resolution had to change.

Only referenced fields are declared, deliberately: the `sys` catalogue is **mode-dependent**
(`sys.query` exists in `advanced-chat` but not in `workflow`, where `sys.app_id` / `sys.user_id`
appear instead), so a fixed list would be wrong for one mode or the other.

**`env.*` is now implemented**, with one amendment forced by a real export. The DSL's
`environment_variables` become constants in a generated `env.py`, reached as `env.NAME`
after `from .. import env` — the module form rather than `from ..env import NAME`, so a DSL
variable called `state` or `output` cannot shadow a local.

The amendment: a `value_type: secret` variable **exports its value in plaintext**, so emitting
it as a constant would write a credential into source the customer then commits. Secrets are
therefore *not* constants. They are read from the process environment on first access (PEP 562
module `__getattr__`), keyed by the DSL's own name, and a missing one raises naming the variable
rather than yielding `""` — the same "fail with a named cause" choice as the Bedrock region
(ADR-0008) and required workflow inputs (ADR-0009). Lazy rather than import-time so a package
whose Stub bodies never read the secret still imports and runs.

Reference resolution moved with it: `env.API_BASE` now renders as `env.API_BASE`, not
`state["env"]["API_BASE"]`. That address only ever reached generated comments and the embedded
NODE_CONFIG block, never executable code — but those are exactly what the LLM body-generation
pass reads, so it was teaching the model to write code that cannot resolve.

Still deferred: `{{#context#}}` resolution, and wiring normalized inputs into non-End node
bodies (arrives with LLM opt-in body generation, ADR-0001).

## Findings from a real export (`tests/fixtures/env_sys_workflow.yml`)

Built in Dify Cloud specifically to pin these shapes down. Three things it shows
that change what "env as module constants" can mean:

- **A `value_type: secret` environment variable exports its value in plaintext.**
  Emitting it as a module constant in a generated `env.py` would write a credential
  into source the customer then commits. Whatever the implementation does, secrets
  cannot be treated like the string and integer cases.
- **`value_type` is `string` / `integer` / `secret`**, not Python type names, and an
  `integer` value arrives as an actual int while a `number` Start default arrives as
  a string. Neither can be passed through untyped.
- **The parser currently normalizes `{{#env.API_BASE#}}` to `state["env"]["API_BASE"]`**,
  which contradicts the decision above -- `env` is specified as constants *outside*
  state, and `GraphState` has no `env` key, so that access cannot resolve. The
  template-string path and this ADR disagree and one of them has to move.

`sys.*` in `mode: workflow` appears as `[sys, app_id]` / `[sys, user_id]` in End
outputs; `sys.query` did not appear (it is a chatflow variable), so the `sys`
membership this ADR assumes -- query/files/user_id -- is mode-dependent.
