# Dify DSL to LangGraph Converter

Dify のワークフロー DSL (YAML) を解析し、実行可能で型安全な LangGraph Python コードを自動生成するツールです。

変換の中核は**決定論的**（同じ DSL からは常に同じコード）で、LLM による補助（スタブ実装の自動埋め・lint 自動修正・ノード名の意味的リネーム）は**オプトインの後処理**です（[ADR-0001](docs/adr/0001-deterministic-core-llm-as-opt-in-postprocessing.md)）。

> 用語の正準定義は [CONTEXT.md](CONTEXT.md)、設計判断の経緯は [docs/adr/](docs/adr/)、ロードマップは [TODO.md](TODO.md) を参照。

## 変換パイプライン

```mermaid
flowchart LR
    DSL[("Dify DSL<br/>(YAML)")] --> Parser
    subgraph Parser["parser/"]
        P1[ノード/エッジ抽出] --> P2["変数参照解析<br/>{{#id.field#}} / value_selector"]
    end
    Parser --> Codegen
    subgraph Codegen["codegen/ (決定論)"]
        C1[state.py] ~~~ C2[nodes/*.py] ~~~ C3[graph.py]
    end
    Codegen --> Opt
    subgraph Opt["任意の後処理 (LLM)"]
        O1[スタブ実装埋め] ~~~ O2[lint 自動修正]
    end
```

## 生成物の設計

- **state**: `GraphState(TypedDict, total=False)`。1 ノード = 1 キーで、正準キーは `node_<dify_node_id>`。存在しないノード参照は Linter が静的に検知（[ADR-0002](docs/adr/0002-canonical-state-key-is-node-id.md)）
- **変数参照**: `{{#id.field#}}` / value_selector の両構文を `state["node_<id>"]["field"]` に正準化（[ADR-0004](docs/adr/0004-variable-reference-normalization-and-special-namespaces.md)）
- **分岐**: question-classifier / if-else は `add_conditional_edges` + 生成 Router で graph.py に可視化（[ADR-0003](docs/adr/0003-conditional-branching-via-generated-routers.md)）
- **ノードタイプ対応**: タイプごとの Node Handler に集約。未対応タイプは型付きスタブとして生成され、コンパイル可能な構造を保つ（[ADR-0005](docs/adr/0005-node-type-handler-registry.md)）
- **RAG**: Dify の公開 Retrieval API を既定バックエンドとし、差し替え可能な `Retriever` ポートの背後に置く（[ADR-0006](docs/adr/0006-retrieval-via-dify-api-behind-a-port.md)）

## インストール

```bash
git clone https://github.com/o02c/dify-workflow-to-langgraph.git
cd dify-workflow-to-langgraph
uv sync
```

## クイックスタート

```bash
# Dify DSL を LangGraph コードに変換
uv run dify2langgraph workflow.yml -o output/

ls output/workflow/
# state.py  graph.py  llm.py  nodes/
```

### CLI オプション

```bash
uv run dify2langgraph --help

# LLM による実装生成をスキップ (決定論的なテンプレートのみ生成)
uv run dify2langgraph workflow.yml --skip-implement

# --- 以下はオプトインの LLM 後処理 ---
# LLM でノード名を生成 (日本語タイトル → snake_case)
uv run dify2langgraph workflow.yml --name-nodes

# リンター実行 / 自動修正
uv run dify2langgraph workflow.yml --lint
uv run dify2langgraph workflow.yml --auto-fix

# LLM プロバイダー指定
uv run dify2langgraph workflow.yml --llm-provider anthropic --llm-model claude-sonnet-4-6
```

## 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `LOG_LEVEL` | ログレベル (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `LOG_FORMAT` | ログ形式 (`console` or `json`) | `console` |
| `LANGSMITH_TRACING` | LangSmith トレーシング有効化 | `false` |
| `LANGSMITH_API_KEY` | LangSmith API キー | - |
| `LANGSMITH_PROJECT` | LangSmith プロジェクト名 | `dify2langgraph` |
| `OPENAI_API_KEY` | OpenAI API キー (LLM 後処理用) | - |
| `ANTHROPIC_API_KEY` | Anthropic API キー (LLM 後処理用) | - |
| AWS credentials | Bedrock 用 (標準 AWS 設定) | - |

## ディレクトリ構造

```
dify-workflow-to-langgraph/
├── src/dify2langgraph/        # メインパッケージ (正典)
│   ├── cli.py                 # CLI エントリポイント
│   ├── parser/                # DSL パーサー
│   ├── codegen/               # 決定論的コード生成 (state / nodes / graph)
│   ├── generator/             # LLM コード生成 (オプトイン)
│   ├── llm/                   # LLM プロバイダー抽象化
│   ├── agents/                # lint 自動修正エージェント (オプトイン)
│   └── templates/             # 生成物に同梱するランタイムテンプレート
├── tests/                     # テスト (fixtures/ に DSL サンプル)
├── docs/
│   ├── adr/                   # 設計判断の記録 (ADR)
│   ├── architecture.md
│   ├── development.md
│   └── STYLE_GUIDE.md
├── CONTEXT.md                 # 用語集 (正準)
├── TODO.md                    # ロードマップ
└── pyproject.toml
```

## ドキュメント

- [CONTEXT.md](CONTEXT.md) — 用語集（正準）
- [docs/adr/](docs/adr/) — 設計判断の記録
- [アーキテクチャ](docs/architecture.md) / [開発ガイド](docs/development.md) / [スタイルガイド](docs/STYLE_GUIDE.md)

## ライセンス

MIT License
