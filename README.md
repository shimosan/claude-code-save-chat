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
├── scratch/                     ← ローカル退避用 (.gitignore 対象、load/save 対象外)
├── local/                       ← 利用者ローカル領域 (.gitignore 対象)
└── notes/                       ← 開発メモ (.gitignore 対象)
```

## 新端末のセットアップ

Claude Code に依頼する:

> 「`<library_path>/CLAUDE.md` を読んでセットアップして」

CLAUDE.md 内のセットアップ手順に沿って Claude が `~/.claude/` 配下を整える。

> **既存端末の更新時**: `CLAUDE.local.md` は自由領域 (端末ローカル管理)。template の構造が変わっても、新 template に合わせる (例: 端末情報をホスト名のみにする) か、旧記述をそのまま引き継ぐかは **ユーザーが決める**。Claude は自動で上書きせず、どちらにするか確認する。

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

## ローカル領域 — `local/` · `notes/`

`.gitignore` 対象のフォルダで、**git 管理外＝バージョン管理されない利用者ローカル領域**。commit も push もされず、`git pull` でライブラリを更新しても**上書きされない**。各自のローカルな内容を安心して置ける (remote が public でも露出しない)。

- `local/` : 端末固有・個人的な設定や事実 (例: マシン台帳)。git に入れたくないがすぐ参照したいもの。
- `notes/` : 長期保存の開発メモ・気付き (日付付き md, `YYYY-MM-DD_topic.md` 推奨)。

> **クラウド同期との合わせ技**: 本 library 全体をクラウド同期フォルダ (Dropbox 等) に置いている場合、これらの gitignore 対象フォルダも git / GitHub を経由せず端末間で自動同期される。マシン台帳を全端末で共有する、といった用途に使える。

### `local/machines.md` のフォーマット例

複数端末を使うなら端末一覧をここに置くと便利 (gitignore 対象なので各自が空から作る)。**フォーマットは好みでよい**。例えば 1 端末 1 行、5 フィールド:

```
`<hostname>` (<機種>, <プロセッサ>, <コア数>, <メモリ>, <OS>)
```

- **hostname**: ユーザーが選ぶ呼称ラベル。OS のホスト名 (`foo.local` の `.local` 等) そのままでなくてよい。`CLAUDE.local.md` のホスト名も同じ
- **プロセッサ**: Apple Silicon は CPU+GPU 一体なので 1 トークン (`M4 Max`)。ディスクリート GPU 機は `CPU / GPU` (`Ryzen 9 7950X / RTX 4090`)
- **OS**: `mac` / `win` / `linux` (Mac/Windows/Linux の判別用、末尾固定)

例:
- `host-a` (MacBook Pro, M4 Max, 16-core, 64GB, mac)
- `host-b` (Mac Studio, M1 Ultra, 20-core, 128GB, mac)
- `host-c` (Surface Laptop, Core Ultra 7, 16-core, 32GB, win)
- `host-d` (自作, Ryzen 9 7950X / RTX 4090, 16-core, 128GB, linux)

1 行でも例が入っていれば、以降の端末追加は Claude が同じ形式で書く。

## OS 固有の注意

load/save やパス操作は POSIX (macOS / Linux) 前提。Mac・Linux は基本そのまま動き、差異が出るのは主に Windows。OS 固有の対処はここに集約する。

### Windows

- **load/save は Bash ツールで実行**: `cp -v` / `diff` を PowerShell でなく Bash ツールで実行すれば Mac と同じコマンドが使える (PowerShell の `diff` は `Compare-Object` のエイリアスで出力が別物)。
- **パスは POSIX 変換**: `D:\Dropbox\library\claude` → `/d/Dropbox/library/claude` に変換して Bash に渡す。`CLAUDE.local.md` のパス定義は Windows 表記 (`D:\...`) のまま書き、使用時に変換する。
- **端末固有メモは FREEZONE へ**: POSIX パス変換・`hostname` の挙動・projects パスエンコード等の Windows 専用補足は `CLAUDE.local.md` の FREEZONE 以下に置く (構造化セクションは template 準拠のまま保つ)。
- **GPU スペック取得**: `Get-WmiObject Win32_VideoController` 等で取得。machines.md の `プロセッサ` 欄にはディスクリート GPU を採用 (統合 GPU は除外)。

## 注意

- 本 library に**個人 secrets を置かない** (`.env`, API キー等は別の場所へ)
- `CLAUDE.local.md` は端末ローカル管理 — クラウド共有しない

## License

MIT — see [LICENSE](LICENSE).
