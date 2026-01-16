# TODO

## High Priority

- [ ] 条件分岐エッジの実装
  - 現状: `add_edge`で単純な接続のみ（分岐ノードで重複エッジ）
  - 改善: `add_conditional_edges`を使った分岐ロジック生成
  - if-else, question-classifierノードの分岐に対応
  - 分岐の可視性向上のためgraph.py側で制御

## Medium Priority

- [ ] ノード実装生成の並列化
  - 現状: 直列処理で時間がかかる
  - 改善: LangChain best practice に従って並列化
  - `batch()` または `ainvoke()` + `asyncio.gather()` を使用

- [ ] ノード実装の自動生成改善 (generator/engine.py)
  - LLMノード: LangChain ChatModel経由 (`from llm import get_chat_model`)
  - knowledge-retrievalノード: 共有retriever経由 (`from retriever import get_retriever`)
  - 共有モジュール（llm.py, retriever.py）のテンプレート生成

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
- [x] `--name-nodes`オプション: LLMでノード名生成
  - 日本語タイトル→英語snake_case/CamelCase変換
  - 例: `知識取得` → `retrieve_knowledge` / `RetrieveKnowledge`
- [x] state keyをLLM生成名に統一
  - `state["retrieve_knowledge"]["result"]` 形式で参照
- [x] LLMプロバイダー抽象化 (OpenAI, Anthropic, Bedrock対応)
- [x] コード生成プロンプト改善 (LangChain抽象使用)
