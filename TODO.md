# TODO

Roadmap after the 2026-08 redesign. Decisions: see [docs/adr/](./docs/adr/); terms: [CONTEXT.md](./CONTEXT.md).

## 要 Windows 実機（o02c さんの手元環境が必要）

エージェント側では実行できないタスク。Parallels の Windows VM が使えるときに。

- [ ] **検証スクリプト 2 本の再実行。** 直近の実測（PowerShell 15 passed / Git Bash
  17 passed）はレビュー修正より前のもので、その後に**検査ロジック自体が変わっている**:
  B3 は常に PASS だったところに FAIL 分岐を追加、C1 は PASS / FAIL の判定を組み替え、
  M4 は新規追加でまだ一度も Windows で走っていない。数字が古いまま「検証済み」にすると、
  このリポジトリで繰り返し潰してきた偽 PASS と同じ状態になる。

  ```powershell
  # 1. macOS 側で基準 digest を取る
  #    make verify-digest
  # 2. VM に展開（Downloads 経由）
  #    git archive --format=zip -o ~/Downloads/d2l.zip HEAD
  # 3. PowerShell
  .\scripts\verify-windows.ps1 -ExpectedDigest <上の digest>
  ```
  ```bash
  # 4. Git Bash（同じ digest を渡す）
  scripts/verify-gitbash.sh --expected-digest <上の digest>
  ```

  > **生成物が何度も変わっているので digest も変わっている。** 過去ログの値
  > （`3ca50a8c...` など）は使えない。必ずその時点の `make verify-digest` の値を使う。

  LLM 経路まで見る場合は `-WithLlm` / `--with-llm` を追加（実際に課金される）。
  Docker は対象外（下記「Windows での Docker 検証は「やらない」と決めた」を参照）。

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
  - [x] `sys.*` / `env.*` の実装（下の Deferred 節に詳細）
  - [ ] `{{#context#}}` 解決、End 以外の本体への入力配線（LLM オプトイン後処理と併走・ADR-0001）
- [x] 生成物を自己完結パッケージ化（相対 import、`__init__`/`__main__`、`sys.path` ハック廃止、ADR-0007）
- [x] RAG: `Retriever` ポート + `DifyApiRetriever` 既定アダプタ（ADR-0006）
  - `templates/retriever.py`（依存フリー・urllib）を生成物にバンドル、knowledge-retrieval ノードが `get_retriever().retrieve(...)` を呼ぶ実本体を生成。未設定時は `[]` を返し資格情報なしでも走る
- [~] テスト拡充
  - [x] 生成コードが ruff の既定設定（line-length 88）で lint クリーンであることを全フィクスチャで固定
        （`TestGeneratedCodeIsLintClean`。生成物は `pyproject.toml` を持たないため既定設定で lint される）
  - [x] AWS リージョン / プロファイル解決、SSO エラーメッセージ、`.env` 探索
  - [~] 循環参照・孤立ノード・自己ループを追加。`get_dependency_order` が循環時に
    静かにノードを落としていた（3 ノード中 1 つしか返らない）ので、循環を検出して
    関与ノードを名指しする `ValueError` にした。ハンドラは `if-else` だけ
    `get_handler` で名指しされていなかったので補った
  - [ ] 残り: ハンドラごとの `output_fields` / `stub_output` の網羅

## Packaging / 移植性（ADR-0008）

- [x] 変換ツールを Docker イメージとして配布（`Dockerfile` / `.dockerignore` / `compose.yaml`）
  - レジストリ公開はせず顧客がローカルビルド。生成物には Dockerfile を出力しない（ADR-0007 の出力契約は不変）
  - `HOME=/home/app`（botocore の SSO キャッシュ解決）、`PYTHONUTF8=1`、`__pycache__`/`.ruff_cache` を
    マウント先に撒かない設定を焼き込み。`chmod 0777` で任意 uid の `--user` に対応
- [x] Windows のコードページ対応 — ファイル I/O の `encoding="utf-8"` 明示、生成 `__main__.py` の
  stdout エスケープ、ANSI カラーの条件付き有効化
- [x] Bedrock のリージョン解決（`--aws-region` / `--aws-profile`、暗黙の `us-east-1` を廃止）
- [x] `.env` 探索を `usecwd=True` に（インストール後に作業ディレクトリの `.env` へ到達できるように）
- [x] 依存検疫 — `[tool.uv] exclude-newer` で公開 3 日未満の版を採用しない（`make lock` が日付を更新）
- [x] 未使用依存の削除 — `psycopg2-binary`（ADR-0006 の残骸）、`langchain` メタパッケージ
- [~] **Windows ホストでの実機検証** — `scripts/verify-windows.ps1` を用意（PowerShell 5.1 互換）。
  macOS からは検証できない主張だけを対象にしている: コンソールのコードページ、PowerShell の
  環境変数構文、パス区切り。Docker は対象外（下記の判断を参照）。
  出力のバイト一致は `make verify-digest`（macOS/Linux）と `-ExpectedDigest`（Windows）で突き合わせる
  - [x] macOS 側の基準値と Linux コンテナ側の検証は完了（両者一致）
  - [x] Windows 実機でのネイティブ CLI 検証（B/C/D 群）— **完了**。
    Windows 11 ARM64 / PowerShell 5.1 / en-US / コードページ 437 で 8 項目パス
    - 生成物が macOS・Linux コンテナとバイト一致。OS をまたいだ
      決定論が実機で裏付けられた（ADR-0001）
    - 生成物の改行が LF（`newline="\n"` の修正が実機で効いている）
    - `PYTHONUTF8` 未設定でも `\uXXXX` にエスケープされて落ちない
    - バックスラッシュ／スラッシュ両方のパス区切りが通る
    - この検証で USAGE.md 8.1 の記述漏れを発見（PowerShell の節に `chcp 65001` が
      無く、`PYTHONUTF8=1` だけではコンソールで化ける）。修正済み
  - [x] Windows 実機での**生成物の実行**検証（F 群）— 完了。`scripts/run_generated.py` で
    最終 GraphState を JSON に落とし、全ノード通過・End の値転送・分岐が 1 つに解決・
    資格情報なしの knowledge-retrieval が `[]` を確認。PowerShell と Git Bash の
    両経路で通過
  - [~] **Git Bash 経路の検証** — `scripts/verify-gitbash.sh`（bash 3.2 互換、
    shellcheck クリーン）で Windows 11 ARM64 / MINGW64 / コードページ 437 上で
    17 passed / 0 failed。実質的な判定は PowerShell 版と同じ Python ヘルパを共有する
    - [ ] **Windows での再実行が未了** — 上の「要 Windows 実機」節を参照。この 17 passed は
      レビュー修正より前の実測で、その後に検査ロジック自体が変わっている
    - MSYS の引数パス変換により `/c/...` と `C:/...` の両形式が CLI に届く（M1 / M3）
    - `pwd -W` が Windows 形式を返す（M2）— USAGE 9.2 の指示の裏付け
    - 生成物が macOS・Linux コンテナとバイト一致（B5）
    - `.gitattributes` に `*.sh text eol=lf` を追加。CRLF の .sh は shebang が
      `/usr/bin/env bash\r` になり Git Bash が起動すら拒否する
    - 共有フォルダ上には venv を作れない（`os error 87`）。Windows では無条件に
      ローカルへ複製するようにし、USAGE 8.3 にも注意として記載した
    - Docker 併用（`MSYS_NO_PATHCONV=1` + `pwd -W` をバインドマウントのソースに使う形）は
      **検証対象から外した** — 下記の判断のとおり Windows での Docker 検証自体をやめたため。
      元の懸念の中心はここだったが、`pwd -W` が Windows 形式を返すこと（M2）までは
      確認できている。`verify-gitbash.sh` 側の E 群も、一度も実行されていないため削除した
  - [x] **Windows での Docker 検証は「やらない」と決めた** — Docker Desktop for Windows は
    WSL2、つまりネスト仮想化を要求するが、`prlctl set --nested-virt` は Parallels Desktop の
    Pro / Business 版専用で、Standard 版では有効化できない。実施には Parallels の
    エディション変更か別の Windows 実機が必要。
    一度も実行されないまま残っていた E 群は削除した。このスクリプトでは「実行されて
    いない検証コードが PASS を返す」不具合を何度も踏んでいるため、動かしたことのない
    検査を置いておくと検証結果全体の信頼性が落ちる。coverage に見えるだけの空白よりは
    無い方がよい。
    コンテナ経路自体は macOS / Linux で検証済み（生成物がネイティブ実行とバイト一致する
    ことまで確認）。未検証なのは Docker Desktop **for Windows** のバインドマウント挙動・
    ドライブレターの `--mount`・ファイル所有者の 3 点。Windows の顧客には
    ネイティブ経路（USAGE 8 章、PowerShell と Git Bash の両方で検証済み）を案内する
- [x] **変換時のプロバイダに google が無い** — `llm/google.py` を追加して解消。
  あわせて `--llm-model` の既定をプロバイダ追随にした（`gpt-4o-mini` 固定だったため
  `--llm-provider google` は 404、`anthropic` も同様に失敗していた）
- [x] **`--llm-provider anthropic` が SDK 非互換で常に失敗していた** — anthropic 1.x が
  `messages.create()` から `temperature` を削除したのに渡し続けており、
  `unexpected keyword argument 'temperature'` で全呼び出しが落ちていた。宣言下限
  `anthropic>=0.75.0` は受け付ける版と受け付けない版の両方を含むため、インストール版の
  シグネチャを見て渡すか判断する形にした。検証スクリプトに `-LlmProvider` を足して
  初めて表面化した（既定の自動選択は OpenAI を優先するため anthropic に到達しない）
- [x] **ワークフロー入力の所在が未定義** — ADR-0009 で解消。Start ノードを決定論化し、
  呼び出し側の値を自分の state スロットから読む（従来の Stub は呼び出し側の値を
  上書きしており、そもそも入力を渡す手段が無かった）。必須入力の欠落は ValueError。
  TODO マーカーが消えたため LLM パスの対象外になり、住所を推測されることも無くなった
- [x] `generator/engine.py` のプロンプトを ADR-0007 に追随させた — 以前は `sys.path.insert` や
  絶対 import（`from llm import ...`）を指示しており、生成される本体が自己完結
  パッケージの形に反していた。Retriever の例も実 API と違っていた（ADR-0009 と同時に修正）
- [x] 依存の下限バージョンを実態に合わせた — 15 件が lock より低い下限を宣言しており、
  うち 7 件はメジャーが 1 つ以上違った（`langchain-core>=0.3.0` に対し lock は 1.6.3 など）。
  `uv sync` は lock どおり入れるので開発中は見えず、USAGE 2 章が主経路として案内している
  `pip install .` でだけ古い版が入りうる状態だった。下限を lock の版に引き上げ、
  `tests/test_packaging.py` で再発を検出する（lock を上げて pyproject を忘れると落ちる）
- [ ] 変換ツール用と生成物用の依存の分離（optional extras）— `--auto-fix` が `templates/llm.py` を
  再利用する関係で現状は混在。分離すると顧客のインストール手順が変わるため保留（docs/tech-stack.md 参照）

## LLM opt-in post-processing（任意・ADR-0001）

- [ ] `# TODO` スタブ本体の LLM 埋め（`generator/engine.py`）をオプトイン後処理として整理
- [ ] lint 自動修正エージェント（`agents/`）をオプトイン後処理として整理
- [ ] 意味的 snake_case リネームパス（`--name-nodes`）を LLM オプトインとして再位置づけ
- [ ] ノード生成の並列化（`batch()` / `ainvoke()` + `asyncio.gather()`）

## Deferred（要調査 / 後続）

- [ ] **`iteration`（配列を map）** — `iterator_selector`（入力配列）/ `output_selector`
  （各周で集める変数）/ `is_parallel` / `parallel_nums`（既定 10、`is_parallel` が false なら
  1 に強制）/ `flatten_output`（既定 true。全周の出力が list のときだけ平坦化）/
  `error_handle_mode` = `terminated` | `continue-on-error` | `remove-abnormal-output`。
  出力は `output` 1 つ。本体内で `[iteration_id, "item"]` / `[iteration_id, "index"]` が読める。
  実装時には**パーサが `iterator_selector` / `output_selector` を収集する必要がある**
  （現状これが唯一の参照収集漏れ。他の全ノード種別は網羅を検証済み）
- [ ] **`loop`（条件付き繰り返し）— `iteration` とは別のノード種別** `loop_count`（最大周回、
  既定 10）/ `break_conditions` + `logical_operator`（`and`/`or`。比較演算子に非 ASCII の
  `≥ ≤ ≠` が実 DSL に現れる）/ `loop_variables`（`label` が変数名の可変ループ状態）。
  **`output` を持たない** — `loop_variables[].label` の最終値 + `loop_round`(number)。
  本体内では `[loop_id, <label>]` を読み書きする。`loop` の `error_handle_mode` は
  UI が書くが graphon は読んでいないので無視してよい。
  マーカー `loop-end` は構造上の終端ではなく break（内側の Loop End は外側を break できない）。
  `iteration-end` は存在しない
- [ ] **ノードのエラー処理の意味論** — グラフ構造（fail-branch が全分岐を発火させる問題）は
  修正済み（ADR-0003 の amendment）。残りは以下。
  - `retry_config` = `{max_retries, retry_interval, retry_enabled}`。**`retry_interval` の
    単位はミリ秒**。総試行回数は `1 + max_retries`。リトライを使い切ってから初めて
    ストラテジが適用される。UI の範囲は max 1–10 / interval 100–5000ms（既定 3 / 1000）で
    バックエンド検証は無い。リトライ対応は llm / code / http-request / tool の 4 種のみ
  - `default_value` = `[{key, type, value}]`。キー集合はノード種別ごとに UI が決める
    （llm→`text` / http-request→`body`+`status_code`+`headers` / tool→`text`+`json` /
    code→`data.outputs` のキー / その他→空）
  - **未検証の罠**: dify の fixture 2 件に `retry_config.enabled` と
    `retry_config.exponential_backoff` という別形状がある。graphon に消費側が無く
    pydantic に落とされる。実装時は `retry_enabled` を正とし、防御的に `enabled` も受ける
  - `agent-v2` は出力ごとの別スキーマを持つ（`on_failure` / `retry_interval_ms` /
    `fail_branch`・`default_value` とアンダースコア表記）。ノード単位のものとは非互換
- [x] **`sys.*` の実装** — 参照されているフィールドだけを `SysInputs` として宣言し、
  `GraphState` に `sys` を追加。呼び出し側が invoke 時に渡す（ADR-0009 と同じ扱い）。
  selector 形式とテンプレート形式の両方が解決される。sys の構成はモード依存
  （`sys.query` は chatflow のみ、workflow は `sys.app_id` / `sys.user_id`）なので、
  固定の一覧は持たない
- [x] **`env.*` の実装** — `env.py` を生成し、`env.NAME` で参照する（ADR-0004）。
  secret は定数にせず、実行時に同名の環境変数から読む（PEP 562 の module `__getattr__`）。
  未設定なら変数名を挙げて `RuntimeError`。DSL は secret の値を平文でエクスポートするため、
  定数にすると顧客がコミットするソースに資格情報が入る。参照解決も
  `state["env"][...]` から `env.NAME` に変えた（前者はコメントと NODE_CONFIG にのみ
  現れていたが、そこは LLM 本体生成の入力そのもの）
- [x] chatflow（`mode: advanced-chat`）の形を fixture 化 — `chatflow_sys_query.yml`。
  `answer` 終端・`variables: []` の Start・非数値ノード ID・`{{#sys.query#}}` を含む。
  これで生成コード品質のバグ 2 件（`END` が未使用 import になる／`__init__.py` の
  import と `__all__` が未整列）も表面化して修正した
- [ ] `conversation.*`（chatflow 専用、対象外）
- [ ] 埋め込みモデル自動解決 — API 経由で不要化の見込みだが、別バックエンド採用時に再検討
- [~] Retriever に検索設定を転送（ADR-0006、実 Dify 1.16.1 で検証）
  - [x] `/retrieve` は完全な `retrieval_model`（search_method / reranking_enable / top_k / score_threshold_enabled）が必須 → adapter が補完。`search_method` は DSL に無いため env `DIFY_RETRIEVAL_SEARCH_METHOD`（既定 semantic_search）で制御。handler が `multiple_retrieval_config` の top_k / score_threshold を投影
  - [ ] reranking（`reranking_model` / provider）の転送、`single` モード（LLM 選択）対応
  - [ ] metadata フィルタの転送 — Dify 側に `metadata_filtering_mode`
    （`disabled`/`automatic`/`manual`）/ `metadata_filtering_conditions` /
    `metadata_model_config` が実在するが未対応
- [x] **ノード種別ごとの出力を Dify の正典に合わせた**（登録 12 → 20）。Dify 本体
  （langgenius/dify + graphon 0.7.0）の実装から出力を取って全ハンドラを突き合わせ、
  `http-request`（未登録だった）/ `parameter-extractor` / `document-extractor` /
  `list-operator` / `assigner` / `iteration-start` / `loop-start` / `loop-end` を追加。
  `if-else` の `selected_branch` は発明した名前だったので Dify の `selected_case_id` に。
  `code` は DSL の `data.outputs` を読む（`result`/`stdout`/`stderr` は架空だった）
- [ ] 残るノード種別の**動的な**出力
  - `tool` / `agent` — プラグインの `output_schema` 由来で DSL には無い。下流が読んでいれば
    安全網（`effective_output_fields`）が宣言するので実行は通る
  - `code` の `outputs[*].children`（入れ子 object スキーマ）。現状 `type` だけを見ている
  - `variable-aggregator` のグループ形式（`[node, group_name, "output"]` の 3 段）
  - `agent-v2` の `agent_declared_outputs` / `switch`（`agent_output_routes.enabled` 依存）
- [ ] 対象外と判断: `datasource` / `datasource-empty` / `knowledge-index`（RAG パイプライン）、
  `trigger-schedule` / `trigger-webhook` / `trigger-plugin`（トリガー系ワークフロー）
- [ ] CLI: `--dry-run`, `--single-file`（`--format`）
- [ ] 生成コードの使い方ガイド / ノードタイプ別実装例

## Done（旧実装で完了済み・再設計で再編対象）

- [x] 基本パーサー / state.py / nodes/ / graph.py 生成
- [x] NODE_CONFIG に Dify 設定を埋め込み
- [x] ruff + ty lint 対応 / Command 戻り値
- [x] LLM プロバイダー抽象化（OpenAI / Anthropic / Bedrock）
- [x] `--name-nodes`（LLM でノード名生成）※ 再設計で opt-in に再位置づけ
