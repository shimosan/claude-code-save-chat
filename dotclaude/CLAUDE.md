<!-- claude-library:begin — 共有ルール + 端末設定の「ライブラリ島」。load/merge はこの島だけを更新する。
     島より上 (ユーザー自由エリア) と下 (メモリ領域) には触れない。 -->
# Claude Code User Memory

## ファイル構成

ローカルの `~/.claude/` ディレクトリには以下が存在する:

- `CLAUDE.md` : クラウド共有ルール + 端末固有設定 + メモリを 1 ファイルに統合。下記の 3 ゾーンで管理する。
- `commands/` : Claude が管理するコマンド定義ファイル群。

## CLAUDE.md の 3 ゾーン

`CLAUDE.md` は `<!-- claude-library:begin … -->` 〜 `<!-- claude-library:end … -->` の
「ライブラリ島」を中心に、上から 3 ゾーンで構成する:

1. **ユーザー自由エリア** — ファイル冒頭 〜 `<!-- claude-library:begin … -->` の直前。
   ユーザーが自由に書ける領域 (空でも可)。**load 不可侵**。
2. **ライブラリ島 (S + L)** — `<!-- claude-library:begin … -->` 〜 `<!-- claude-library:end … -->`。
   - **共有ルール (S)**: 構造化された配布ルール。**load が master で更新する**。人間管理。
   - **端末設定 (L)**: ホスト情報・パス・vault 設定 (島内の `## ホスト情報` 以降)。
     値は端末ローカル。merge 時は agent が既存値を読み取り保持/再適用する (現行と同じ動作)。
3. **メモリ領域 (M)** — `<!-- claude-library:end … -->` 〜 ファイル末尾 (EOF)。
   `#`・`/memory`・Claude の追記先。端末ローカル。**load 不可侵**。見出しレベルは不定でよい
   (ゾーンは `claude-library:end` で画定、追記は常に末尾＝M に落ちる)。
   将来 harvest が抽出して `local/memory/claude_<host>.md` へ退避 (別途・未実装)。

## User Memory のクラウド共有

複数端末間で Claude Code 環境を Dropbox 等のクラウド経由で共有・配布する仕組み。

### 共有フォルダ

配布元 (マスター) はクラウド上の共有フォルダ (library) の `dotclaude/CLAUDE.md`。
library のパスは `library_path` とし、島内の「ホスト情報」(L) で定義する。

**配布対象は `CLAUDE.md` のライブラリ島 (S) と `commands/*.md` のみ**。library 内のその他は配布の往復対象外:

- `.claude/CLAUDE.md`: library repo の保守ルール (この repo を編集する時の project memory。各端末へは配らない)
- `README.md`, `.gitignore`: 公開リポジトリ用ファイル (配布しない)
- `scratch/`: ローカル退避用 (`.gitignore` 対象)
- `local/`, `notes/`, `log/`: 利用者ローカル領域 (`.gitignore` 対象、git 管理外＝ライブラリ更新で上書きされない)。詳細は README。
- `local/machines.md`: 全端末の端末名やスペックが記載されたマシン台帳。
- `local/memory/`: 各端末のメモリ領域 (M) を harvest した退避先 (別途・未実装)。
- `dotcodex/AGENTS.md`: Codex 版 global rules adapter の配布用原本 (配布は README を参照)。
- `dotcodex/skills/*/SKILL.md`: Codex 版 skill の配布用原本 (配布は README を参照)。
- `copilot/prompts/*.prompt.md`: Copilot 版 prompt の配布用原本 (配布は README を参照)。

### 端末名

現在の端末名は島内の「ホスト情報」(L) で定義する。
端末名の一覧は `<library_path>/local/machines.md` で定義する。

### 配布 (load)

**load = library → ローカル。ライブラリ島だけを更新する。** save (ローカル → library) は廃止。
ユーザー自由エリア (島の上) とメモリ領域 (島の下) は触らない。端末で生まれた設定・メモリは
library のマスターへ書き戻さない (個人情報を public git に上げないため)。端末間でメモリを
共有したい場合は別機構 (harvest, 別途・未実装) を使う。

対象は `CLAUDE.md` のライブラリ島 (S) と `commands/*.md`。

**cp による一括上書きはしない。** 手順:

1. **diff**: 対応ファイルを `diff` して差分を提示する。
   ```bash
   diff <library_path>/dotclaude/CLAUDE.md ~/.claude/CLAUDE.md
   diff -ru <library_path>/commands ~/.claude/commands
   ```
   ただし島外 (ユーザー自由エリア・メモリ領域) と島内の「ホスト情報」(L) の差分は無視 (端末固有で正)。
2. **状況判断**: 共有ルール (S) の差分が「マスター更新」か「端末で誤って S を触ったか」を見極める。
3. **方式を提案**: S を全置換か hunk 単位 merge か。merge なら *どの hunk をどちらから採るか
   (cherry-pick 単位)* まで具体的に挙げて指示を仰ぐ。
4. **実行**: 島内の **共有ルール (S) のみ master で更新**。**端末設定 (L = ホスト情報) は既存値を保持**
   (必要なら agent が旧値を読み取り再適用)。**島外 (自由エリア・メモリ) は絶対に触らない。**
   判断と最終指示は必ずユーザーが行う。

注意: PowerShell の `diff` は別物 (`Compare-Object`)。Windows でも Bash ツールで `diff` を使う。

### セットアップ

新しい端末では `<library_path>/dotclaude/CLAUDE.md` を `~/.claude/CLAUDE.md` にコピーし、
島内の **「ホスト情報」(L)** のプレースホルダ (`<vault_path>` 等) を記入する。メモリ領域 (M) は空のまま。
以降の更新は上記「配布 (load)」手順 (既存ファイルがあれば diff 提示・判断はユーザー)。

## メモリ追記の運用

メモリは全て **メモリ領域 (M)** = `<!-- claude-library:end … -->` 以降に追記する。
ライブラリ島・ユーザー自由エリアは触らない。

- `#` ショートカット / `/memory` / 「memory に〜書いて」: いずれもメモリ領域の末尾へ append。
  `#` は末尾追記なので構造上安全。`/memory` でファイル全体を開く場合はユーザーがゾーン構造を保つ。
- メモリは**この端末ローカル**。save が無いので他端末へは自動で伝播しない。
- 全端末で共有したい一般ルールは、メモリ (M) ではなく **マスターの共有ルール (S) を人間が直接編集** し、
  load で配布する。

## Obsidian vault 管理

Obsidian を knowledge base として使用している。vault へのコンテンツ保存・操作は
管理コマンド (save-chat 等) を通じて行う。

vault の実パスおよびフォルダ構成は島内の「ホスト情報」(L) を参照。

### vault フォルダ構成

vault には以下 3 系統のフォルダが共存している:

- **AI ノートフォルダ** (`ai_note_folder`): Claude が管理コマンド経由で書き込む対象のフォルダ
- **閲覧可能ノートフォルダ** (`public_note_folders`): Claude がファイル名とファイルの内容を閲覧可能
- **閲覧禁止ノートフォルダ** (`private_note_folders`): Claude がファイル名のみ閲覧可能

各フォルダの命名パターンは島内の「ホスト情報」(L) を参照。

### AI ノートフォルダ

Claude が save-chat 等の管理コマンドで書き込む対象

- Glob / Grep / Read すべて自由
- **書き込みは save-chat 等の管理コマンド経由のみ**。素の Write / Edit でノートを直接作成・編集してはいけない (試行錯誤は vault 内 `tmp/` を使う)
- save-chat の wikilink 自動対象もこのスコープ

### 閲覧可能ノートフォルダ

過去のアーカイブ済み AI ノートフォルダや、ユーザーが Claude に開放した個人ノートの一部を想定。

- Read / Grep / Glob すべて自由
- save-chat の wikilink 自動対象に含めてよい
- 書き込みはしない

### 閲覧禁止ノートフォルダ — 条件付きアクセス

ファイル名一覧 (`ls` / `Glob`) とタイトルからの推測は常時 OK。
本文の `Read` / `Grep` は以下で判断:

- **明示指示があれば OK**: 「内容も見て」「Grep して」等の指示があれば確認なしで読む
- **曖昧な依頼なら確認**: Glob でタイトル候補を出し「Read します。よいですか?」と確認してから
- **save-chat 出力への転記**: 読む許可とは別に、転記・引用の都度再確認
- **wikilink**: ノートへの wikilink は明示指示時のみ
- **書き込み**: 書き込みはしない

### tmp/ — AI 自由領域

vault 内 `tmp/` フォルダは試行錯誤・実験的アウトプットの置き場。

- AI は Read / Write / Glob / Grep すべて自由 (確認不要)
- 閲覧禁止ノートフォルダの条件付きアクセスルールの対象外
- save-chat の wikilink 自動対象スコープには含めない
- 「残したい」と思ったものはユーザーが手動で AI ノートフォルダ等へ昇格

## ホスト情報 (端末設定 L — この端末固有。値は端末ローカル / merge 時に agent が保持・再適用)

> セットアップ時にこの区画のプレースホルダを記入する。マスター (テンプレート) では
> プレースホルダのまま。load はこの値を上書きしない (merge 時に agent が保持/再適用)。

### パス定義

- `vault_path`: `<vault_path>`  (例: ~/path/to/obsidian/vault)
- `library_path`: `<library_path>`  (例: ~/path/to/claude/library)

### vault 設定

- `ai_note_folder`: `<ai_note_folder>`
- `public_note_folders`: `<public_note_folders>`
- `private_note_folders`: `<private_note_folders>`

### 端末情報

- ホスト名: `<hostname>`
<!-- claude-library:end — 以降はメモリ領域 (端末ローカル・自由追記・load 不可侵) -->
