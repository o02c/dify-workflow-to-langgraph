# 利用ガイド

このツールは、**Dify で作ったワークフローを Python のプログラムに書き換える**変換ツールです。
書き換えたプログラムは Dify なしで、お手元のサーバーやパソコンで動かせます。

この文書 1 つで使い始められるようにしてあります。他の文書を読む必要はありません。

まず「[1. このツールは何をするものか](#1-このツールは何をするものか)」を読んで、
必要なものかどうかを判断してください。使うと決めたら
「[2. 全体の流れ](#2-全体の流れ)」で作業の全体像をつかみ、そこから必要な章に進みます。

---

## 目次

**まず読むところ**

- [1. このツールは何をするものか](#1-このツールは何をするものか)
- [2. 全体の流れ](#2-全体の流れ)

**手順**

- [3. 準備する](#3-準備する)
- [4. 変換する](#4-変換する)
- [5. 変換したプログラムを動かす](#5-変換したプログラムを動かす)
- [6. Dify 側で設定していた値を渡す](#6-dify-側で設定していた値を渡す)
- [7. 変換したプログラムの中身](#7-変換したプログラムの中身)

**環境ごとの注意**

- [8. 変換のときに AI を使う場合](#8-変換のときに-ai-を使う場合)
- [9. Windows で使う場合](#9-windows-で使う場合)
- [10. Docker で使う場合](#10-docker-で使う場合)
- [11. うまくいかないとき](#11-うまくいかないとき)

---

## 1. このツールは何をするものか

### 1.1 やること

Dify の画面で作ったワークフローは、「書き出し（エクスポート）」すると 1 つのファイルに
なります。拡張子は `.yml` で、中身は人が読めるテキストです。

このツールは、**その書き出しファイルを読んで、同じ流れをたどる Python のプログラムを
作ります。**

```
Dify で作ったワークフロー
        ↓  画面から「書き出し」
  workflow.yml               ← このファイルを渡す
        ↓  このツール
  Python のプログラム一式     ← Dify なしで動く
```

### 1.2 何のために使うか

- **Dify のサーバーに依存せずに動かしたい。** 社内のサーバーや他のシステムの中に
  組み込んで動かせます。
- **処理の中身を自分で書き換えたい。** ふつうの Python のコードになるので、
  ログを足す、別の社内システムを呼ぶ、といった改造ができます。
- **何が起きているか目で確認したい。** どのような順で処理が進み、どこで分岐するかが
  コードとして書き出されます。

### 1.3 できること・できないこと

このツールが自動で作るのは、**処理の「骨組み」**です。

| | 自動で作られるか |
|---|---|
| 処理の順序（どのノードの次にどのノードが動くか） | **作られます** |
| 条件分岐（どの条件でどちらに進むか） | **作られます** |
| ノード間で受け渡す値の形 | **作られます** |
| ワークフローの入力の受け取り | **作られます** |
| 終了ノード（Dify の End）の値の受け渡し | **作られます** |
| 知識取得（RAG）の処理 | **作られます** |
| **その他のノードの処理そのもの** | **作られません**（後述） |

「その他のノードの処理そのもの」とは、たとえば LLM ノードが実際に AI を呼ぶ部分、
コードノードの計算、HTTP ノードの通信などです。これらは**中身が空の状態**で、

```python
# TODO: Implement llm node logic
```

というしるしが付いたまま出力されます。**そこを埋めるのは利用者の作業です。**
空のままでもプログラムは最後まで動くので、先に全体の流れを確認してから、
必要なノードを順に埋めていけます。

> **AI に下書きさせることもできます。** このツールには、空の部分を AI（LLM）に
> 書かせる機能があります（[8 章](#8-変換のときに-ai-を使う場合)）。ただし AI の
> 出力なので、必ず中身を確認してください。**この機能を使わなければ、変換は
> インターネットに一切つながりません。**

### 1.4 用意するもの

- **Python 3.13 以上**（入れ方は [3 章](#3-準備する)）
- **Dify から書き出したワークフローファイル**（`.yml`）
- OS は Windows / macOS / Linux のどれでも動きます

Python を用意したくない場合は、Docker を使う方法もあります
（[10 章](#10-docker-で使う場合)）。

### 1.5 この文書に出てくる言葉

| 言葉 | 意味 |
|---|---|
| ワークフロー | Dify の画面で作った処理の流れ全体 |
| ノード | ワークフローの中に置いた箱ひとつ（LLM、コード、条件分岐など） |
| 書き出しファイル（`.yml`） | Dify の画面からワークフローを書き出したテキストファイル。ツールが出すメッセージでは **DSL** と呼ばれます |
| 変換 | このツールで書き出しファイルを Python のプログラムに変える作業 |
| パッケージ | Python のプログラム一式が入ったフォルダ。1 つのまとまりとして動かせる |
| ターミナル | 文字でコマンドを打つ画面。Windows なら PowerShell、macOS なら「ターミナル」 |
| 環境変数 | コマンドを打つ前に設定しておく値。パスワードや接続先を渡すのに使う |

---

## 2. 全体の流れ

作業は 4 段階です。各段階の詳しい手順は、右の章に書いてあります。

```
① Dify から書き出す      Dify の画面で操作      （このツールの外の作業）
        ↓
② 準備する               Python とこのツールを入れる     → 3 章
        ↓
③ 変換する               コマンドを 1 つ打つ             → 4 章
        ↓
④ 動かす・埋める         動かして確認し、空の部分を埋める → 5〜7 章
```

### まず最短で試す

細かい設定は後で構いません。次の 3 つを打つと、**AI もインターネットも使わずに**
変換して動かすところまで確認できます。

```bash
pip install .

dify2langgraph workflow.yml -o output/ --skip-implement

cd output && python -m workflow
```

最後のコマンドで、処理を最後までたどった結果が画面に出ます。
中身が空のノードは仮の値（`"placeholder"` など）を返します。

- うまくいかない場合 → [11. うまくいかないとき](#11-うまくいかないとき)
- Windows の場合、文字化けや書き方の違いに注意が必要です → [9 章](#9-windows-で使う場合)

### このあとどこを読むか

| 知りたいこと | 章 |
|---|---|
| Python とツールの入れ方 | [3. 準備する](#3-準備する) |
| 変換コマンドの細かい指定 | [4. 変換する](#4-変換する) |
| 作ったプログラムの動かし方、入力の渡し方 | [5. 変換したプログラムを動かす](#5-変換したプログラムを動かす) |
| Dify 側で設定していた値（システム変数・環境変数・知識取得）の渡し方 | [6 章](#6-dify-側で設定していた値を渡す) |
| どのファイルがどんな役割か、どこを埋めるか | [7. 変換したプログラムの中身](#7-変換したプログラムの中身) |
| 空のノードを AI に書かせたい | [8. 変換のときに AI を使う場合](#8-変換のときに-ai-を使う場合) |
| Windows 特有の注意 | [9 章](#9-windows-で使う場合) |
| Python を入れずに Docker で使いたい | [10 章](#10-docker-で使う場合) |

---

## 3. 準備する

### 3.1 Python を用意する

Python 3.13 以上が必要です。ターミナルで確認できます。

```bash
python --version
```

`Python 3.13.x` 以上と出れば準備できています。入っていない場合は次のどちらかで。

- **[python.org](https://www.python.org/downloads/) からインストーラーを入れる**
- **`uv` という道具を使う**（推奨）。`uv` は Python 本体も自動で用意してくれるので、
  Python のバージョン合わせで悩まずに済みます。
  インストール方法は [docs.astral.sh/uv](https://docs.astral.sh/uv/) にあります。

### 3.2 このツールを入れる

配布ファイルを展開したフォルダの中で、次を実行します。

```bash
pip install .
```

`uv` を使う場合:

```bash
uv pip install .
```

これで `dify2langgraph` というコマンドが使えるようになります。確認:

```bash
dify2langgraph --help
```

### 3.3 インストールせずに使う場合

会社の方針でインストールできない場合は、展開したフォルダから直接動かせます。

```bash
PYTHONPATH=src python -m dify2langgraph.cli workflow.yml -o output/
```

Windows の PowerShell では書き方が違います（[9.2](#92-環境変数の書き方) 参照）。

```powershell
$env:PYTHONPATH = "src"
python -m dify2langgraph.cli workflow.yml -o output/
```

---

## 4. 変換する

### 4.1 基本の使い方

```bash
dify2langgraph workflow.yml -o output/ --skip-implement
```

- `workflow.yml` … Dify から書き出したファイル
- `-o output/` … 結果を入れるフォルダ（無ければ作られます）
- `--skip-implement` … **AI を使わない**。ノードの中身は空のまま出力します

結果は `output/<書き出しファイルの名前>/` の中に入ります。上の例なら
`output/workflow/` です。

> **`--skip-implement` を付けた場合、インターネットにはつながりません。**
> AI の利用料もかかりません。まずはこれで試すことをおすすめします。

### 4.2 指定できるもの一覧

| 指定 | 既定 | 何をするか |
|---|---|---|
| （1 つめの引数） | 必須 | 入力する書き出しファイル |
| `-o`, `--output` | `outputs` | 結果を入れるフォルダ |
| `--skip-implement` | off | **AI を使わず**、ノードの中身を空のまま出力する |
| `--name-nodes` | off | ノードのファイル名を AI に付けさせる（日本語のノード名を英語の識別子にする） |
| `--llm-provider` | `openai` | AI の提供元（`openai` / `anthropic` / `bedrock` / `google`） |
| `--llm-model` | 提供元ごとの既定 | AI のモデル名 |
| `--aws-region` | 未指定 | `bedrock` を使うときの AWS リージョン |
| `--aws-profile` | 未指定 | `bedrock` を使うときの AWS プロファイル名 |
| `--lint` | off | 出力したコードの書式チェックを走らせる |
| `--auto-fix` | off | 書式チェックのエラーを AI に直させる |

> **AI を一切使いたくないとき**は `--skip-implement` を付け、`--name-nodes` と
> `--auto-fix` を**付けない**でください。
>
> 逆に `--skip-implement` を**付けない**と、既定でノードの中身を AI に書かせます。
> その場合は AI の接続設定が必要です（[8 章](#8-変換のときに-ai-を使う場合)）。

### 4.3 変換時に出るメッセージ

変換中、次のような注意が出ることがあります。いずれも変換は続きます。

| メッセージ | 意味 |
|---|---|
| `This DSL declares no version` / `newer than the newest version this converter has been tested against` | 書き出しファイルのバージョンが、このツールで動作確認した範囲の外です。変換はしますが、出力を一度確認してください |
| `Skipping environment variable '...'` | Dify 側の環境変数の名前が Python で使えない（予約語など）か、値が入っていません。Dify 側で名前を変えてください |
| `references '...', which the DSL does not declare` | 消した環境変数への参照が Dify 側に残っています。Dify 側で参照を直してください |
| `shares its name with a standard environment variable` | Dify 側のシークレットの名前が `PATH` などのシステムの値とぶつかっています。Dify 側で名前を変えてください |

---

## 5. 変換したプログラムを動かす

### 5.1 そのまま動かす

できたプログラムは、**1 つ上のフォルダから**動かします。

```bash
cd output
python -m workflow        # workflow は書き出しファイルの名前
```

処理を最後までたどった結果が、まとめて画面に出ます。
このとき使われる入力の例は、プログラムの中に自動で入っています。

> **フォルダ名は Python の名前の規則に従う必要があります。** 記号のハイフン（`-`）を
> 含んでいたり、数字で始まっていると動きません。書き出しファイルの名前がそうなっている
> 場合は、できたフォルダの名前を変えてください（例: `my-flow` → `my_flow`）。

### 5.2 自分のプログラムから呼ぶ

```python
from workflow import build_graph

graph = build_graph()
result = graph.invoke({"start_node": {"query": "調べたいこと"}})
print(result)
```

`build_graph()` で処理の流れを組み立て、`invoke()` に入力を渡すと動きます。
入力の渡し方は [6.1](#61-ワークフローの入力を渡す) を見てください。

### 5.3 結果の読み方

`invoke()` が返すのは、**ノードごとの結果をまとめたもの**です。

```python
{
  "start_node": {"query": "調べたいこと"},
  "llm_node":   {"text": "placeholder", ...},
  "end_node":   {"result": "placeholder"},
}
```

- キー（`llm_node` など）が 1 つのノードに対応します
- まだ中身を埋めていないノードは `"placeholder"` のような仮の値を返します
- **分岐で通らなかった側のノードは、そもそもキーが現れません**。
  そのノードの値を受け取る側は `None` になります（これは Dify 本体と同じ動きです）

---

## 6. Dify 側で設定していた値を渡す

Dify で動かしていたときは Dify が用意していた値を、変換後は**呼び出す側が渡します**。
4 種類あります。

- [6.1 ワークフローの入力](#61-ワークフローの入力を渡す)
- [6.2 `sys.` で始まるシステム変数](#62-sys-で始まるシステム変数)
- [6.3 `env.` で始まる環境変数とシークレット](#63-env-で始まる環境変数とシークレット)
- [6.4 知識取得 RAG の接続先](#64-知識取得-rag-の接続先)

### 6.1 ワークフローの入力を渡す

Dify の **Start ノード**で作った変数が、そのワークフローの入力です。
**Start ノードの名前をキーにして**、その下に渡します。

```python
result = graph.invoke({"start_node": {"query": "調べたいこと"}})
```

キーの名前（`start_node` の部分）とその中の変数名は、できたプログラムの
`state.py` を開けば書いてあります。`python -m` で動かしたときに使われる例も
`__main__.py` に入っているので、それを写すのが確実です。

> **書いていない名前を渡しても無視されます。** `{"start_node": {"quey": "..."}}` の
> ように打ち間違えると、値は届かず既定値のまま進みます。変数名は `state.py` で
> 確認してください。

> **必須の入力を渡さないとエラーで止まります。**
> Dify 側で「必須」にした変数を渡さないと、勝手な値で進めずに
> `ValueError` で止まり、足りない変数の名前がメッセージに出ます。
>
> **Dify 側で初期値を設定していても、「必須」なら渡さなければエラーです。**
> これは Dify 本体と同じ動きです。
>
> 必須でない変数は、Dify 側の初期値、無ければ空文字（数値なら `0.0`）になります。

### 6.2 sys. で始まるシステム変数

ワークフローが `sys.user_id` や `sys.query` などを使っている場合、それらは
`"sys"` というキーにまとめて渡します。

```python
result = graph.invoke({
    "start_node": {"query": "調べたいこと"},
    "sys": {"app_id": "my-app", "user_id": "u-123"},
})
```

何を渡す必要があるかは、`state.py` の `SysInputs` という部分に書いてあります。
**ワークフローが実際に使っているものだけ**が並びます。

> **渡し忘れると、足りない名前を挙げてエラーになります。**
> `ValueError: missing required sys input(s): app_id`
>
> Dify で動かしていたときは Dify が自動で入れていた値なので、変換後は渡す側が
> 用意する必要があります。`python -m` で動かす場合は例が入っているのでそのまま動きます。

### 6.3 env. で始まる環境変数とシークレット

Dify の「環境変数」を設定していたワークフローには、`env.py` というファイルが
できています。

**シークレットでない値**は、そのまま書き込まれているので設定は不要です。

```python
from workflow import env
print(env.API_BASE)      # Dify で設定した値がそのまま入っている
```

**シークレット（種類が `secret` の値）は書き込まれません。**
Dify の書き出しファイルにはシークレットの中身がそのまま載ってしまうため、
それをプログラムに埋め込むと、パスワードごとソースコードを保存することになります。
代わりに**動かすときに同じ名前で渡します**。

```bash
export SECRET_TOKEN=...            # Dify で付けた名前と同じ名前で渡す
python -m workflow
```

渡すべき名前の一覧は、動かす前に確認できます。

```python
from workflow import env
print(env.REQUIRED_ENV_VARS)       # 例: ('SECRET_TOKEN',)
```

`.env` という名前のファイルに書いておく方法もあります。プログラムのフォルダか、
その上のフォルダに置けば読まれます。`export` で直接渡した値のほうが優先されます。

```
SECRET_TOKEN=xxxxxxxx
```

> **渡さずに動かすと、名前を挙げて止まります。**
> `RuntimeError: environment variable 'SECRET_TOKEN' is required by this workflow (declared as a secret in the Dify DSL) but is not set`
>
> 空のまま先に進むと、後のほうで理由の分からないエラーになるため、ここで止めています。

### 6.4 知識取得 RAG の接続先

Dify の「知識取得」ノードを使っているワークフローは、**Dify の API を呼んで**
知識を取ってきます。次の値を設定してください。

| 環境変数 | 既定 | 何を設定するか |
|---|---|---|
| `DIFY_API_BASE_URL` | 未設定 | Dify の URL（例 `https://api.dify.ai`） |
| `DIFY_API_KEY` | 未設定 | Dify の「ナレッジ API」のキー |
| `DIFY_RETRIEVAL_SEARCH_METHOD` | `semantic_search` | 検索方式。埋め込みモデルを設定していないナレッジでは `keyword_search` か `full_text_search` |
| `DIFY_RETRIEVAL_TOP_K` | `4` | 何件取ってくるか |

```bash
export DIFY_API_BASE_URL=https://your-dify-instance
export DIFY_API_KEY=dataset-xxxxxxxx
export DIFY_RETRIEVAL_SEARCH_METHOD=keyword_search
python -m workflow
```

> **設定しなくても動きます。** URL とキーが未設定なら知識取得は「0 件」を返し、
> 処理はそのまま最後まで進みます。まず流れを確認したいときに便利です。
>
> Dify ではなく別の検索の仕組みを使いたい場合は、`retriever.py` の
> `get_retriever()` が返すものを差し替えてください。

> ここで挙げた環境変数はすべて、`.env` ファイルに書いても渡せます
> （[6.3](#63-env-で始まる環境変数とシークレット) と同じ方法）。
> OS やターミナルごとの書き方の違いを気にせずに済むので、こちらをおすすめします。

---

## 7. 変換したプログラムの中身

```
workflow/                  ← 書き出しファイルの名前が付いたフォルダ
├── __init__.py            外から使うときの入口
├── __main__.py            python -m で動かしたときに実行される部分（入力の例が入っている）
├── state.py               ノード間で受け渡す値の形の定義
├── graph.py               処理の順序と分岐の配線
├── nodes/                 ノード 1 つ = ファイル 1 つ  ← 主にここを埋める
│   ├── __init__.py
│   └── <ノード名>.py
├── llm.py                 AI を呼ぶときの共通設定
├── env.py                 Dify の環境変数（設定していた場合だけ）
└── retriever.py           知識取得（Dify の API を呼ぶ部分）
```

### 7.1 どこを埋めるか

`nodes/` の中の各ファイルを開くと、次のようになっています。

```python
def llm_node(state: GraphState) -> Command:
    """Execute node: LLM Node.
    ...
    """
    # How to access input variables:
    # start_node.query -> state.get("start_node", {}).get("query")

    # TODO: Implement llm node logic
    # See NODE_CONFIG for full Dify configuration details

    output: LlmNodeOutput = {
        "text": "placeholder",
        "reasoning_content": "placeholder",
        "finish_reason": "placeholder",
        "usage": {},
    }

    return Command(update={"llm_node": output})
```

- `# TODO: Implement ...` が**埋める場所**です
- `# How to access input variables:` に、**前のノードの値をどう取り出すか**が
  そのまま書かれています。**この行をコピーして使ってください。**
  `state.get(...)` という書き方になっているのは、分岐で通らなかったノードの値を
  読んでもエラーにせず `None` にするためです
- `NODE_CONFIG_JSON` に、Dify 側の設定がそのまま入っています。プロンプトの文面や
  接続先など、埋めるのに必要な情報はここにあります
- `output` に入れる項目は決まっています。**項目を減らさないでください**。
  後のノードがその項目を読んでいる場合、減らすと動かなくなります

### 7.2 最初から中身が入っているもの

次は埋める必要がありません。

- **終了ノード（Dify の End）** … 前のノードの値をそのまま受け渡します
- **知識取得ノード** … `retriever.py` 経由で Dify の API を呼びます

### 7.3 知っておくと役に立つこと

- **このツールが知らない種類のノードでも、プログラムは動きます。** 後のノードが
  読んでいる項目は、書き出しファイルを見て自動で用意されます。中身は仮の値です。
- **`env.py` は、Dify 側で環境変数を設定していた場合だけ**できます。
- 埋めるノードが `env.` の値を使う場合、ファイルの先頭に
  `from .. import env` を足す必要があります。その旨がコメントに書かれています
  （使っていない行を残さないため、埋めるまでは書いていません）。
- **改行コードは OS を問わず LF で統一**されます。Windows で作っても
  Docker で作っても同じファイルになるので、Git で管理しても差分が出ません。

---

## 8. 変換のときに AI を使う場合

`--skip-implement` を付けないと、ノードの中身の下書きを AI に書かせます。
`--name-nodes` でも AI を使います。その場合は接続設定が必要です。

| 提供元 | 設定する環境変数 |
|---|---|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Google | `GOOGLE_API_KEY`（`GEMINI_API_KEY` でも可） |
| Amazon Bedrock | AWS の通常の認証（リージョン指定が必須。[8.1](#81-amazon-bedrock-を使う場合)） |

```bash
export ANTHROPIC_API_KEY=sk-...
dify2langgraph workflow.yml --llm-provider anthropic --llm-model claude-sonnet-4-6
```

モデル名を省略すると、提供元ごとの既定が使われます（提供元によってモデル名の形が
まったく違うため、共通の既定値は置けません）。

> **AI の出力は必ず確認してください。** 下書きとして便利ですが、正しさは保証されません。

> できたプログラムの中の LLM ノードは、**動かすときに**別途 AI を呼びます。
> そのときの設定は `LLM_PROVIDER` / `LLM_MODEL` という環境変数で指定します
> （詳しくは `llm.py` を参照）。変換時の指定とは別物です。

### 8.1 Amazon Bedrock を使う場合

**リージョンをどこかで必ず指定してください。** 指定がないと `NoRegionError` で
止まります（間違ったリージョンに黙って接続するのを避けるためです）。
指定の方法は次のいずれかです。

- `--aws-region ap-northeast-1` を付ける（これが一番簡単です）
- 環境変数 `AWS_REGION` と `AWS_DEFAULT_REGION` を**両方**設定する
- AWS プロファイルに `region` を書いておく

```bash
dify2langgraph workflow.yml --llm-provider bedrock \
  --llm-model anthropic.claude-3-5-sonnet-20241022-v2:0 \
  --aws-region ap-northeast-1 --aws-profile my-sso-profile
```

> **`AWS_REGION` と `AWS_DEFAULT_REGION` は両方設定してください。**
> 変換ツールが使う部品と、できたプログラムが使う部品で、読む変数が違います。
> 片方だけだと両者が別のリージョンを見てしまいます。`--aws-region` を使えば
> この問題は起きません。

> **AWS SSO を使っている場合**、ログインは先に済ませておいてください。
> `aws sso login --profile <プロファイル名>`

---

## 9. Windows で使う場合

Windows でも同じコマンドがそのまま使えます。**PowerShell と Git Bash の両方で
実機確認済み**です。ただし次の 2 点だけ macOS / Linux と違います。

- [9.1 文字化けを防ぐ](#91-文字化けを防ぐ)
- [9.2 環境変数の書き方](#92-環境変数の書き方)
- [9.3 Git Bash の場合](#93-git-bash-の場合)
- [9.4 その他](#94-その他)

> Python の用意が面倒な場合は `uv` を使うと Python 本体も自動で入ります
> （[3.1](#31-python-を用意する)）。

### 9.1 文字化けを防ぐ

Dify のワークフローには日本語が入るのが普通です。一方 Windows の Python は、
画面に出す文字の扱いを**そのターミナルの設定**に合わせます。
日本語版 Windows と英語版 Windows で設定が違うため、そのままだと読めなくなります。

**設定は 2 つ必要です。片方だけでは読めません。**

| | 何をするか | 設定しないとどうなるか |
|---|---|---|
| ① `PYTHONUTF8=1` | Python 側を UTF-8 で**出力させる** | 日本語が `\u7ffb\u8a33` のような記号列になる |
| ② `chcp 65001` | ターミナル側を UTF-8 として**読ませる** | 文字化けする（例: `翻訳結果` → `τ┐╗Φ¿│τ╡Éµ₧£`） |

PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
chcp 65001

# 毎回設定しなくてよいようにする（次に開いたウィンドウから有効）
setx PYTHONUTF8 1
```

コマンドプロンプト:

```bat
set PYTHONUTF8=1
chcp 65001
```

> ② の代わりに、PowerShell の今のウィンドウだけを UTF-8 にすることもできます。
> ターミナル全体の設定を変えないので、影響範囲が小さくて済みます。
>
> ```powershell
> [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
> ```

> **設定しなくてもプログラムが落ちることはありません。** 表示できない文字は
> `\u7ffb` のような形に置き換えて出すので、エラーで止まることはありません。
> ただし読みづらいので、上の設定をおすすめします。

### 9.2 環境変数の書き方

この文書のコマンド例は macOS / Linux の書き方（`export VAR=値`）です。
PowerShell とコマンドプロンプトでは書き方が違います。

| macOS / Linux / Git Bash | PowerShell | コマンドプロンプト |
|---|---|---|
| `export VAR=値` | `$env:VAR = "値"` | `set VAR=値` |
| `VAR=値 command` | `$env:VAR = "値"` を先に実行 | `set VAR=値` を先に実行 |
| `PYTHONPATH=src python -m ...` | `$env:PYTHONPATH = "src"` を先に実行 | `set PYTHONPATH=src` を先に実行 |

**Git Bash なら左端の列がそのまま使えます。**

> **いちばん確実なのは `.env` ファイルを使う方法です。** ターミナルごとの書き方の
> 違いを気にせずに済みます（[6.3](#63-env-で始まる環境変数とシークレット)）。

### 9.3 Git Bash の場合

環境変数は macOS / Linux と同じ書き方が使えます。
ファイルの場所（パス）は、**Git Bash 式（`/c/Users/you/wf.yml`）と
Windows 式（`C:/Users/you/wf.yml`）のどちらでも渡せます。**

```bash
dify2langgraph /c/Users/you/workflow.yml -o out --skip-implement   # どちらでも可
dify2langgraph C:/Users/you/workflow.yml -o out --skip-implement
```

> **エクスプローラーからコピーしたパスは、引用符で囲んでください。**
> `C:\Users\you\wf.yml` のような円記号（`\`）区切りは、囲まないと記号が消えて
> `C:Usersyouwf.yml` になり、ファイルが見つかりません。
>
> ```bash
> dify2langgraph "C:\Users\you\workflow.yml" -o out --skip-implement
> ```

> **ネットワークドライブや共有フォルダの上で作業しないでください。**
> そこに置いて `uv` で環境を作ると `The parameter is incorrect. (os error 87)`
> のような失敗をします。ローカルディスクにコピーしてから作業してください。
> なお `pip install .` を使う方法（[3.2](#32-このツールを入れる)）なら
> この問題は起きません。

### 9.4 その他

- ファイルの場所の区切りは `\` と `/` のどちらでも動きます。
- `cd output && python -m workflow` の `&&` は、PowerShell 7 以降でのみ使えます。
  Windows 標準の PowerShell 5.1 では `cd output; python -m workflow` と書いてください。

---

## 10. Docker で使う場合

**Python を用意せずに変換したい場合**の方法です。Python のバージョン合わせ、
文字化け対策、ターミナルごとの書き方の違いが、いずれも不要になります。

> **動作確認の状況: macOS と Linux は確認済み、Windows は未確認です。**
> Windows で使う場合は [9 章](#9-windows-で使う場合) の通常の方法をおすすめします
> （こちらは実機確認済みです）。
>
> なお Docker Desktop は、一定の規模を超える企業では有償ライセンスが必要です。
> 社内の申請が必要かどうか、事前に確認してください。

> **Docker にするのは変換ツールだけです。** できたプログラムのほうには Dockerfile は
> 出力されません。そちらはお手元の Python で動かす前提です。

- [10.1 イメージを作る](#101-イメージを作る)
- [10.2 変換する](#102-変換する)
- [10.3 Linux でのファイルの持ち主](#103-linux-でのファイルの持ち主)
- [10.4 API キーの渡し方](#104-api-キーの渡し方)
- [10.5 Docker から Amazon Bedrock を使う場合](#105-docker-から-amazon-bedrock-を使う場合)

### 10.1 イメージを作る

配布物に `Dockerfile` が入っています。**中身を確認してから自分で組み立てる**方式です
（どこかから完成品をダウンロードする方式にはしていません）。

```bash
docker build -t dify2langgraph .
```

組み立てのときだけインターネットが必要です。使うライブラリのバージョンは
固定されているので、作るたびに中身が変わることはありません。

> 同梱の設定により、**公開されてから 3 日たっていないバージョンのライブラリは
> 使いません**。公開直後に取り下げられた版や不正な版を取り込む危険を減らすためです。

### 10.2 変換する

作業フォルダをコンテナの `/work` につないで実行します。

```bash
docker run --rm \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

`compose.yaml` も同梱しているので、こちらなら 1 行で済みます。

```bash
docker compose run --rm convert workflow.yml -o outputs --skip-implement
```

PowerShell:

```powershell
docker run --rm `
  --mount type=bind,source="$PWD",target=/work `
  dify2langgraph workflow.yml -o outputs --skip-implement
```

Git Bash:

```bash
MSYS_NO_PATHCONV=1 docker run --rm \
  --mount type=bind,source="$(pwd -W)",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

> **Git Bash では 2 か所の書き換えが必要です。**
>
> 1. 先頭に `MSYS_NO_PATHCONV=1` を付ける。Git Bash はパスに見える文字列を自動で
>    Windows 式に書き換えますが、その書き換えがコンテナ側の `/work` にも及んで
>    別の場所に化けてしまいます。この指定で書き換えを止められます。
> 2. `$PWD` ではなく `$(pwd -W)` を使う。Docker は Windows 式のパスを求めるためです。

> **`-v` ではなく `--mount type=bind,source=...` を使ってください。**
> Windows のパスには `C:` のようにコロンが入り、`-v` ではそれが区切り記号と
> 混同されます。`--mount` なら曖昧さがありません。

> コンテナの中でも既定は同じです。`--skip-implement` を付けなければ AI を呼びます。
> まずは上の例のように付けて試してください。

### 10.3 Linux でのファイルの持ち主

| OS | どうするか |
|---|---|
| **Linux** | `--user "$(id -u):$(id -g)"` を**付ける**。付けないとできたファイルが別のユーザーの持ち物になり、書き換えられなくなります |
| **macOS / Windows** | **付けない**。自動で調整されるので不要です。付けると別の不具合が起きることがあります |

```bash
# Linux
docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

`compose.yaml` では既定で付けていません。Linux で使う場合は `compose.yaml` の
`user:` の行のコメントを外してください。

> 作業フォルダに `__pycache__/` や `.ruff_cache/` のような作業用フォルダが
> 残らないように設定済みです。

### 10.4 API キーの渡し方

**`.env` ファイルを使ってください。`docker run --env-file` は使わないでください。**

作業フォルダごと `/work` につないでいれば、そこに置いた `.env` はそのまま読まれます。

```bash
docker run --rm \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider openai
```

一部の値だけ上書きしたいときは `-e KEY=値` を足せます（`.env` より優先されます）。

> **`--env-file` を使うと、キーが使えない形で渡ります。** `docker run --env-file` は
> `.env` の読み方が違い、引用符が値の一部として残ってしまいます。たとえば
> `OPENAI_API_KEY="sk-xxx"` と書いた場合、引用符込みで渡るため**エラーにならず
> 認証だけ失敗します（401）**。原因が分かりにくいので避けてください。
> 行頭に `export ` が付いていると起動そのものが失敗します。
>
> `docker compose` の `env_file:` は別の読み方なので問題ありません
> （同梱の `compose.yaml` はこちらを使っています）。

変換ツールが読む環境変数は次で全部です。

| 用途 | 変数 |
|---|---|
| AI（変換の補助） | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` |
| Amazon Bedrock | `AWS_PROFILE`, `AWS_REGION`, `AWS_DEFAULT_REGION` |
| 実行の記録 | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` |
| ログ | `LOG_LEVEL`, `LOG_FORMAT` |

### 10.5 Docker から Amazon Bedrock を使う場合

**`aws sso login` はコンテナの外（ふだんのターミナル）で先に実行してください。**
コンテナの中にはブラウザが無いため実行できません。

```bash
aws sso login --profile <プロファイル名>          # 先にこちら。ブラウザが開く

docker run --rm \
  -e AWS_PROFILE=<プロファイル名> \
  -e AWS_REGION=ap-northeast-1 -e AWS_DEFAULT_REGION=ap-northeast-1 \
  --mount type=bind,source="$HOME/.aws",target=/home/app/.aws \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider bedrock \
  --llm-model anthropic.claude-3-5-sonnet-20241022-v2:0
```

`compose.yaml` を使う場合（AWS の設定フォルダのつなぎ込み込み）:

```bash
export AWS_PROFILE=<プロファイル名>
export AWS_REGION=ap-northeast-1
export AWS_DEFAULT_REGION=ap-northeast-1
docker compose run --rm bedrock workflow.yml -o outputs --llm-provider bedrock
```

> PowerShell では `$HOME` が使えないため、代わりに次を設定してください。
> `$env:AWS_DIR = "$env:USERPROFILE\.aws"`

**注意点が 3 つあります。**

1. **`AWS_REGION` と `AWS_DEFAULT_REGION` を両方設定してください。**
   読む変数が部品によって違うため、片方だけだと別のリージョンを見てしまいます。
   `--aws-region` を使えば一度で済みます。

2. **AWS の設定フォルダは書き込み可能でつないでください（`:ro` を付けない）。**
   ログイン情報の期限が近づくと自動で更新され、その結果が設定フォルダに
   書き戻されます。読み取り専用だとそこで失敗します。しかも失敗するのは
   期限が迫った一時期だけなので、「ときどき落ちる」ように見えて原因が分かりにくく
   なります。書き込まれるのは、ふだん AWS のコマンドがしているのと同じ更新だけです。

   社内の方針で読み取り専用が必須の場合は、`docker run` の**直前に**
   `aws sts get-caller-identity --profile <プロファイル名>` を実行して
   ログイン情報を更新させてください。

3. **つなぎ先の `/home/app/.aws` は変えないでください。** ログイン情報の
   置き場所が決まっているためです。

#### AWS の設定フォルダをつなげない場合

一時的なログイン情報をファイルに書き出して渡します。

```bash
aws configure export-credentials --profile <プロファイル名> --format env-no-export > aws.env

docker run --rm --env-file aws.env \
  -e AWS_REGION=ap-northeast-1 -e AWS_DEFAULT_REGION=ap-northeast-1 \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --llm-provider bedrock
```

ここで `--env-file` を使ってよいのは、このコマンドの出力が機械的に作られた
きれいな形（引用符なし・1 行 1 項目）だからです。**手で書いた `.env` には
使わないでください**（[10.4](#104-api-キーの渡し方)）。

> **この方法では `AWS_PROFILE` と `--aws-profile` を渡さないでください。**
> 設定フォルダが無い状態でプロファイル名を指定すると、有効なログイン情報が
> あっても `ProfileNotFound` で即座に失敗します。

> **有効期限は既定で 1 時間です。** さらに期限の 10 分前になると
> `RuntimeError: Credentials were refreshed, but the refreshed credentials are still expired.`
> というエラーが出ます。出たら `aws configure export-credentials` をやり直してください。

> **PowerShell では文字コードを指定してください。** 既定のままだとファイルの先頭が
> 壊れて読めません。
>
> ```powershell
> aws configure export-credentials --profile <プロファイル名> --format env-no-export |
>   Out-File -Encoding ascii aws.env
> ```

---

## 11. うまくいかないとき

### 11.1 変換のとき

| 症状 | 原因と対処 |
|---|---|
| `dify2langgraph: command not found` | インストールできていません。[3.2](#32-このツールを入れる) をやり直すか、[3.3](#33-インストールせずに使う場合) の方法を使ってください |
| `Python 3.13 以上が必要` と出る | Python のバージョンが足りません。[3.1](#31-python-を用意する) |
| 日本語が化ける（Windows） | ターミナルの文字コード設定が 2 つとも必要です。[9.1](#91-文字化けを防ぐ) |
| `NoRegionError` | Amazon Bedrock のリージョン指定がありません。[8.1](#81-amazon-bedrock-を使う場合) |
| `TokenRetrievalError: Token has expired and refresh failed` | AWS SSO のログイン期限切れです。ふだんのターミナルで `aws sso login --profile <プロファイル名>` |
| `ProfileNotFound` | AWS の設定フォルダをつながずにプロファイル名を指定しています。指定を外してください |
| `AccessDeniedException`（Bedrock） | リージョンかモデル名が想定と違います。`--aws-region` で明示してください |
| AI のキーが読まれない（Docker） | `--env-file` に手書きの `.env` を渡していませんか。[10.4](#104-api-キーの渡し方) |
| `invalid reference format` などのつなぎ込みエラー（Windows + Docker） | `-v` を使っています。`--mount type=bind,source=...` に置き換えてください |
| できたファイルが別のユーザーの持ち物になる（Linux + Docker） | `--user "$(id -u):$(id -g)"` を付けてください。[10.3](#103-linux-でのファイルの持ち主) |
| 読み取り専用に関するエラー（AWS の設定フォルダ付近） | `:ro` を外してください。[10.5](#105-docker-から-amazon-bedrock-を使う場合) |

### 11.2 できたプログラムを動かすとき

| 症状 | 原因と対処 |
|---|---|
| `ValueError` で「必須の入力が足りない」と出る | Dify 側で必須にした変数を渡していません。[6.1](#61-ワークフローの入力を渡す) |
| `ValueError: missing required sys input(s): ...` | システム変数を渡していません。[6.2](#62-sys-で始まるシステム変数) |
| `RuntimeError: environment variable '...' is required` | シークレットを渡していません。[6.3](#63-env-で始まる環境変数とシークレット) |
| `ModuleNotFoundError: No module named 'workflow'` | 動かす場所が違います。できたフォルダの**1 つ上**から `python -m workflow` |
| フォルダ名に関するエラー | フォルダ名にハイフンが入っているか数字で始まっています。[5.1](#51-そのまま動かす) |
| 知識取得の結果がいつも空 | `DIFY_API_BASE_URL` と `DIFY_API_KEY` が未設定です。[6.4](#64-知識取得-rag-の接続先) |
| 値が `None` になっている | 分岐で通らなかった側のノードの値です。異常ではありません。[5.3](#53-結果の読み方) |
| 値が `"placeholder"` になっている | そのノードの中身をまだ埋めていません。[7.1](#71-どこを埋めるか) |

### 11.3 その他の環境固有の注意

このツール側では対応していないため、環境に合わせて対処してください。

- **社内プロキシ / 独自の証明書**（Docker を使う場合）: `docker build` に
  `--build-arg HTTP_PROXY=...` を渡し、社内証明書が必要な場合は `Dockerfile` に
  追加してください。
- **SELinux が有効な Linux**（RHEL 系）: つなぎ込みに `,z` を付ける必要がある場合が
  あります。
- **時計のずれ**: パソコンの時計が大きくずれていると AWS の認証に失敗します。
