# Project: Dify DSL to LangGraph Converter

## 1. Overview
Dify (v1.11) のワークフロー DSL (YAML) を解析し、AWS環境で動作する LangGraph プログラムを自動生成する。

## 2. Goals
- Dify のワークフローを Python (LangGraph) コードに変換し、カスタマイズ性を向上させる。
- Dify が使用している既存の AWS RDS (PGVector) に直接接続し、RAG 機能を維持する。
- `TypedDict` を活用し、存在しないノード参照を静的に検知（Linter警告）できる型安全なコードを出力する。

## 3. System Architecture
- **Runtime:** AWS EC2 (Dify と同 VPC 内)
- **Database:** Dify 用 RDS (PostgreSQL / PGVector)
- **LLM API:** Amazon Bedrock (Claude 3.5 Sonnet / 3.7)
- **Libraries:** LangGraph, LangChain, psycopg2-binary, PyYAML, boto3

## 4. Implementation Requirements

### 4.1 Dependency Parser
- YAML 内の `nodes` から全 `id` を抽出する。
- 各ノード内の `{{#node_id.field#}}` 形式の変数を正規表現で抽出し、ノード間の依存関係を特定する。

### 4.2 State Management Design
- `TypedDict(total=False)` を用いた `GraphState` を生成する。
- YAML に存在する全ノード ID をキーとして定義し、Linter が未知のキーへのアクセスを検知できるようにする。

### 4.3 Code Generation logic
- **state.py:** `GraphState` の定義ファイル。
- **nodes.py:** 各ノードを関数として定義。Dify の変数参照を `state["node_id"]["field"]` に置換する。
- **graph.py:** `StateGraph` の構築、エッジ（Conditional含む）の接続、コンパイル処理。

## 5. Directory Structure
```text
├── core/
│   ├── base_state.py      # NodeOutput の基底クラス
│   └── db_retriever.py    # Dify DB (PGVector) 接続用共通モジュール
├── generator/
│   ├── parser.py          # YAML 解析ロジック
│   └── engine.py          # Bedrock を用いたコード生成エンジン
├── translator.py          # メイン・エントリポイント
└── output/                # 生成されたコードの出力先