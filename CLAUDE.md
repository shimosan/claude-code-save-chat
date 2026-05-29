# Claude Code User Memory

## ファイル構成

ローカルの `~/.claude/` ディレクトリには以下のファイル・フォルダが存在する:

- `CLAUDE.md` : クラウド共有のルール集。上半分は構造化セクション (人間管理)、下半分は自由領域 (memory 追記用)。
- `CLAUDE.local.md` : 端末固有の設定 + 自由領域。クラウド共有なし。
- `commands/` : Claude が管理するコマンド定義ファイル群。

## User Memoryの クラウド共有

複数端末間で Claude Code 環境を Dropbox 等のクラウドを利用して共有・同期するための仕組み。

### 共有フォルダ

このファイルのミラーはクラウド上の共有フォルダ (library) に置く。共有フォルダのパスは `library_path` とし、`CLAUDE.local.md` で定義する。

**load/save 対象は `CLAUDE.md` と `commands/*.md` のみ**。library 内のその他のファイル・フォルダはすべて load/save の往復対象外:

- `CLAUDE.local.md.template`: 新端末セットアップ時にのみ Claude が参照 (詳細は下記「セットアップ」)
- `README.md`, `.gitignore`: 公開リポジトリ用ファイル (load/save しない)
- `scratch/`: ローカル退避用 (`.gitignore` 対象)
- `local/`, `notes/`: 利用者ローカル領域 (`.gitignore` 対象、git 管理外＝ライブラリ更新で上書きされない)。詳細は README。
- `local/machines.md`: 全端末の端末名やスペックが記載されたマシン台帳。

### 端末名

現在の端末名は `CLAUDE.local.md`で定義する。
端末名の一覧は `<library_path>/local/machines.md` で定義する。

### 同期 (load / save)

ローカル (`~/.claude/`) と共有フォルダ (`library_path`) の間で同期する。
どちらが「正」かは状況による。Claude は実行前に必ず diff を提示する。判断と実行指示はユーザーが行う。

**load** (クラウド → ローカル):
```bash
cp -v <library_path>/CLAUDE.md ~/.claude/CLAUDE.md
cp -v <library_path>/commands/*.md ~/.claude/commands/
```

**save** (ローカル → クラウド):
```bash
cp -v ~/.claude/CLAUDE.md <library_path>/CLAUDE.md
cp -v ~/.claude/commands/<ファイル名> <library_path>/commands/
```

注意: `cp -i` は非対話シェルでは黙ってスキップする。`cp -v` を使うこと。
**`CLAUDE.local.md` は対象外** — クラウド共有していないので load/save 不要。

### セットアップ

新しい端末でセットアップする際は、まず `CLAUDE.local.md.template` を `~/.claude/CLAUDE.local.md` にコピーし、端末固有の設定 (パス・マシン情報) を記入する。
次に上記の load 手順を実行する (既存ファイルがあれば diff 提示・上書き判断はユーザー)。


## メモリ追記の運用

`CLAUDE.md` と `CLAUDE.local.md` の両方に末尾の自由領域を設けている。
境界は `## ━━━━━━ FREEZONE BOUNDARY ━━━━━━` の見出しで明示。
構造化セクション (境界より上) は触らず、追記は自由領域 (境界より下) に限る。

### スコープによる宛先選択

- 共有 (全端末で必要なメモリ) → `CLAUDE.md` の自由領域
- 端末ローカル → `CLAUDE.local.md` の自由領域

### Claude の振る舞い

ユーザーから「memory に〜書いて」と指示されたとき、Claude は:

1. **スコープを確認**: 「これは全端末で共有? それともこの端末だけ?」
2. 該当ファイルの自由領域に append (構造化セクションは触らない)
3. `CLAUDE.md` に追記した場合は「save しますか?」と確認する

`#` ショートカットや `/memory` コマンドも同じ原則: 自由領域に書く。`#` は末尾追記なので構造上安全。`/memory` でファイル全体を開く場合はユーザー自身が構造を保つ。


## Obsidian vault 管理

Obsidian を knowledge base として使用している。vault へのコンテンツ保存・操作は
管理コマンド (save-chat 等) を通じて行う。

vault の実パスおよびフォルダ構成は `CLAUDE.local.md` を参照。

### vault フォルダ構成

vault には以下 3 系統のフォルダが共存している:

- **AI ノートフォルダ** (`ai_note_folder`): Claude が管理コマンド経由で書き込む対象のフォルダ
- **閲覧可能ノートフォルダ** (`public_note_folders`): Claude がファイル名とファイルの内容を閲覧可能
- **閲覧禁止ノートフォルダ** (`private_note_folders`): Claude がファイル名のみ閲覧可能

各フォルダの命名パターンは `CLAUDE.local.md` を参照。

### AI ノートフォルダ

Claude が save-chat 等のコマンドで書き込む対象

- Glob / Grep / Read すべて自由
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

## 端末固有ルール

`~/.claude/CLAUDE.local.md` を import する (端末ローカル管理、クラウド共有なし)。

@~/.claude/CLAUDE.local.md


## ━━━━━━ FREEZONE BOUNDARY ━━━━━━

ここから下は `#`・`/memory`・Claude の追記用ゾーン (共有メモリ)。
全端末で共有したいメモリをここに追記する (`CLAUDE.md` 全体が load/save 対象なのでクラウド経由で他端末にも反映される)。
境界より上の構造化セクションは触らない。
