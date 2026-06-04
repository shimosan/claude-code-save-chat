# claude-code-save-chat

複数端末で利用する Claude Code (CLI / VS Code 拡張 / Cursor 等) の chat 履歴サマリーを Obsidian vault のノートに保存するためのコマンド `/save-chat` を実装する。あわせて、Claude Code / Codex / Copilot 向けの agent 設定、save-chat workflow、補助スクリプトをクラウドストレージ (Dropbox / iCloud Drive / Google Drive 等) 経由で配布・共有する。Obsidian vault もクラウドストレージ経由で共有すると便利。

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
├── .claude/CLAUDE.md            ← library repo の保守ルール (Claude Code 用・この repo 編集用、配布しない)
├── AGENTS.md                    ← library repo の保守ルール (Codex 用・.claude/CLAUDE.md を参照する adapter、配布しない)
├── dotclaude/                   ← 各端末の ~/.claude/ へ deploy する Claude Code 原本
│   ├── CLAUDE.md                ← クラウド共有のルール集
│   └── CLAUDE.local.md          ← 端末固有設定のひな型
├── .gitignore                   ← git 除外パターン
├── commands/                    ← slash commands
│   └── save-chat.md             ← 会話を Obsidian vault に保存
├── dotcodex/                    ← 各端末の ~/.codex/ へ deploy する Codex 原本
│   ├── AGENTS.md                ← Codex global rules adapter
│   └── skills/save-chat/SKILL.md ← Codex 版 save-chat (参照型)
├── copilot/                     ← Copilot 版 prompt の配布用原本 (任意・VS Code + Copilot 端末のみ)
│   └── prompts/save-chat.prompt.md ← Copilot 版 save-chat (参照型)
├── scripts/                     ← 補助スクリプト集 (任意。README は目次、必要に応じて個別 md)
│   ├── README.md                ← scripts の目次
│   ├── patch-vscode-webview-ctrlf.md ← Ctrl-F 修正 patcher の詳細
│   └── patch-vscode-webview-ctrlf.js ← VS Code/Cursor webview 入力欄の Ctrl-F 修正 patcher
├── scratch/                     ← ローカル退避用 (.gitignore 対象、load/save 対象外)
├── local/                       ← 利用者ローカル領域 (.gitignore 対象)
└── notes/                       ← 開発メモ (.gitignore 対象)
```

各ツールの agent 設定は **2 層 (二枚看板)** に分かれる — 「この repo を保守する時に読ませるルール (配布しない)」と「各端末へ配る原本」。両者を混同しない:

| | repo 保守用 (配布しない) | 配布原本 (各端末へ deploy) |
|---|---|---|
| **Claude Code** | `.claude/CLAUDE.md` (subfolder ゆえ自動ロードはされない) | `dotclaude/CLAUDE.md` → `~/.claude/CLAUDE.md` |
| **Codex** | `AGENTS.md` (repo 直下ゆえ Codex が自動で読む。中身は `.claude/CLAUDE.md` を参照する adapter) | `dotcodex/AGENTS.md` → `~/.codex/AGENTS.md` |

repo 保守用の 2 ファイルは「この library を編集する agent」向け、配布原本は「配られた先の端末で動く agent」向け。同名 (`AGENTS.md` / `CLAUDE.md`) が repo 直下と `dot*/` の両方に出てくるのはこのため。

## 新端末のセットアップ

Claude Code を使う端末では Claude Code に依頼する:

> 「`<library_path>/dotclaude/CLAUDE.md` を読んでセットアップして」

`dotclaude/CLAUDE.md` 内のセットアップ手順に沿って Claude が `~/.claude/` 配下を整える。

> **既存端末の更新時**: `CLAUDE.local.md` は自由領域 (端末ローカル管理)。template の構造が変わっても、新 template に合わせる (例: 端末情報をホスト名のみにする) か、旧記述をそのまま引き継ぐかは **ユーザーが決める**。Claude は自動で上書きせず、どちらにするか確認する。

Codex を使う端末でも、save-chat の原典は Claude Code 版の設定ファイルなので、
最低限 `~/.claude/CLAUDE.local.md` を配置して `library_path` / `vault_path` 等を
記入する必要がある。Claude Code 本体を使わない端末でも、この `~/.claude/`
ファイル群は Codex / Copilot が参照する設定原典として必要。

そのうえで `dotcodex/` を `~/.codex/` へ展開する。既存の
`~/.codex/AGENTS.md` がある場合は上書きせず、`dotcodex/AGENTS.md` の
マーカー付き adapter block を diff/merge する。

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

## Codex 版 global rules / save-chat (任意)

Codex でも Claude Code 側のルールと save-chat workflow を参照できる。Codex 版は**参照型** — 実行時に Claude Code 版の原典 (`~/.claude/CLAUDE.md`, `~/.claude/CLAUDE.local.md`, `~/.claude/commands/save-chat.md`) を仕様として読むので、原典の更新に自動追従する (フォークではない)。

> **前提: `~/.claude/CLAUDE.local.md` が必須。** spec (`commands/save-chat.md`) と `CLAUDE.md` は `~/.claude/` に無ければ library 側 (それぞれ `<library_path>/commands/`、`<library_path>/dotclaude/`) へフォールバックする。ただし `CLAUDE.local.md` は端末ローカル専用で library に複製が無く (`vault_path` と `library_path` を保持)、これが無いと保存先も library の位置も解決できない。

> **Codex 単体利用時の注意:** Claude Code binary が未導入でもよいが、`~/.claude/CLAUDE.local.md` は必要。可能なら `~/.claude/CLAUDE.md` と `~/.claude/commands/save-chat.md` も通常の Claude Code セットアップと同じ形で配置する。これらが無い場合、Codex skill は `CLAUDE.local.md` の `library_path` から library 側原本へフォールバックする。

- **global rules**: `dotcodex/AGENTS.md` を `~/.codex/AGENTS.md` へ展開する。既存の `~/.codex/AGENTS.md` があれば上書きせず、マーカー付き adapter block を diff/merge する。
- **呼び出し**: save-chat は slash command ではなく skill の自然文トリガー。例: `save-chatしてください` / `/save-chat` / `save-chat <slug>`
- **frontmatter**: `source: codex` (`model` / `session_id` は安定取得できる場合のみ記録)
- **sandbox**: vault が Codex の writable root 外なら保存時に承認を求める (vault 全体を writable root にはしない。必要なら `claude{YYYY}` だけ許可する程度に留める)

### 展開 (Codex)

- 原本 (正): `<library_path>/dotcodex/`
- 展開先: `~/.codex/`

展開時は既存ファイルを一括上書きしない。特に `~/.codex/AGENTS.md` は
ユーザー固有の global rules が入っている可能性があるため、`dotcodex/AGENTS.md`
のマーカー付き managed block を diff/merge する。`~/.codex/skills/save-chat/SKILL.md`
も既存ファイルがあれば差分を確認してから反映する。

新端末セットアップ時に Claude Code 版の load と一緒に展開してもよいし、Codex 自身にこの README を読ませて展開させてもよい。ただし Codex だけを使う端末でも、上記の `~/.claude/CLAUDE.local.md` は先に用意する。Codex を使わない端末では `dotcodex/` の展開は不要。

- 編集の正は **library 側の原本**。Codex ルールや skill を直すときは `dotcodex/` を編集して各端末へ再配布する (端末側を直接いじったら原本にも反映する)。
- 展開対象は `dotcodex/AGENTS.md` と `dotcodex/skills/*/SKILL.md` のみ。`~/.codex/` 配下のその他 (auth・sessions 等の端末ローカル状態) は同期しない。
- `~/.codex/AGENTS.override.md` がある場合は `AGENTS.md` より優先される可能性があるため、展開前に確認する。

## Copilot 版 save-chat (任意)

VS Code + GitHub Copilot でも save-chat を使える。Copilot 版は**参照型** — 実行時に Claude Code 版の原典 (`~/.claude/commands/save-chat.md`) を仕様として読む (フォークではない)。

> **前提: `~/.claude/CLAUDE.local.md` が必須。** spec (`commands/save-chat.md`) と `CLAUDE.md` は `~/.claude/` に無ければ library 側 (それぞれ `<library_path>/commands/`、`<library_path>/dotclaude/`) へフォールバックする (Codex 版と同等)。ただし `CLAUDE.local.md` は端末ローカル専用で library に複製が無く (`vault_path` と `library_path` を保持)、これが無いと保存先も library の位置も解決できない。

- **呼び出し**: Copilot Chat の `/save-chat` (`/save-chat <slug>` で slug 指定)
- **frontmatter**: `source: github-copilot`

### 展開 (Copilot)

VS Code の **user prompts** ディレクトリ (エディタ共通。Copilot Chat が `/` で拾う) に prompt 1 ファイルを置く。

- 原本 (正): `<library_path>/copilot/prompts/save-chat.prompt.md`
- 展開先:
  - macOS: `~/Library/Application Support/Code/User/prompts/save-chat.prompt.md`
  - Windows: `%APPDATA%\Code\User\prompts\save-chat.prompt.md`
  - Linux: `~/.config/Code/User/prompts/save-chat.prompt.md`

```bash
# macOS の例
mkdir -p ~/"Library/Application Support/Code/User/prompts"
cp -v <library_path>/copilot/prompts/save-chat.prompt.md ~/"Library/Application Support/Code/User/prompts/save-chat.prompt.md"
```

- prompts ディレクトリは VS Code が自動生成しないので、無ければ作ってからコピーする (Windows は親があっても `prompts` 自体が無いことがある)。
- コピー後は VS Code を再読込/再起動し、Copilot Chat で `/save-chat` が見えることを確認する。
- VS Code Insiders を使う端末は `Code - Insiders` 配下 (`~/Library/Application Support/Code - Insiders/User/prompts/` 等) に合わせる。
- 編集の正は **library 側の原本**。load/save (双方向同期) とは独立した一方向配布 (原本 → 端末)。同期対象は `copilot/prompts/*.prompt.md` のみ。

## Obsidian vault 管理

Claude Code は vault 内のフォルダを 3 系統に分類して扱う:

- **AI ノートフォルダ** (`claude{YYYY}/` 等) — save-chat の保存先、Read/Write 自由
- **閲覧可能ノートフォルダ** — 過去アーカイブやユーザーが開放したノート、Read 自由・書き込み不可
- **閲覧禁止ノートフォルダ** — 個人ノート、ファイル名のみ閲覧可、本文は条件付きアクセス

各端末の vault パスとフォルダ命名は `CLAUDE.local.md` で定義。アクセスルールは [`dotclaude/CLAUDE.md`](dotclaude/CLAUDE.md) を参照。

## 運用

基本的に library 側 (`dotclaude/`, `commands/`, `dotcodex/`, `copilot/`) を編集の正とし、
各端末の `$HOME` 配下や editor user prompts へ展開する。端末側で直接編集した場合は、
差分を確認して library 側へ戻す。

Claude Code の `~/.claude/` との `load` / `save` 手順の詳細は
[`dotclaude/CLAUDE.md`](dotclaude/CLAUDE.md) を参照。

## 補助スクリプト — `scripts/`

`scripts/` は `/save-chat` 本体とは独立した補助ツール置き場。Claude Code / Codex / VS Code / Cursor 周辺で見つかった再利用可能な修正・診断スクリプトをここに置く。[`scripts/README.md`](scripts/README.md) は目次とし、軽いスクリプトは 1-2 行の説明だけでよい。使い方・注意点・復旧手順が必要なものは、スクリプト専用の `.md` に詳しく書く。

現在の主なスクリプト:

- [`patch-vscode-webview-ctrlf.js`](scripts/patch-vscode-webview-ctrlf.js): Claude Code / Codex の VS Code/Cursor webview 入力欄で macOS `Control-F` が forward-character として動かない問題を、ローカル拡張 webview への小さな patch で補正する。`--status` / `--dry-run` / `--restore` 対応。詳細は [`scripts/patch-vscode-webview-ctrlf.md`](scripts/patch-vscode-webview-ctrlf.md)。

`scripts/` の内容は任意利用。新端末セットアップに必須ではなく、必要な端末で必要なものだけ実行する。

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
