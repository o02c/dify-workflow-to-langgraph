# Fixture provenance

Some fixtures are real Dify workflow DSL exports, used to test the transpiler
against workflows in the wild (not just hand-written minimal cases).

## Hand-written (authored for this repo)

- `simple_workflow.yml` — minimal linear start → llm → end.
- `ifelse_workflow.yml` — minimal `if-else` with `true`/`false` branches.
- `guardduty_handler.yml` — a `question-classifier` branching workflow.
- `env_sys_workflow.yml` — built in Dify Cloud specifically to pin down shapes no
  other fixture had. Exercises, in one `mode: workflow` export:
  - `environment_variables` with `value_type` `string`, `integer` and **`secret`**
    (the secret's value is exported in plaintext)
  - both env reference syntaxes: `{{#env.API_BASE#}}` in a prompt, and
    `variable_selector: [env, MAX_RETRY]` in an `if-else` condition
  - `sys.*` in End outputs: `[sys, app_id]` and `[sys, user_id]`
  - Start variables covering `paragraph` / `text-input` / `number` / `select`,
    required and optional, with and without a `default` -- including Dify's habit
    of writing `default: ''` where no default was set, and a `number` whose
    default arrives as the string `'3'`
  - an LLM node with `structured_output_enabled` whose schema an End node reads
    through a three-element selector
- `error_strategy_workflow.yml` — built in Dify Cloud (exported as
  `http-request_code_error-strategy`), `mode: workflow`, `version: 0.7.0`. Built to
  pin down three shapes the transpiler was getting wrong, each verified to fail
  before the fix:
  - an **`http-request`** node, which had no handler at all -- downstream reads of
    `body` / `status_code` raised `KeyError`
  - a **`code`** node declaring its outputs in the DSL
    (`outputs: {body_head: {type: string}}`), where the generator emitted an
    invented `result` / `stdout` / `stderr` instead
  - **`error_strategy: fail-branch`** with `retry_config`
    (`retry_enabled: true`, `retry_interval: 100` -- milliseconds), and the
    resulting `sourceHandle: fail-branch` edge alongside the `source` edge. The
    generator emitted both as unconditional edges, so the failure path ran on
    success.
  - both branches converging on **one End node**, which reads `error_message` /
    `error_type` / `status_code` from the failing node on the error path. Reading
    from the branch that did not run raised `KeyError` on the node key itself.
- `chatflow_sys_query.yml` — also built in Dify Cloud. `mode: advanced-chat`, the
  one shape a `mode: workflow` export cannot show:
  - `{{#sys.query#}}` and `{{#sys.files#}}` as template strings (both in
    `prompt_template` and in `memory.query_prompt_template`) -- `sys.query` does
    not exist in workflow mode
  - a Start Node with `variables: []`: in a chatflow the user's input arrives as
    `sys.query`, not as a declared variable
  - an `answer` node, whose `answer` field is a template referencing an upstream
    node the same way an End Node's `value_selector` does
  - non-numeric node ids (`llm`, `answer`)

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
  the converter leaves as an open question (currently stubbed via the fallback handler).
