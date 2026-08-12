# Project: Dify DSL to LangGraph Converter

> Redesign in progress (2026-08). The canonical glossary is [CONTEXT.md](./CONTEXT.md);
> the "why" behind each decision lives in [docs/adr/](./docs/adr/). This file is the
> high-level requirement summary and defers to those for detail.

## 1. Overview
Dify のワークフロー DSL (YAML) を解析し、実行可能で型安全な LangGraph の Python コードを自動生成する。
変換の中核は**決定論的**で、LLM 支援は任意の後処理（ADR-0001）。

## 2. Goals
- Dify のワークフロー構造（state / 依存 / エッジ・分岐）を、型安全な LangGraph コードに**決定論的に**変換し、カスタマイズ性を高める。
- `TypedDict` を活用し、存在しないノード参照を静的に検知（Linter 警告）できる型安全なコードを出力する（ADR-0002）。
- RAG は Dify の**公開 Retrieval API** 経由で維持し、バックエンドを差し替え可能な `Retriever` ポートの背後に置く（ADR-0006）。
  - ~~既存の AWS RDS (PGVector) に直接接続する~~ … 要件変更により撤回。ADR-0006 が置換。

## 3. Scope (v1)
- **構造レイヤー**は全ノードで正しく生成することを目標とする。
  - 分岐（`add_conditional_edges`, ADR-0003）は **実装済み**。`question-classifier` / `if-else` に対し `route_<node>` 関数と条件エッジを生成（`codegen/routing.py`）。`tests/test_generated.py` で単一分岐到達を検証。
- **ノード本体**は全タイプが Node Handler レジストリ（ADR-0005、実装済み `codegen/handlers.py`）経由で型付き出力を持つ Stub を生成。`start` / `end` は宣言された変数から出力フィールドを導出。未登録タイプは汎用 Stub にフォールバック。本体（実装）の LLM 埋めは任意後処理（ADR-0001）。分岐 Stub は決定フィールドを先頭ブランチにデフォルトするため、本体未実装でもグラフは単一経路で走る。
- 未対応・保留は「Deferred」（[TODO.md](./TODO.md)）参照。

## 4. Implementation Requirements
決定は ADR に集約。要点のみ:

- **Parser**: `nodes` から全 `id` を抽出し、value_selector 配列と `{{#id.field#}}` の両構文からノード間依存を特定（ADR-0004）。
- **State**: `TypedDict(total=False)` の `GraphState`。正準キーは `node_<dify_node_id>`（ADR-0002）。`sys` は予約キー、`env` は生成 `env.py` の定数（ADR-0004）。
- **Codegen**: ノードタイプごとの Node Handler（`codegen/handlers.py`）が `output_fields` / `stub_output` と分岐情報（`is_branching` / `decision_field`）を担う（ADR-0005）。構造的な分岐マップ導出は `codegen/routing.py`。生成物の自己完結パッケージ化（相対 import、1 ノード 1 ファイル）は目標（未実装）。
- **LLM 後処理（任意）**: `# TODO` スタブ本体の LLM 埋め、および lint 自動修正エージェントはオプトイン（ADR-0001）。

## 5. Canonical Layout
`src/dify2langgraph/` をパッケージ正典とする（旧フラット構成 `translator.py` 等は廃止）。
生成物は自己完結パッケージ（相対 import・`sys.path` ハック廃止）を目標とする。
- 現状出力: `state.py` / `graph.py` / `nodes/<node>.py` / `llm.py`（フラット import・要 `sys.path`）
- 目標追加: `env.py`（ADR-0004）/ `retriever.py`（ADR-0006）、および相対 import 化（いずれも未実装）
