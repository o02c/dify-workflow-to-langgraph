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
- [~] テスト拡充
  - [x] 生成コードが ruff の既定設定（line-length 88）で lint クリーンであることを全フィクスチャで固定
        （`TestGeneratedCodeIsLintClean`。生成物は `pyproject.toml` を持たないため既定設定で lint される）
  - [x] AWS リージョン / プロファイル解決、SSO エラーメッセージ、`.env` 探索
  - [ ] ハンドラ単位、循環参照・孤立ノード等のエッジケース

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
  環境変数構文、パス区切り、`--mount` のドライブレター、Docker Desktop for Windows のマウント所有者。
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
  - [ ] Windows 実機での**生成物の実行**検証（F 群）— `scripts/run_generated.py` と
    F1/F2/F3 を追加済み。グラフが実際に実行されたか（全ノード通過、End の値転送、
    分岐が 1 つに解決、資格情報なしの knowledge-retrieval が `[]`）を最終状態の
    JSON で確認する。macOS ではドライラン済み、Windows 実機はこれから
  - [ ] **Git Bash 経路の検証** — 顧客環境には Git Bash があるため、PowerShell と並ぶ
    実使用経路。`MSYS_NO_PATHCONV=1` と `$(pwd -W)` を使う形を USAGE.md 9.2 に書いたが
    **実機未検証**。MSYS2 のパス変換は `target=/work` にも及ぶので、ここを外すと
    マウント先が化ける。検証は `verify-windows.ps1` の bash 版を起こすか、
    B/C 群をシェル非依存な形に切り出して両方から呼ぶ形が考えられる
  - [ ] Windows 実機での Docker 検証（E 群）— **現状の手元環境では不可**。Docker Desktop for
    Windows は WSL2、つまりネスト仮想化を要求するが、`prlctl set --nested-virt` は
    Parallels Desktop の Pro / Business 版専用で、Standard 版では有効化できない。
    実施するには Parallels のエディション変更か、別の Windows 実機が要る
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
- [ ] 依存の下限バージョンを実態に合わせる — 例 `langchain-core>=0.3.0` に対し lock は 1.6.3。
  `uv.lock` 経由なら問題ないが、lock を使わない `pip install .` では古い版が入りうる
- [ ] 変換ツール用と生成物用の依存の分離（optional extras）— `--auto-fix` が `templates/llm.py` を
  再利用する関係で現状は混在。分離すると顧客のインストール手順が変わるため保留（docs/tech-stack.md 参照）

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
- [~] Retriever に検索設定を転送（ADR-0006、実 Dify 1.16.1 で検証）
  - [x] `/retrieve` は完全な `retrieval_model`（search_method / reranking_enable / top_k / score_threshold_enabled）が必須 → adapter が補完。`search_method` は DSL に無いため env `DIFY_RETRIEVAL_SEARCH_METHOD`（既定 semantic_search）で制御。handler が `multiple_retrieval_config` の top_k / score_threshold を投影
  - [ ] reranking（`reranking_model` / provider）の転送、`single` モード（LLM 選択）対応
- [ ] 他ノードタイプ: parameter-extractor / http-request / variable-assigner / template-transform / tool / agent / code
- [ ] CLI: `--dry-run`, `--single-file`（`--format`）
- [ ] 生成コードの使い方ガイド / ノードタイプ別実装例

## Done（旧実装で完了済み・再設計で再編対象）

- [x] 基本パーサー / state.py / nodes/ / graph.py 生成
- [x] NODE_CONFIG に Dify 設定を埋め込み
- [x] ruff + ty lint 対応 / Command 戻り値
- [x] LLM プロバイダー抽象化（OpenAI / Anthropic / Bedrock）
- [x] `--name-nodes`（LLM でノード名生成）※ 再設計で opt-in に再位置づけ
