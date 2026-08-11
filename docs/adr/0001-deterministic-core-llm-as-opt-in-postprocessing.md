# Deterministic core, LLM as opt-in post-processing

We convert Dify Workflow DSL into LangGraph code with a **deterministic** pipeline (parse → generate state / node skeletons / graph wiring); the same DSL always yields the same output, so the result is testable and the generated `GraphState` gives static, linter-detectable type safety. LLM-based steps (filling node bodies from `# TODO` stubs, auto-fixing lint errors) are **opt-in post-processing**, never a required stage, because making them mandatory would sacrifice reproducibility, unit-testability, and the correctness guarantees that are the tool's core value.

## Considered Options

- **LLM-driven generator** (skeleton deterministic, node bodies written by an LLM as the default path) — rejected: non-deterministic, requires an API key to produce runnable output, hard to test, weak correctness guarantees.
- **Pure deterministic transpiler** (no LLM at all) — good guarantees but leaves hard-to-mechanize node bodies (e.g. `code` nodes, free-form prompts) permanently as stubs.
- **Deterministic core + opt-in LLM post-processing** (chosen) — default run is fully deterministic and produces a runnable/typed skeleton; LLM fill-in and lint-fix are separate, opt-in stages layered on top.
