---
description: 現在の会話を Obsidian vault (claudeYYYY/) に markdown で保存する。既存ファイルがあれば改訂モード。
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
---

# /save-chat — 会話を Obsidian に保存 (Claude Code 皮)

library の save-chat core (共通仕様) へ委譲する thin な Claude Code エントリポイント。
仕様 (フォーマット・判定規則) をこのファイルに複製しない。

## Source Of Truth

save-chat のあらゆるタスクで、以下を読んで従う:

1. `<library_path>/scripts/save-chat-core.md` — save-chat の共通仕様 (workflow authority)
2. `~/.claude/CLAUDE.md` — 「ホスト情報」セクション (`vault_path` / `library_path` /
   `ai_note_folder` / `public_note_folders` / `private_note_folders`) と「Obsidian vault 管理」
   (vault アクセス・wikilink・プライバシー規則)

## `<library_path>` の解決

`scripts/save-chat-core.md` を含むなら現在の workspace を使う。

無ければ `~/.claude/CLAUDE.md` の「ホスト情報」セクションの `library_path` から読む
(未移行端末では旧 `~/.claude/CLAUDE.local.md` から)。どちらも定義していなければユーザーに
尋ねる。パスを捏造しない。

core が読めない場合は、勝手な fallback 保存をせず、中断してユーザーに報告する。

## 引数

- `/save-chat`: 会話の主題から自動で slug を決定
- `/save-chat <slug>`: 指定した slug を使用

slug の扱い・実行手順・ノート構造・テンプレート・改訂規則はすべて core に従う。

## Claude Code binding (core の platform binding 規約に対応)

- `source`: `claude-code`
- `model`: 現セッションのモデル ID (例: `claude-fable-5`)。reasoning effort 相当が同時に
  分かる場合のみ `model: <ID> (<effort>)` 形式で付記 (現状の Claude Code は通常 ID のみ)。
  不明なら省略
- `session_id`: 初版時の JSONL UUID。cwd の encoded path から
  `~/.claude/projects/<encoded>/` 内の最新 mtime の `.jsonl` から取得。不明なら省略
  (この取得法は Claude Code 専用 — 他 platform は流用しない)
- `workspace`: 初版時の cwd (絶対パス)
- `machine`: 初版時の hostname (短縮形、`hostname -s` の出力)

## tool 流儀

- タグ語彙抽出: `Grep` tool (`output_mode: "content"`) で `tags:` 行と直後のタグリスト行を
  抽出する。Bash + `rg` には降りない
- related-note search・既存ファイル探索: `Glob` / `Grep` tool を使う
- ノートの書き出し・上書き: `Write` tool

## 補足

- このコマンドは user global command としてどのワークスペースからでも起動できる
- 保存先・報告形式は core の規定に従う
