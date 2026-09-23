# Fixture provenance

Some fixtures are real Dify workflow DSL exports, used to test the transpiler
against workflows in the wild (not just hand-written minimal cases).

## Hand-written (authored for this repo)

- `simple_workflow.yml` — minimal linear start → llm → end.
- `ifelse_workflow.yml` — minimal `if-else` with `true`/`false` branches (ADR-0003).
- `guardduty_handler.yml` — a `question-classifier` branching workflow.
- `env_sys_workflow.yml` — built in Dify Cloud specifically to pin down shapes no
  other fixture had. Exercises, in one `mode: workflow` export:
  - `environment_variables` with `value_type` `string`, `integer` and **`secret`**
    (the secret's value is exported in plaintext -- see ADR-0004)
  - both env reference syntaxes: `{{#env.API_BASE#}}` in a prompt, and
    `variable_selector: [env, MAX_RETRY]` in an `if-else` condition
  - `sys.*` in End outputs: `[sys, app_id]` and `[sys, user_id]`
  - Start variables covering `paragraph` / `text-input` / `number` / `select`,
    required and optional, with and without a `default` -- including Dify's habit
    of writing `default: ''` where no default was set, and a `number` whose
    default arrives as the string `'3'`
  - an LLM node with `structured_output_enabled` whose schema an End node reads
    through a three-element selector

## Real exports

From [svcvit/Awesome-Dify-Workflow](https://github.com/svcvit/Awesome-Dify-Workflow)
(`DSL/` directory, MIT License). Downloaded 2026-08-12. Structure unmodified; the
only edit is the LLM `provider` / model `name` fields, normalized to
`openai` / `gpt-4o-mini` (the transpiler is provider-agnostic — the DSL's provider
is not propagated into generated code, so this does not affect what is tested):

- `translation_workflow.yml` — `mode: workflow`; start, llm×4, **if-else**,
  **variable-aggregator**, end. Exercises real conditional branching.
- `json_translate.yml` — `mode: workflow`; start, code×4, tool, **iteration**
  (+ `iteration-start`), end. Exercises the iteration container shape that
  ADR-0005 leaves as an open question (currently stubbed via the fallback handler).
