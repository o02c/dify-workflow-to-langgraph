# TODO

## High Priority

- [ ] ノード名の命名規則を改善
  - 現状: 数字IDに`node_`プレフィックスを付与 (例: `node_1722391426202`)
  - 改善: Difyのノードtitleからsnake_case/CamelCaseを生成
  - 例: `知識取得` → `knowledge_retrieval` / `KnowledgeRetrieval`

- [ ] 条件分岐エッジの実装
  - 現状: `add_edge`で単純な接続のみ
  - 改善: `add_conditional_edges`を使った分岐ロジック生成
  - if-else, question-classifierノードの分岐に対応

## Medium Priority

- [ ] ノード実装の自動生成 (generator/engine.py)
  - Bedrock (Claude) を使ったコード生成エンジン
  - NODE_CONFIGを入力としてノードロジックを生成
  - LLMノード: プロンプトテンプレート展開 + Bedrock呼び出し
  - knowledge-retrievalノード: PGVector検索ロジック

- [ ] 変数参照のstate_accessをサニタイズ済みキーに対応
  - 現状: `state["1722391426202"]["field"]` (元のID)
  - 改善: `state["node_1722391426202"]["field"]` (サニタイズ済み)

- [ ] テスト拡充
  - より多くのDify DSLサンプルでのテスト
  - エッジケース (循環参照、孤立ノード等)

## Low Priority

- [ ] CLIオプション拡充
  - `--dry-run`: 生成せずにパース結果のみ表示
  - `--format`: 出力フォーマット指定 (nodes分割 or 単一ファイル)

- [ ] ドキュメント
  - 生成されるコードの使い方ガイド
  - 各ノードタイプの実装例

- [ ] Difyの他のノードタイプ対応
  - iteration (ループ)
  - parameter-extractor
  - http-request
  - variable-assigner

## Done

- [x] 基本的なパーサー実装
- [x] state.py生成 (TypedDict)
- [x] nodes/ディレクトリ生成 (個別ファイル)
- [x] graph.py生成 (StateGraph)
- [x] NODE_CONFIGにDify設定を含める
- [x] ruff + ty でのlint対応
- [x] Commandを使った戻り値
