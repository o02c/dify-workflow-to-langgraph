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
- `sys.*` (ADR-0004) is still unimplemented. It is a different namespace —
  workflow-level runtime inputs such as `sys.query` — and is unaffected by this.
