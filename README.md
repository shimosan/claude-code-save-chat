# claude-code-save-chat

Claude Code / Codex / Copilot の会話保存と複数端末 config 管理を、Obsidian とクラウド同期フォルダに寄せて運用するための個人用ライブラリ。

複数端末で利用する Claude Code (CLI / VS Code 拡張 / Cursor 等) の chat 履歴サマリーを Obsidian vault のノートに保存するためのコマンド `/save-chat` と、端末設定の snapshot / drift 確認 / 安全な apply review を行う `/config-manager` を実装する。あわせて、Claude Code / Codex / Copilot 向けの agent 設定、save-chat / config-manager workflow、補助スクリプトをクラウドストレージ (Dropbox / iCloud Drive / Google Drive 等) 経由で配布・共有する。Obsidian vault もクラウドストレージ経由で共有すると便利。

## 免責

このライブラリは個人用の設定・運用補助を公開しているもので、無保証で提供される。内容には未確認・実験的な前提を含む場合があり、作者は利用に伴う設定変更、データ損失、環境不整合、その他の損害について責任を負わない。各コマンドやスクリプトは、内容と影響範囲を確認したうえで自己責任で実行する。

This library publishes personal configuration and operations helpers as-is, without warranty. It may include unverified or experimental assumptions. The author assumes no responsibility for configuration changes, data loss, environment inconsistencies, or any other damage caused by use of this library. Review each command or script and its impact before running it, and use it at your own risk.

## 配置場所

このフォルダはクラウド同期される場所であればどこに置いてもよく、フォルダ名も自由。`git clone` すると既定で repo 名の `claude-code-save-chat/` になるが、好きにリネームしてよい。各端末では、このフォルダの実パスを `library_path` として `~/.claude/CLAUDE.md` の「ホスト情報」セクションに記録する。

例:
- `~/Dropbox/library/claude-code-save-chat/`  (clone 既定)
- `~/iCloud/claude-code-save-chat/`
- `~/GoogleDrive/agent-config/`  (任意にリネーム)
- `~/Dropbox/library/claude/`  (作者の実運用例: `claude` にリネーム)

## 構成

```
<library_path>/
├── README.md                    ← このファイル
├── .claude/CLAUDE.md            ← library repo の保守ルール (Claude Code 用・この repo 編集用、配布しない)
├── AGENTS.md                    ← library repo の保守ルール (Codex 用・.claude/CLAUDE.md を参照する adapter、配布しない)
├── dotclaude/                   ← 各端末の ~/.claude/ へ deploy する Claude Code 原本
│   └── CLAUDE.md                ← 共有ルール + 端末設定 + メモリを統合した管理ブロック構造 (1 ファイル)
├── .gitignore                   ← git 除外パターン
├── commands/                    ← slash commands
│   ├── save-chat.md             ← 会話を Obsidian vault に保存
│   └── config-manager.md        ← config snapshot/update workflow への薄い入口
├── dotcodex/                    ← 各端末の ~/.codex/ へ deploy する Codex 原本
│   ├── AGENTS.md                ← Codex global rules adapter
│   ├── skills/save-chat/SKILL.md ← Codex 版 save-chat (参照型)
│   └── skills/config-manager/SKILL.md ← Codex 版 config-manager (薄い入口)
├── copilot/                     ← Copilot 版 prompt の配布用原本 (任意・VS Code + Copilot 端末のみ)
│   └── prompts/save-chat.prompt.md ← Copilot 版 save-chat (参照型)
├── scripts/                     ← 補助スクリプト集 (任意。README は目次、必要に応じて個別 md)
│   ├── README.md                ← scripts の目次
│   ├── patch-vscode-webview-ctrlf.md ← Ctrl-F 修正 patcher の詳細
│   └── patch-vscode-webview-ctrlf.js ← VS Code/Cursor webview 入力欄の Ctrl-F 修正 patcher
├── scratch/                     ← ローカル退避用 (.gitignore 対象、配布対象外)
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

> **既存端末の更新時**: load は `CLAUDE.md` の管理ブロック内にある共有ルール (S) だけを更新し、「ホスト情報」セクション (端末設定 L) と管理ブロック外のメモリ領域 (M) は触らない。S の構造が変わっても L/M は既存値を保持する。Claude は自動で上書きせず、merge 方針をユーザーに確認する。

Codex を使う端末でも、save-chat の原典は Claude Code 版の設定ファイルなので、
最低限 `~/.claude/CLAUDE.md`(「ホスト情報」セクションに `library_path` / `vault_path` 等を
記入)を配置する必要がある。Claude Code 本体を使わない端末でも、この `~/.claude/`
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
save-chatしてください        ← Codex 版 skill の自然文トリガー
```

詳細仕様は [`commands/save-chat.md`](commands/save-chat.md) を参照。

## `/config-manager` — 端末設定の review / 比較 / 安全な apply

config snapshot/update workflow への薄い入口 (thin command)。設定の drift 確認、マシン間比較、最近の変更 review、他端末からの設定取り込み、ロールバック、config policy/recipe 管理に使う。実体のワークフローは持たず [`scripts/config-update.md`](scripts/config-update.md) に委譲する。

```
/config-manager                         ← Claude Code 版 slash command
config-managerで最近の設定差分を見て   ← overview / review
config-managerで timeline の生出力を見せて ← helper 出力をそのまま表示
<machine> の設定をこの端末に取り込みたい ← apply 候補を review、明示承認後に反映
```

config-manager は save-chat と同じく **複数エージェントに二枚看板で配る**。両エージェントを使う端末では両方を展開する (save-chat と違い Copilot 版は無い):

| | 配布原本 (正) | 展開先 |
|---|---|---|
| **Claude Code 版** | [`commands/config-manager.md`](commands/config-manager.md) | `~/.claude/commands/config-manager.md` |
| **Codex 版** | [`dotcodex/skills/config-manager/SKILL.md`](dotcodex/skills/config-manager/SKILL.md) | `~/.codex/skills/config-manager/SKILL.md` |

どちらも薄い入口で、実体の workflow・apply recipe・local policy の扱いは [`scripts/config-update.md`](scripts/config-update.md) が持つ。設定変更・ロールバック等の apply は `scripts/config-update.md` の apply mode の承認手順に従い、具体的変更への明示承認なしに live config を触らない。人間向けの詳しい入口仕様と例は [`commands/config-manager.md`](commands/config-manager.md) を参照。Claude Code 版の展開は `commands/` の他コマンドと同じ load 手順、Codex 版は下記「展開 (Codex)」に従う。

### config-manager の設計思想

config-manager は「snapshot に出た値を機械的に全適用する同期ツール」ではない。snapshot は端末の live 状態をできるだけ網羅的に観測するための材料であり、apply は agent が review-only で差分・意図・危険度を整理し、ユーザーが承認した具体的変更だけを現在端末へ反映する。

config-manager は `local/` に固定の目標値を維持しない。取り込み元は snapshot、ユーザーが明示した値、private policy、または承認済み recipe の入力として都度選ぶ。`local/` は machine inventory / private policy / private recipes などの軽いローカル知識置き場であり、live 設定が `local/` 内の任意ファイルと違うだけでは drift や apply 対象とは扱わない。

apply recipe は、よく使う安全な操作の型を固定するためのもの。snapshot には editor settings のように低リスクで宣言的に再現できる値もあれば、`brew` / `pyenv` / fonts / model list のように provisioning 計画が必要な値、`claude.md` の host-info のように端末固有でコピーしてはいけない値、version/path のような診断値も混在する。したがって、recipe が無い source は即エラーではなく、まず review-only で `low` / `medium` / `high` / `system` / `local-sensitive` / `diagnostic` の性質を分類し、target・old/new・backup・rollback・verification を明示してから承認を求める。反復する ad-hoc 操作だけを public recipe または `local/config-local-recipes.md` へ昇格する。

実装済み recipe には [`scripts/config-apply-recipes.md`](scripts/config-apply-recipes.md) で `risk class` を明示する。未カバー source の一般ルールも同ファイルに置き、流動的な拡張・ツール・環境差を全列挙しない方針にしている。

## Codex 版 global rules / skills (任意)

Codex でも Claude Code 側のルール、save-chat workflow、config 管理 workflow を参照できる。Codex 版 skill は原則**参照型** — 実行時に library 側または Claude Code 版の原典を仕様として読むので、原典の更新に追従しやすい (フォークではない)。

> **前提: `~/.claude/CLAUDE.md` が必須。** spec (`commands/save-chat.md`) は `~/.claude/` に無ければ library 側 (`<library_path>/commands/`) へフォールバックする。ただし `CLAUDE.md` の「ホスト情報」セクション (`vault_path` / `library_path` 等) は端末ローカルで library に複製が無く、これが無いと保存先も library の位置も解決できない。(移行前の端末で旧 `~/.claude/CLAUDE.local.md` が残っていれば、そこからの解決もフォールバックとして可。)

> **Codex 単体利用時の注意:** Claude Code binary が未導入でもよいが、`~/.claude/CLAUDE.md`(「ホスト情報」セクション記入済み)は必要。可能なら `~/.claude/commands/save-chat.md` も通常の Claude Code セットアップと同じ形で配置する。これが無い場合、Codex skill は `CLAUDE.md` の `library_path` から library 側原本へフォールバックする。

- **global rules**: `dotcodex/AGENTS.md` を `~/.codex/AGENTS.md` へ展開する。既存の `~/.codex/AGENTS.md` があれば上書きせず、マーカー付き adapter block を diff/merge する。
- **save-chat 呼び出し**: slash command ではなく skill の自然文トリガー。例: `save-chatしてください` / `/save-chat` / `save-chat <slug>`
- **config-manager 呼び出し**: config snapshot / drift / apply review 用の薄い入口。例: `config-managerで最近の設定差分を見て` / `<machine> の設定をこの端末に取り込みたい`
- **frontmatter**: `source: codex` (`model` / `session_id` は安定取得できる場合のみ記録)
- **sandbox**: vault が Codex の writable root 外なら保存時に承認を求める (vault 全体を writable root にはしない。必要なら `claude{YYYY}` だけ許可する程度に留める)

### 展開 (Codex)

- 原本 (正): `<library_path>/dotcodex/`
- 展開先: `~/.codex/`

展開時は既存ファイルを一括上書きしない。特に `~/.codex/AGENTS.md` は
ユーザー固有の global rules が入っている可能性があるため、`dotcodex/AGENTS.md`
のマーカー付き managed block を diff/merge する。`~/.codex/skills/save-chat/SKILL.md`
も既存ファイルがあれば差分を確認してから反映する。

新端末セットアップ時に Claude Code 版の load と一緒に展開してもよいし、Codex 自身にこの README を読ませて展開させてもよい。ただし Codex だけを使う端末でも、上記の `~/.claude/CLAUDE.md`(「ホスト情報」セクション記入済み)は先に用意する。Codex を使わない端末では `dotcodex/` の展開は不要。

- 編集の正は **library 側の原本**。Codex ルールや skill を直すときは `dotcodex/` を編集して各端末へ再配布する (端末側を直接いじったら原本にも反映する)。
- 展開対象は `dotcodex/AGENTS.md` と `dotcodex/skills/*/SKILL.md` のみ。`~/.codex/` 配下のその他 (auth・sessions 等の端末ローカル状態) は同期しない。
- `~/.codex/AGENTS.override.md` がある場合は `AGENTS.md` より優先される可能性があるため、展開前に確認する。

## Copilot 版 save-chat (任意)

VS Code + GitHub Copilot でも save-chat を使える。Copilot 版は**参照型** — 実行時に Claude Code 版の原典 (`~/.claude/commands/save-chat.md`) を仕様として読む (フォークではない)。

> **前提: `~/.claude/CLAUDE.md` が必須。** spec (`commands/save-chat.md`) は `~/.claude/` に無ければ library 側 (`<library_path>/commands/`) へフォールバックする (Codex 版と同等)。ただし `CLAUDE.md` の「ホスト情報」セクション (`vault_path` / `library_path` 等) は端末ローカルで library に複製が無く、これが無いと保存先も library の位置も解決できない。(移行前の端末で旧 `~/.claude/CLAUDE.local.md` が残っていれば、そこからの解決もフォールバックとして可。)

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
- 編集の正は **library 側の原本**。Claude Code の load (配布) とは独立した一方向配布 (原本 → 端末)。同期対象は `copilot/prompts/*.prompt.md` のみ。

## Obsidian vault 管理

Claude Code は vault 内のフォルダを 3 系統に分類して扱う:

- **AI ノートフォルダ** (`claude{YYYY}/` 等) — save-chat の保存先、Read/Write 自由
- **閲覧可能ノートフォルダ** — 過去アーカイブやユーザーが開放したノート、Read 自由・書き込み不可
- **閲覧禁止ノートフォルダ** — 個人ノート、ファイル名のみ閲覧可、本文は条件付きアクセス

各端末の vault パスとフォルダ命名は `~/.claude/CLAUDE.md` の「ホスト情報」セクションで定義。アクセスルールは [`dotclaude/CLAUDE.md`](dotclaude/CLAUDE.md) を参照。

## 運用

基本的に library 側 (`dotclaude/`, `commands/`, `dotcodex/`, `copilot/`) を編集の正とし、
各端末の `$HOME` 配下や editor user prompts へ展開する。端末側で直接編集した場合は、
差分を確認して library 側へ戻す。

Claude Code の `~/.claude/` への `load`(配布)手順の詳細は
[`dotclaude/CLAUDE.md`](dotclaude/CLAUDE.md) を参照(`save` は廃止)。

## 補助スクリプト — `scripts/`

`scripts/` は `/save-chat` 本体とは独立した補助ツール置き場。Claude Code / Codex / VS Code / Cursor 周辺で見つかった再利用可能な修正・診断スクリプトをここに置く。[`scripts/README.md`](scripts/README.md) は目次とし、軽いスクリプトは 1-2 行の説明だけでよい。使い方・注意点・復旧手順が必要なものは、スクリプト専用の `.md` に詳しく書く。

主な分類:

- Config workflow and helpers: config snapshot / compare / apply protocol と、JSONC・log 操作用の helper。詳細は [`scripts/README.md`](scripts/README.md) と [`scripts/config-update.md`](scripts/config-update.md)。
- Patch and recovery utilities: VS Code / Cursor / Codex 周辺の optional local patch・復旧 script。詳細は [`scripts/README.md`](scripts/README.md) と [`scripts/config-apply-patches.md`](scripts/config-apply-patches.md)。

`scripts/` の内容は任意利用。新端末セットアップに必須ではなく、必要な端末で必要なものだけ実行する。

## ローカル領域 — `local/` · `notes/`

`.gitignore` 対象のフォルダで、**git 管理外＝バージョン管理されない利用者ローカル領域**。commit も push もされず、`git pull` でライブラリを更新しても**上書きされない**。各自のローカルな内容を安心して置ける (remote が public でも露出しない)。

- `local/` : 端末固有・個人的な設定や事実 (例: マシン台帳)。git に入れたくないがすぐ参照したいもの。
- `notes/` : 長期保存の開発メモ・気付き (日付付き md, `YYYY-MM-DD_topic.md` 推奨)。

`local/` は config-manager の固定 target state 置き場ではない。過去に置いていた editor 設定テンプレートは `scratch/` へ退避済みで、必要時に明示承認された source artifact としてだけ参照する。

> **クラウド同期との合わせ技**: 本 library 全体をクラウド同期フォルダ (Dropbox 等) に置いている場合、これらの gitignore 対象フォルダも git / GitHub を経由せず端末間で自動同期される。マシン台帳を全端末で共有する、といった用途に使える。

### `local/machines.md` のフォーマット例

複数端末を使うなら端末一覧をここに置くと便利 (gitignore 対象なので各自が空から作る)。**フォーマットは好みでよい**。例えば 1 端末 1 行、5 フィールド:

```
`<hostname>` (<機種>, <プロセッサ>, <コア数>, <メモリ>, <OS>)
```

- **hostname**: ユーザーが選ぶ呼称ラベル。OS のホスト名 (`foo.local` の `.local` 等) そのままでなくてよい。`CLAUDE.md` の「ホスト情報」セクションのホスト名も同じ
- **プロセッサ**: Apple Silicon は CPU+GPU 一体なので 1 トークン (`M4 Max`)。ディスクリート GPU 機は `CPU / GPU` (`Ryzen 9 7950X / RTX 4090`)
- **OS**: `mac` / `win` / `linux` (Mac/Windows/Linux の判別用、末尾固定)

例:
- `host-a` (MacBook Pro, M4 Max, 16-core, 64GB, mac)
- `host-b` (Mac Studio, M1 Ultra, 20-core, 128GB, mac)
- `host-c` (Surface Laptop, Core Ultra 7, 16-core, 32GB, win)
- `host-d` (自作, Ryzen 9 7950X / RTX 4090, 16-core, 128GB, linux)

1 行でも例が入っていれば、以降の端末追加は Claude が同じ形式で書く。

## OS 固有の注意

load (配布) やパス操作は POSIX (macOS / Linux) 前提。Mac・Linux は基本そのまま動き、差異が出るのは主に Windows。OS 固有の対処はここに集約する。

### Windows

- **load は Bash ツールで実行**: `cp -v` / `diff` を PowerShell でなく Bash ツールで実行すれば Mac と同じコマンドが使える (PowerShell の `diff` は `Compare-Object` のエイリアスで出力が別物)。
- **パスは POSIX 変換**: `D:\Dropbox\library\claude` → `/d/Dropbox/library/claude` に変換して Bash に渡す。`CLAUDE.md` の「ホスト情報」セクションのパス定義は Windows 表記 (`D:\...`) のまま書き、使用時に変換する。
- **端末固有メモはメモリ領域へ**: POSIX パス変換・`hostname` の挙動・projects パスエンコード等の Windows 専用補足は `CLAUDE.md` の管理ブロック外にあるメモリ領域 (M) に置く (管理ブロック内の共有ルール S は master 準拠のまま保つ)。
- **GPU スペック取得**: `Get-WmiObject Win32_VideoController` 等で取得。machines.md の `プロセッサ` 欄にはディスクリート GPU を採用 (統合 GPU は除外)。

## 注意

- 本 library に**個人 secrets を置かない** (`.env`, API キー等は別の場所へ)
- `CLAUDE.md` の「ホスト情報」セクションとメモリ領域は端末ローカル — load で配布・上書きしない

## License

MIT — see [LICENSE](LICENSE).
