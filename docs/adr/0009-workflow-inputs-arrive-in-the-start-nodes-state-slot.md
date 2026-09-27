# Workflow inputs arrive in the Start Node's own state slot

A workflow's inputs — the variables the Dify Start Node declares — are supplied
by the caller under that node's canonical state key (ADR-0002):

```python
build_graph().invoke({"start_node": {"query": "..."}})
```

The Start Node is therefore **deterministic**, like End (ADR-0004) and
knowledge-retrieval (ADR-0006). Its generated body reads that slot, rejects
missing **required** variables with a named error, and defaults optional ones
from the DSL's `required: false` flag. It computes nothing.

Before this, the Start Node emitted a Stub that returned
`{"<var>": "placeholder"}`. That Stub *overwrote* whatever the caller passed, so
**a generated workflow could not be given inputs at all** — the address question
never came up because no address worked.

It surfaced through the LLM body-generation pass (ADR-0001). With nothing in the
code or the prompt saying where inputs live, the model invented an address and
invented a different one each run: `state["query"]` on one run,
`state["start_node"]["query"]` on the next. The first is not merely unconventional
— LangGraph drops keys absent from the `GraphState` schema, and `GraphState` has
one key per Node and nothing else, so that variant cannot run no matter what the
caller passes.

## Consequences

- **The Start Node is no longer sent to the LLM.** Like the other deterministic
  types it carries no `# TODO: Implement` marker, so the opt-in pass skips it and
  cannot reintroduce a guessed address.
- **Missing required inputs raise rather than default.** Consistent with the
  Bedrock region decision (ADR-0008): fail with a named cause instead of running
  against a silently wrong value.
- **The generated `__main__.py` now carries example inputs** derived from the
  declared variables, so `python -m <package>` stays a working demonstration
  rather than an immediate `ValueError`.
- **Generated output changed**, so the ADR-0001 reference digest moved. Callers
  that previously invoked with `{}` must now pass the declared inputs.
- `sys.*` (ADR-0004) is a different namespace — workflow-level runtime inputs
  such as `sys.query` — and arrives separately. It is now implemented, and reads
  of it are guarded the same way: a named `ValueError` listing the missing fields
  rather than a bare `KeyError` from inside whichever body read it first.

## Correction: `required` beats `default`

The first implementation treated a declared `default` as satisfying a
`required: true` variable — "there is already a value to use". **That is not
Dify's rule, and it let a generated package run a workflow Dify itself would
reject.** `api/core/app/apps/base_app_generator.py::_validate_inputs`:

```python
if value is None:
    if variable_entity.required:
        raise ValueError(f"{variable_entity.variable} is required in input form")
    # Use default value and continue validation to ensure type conversion
    value = variable_entity.default
```

`required` is checked first and `default` is only read on the non-required branch.
So `required: true` raises whatever the default is, and the generated body indexes
(`supplied["topk"]`) rather than defaulting — substituting the default would have
hidden the same omission one layer down.

This also removes a heuristic. Dify writes `default: ''` for every field where the
author set nothing, which is why the original rule disabled the required check on
*every* real export; the empty-string special case was patching that rather than
the rule. `declared_default` still discards `''` — Dify does the same for an
unsupplied optional variable — but nothing required depends on it any more.

Number defaults follow Dify too: it converts with `int()` unless the string has a
decimal point, so `'3'` is `3`, not `3.0`. Emitting `3.0` put "3.0" into any
prompt that interpolated the value.
