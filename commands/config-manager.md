---
description: config snapshot/update ワークフローでこの端末のローカル設定を review・比較・安全に apply する。
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
---

# /config-manager — 端末設定の review / 比較 / 安全な apply

このライブラリの config snapshot/update ワークフローへ委譲する thin な Claude Code エントリポイント。
端末間の config drift 確認、マシン比較、最近の設定変更の review、他端末からの設定取り込み、設定のロールバック、config policy/recipe の管理に使う。

## Source Of Truth

review / apply / config-policy のあらゆるタスクで、以下を読んで従う:

1. `<library_path>/scripts/config-update.md`
2. そのワークフローが指示した時だけ: `<library_path>/scripts/config-apply-recipes.md`

policy・private recipe・apply rule をこのコマンドに複製しない。

## `<library_path>` の解決

`scripts/config-update.md` を含むなら現在の workspace を使う。

無ければ `~/.claude/CLAUDE.md` 島内「ホスト情報」の `library_path` から読む(未移行端末では旧 `~/.claude/CLAUDE.local.md` から)。どちらも `library_path` を定義していなければユーザーに尋ねる。パスを捏造しない。

## 起動トリガ

次のような要求で起動する:

- `/config-manager`
- `設定の差分を見て`
- `最近の config 変更を見せて`
- `<machine> の設定をこの端末に取り込みたい`
- `この設定を前の状態に戻して`
- `config policy に記録して`

## 振る舞い

- review / apply / config-policy 作業では、まず `scripts/config-update.md` を読んで従う。
- 純粋な overview 要求なら `scripts/config-log-helper.py timeline` / `drift` / `nway` を直接実行してよい。解釈・提案・policy 更新・apply が要るなら `scripts/config-update.md` に戻る。
- `local/config-policy.md` と `local/config-local-recipes.md` は `scripts/config-update.md` が管理する private ファイルとして扱う。当該ワークフローが要求し、かつユーザーが具体的変更を明示承認した時以外は編集しない。
- 具体的変更の明示承認前に、live な VS Code / Cursor / shell / Git / 拡張 / skill / prompt その他の設定を編集しない。
- apply / rollback / live config 変更は `scripts/config-update.md` の `apply` mode 手順に従い、old/new 値と対象を示してからユーザーの明示承認を得る。
- snapshot helper は、ツールが対応するなら non-login shell 実行を優先する。

## 報告

ユーザー向け応答は簡潔に:

- active mode(`review-only` か `apply`)を述べる
- 参照した snapshot/log を要約する
- apply 前に old/new 値と対象を示す
- apply 後は backup・verification snapshot・apply log・reload/restart 要否を報告する
