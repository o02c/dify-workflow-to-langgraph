# Dify DSL to LangGraph Converter

**Dify で作ったワークフローを、Dify なしで動く Python のプログラムに変換するツールです。**

Dify の画面から書き出したファイル（`.yml`）を渡すと、同じ流れをたどる Python の
プログラム一式が出てきます。社内のサーバーに組み込む、処理を自分で書き換える、
といった使い方ができます。

> **使い方はすべて [USAGE.md](USAGE.md)（利用ガイド）に書いてあります。**
> あの 1 ファイルだけで使い始められるようにしてあるので、まずそちらを読んでください。

## できること・できないこと

自動で作られるのは**処理の骨組み**です。処理の順序・条件分岐・値の受け渡しの形・
ワークフローの入力の受け取り・終了ノードの値の受け渡し・知識取得（RAG）は、
そのまま動く形で出力されます。

一方 **LLM ノードやコードノードなど、個々のノードの処理そのものは空のまま**で、
`# TODO` のしるしが付いて出てきます。そこを埋めるのは利用者の作業です。
空のままでもプログラムは最後まで動くので、先に全体の流れを確認できます。

空の部分を AI に下書きさせる機能もありますが、任意です。**使わなければ変換は
インターネットに一切つながりません。**

## 最短の試し方

```bash
# インストール（同梱の pyproject.toml を使います）
pip install .

# 変換（AI もインターネットも使いません）
dify2langgraph workflow.yml -o output/ --skip-implement

# 動かす（できたフォルダの 1 つ上から）
cd output && python -m workflow
```

Python を用意せずに変換したい場合は、同梱の `Dockerfile` からビルドして使う方法も
あります（macOS / Linux で動作確認済み。Windows は未確認です）。

```bash
docker build -t dify2langgraph . && docker run --rm \
  --mount type=bind,source="$PWD",target=/work \
  dify2langgraph workflow.yml -o outputs --skip-implement
```

> **Windows でも動きます。** PowerShell と Git Bash の両方で実機確認済みです。
> 文字化けを防ぐ設定など、Windows 特有の注意は
> [USAGE.md「9. Windows で使う場合」](USAGE.md#9-windows-で使う場合) にあります。

## ライセンス

MIT License

---
