# TODO

Roadmap after the 2026-08 redesign. Decisions: see [docs/adr/](./docs/adr/); terms: [CONTEXT.md](./CONTEXT.md).

## Cleanup (整理 PR #4 — 完了)

- [x] `src/dify2langgraph/` を正典化し、旧フラット構成を削除
  - 削除済: `translator.py`, ルート直下の `generator/` `core/` `agents/` `templates/` `logging_config.py`
- [x] 陳腐化ドキュメントの処理
  - 削除済: `docs/migration.md`
  - 一部改訂済: `docs/architecture.md` `docs/development.md`（ADR/CONTEXT へのポインタ追加）。`STYLE_GUIDE.md` の本格改訂は後続
- [x] `outputs/` は既に `.gitignore` 済み、`.DS_Store` 除去済
- [x] `core/db_retriever.py`（直接 SQL）は ADR-0006 により削除（将来アダプタ化は下記 Core 参照）

## Core (v1, 決定論)

- [x] 条件分岐エッジの実装 — `add_conditional_edges` + 生成 Router（ADR-0003）
  - `codegen/routing.py` に決定論ルール、`graph_generator` が `route_<node>` + 条件エッジを生成
  - 対応: question-classifier / if-else。分岐 Stub は先頭ブランチにデフォルト
- [x] Node Handler レジストリへ再編（ADR-0005）
  - `codegen/handlers.py` に per-type 知識（output_fields / stub_output / is_branching / decision_field）を集約
  - state/node/graph ジェネレータは `get_handler()` 経由の薄いオーケストレータに
  - v1 ハンドラ: start / llm / end / knowledge-retrieval / code / tool / template-transform / variable-aggregator / answer / agent / question-classifier / if-else、他は Stub フォールバック
- [~] 変数参照の正準化（ADR-0004）— value_selector と `{{#id.field#}}` の両構文 → `state["node_<id>"]["field"]`
  - [x] 正準キー化（`sanitize_function_name` を leaf `dify2langgraph/naming.py` に集約し parser が共有、数値 ID バグ修正）
  - [x] End ノードは value_selector を正規化アクセスに変換した決定論的本体を生成
  - [ ] `{{#context#}}` 解決、`sys.*` / `env.*` の住所実装、End 以外の本体への入力配線（LLM オプトイン後処理と併走・ADR-0001）
- [x] 生成物を自己完結パッケージ化（相対 import、`__init__`/`__main__`、`sys.path` ハック廃止、ADR-0007）
- [x] RAG: `Retriever` ポート + `DifyApiRetriever` 既定アダプタ（ADR-0006）
  - `templates/retriever.py`（依存フリー・urllib）を生成物にバンドル、knowledge-retrieval ノードが `get_retriever().retrieve(...)` を呼ぶ実本体を生成。未設定時は `[]` を返し資格情報なしでも走る
- [ ] テスト拡充 — ハンドラ単位、循環参照・孤立ノード等のエッジケース

## LLM opt-in post-processing（任意・ADR-0001）

- [ ] `# TODO` スタブ本体の LLM 埋め（`generator/engine.py`）をオプトイン後処理として整理
- [ ] lint 自動修正エージェント（`agents/`）をオプトイン後処理として整理
- [ ] 意味的 snake_case リネームパス（`--name-nodes`）を LLM オプトインとして再位置づけ
- [ ] ノード生成の並列化（`batch()` / `ainvoke()` + `asyncio.gather()`）

## Deferred（要調査 / 後続）

- [ ] iteration（ループ）— ループ全体が 1 ノードで内部にサブグラフを持つ表現。実 DSL 調査後に Handler 形状を決定（ADR-0005 参照）
- [ ] `sys.*` / `env.*` の実装（住所は ADR-0004 で予約済み、実装は後追い）
- [ ] `conversation.*`（chatflow 専用、対象外）
- [ ] 埋め込みモデル自動解決 — API 経由で不要化の見込みだが、別バックエンド採用時に再検討
- [ ] 他ノードタイプ: parameter-extractor / http-request / variable-assigner / template-transform / tool / agent / code
- [ ] CLI: `--dry-run`, `--single-file`（`--format`）
- [ ] 生成コードの使い方ガイド / ノードタイプ別実装例

## Done（旧実装で完了済み・再設計で再編対象）

- [x] 基本パーサー / state.py / nodes/ / graph.py 生成
- [x] NODE_CONFIG に Dify 設定を埋め込み
- [x] ruff + ty lint 対応 / Command 戻り値
- [x] LLM プロバイダー抽象化（OpenAI / Anthropic / Bedrock）
- [x] `--name-nodes`（LLM でノード名生成）※ 再設計で opt-in に再位置づけ
