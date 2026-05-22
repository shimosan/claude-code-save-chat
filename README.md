# claude-code-save-chat

複数端末で利用する Claude Code (CLI / VS Code 拡張 / Cursor 等) の chat 履歴サマリーを Obsidian vault のノートに保存するためのコマンド `/save-chat` を実装する。あわせて、Claude Code の設定ファイルをクラウドストレージ (Dropbox / iCloud Drive / Google Drive 等) 経由で複数端末間で共有する。Obsidian vault もクラウドストレージ経由で共有すると便利。

## 配置場所

このフォルダはクラウド同期される場所であればどこに置いてもよい。

例:
- `~/Dropbox/library/claude/`
- `~/iCloud/claude-library/`
- `~/GoogleDrive/claude/`

## 構成

```
<library_path>/
├── README.md                    ← このファイル
├── CLAUDE.md                    ← クラウド共有のルール集
├── CLAUDE.local.md.template     ← 端末固有設定のひな型
├── .gitignore                   ← git 除外パターン
├── commands/                    ← slash commands
│   └── save-chat.md             ← 会話を Obsidian vault に保存
└── scratch/                     ← ローカル退避用 (.gitignore 対象、load/save 対象外)
```

## 新端末のセットアップ

Claude Code に依頼する:

> 「`<library_path>/CLAUDE.md` を読んでセットアップして」

CLAUDE.md 内のセットアップ手順に沿って Claude が `~/.claude/` 配下を整える。

## `/save-chat` — 会話を Obsidian vault に保存

現在の会話を markdown ノートとして Obsidian vault に書き出す slash command。

- **保存先**: vault 内の **AI ノートフォルダ** (`claude{YYYY}/` 等)
- **構造**: frontmatter (tags / model / machine / session_id 等) + 本体 + 改訂履歴
- **改訂モード**: 同 slug 既存ファイルがあれば上書き + 改訂履歴に追記
- **テンプレート**: default / qa / worklog / troubleshoot / decision から会話の性質に応じて選択

```
/save-chat                  ← slug 自動生成
/save-chat my-topic-slug    ← slug 指定
```

詳細仕様は [`commands/save-chat.md`](commands/save-chat.md) を参照。

## Obsidian vault 管理

Claude Code は vault 内のフォルダを 3 系統に分類して扱う:

- **AI ノートフォルダ** (`claude{YYYY}/` 等) — save-chat の保存先、Read/Write 自由
- **閲覧可能ノートフォルダ** — 過去アーカイブやユーザーが開放したノート、Read 自由・書き込み不可
- **閲覧禁止ノートフォルダ** — 個人ノート、ファイル名のみ閲覧可、本文は条件付きアクセス

各端末の vault パスとフォルダ命名は `CLAUDE.local.md` で定義。アクセスルールは [`CLAUDE.md`](CLAUDE.md) を参照。

## 運用

ローカル (`~/.claude/`) と本 library の間で `load` / `save` で同期する。
詳細は [`CLAUDE.md`](CLAUDE.md) を参照。

## 注意

- 本 library に**個人 secrets を置かない** (`.env`, API キー等は別の場所へ)
- `CLAUDE.local.md` は端末ローカル管理 — クラウド共有しない
