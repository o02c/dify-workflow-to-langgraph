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

Only referenced fields are declared, deliberately: which `sys` fields exist is
**mode-dependent** (`sys.query` exists in `advanced-chat` but not in `workflow`, where
`sys.app_id` / `sys.user_id` / `sys.timestamp` appear instead), so declaring a fixed set would be
wrong for one mode or the other. Dify gates them the same way in its own variable picker.

*Membership* being mode-dependent does not make each field's *type* unknown, and the two were
conflated at first: the generator carried a table of one entry (`files`) and defaulted everything
else to `str`. `sys.dialogue_count` and `sys.timestamp` are numbers, so that annotated them wrongly
and put `"dialogue_count": "example"` into the generated entry point. The type table is now Dify's
own `SystemVariableKey` set, and a field outside it resolves to `Any` — honest about not knowing,
rather than wrong.

**Reads of `sys` are guarded.** The caller supplies these at invoke time, exactly like the workflow
inputs a Start Node validates (ADR-0009), but omitting them produced a bare `KeyError: 'sys'` from
inside whichever body read it first — naming neither the field nor who was supposed to provide it.
A deterministic body that reads `sys` now rejects the omission by name. Only a deterministic body:
a Stub does not read them yet, and rejecting an input nothing consumes would be stricter than the
workflow. Dify itself fills several of these (it defaults `files` to `[]`, generates
`workflow_run_id`, derives `timestamp` and `dialogue_count`); the generated package is detached from
Dify, so the caller must supply whatever the workflow reads — `app_id` in particular is not in the
export and cannot be inferred.

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

Two further constraints came out of hardening this against DSLs we had not seen:

- **A DSL name cannot be pasted into generated source unchecked.** Dify's only rule is
  `/^\w+$/` not starting with a digit, which admits every Python keyword and every name the
  generated module defines itself. `class = 'x'` is a `SyntaxError` — the whole package stops
  importing — and `os = 'x'` after `import os` compiles and then breaks every secret read.
  Unusable names are skipped with a warning naming the reason, as is a non-secret with no
  `value` (which used to abort the translation with a bare `KeyError: 'value'`).
- **One filter decides what exists.** `env.py` is written from `environment_variables` while
  references were resolved from the *reference*, so the two could disagree: a node got
  `from .. import env` for a module that was never generated, and the package then failed to
  import at all — reported by Python as a circular import, pointing at the wrong file. The
  filter now runs once, in the parser, so every generator downstream sees the same list.
  Dify does not scrub stale selectors, so an export can reference a variable the author
  deleted; that resolves to a placeholder rather than to `env.GONE` as executable code.

`env.py` also loads a `.env` before resolving any secret. Without it, a secret written to
`.env` resolved only if `llm.py` — which also calls `load_dotenv` — happened to be imported
first, so the same `.env` and the same workflow succeeded or failed depending on import order.
Exported variables still win. The required names are exposed as `REQUIRED_ENV_VARS` so a caller
can check them up front instead of discovering one missing mid-run.

Still deferred: `{{#context#}}` resolution, and wiring normalized inputs into non-End node
bodies (arrives with LLM opt-in body generation, ADR-0001).

## What a real export settled (`tests/fixtures/env_sys_workflow.yml`)

Built in Dify Cloud specifically to pin these shapes down, because the decisions above
were made against guessed schemas. What it showed, and how each was resolved:

- **A `value_type: secret` environment variable exports its value in plaintext.** Emitting
  it as a module constant would write a credential into source the customer then commits.
  → Secrets are read from the environment instead (above).
- **`value_type` is a Dify vocabulary, not Python type names.** The factory accepts `string`,
  `number`, `integer`, `float`, `boolean`, `object`, `array[string|number|object|boolean]`,
  `secret` and `llm`. An `integer` value arrives as an actual int while a `number` Start
  default arrives as a string. → Values are emitted with `repr`, which is faithful for all of
  them; `object` / `array[*]` become mutable module-level constants and an `llm` variable
  becomes its raw `{provider, name, mode, completion_params}` dict rather than a resolved
  model. Neither is interpreted further.
- **The parser normalized `{{#env.API_BASE#}}` to `state["env"]["API_BASE"]`**, contradicting
  this ADR: `env` is constants *outside* state and `GraphState` has no `env` key, so that
  access could not resolve. → The parser path moved; `env.API_BASE` renders as `env.API_BASE`.
- **`sys.*` in `mode: workflow` appears as `[sys, app_id]` / `[sys, user_id]`**, and `sys.query`
  did not appear at all. → Confirmed that membership is mode-dependent; only referenced fields
  are declared.
