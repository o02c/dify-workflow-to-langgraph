# 利用ガイド

Dify のワークフロー DSL（YAML）を、実行可能な LangGraph の Python パッケージに変換して使うための手順です。

- [1. 動作要件](#1-動作要件)
- [2. インストール](#2-インストール)
- [3. 変換する（CLI）](#3-変換するcli)
- [4. 生成物を実行する](#4-生成物を実行する)
- [5. RAG（知識取得）の設定](#5-rag知識取得の設定)
- [6. 生成に LLM を使う場合の設定](#6-生成に-llm-を使う場合の設定)
- [7. 生成物の構造](#7-生成物の構造)

---

## 1. 動作要件

- Python 3.13 以上
- 依存パッケージ（`langgraph` / `langchain` ほか。`pyproject.toml` の `dependencies` 参照）

---

## 2. インストール

このリリースは `.py` ソースをそのまま同梱しています。用途に応じて 2 通り。

### A. パッケージとしてインストール（推奨）

同梱の `pyproject.toml` を使ってインストールすると、`dify2langgraph` コマンドが使えます。

```bash
pip install .
# または uv を使う場合
uv pip install .
```

### B. そのままソースとして使う

インストールせず、ソースを直接使うこともできます。

```bash
# リポジトリ(展開先)のルートで
PYTHONPATH=src python -m dify2langgraph.cli workflow.yml -o output/
```

---

## 3. 変換する（CLI）

最小の使い方（**LLM 不要・決定論的に変換だけ**行う）:

```bash
dify2langgraph workflow.yml -o output/ --skip-implement
```

生成物は `output/<入力ファイル名>/` に出力されます。

### CLI オプション一覧

| オプション | 既定 | 説明 |
|-----------|------|------|
| `input` | （必須） | 入力の Dify DSL YAML ファイル |
| `-o`, `--output` | `outputs` | 出力ディレクトリ |
| `--skip-implement` | off | **LLM によるノード本体実装をスキップ**（決定論的なテンプレート/Stub のみ出力） |
| `--name-nodes` | off | LLM でノード名を意味的な snake_case に生成（日本語タイトル対応） |
| `--llm-provider` | `openai` | 生成補助に使う LLM プロバイダ（`openai` / `anthropic` / `bedrock`） |
| `--llm-model` | `gpt-4o-mini` | 生成補助に使う LLM モデル |
| `--lint` | off | 生成コードに linter（ruff）を実行 |
| `--auto-fix` | off | lint エラーを LLM エージェントで自動修正 |

> **LLM を一切使いたくない場合**は `--skip-implement` を付け、`--name-nodes` / `--auto-fix` を
> 付けないでください。この場合、変換は完全に決定論的で、ネットワークアクセスも発生しません。
>
> 逆に **既定（`--skip-implement` なし）ではノード本体の実装に LLM を呼びます**。その場合は
> [6. 生成に LLM を使う場合の設定](#6-生成に-llm-を使う場合の設定)を参照してください。

---

## 4. 生成物を実行する

生成物は自己完結した Python パッケージです。**親ディレクトリから** `python -m` で実行します。

```bash
cd output
python -m <入力ファイル名>     # 例: python -m workflow
```

Python から使う場合:

```python
from workflow import build_graph

graph = build_graph()
result = graph.invoke({"start_node": {}})
print(result)
```

> パッケージのディレクトリ名は有効な Python 識別子である必要があります（ハイフン不可・数字始まり不可）。
> 入力ファイル名がこれに反する場合は、出力ディレクトリ名をリネームしてから実行してください。

---

## 5. RAG（知識取得）の設定

`knowledge-retrieval` ノードを含むワークフローは、生成物の `retriever.py` 経由で
Dify の Retrieval API を呼びます。以下の環境変数で有効化します。

| 環境変数 | 既定 | 説明 |
|----------|------|------|
| `DIFY_API_BASE_URL` | （未設定） | Dify インスタンスのベース URL（例 `https://api.dify.ai`） |
| `DIFY_API_KEY` | （未設定） | Dify のデータセット API キー |
| `DIFY_RETRIEVAL_SEARCH_METHOD` | `semantic_search` | 検索方式。埋め込みモデル未設定のデータセットでは `keyword_search` / `full_text_search` |
| `DIFY_RETRIEVAL_TOP_K` | `4` | 取得件数 |

```bash
export DIFY_API_BASE_URL=https://your-dify-instance
export DIFY_API_KEY=dataset-xxxxxxxx
export DIFY_RETRIEVAL_SEARCH_METHOD=keyword_search
python -m workflow
```

> `DIFY_API_BASE_URL` / `DIFY_API_KEY` が未設定の場合、知識取得は空の結果（`[]`）を返し、
> グラフはそのまま最後まで実行されます（資格情報なしでも動作確認できます）。
>
> 検索バックエンドを差し替えたい場合は、`retriever.py` の `get_retriever()` が返す
> シングルトンを、`Retriever` プロトコルを満たす別実装に置き換えてください。

---

## 6. 生成に LLM を使う場合の設定

`--name-nodes` やノード本体実装（既定 ON）を使うと、変換時に LLM を呼びます。
プロバイダは `--llm-provider` / `--llm-model` で選び、認証情報は環境変数で渡します。

| プロバイダ | 認証 |
|-----------|------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Bedrock | AWS 標準認証（region は既定 `us-east-1`） |

```bash
export ANTHROPIC_API_KEY=sk-...
dify2langgraph workflow.yml --llm-provider anthropic --llm-model claude-sonnet-4-6
```

生成物内の `llm` ノードは、**実行時**に別途 LLM を呼びます（`llm.py` を参照）。
実行時の既定は `LLM_PROVIDER` / `LLM_MODEL` 環境変数で制御します。

---

## 7. 生成物の構造

```
<入力ファイル名>/          # Python パッケージ
├── __init__.py           # build_graph を再エクスポート
├── __main__.py           # `python -m <pkg>` の実行入口
├── state.py              # GraphState と各ノード出力の型定義
├── graph.py              # build_graph()（グラフ構築・分岐の配線）
├── nodes/                # 1 ノード 1 ファイル
│   ├── __init__.py
│   └── <node>.py
├── llm.py                # LLM 設定ヘルパー
└── retriever.py          # 知識取得の Retriever（Dify Retrieval API）
```

- ノード本体の多くは `# TODO` のプレースホルダです。ワークフローの構造（状態・エッジ・分岐）は
  正しく生成されるので、各ノードの中身を埋めていくことで完成させられます。
- `end` ノードと `knowledge-retrieval` ノードは、そのまま動く実装が生成されます。
