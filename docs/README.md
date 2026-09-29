# 開発者向けドキュメント索引

このディレクトリと関連ファイルは**リポジトリ内部のみ**で、配布物には含まれません。
配布するのはソースコード（ビルド資材・スクリプト・テスト資材を含む）と
`README.md` / `USAGE.md` だけなので、**配布されるファイルからここへの参照は
置かないでください**（参照が残っていないことは
`tests/test_translator.py::TestNoPointersOutsideTheDistribution` が検査します）。

- [OVERVIEW.md](OVERVIEW.md) — トップダウンの全体像（図解つき）
- [../CONTEXT.md](../CONTEXT.md) — 用語集（正準）
- [adr/](adr/) — 設計判断の記録（ADR）
- [tech-stack.md](tech-stack.md) — 技術スタック（レイヤー別に何をなぜ使うか）
- [architecture.md](architecture.md) / [development.md](development.md) / [STYLE_GUIDE.md](STYLE_GUIDE.md)
- [../TODO.md](../TODO.md) — ロードマップ

利用者向けの説明は `USAGE.md` に単体で完結する形でまとめてあります。
