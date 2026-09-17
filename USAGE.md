# 利用ガイド

Dify のワークフロー DSL（YAML）を、実行可能な LangGraph の Python パッケージに変換して使うための手順です。

- [1. 動作要件](#1-動作要件)
- [2. インストール](#2-インストール)
- [3. 変換する（CLI）](#3-変換するcli)
- [4. 生成物を実行する](#4-生成物を実行する)
- [5. RAG（知識取得）の設定](#5-rag知識取得の設定)
- [6. 生成に LLM を使う場合の設定](#6-生成に-llm-を使う場合の設定)
- [7. 生成物の構造](#7-生成物の構造)
- [8. Windows で使う場合](#8-windows-で使う場合)
- [9. Docker で使う](#9-docker-で使う)

---

## 1. 動作要件

- Python 3.13 以上
- OS: Windows / macOS / Linux
- 依存パッケージ（`langgraph` / `langchain` ほか。`pyproject.toml` の `dependencies` 参照）

> 本ガイドのコマンド例は bash（macOS / Linux）表記です。**Windows（PowerShell / コマンド
> プロンプト）で使う場合は [9. Docker で使う](#9-docker-で使う) を推奨します。**
> Python 3.13 の用意・コンソールの文字コード設定・シェルごとの環境変数の書き方が
> すべて不要になります。Windows にそのまま入れる場合は
> [8. Windows で使う場合](#8-windows-で使う場合) を先に参照してください。

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

PowerShell の場合:

```powershell
$env:PYTHONPATH = "src"
python -m dify2langgraph.cli workflow.yml -o output/
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
| `--aws-region` | （未指定） | `--llm-provider bedrock` のリージョン。未指定なら `AWS_REGION` / `AWS_DEFAULT_REGION` → プロファイルの `region` の順に解決 |
| `--aws-profile` | （未指定） | `--llm-provider bedrock` の AWS プロファイル。静的な資格情報を環境変数で渡す場合は**指定しない** |
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

PowerShell の場合:

```powershell
$env:DIFY_API_BASE_URL = "https://your-dify-instance"
$env:DIFY_API_KEY = "dataset-xxxxxxxx"
$env:DIFY_RETRIEVAL_SEARCH_METHOD = "keyword_search"
python -m workflow
```

> `DIFY_API_BASE_URL` / `DIFY_API_KEY` が未設定の場合、知識取得は空の結果（`[]`）を返し、
> グラフはそのまま最後まで実行されます（資格情報なしでも動作確認できます）。
>
> 検索バックエンドを差し替えたい場合は、`retriever.py` の `get_retriever()` が返す
> シングルトンを、`Retriever` プロトコルを満たす別実装に置き換えてください。

> OS を問わず、実行ディレクトリ（またはその親）に `.env` ファイルを置く方法も使えます。
> 生成物は起動時に `.env` を読み込むので、シェルごとの環境変数の書き方を気にせずに済みます。

---

## 6. 生成に LLM を使う場合の設定

`--name-nodes` やノード本体実装（既定 ON）を使うと、変換時に LLM を呼びます。
プロバイダは `--llm-provider` / `--llm-model` で選び、認証情報は環境変数で渡します。

| プロバイダ | 認証 |
|-----------|------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Bedrock | AWS 標準認証（region の指定は必須。[9.5](#95-bedrock-を使う) 参照） |

```bash
export ANTHROPIC_API_KEY=sk-...
dify2langgraph workflow.yml --llm-provider anthropic --llm-model claude-sonnet-4-6
```

Bedrock の場合、**リージョンはどこかで必ず指定してください**。`--aws-region`、
`AWS_REGION` と `AWS_DEFAULT_REGION` の両方、または AWS プロファイルの `region` の
いずれかです。どれも無い場合は `NoRegionError` で停止します（以前は暗黙に
`us-east-1` を使っていましたが、誤ったリージョンを黙って叩くより明示的に失敗する
方針に変更しました）。

```bash
dify2langgraph workflow.yml --llm-provider bedrock \
  --llm-model anthropic.claude-3-5-sonnet-20241022-v2:0 \
  --aws-region ap-northeast-1 --aws-profile my-sso-profile
```

PowerShell の場合:

```powershell
$env:ANTHROPIC_API_KEY = "sk-..."
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

---

## 8. Windows で使う場合

> **まず [9. Docker で使う](#9-docker-で使う) を検討してください。** この章で説明する
> 3 つの落とし穴（Python 3.13 の用意・コンソールの文字コード・シェルごとの環境変数の
> 書き方）は、Docker で実行すればいずれも発生しません。この章は Docker を使わず
> Windows に直接インストールする場合の手順です。

Windows でも同じ CLI がそのまま動きますが、次の 2 点だけ macOS / Linux と異なります。

### 8.1 コンソールの文字コードを UTF-8 にする

Dify のワークフローはノード名・プロンプト・出力に日本語（中国語）を含むのが普通です。
一方 Windows の Python は、標準出力・標準エラーの文字コードに**コンソールのコードページ**
（日本語環境なら cp932）を使います。UTF-8 にしておくと文字化けや実行時エラーを避けられます。

**推奨: UTF-8 モードを有効にする**

```powershell
# 現在のセッションだけ
$env:PYTHONUTF8 = "1"

# 常時有効にする（ユーザー環境変数に登録。以後の新しいセッションから有効）
setx PYTHONUTF8 1
```

コマンドプロンプトの場合:

```bat
set PYTHONUTF8=1
chcp 65001
```

> UTF-8 モードを使わない場合でも、生成物の `__main__.py` はコンソールが表現できない文字を
> `\uXXXX` にエスケープして出力するため、`UnicodeEncodeError` で落ちることはありません。
> ただし表示は読みづらくなるので、`PYTHONUTF8=1` の設定を推奨します。

### 8.2 環境変数の指定方法

bash の `export VAR=値` や `VAR=値 コマンド`（行頭でのインライン指定）は
PowerShell / コマンドプロンプトでは使えません。以下に読み替えてください。

| bash | PowerShell | コマンドプロンプト |
|------|-----------|------------------|
| `export VAR=値` | `$env:VAR = "値"` | `set VAR=値` |
| `VAR=値 command` | `$env:VAR = "値"` の後に `command` | `set VAR=値` の後に `command` |
| `PYTHONPATH=src python -m ...` | `$env:PYTHONPATH = "src"` の後に `python -m ...` | `set PYTHONPATH=src` の後に `python -m ...` |

環境変数を使わず、実行ディレクトリに `.env` ファイルを置く方法（[5 章](#5-rag知識取得の設定)参照）
が最も移植性が高くおすすめです。

### 8.3 補足

- パス区切りは `\` / `/` どちらでも動作します（内部で `pathlib` を使用）。
- `cd output && python -m workflow` の `&&` は PowerShell 7 以降でのみ有効です。
  Windows PowerShell 5.1 では `cd output; python -m workflow` と書いてください。
- リポジトリ同梱の `Makefile` と `scripts/build-release.sh` は開発者向けで、
  `make` と bash を前提としています（利用者側では不要です）。

---

## 9. Docker で使う

**変換ツールを実行環境ごと**コンテナで配布する方法です。Python 3.13 の用意も、
コンソールの文字コード設定（`PYTHONUTF8`）も、シェルごとの環境変数の書き方も不要になります。
**Windows ではこちらを第一候補にしてください。**

> **対象は変換ツールだけです。** 生成された LangGraph パッケージには Dockerfile も
> `requirements.txt` も出力されません。生成物はお手元の既存 Python 環境で実行する前提です
> （[7. 生成物の構造](#7-生成物の構造)）。

- [9.1 イメージをビルドする](#91-イメージをビルドする)
- [9.2 変換する](#92-変換する)
- [9.3 ファイルの所有者（Linux のみ注意）](#93-ファイルの所有者linux-のみ注意)
- [9.4 API キーの渡し方](#94-api-キーの渡し方)
- [9.5 Bedrock を使う](#95-bedrock-を使う)
- [9.6 うまくいかないとき](#96-うまくいかないとき)

### 9.1 イメージをビルドする

イメージはレジストリから配布していません。**同梱の `Dockerfile` から自分でビルド**します
（中身を読んでから実行できます）。

```bash
docker build -t dify2langgraph .
```

ビルドは `uv.lock` を `uv sync --frozen` でそのまま再現するだけで、依存解決は行いません。
インターネットアクセスはビルド時のみ必要です。

> 同梱の `pyproject.toml` には `[tool.uv] exclude-newer` が入っており、
> **公開されてから 3 日未満のバージョンは採用されません**（取り下げ（yank）や
> 不正リリースを掴むリスクを下げるため）。開発側は `make lock` でこの日付を
> 3 日前に進めてから再解決します。設定がファイルに入っているので、
> お手元で `uv lock` や `uv sync` を実行した場合も同じ検疫が効きます。

### 9.2 変換する

作業ディレクトリを `/work` にマウントして実行します。

```bash
docker run --rm \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

`compose.yaml` を使うと 1 行で済みます（マウントと環境変数が定義済み）。

```bash
docker compose run --rm convert workflow.yml -o outputs --skip-implement
```

PowerShell の場合:

```powershell
docker run --rm `
  --mount type=bind,source="$PWD",target=/work `
  dify2langgraph workflow.yml -o outputs --skip-implement
```

> **`-v` ではなく `--mount type=bind,source=...` を使ってください。** Windows のパスは
> `C:\Users\you\project:/work` のようにドライブレターのコロンを含み、`-v` のパーサが
> これを区切り文字と誤認します。`--mount` は `source=` が 1 トークンなので曖昧さがありません。

> コンテナ内の既定は CLI と同じです。つまり `--skip-implement` を付けない場合は
> **ノード本体の実装に LLM を呼びます**。まずは上記のように `--skip-implement` を付けた
> 決定論的な変換から始めてください（LLM 不要・ネットワーク不要）。

### 9.3 ファイルの所有者（Linux のみ注意）

| ホスト | `--user` |
|--------|----------|
| **Linux** | `--user "$(id -u):$(id -g)"` を**付ける**。イメージの既定は uid 1000 なので、付けないと生成物が **uid 1000 の所有**になります。あなたの uid が 1000 でなければ書き換えられません （`id -u` で確認できます。ディストリビューションによっては最初のユーザーが 1000 なので、その場合はたまたま一致します） |
| **macOS / Windows**（Docker Desktop / Rancher Desktop） | **付けない**。マウント層が所有者を変換するので不要で、付けると `HOME` の解決が壊れる場合があります |

```bash
# Linux
docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

`compose.yaml` では既定で `user:` を設定していません（誤設定の害の方が大きいため）。
Linux で使う場合は `compose.yaml` の `user:` 行のコメントを外してください。

> イメージは `PYTHONDONTWRITEBYTECODE=1` と `RUFF_CACHE_DIR=/tmp/ruff` を設定済みなので、
> マウントした作業ディレクトリに `__pycache__/` や `.ruff_cache/` が残ることはありません。

### 9.4 API キーの渡し方

**`.env` をマウントしてください。`docker run --env-file` は使わないでください。**

```bash
docker run --rm \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider openai
```

作業ディレクトリごと `/work` にマウントしていれば、`./.env` はそのままコンテナ内の
`/work/.env` になり、変換ツールが起動時に読み込みます。個別に上書きしたい値だけ
`-e KEY=値` を追加できます（`.env` の値より `-e` が優先されます）。

> **なぜ `--env-file` を使わないのか**: `docker run --env-file` は python-dotenv とは
> **別のパーサ**（`docker/cli/pkg/kvfile`）を使います。次の `.env` を両方に食わせた
> 実測結果です。
>
> ```
> OPENAI_API_KEY="sk-quoted"
> ANTHROPIC_API_KEY='sk-single'
> LOG_LEVEL=DEBUG  # trailing comment
> ```
>
> | 変数 | python-dotenv（CLI が読む値） | `docker run --env-file` |
> |------|------------------------------|--------------------------|
> | `OPENAI_API_KEY` | `sk-quoted` | `"sk-quoted"` ← クォートが値に残る |
> | `ANTHROPIC_API_KEY` | `sk-single` | `'sk-single'` ← 同上 |
> | `LOG_LEVEL` | `DEBUG` | `DEBUG  # trailing comment` |
>
> API キーの前後にクォートが残ったまま送られるため、**エラーにならず 401 になります**。
> さらに行頭の `export ` が付いていると
> `invalid env file: variable 'export OPENAI_API_KEY' contains whitespaces`
> で起動そのものが失敗します。
>
> `docker compose` の `env_file:` は dotenv 互換の別実装なので安全です
> （`compose.yaml` はこちらを使っています）。

変換ツールが読む環境変数は次で全部です。

| 用途 | 変数 |
|------|------|
| LLM（変換補助） | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| Bedrock | `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION` |
| トレース | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` |
| ログ | `LOG_LEVEL`, `LOG_FORMAT` |

### 9.5 Bedrock を使う

#### 既定の方法: `~/.aws` をマウントする

**`aws sso login` はホスト側で先に実行してください。** コンテナにはブラウザが無いため
実行できず、イメージに AWS CLI も入れていません。

```bash
aws sso login --profile <profile>          # ホスト側。ブラウザが開く

docker run --rm \
  -e AWS_PROFILE=<profile> \
  -e AWS_REGION=ap-northeast-1 -e AWS_DEFAULT_REGION=ap-northeast-1 \
  --mount type=bind,source="$HOME/.aws",target=/home/app/.aws \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider bedrock \
  --llm-model anthropic.claude-3-5-sonnet-20241022-v2:0
```

`compose.yaml` を使う場合（`~/.aws` のマウント込み）。`bedrock` サービスは
`AWS_PROFILE` / `AWS_REGION` / `AWS_DEFAULT_REGION` を**ホストの環境変数からそのまま
引き継ぎます**（未設定の変数はコンテナに渡りません）。

```bash
export AWS_PROFILE=<profile>
export AWS_REGION=ap-northeast-1
export AWS_DEFAULT_REGION=ap-northeast-1
docker compose run --rm bedrock workflow.yml -o outputs --llm-provider bedrock
```

> PowerShell では `$HOME` が環境変数として公開されていないため、compose には
> `AWS_DIR` を渡してください: `$env:AWS_DIR = "$env:USERPROFILE\.aws"`

押さえるべき点が 3 つあります。

1. **`AWS_REGION` と `AWS_DEFAULT_REGION` の両方を設定してください。**
   botocore は `AWS_DEFAULT_REGION` しか読みません（`AWS_REGION` は無視します）。
   一方 `langchain-aws` は `AWS_REGION` も読みます。片方だけだと、変換ツールと
   生成物で見るリージョンが食い違います。`--aws-region` を使えば一度で済みます。

2. **`~/.aws` は read-write でマウントしてください（`:ro` を付けない）。**
   botocore は SSO トークンの残り時間が 15 分を切ると自動で更新し、結果を
   `~/.aws/sso/cache/` に**書き戻します**。この書き込みは `try/except` で守られておらず、
   read-only だと `OSError` で落ちます。しかも sso-oidc の通信が成功した**後**に落ちるため
   原因が分かりにくく、8 時間ごとに 15 分だけ現れる窓なので「たまに落ちる」ように見えます。
   書き込む内容はホストの AWS CLI がしているのと同じトークン更新だけです。

   組織のポリシーで `:ro` が必須の場合は、`docker run` の**直前にホストで**
   `aws sts get-caller-identity --profile <profile>` を実行してトークンを更新させてください。

3. **イメージの `HOME=/home/app` を上書きしないでください。** botocore は SSO トークンの
   キャッシュ先を `~/.aws/sso/cache` に固定しており、場所を変える環境変数はありません。
   マウント先を `/home/app/.aws` に合わせる必要があります。

#### 代替: 静的な資格情報を `--env-file` で渡す

`~/.aws` をマウントできない環境向けです。

```bash
aws configure export-credentials --profile <profile> --format env-no-export > aws.env

docker run --rm --env-file aws.env \
  -e AWS_REGION=ap-northeast-1 -e AWS_DEFAULT_REGION=ap-northeast-1 \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider bedrock
```

ここで `--env-file` を使ってよいのは、`aws configure export-credentials --format
env-no-export` の出力が**機械生成・クォート無し・1 行 1 変数**で、docker のパーサでも
正しく読める数少ない入力だからです。手書きの `.env` には使わないでください（[9.4](#94-api-キーの渡し方)）。

> **このモードでは `AWS_PROFILE` を渡さないでください。** `~/.aws` が無い状態で
> プロファイル名を指定すると、有効な静的資格情報があっても `ProfileNotFound` で
> 即座に失敗します。`--aws-profile` も同様に付けないでください。

> **有効期限**: 権限セットのセッション長（既定 1 時間）で切れます。さらに botocore は
> 期限の 10 分前の時点で
> `RuntimeError: Credentials were refreshed, but the refreshed credentials are still expired.`
> を投げます。このメッセージが出たら `aws configure export-credentials` をやり直してください。

> **PowerShell の場合**は出力の文字コードを明示してください。PowerShell 5.1 の既定は
> UTF-16LE + BOM で、docker のパーサが先頭のキー名を壊します。
>
> ```powershell
> aws configure export-credentials --profile <profile> --format env-no-export |
>   Out-File -Encoding ascii aws.env
> ```

### 9.6 うまくいかないとき

| 症状 | 原因と対処 |
|------|-----------|
| `TokenRetrievalError: Token has expired and refresh failed` | SSO トークン切れ。**ホストで** `aws sso login --profile <profile>` を実行。変換ツールはこの場合に案内メッセージも出します |
| `OSError` / `Read-only file system`（`~/.aws` 付近） | `~/.aws` を `:ro` でマウントしている。read-write にする（[9.5](#95-bedrock-を使う)） |
| `ProfileNotFound` | `~/.aws` をマウントせずに `AWS_PROFILE` / `--aws-profile` を指定している。外す |
| `NoRegionError` | リージョンがどこにも無い。`--aws-region`、または `AWS_REGION` と `AWS_DEFAULT_REGION` の両方を設定 |
| `AccessDeniedException`（Bedrock） | リージョンかモデル ID が想定と違う。`--aws-region` で明示する |
| 生成物が別ユーザー所有になる（Linux） | イメージ既定の uid 1000 で書かれている。`--user "$(id -u):$(id -g)"` を付ける（[9.3](#93-ファイルの所有者linux-のみ注意)） |
| `invalid reference format` 等のマウントエラー（Windows） | `-v` を使っている。`--mount type=bind,source=...` に置き換える |
| API キーが読まれない | `--env-file` で手書き `.env` を渡している。`.env` を `/work` にマウントする方式に変える（[9.4](#94-api-キーの渡し方)） |

その他の環境固有の注意（実装では扱っていません）:

- **企業プロキシ / 独自 CA**: `docker build` に `--build-arg HTTP_PROXY=...` を渡し、
  社内 CA 証明書が必要な場合は Dockerfile に追加してください。
- **SELinux 有効な Linux**（RHEL 系）: マウントに `,z` を付ける必要がある場合があります。
- **時刻ずれ**: ホストの時計が大きくずれていると SSO / SigV4 の署名が失敗します。

> **検証状況**: macOS（Rancher Desktop）で以下を確認済みです。
> `docker build` / `--skip-implement` / `--lint` / `--user` 指定 / `docker compose run` /
> `~/.aws` を rw マウントした Bedrock 経路（`--name-nodes` を実資格情報で 1 回通し、
> SSO トークン期限切れ時のエラーメッセージも実地で確認）。生成物はホストで
> `uv run dify2langgraph` した場合と**バイト単位で一致**します（ADR-0001 の決定論）。
>
> ファイル所有者（9.3）は named volume を使って Linux の素のセマンティクスで確認済みです
> （`--user` 無し → uid 1000、`--user 0:0` → root、`--user 4242:4242` → 4242）。
>
> **未検証**: Windows ホストでの実機動作。Windows コンテナは Windows ホストでしか
> 動かないため、この開発環境（Linux daemon）では検証できません。ただし文字コード周りの
> 挙動は、子プロセスの stdio に狭いコーデックを固定するテストで OS に依らず再現しています。
