# TODO

Roadmap after the 2026-08 redesign. Decisions: see [docs/adr/](./docs/adr/); terms: [CONTEXT.md](./CONTEXT.md).

## Cleanup (整理 PR)

- [ ] `src/dify2langgraph/` を正典化し、旧フラット構成を削除
  - 削除: `translator.py`, ルート直下の `generator/` `core/` `agents/` `templates/` `logging_config.py`
- [ ] 陳腐化ドキュメントの処理
  - 削除: `docs/migration.md`（v0.1→v0.2 移行、役割終了）
  - 改訂 or ADR/CONTEXT へ一本化: `docs/architecture.md` `docs/development.md` `docs/STYLE_GUIDE.md`
- [ ] `outputs/` を `.gitignore`（サンプルを残すなら `examples/` に隔離）、`.DS_Store` 除去
- [ ] `core/db_retriever.py`（直接 SQL）は ADR-0006 により撤去 or 任意アダプタに縮小

## Core (v1, 決定論)

- [ ] 条件分岐エッジの実装 — `add_conditional_edges` + 生成 Router（ADR-0003）
  - 現状は分岐が全て素の `add_edge` で両方発火してしまうバグ
  - 対応: question-classifier / if-else
- [ ] Node Handler レジストリへ再編（ADR-0005）
  - per-type ロジックを state/node/graph ジェネレータから 1 ハンドラに集約
  - v1 ハンドラ: start / llm / end / question-classifier / if-else、他は Stub フォールバック
- [ ] 変数参照の正準化（ADR-0004）— value_selector と `{{#id.field#}}` の両構文 → `state["node_<id>"]["field"]`
- [ ] 生成物を自己完結パッケージ化（相対 import、1 ノード 1 ファイル）
- [ ] RAG: `Retriever` ポート + `DifyApiRetriever` 既定アダプタ（ADR-0006）
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
