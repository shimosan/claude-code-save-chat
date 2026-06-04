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

- `dotclaude/CLAUDE.local.md`: 新端末セットアップ時にのみ Claude が参照するひな型 (詳細は下記「セットアップ」)
- `.claude/CLAUDE.md`: library repo の保守ルール (この repo を編集する時の project memory。各端末へは配らない)
- `README.md`, `.gitignore`: 公開リポジトリ用ファイル (load/save しない)
- `scratch/`: ローカル退避用 (`.gitignore` 対象)
- `local/`, `notes/`: 利用者ローカル領域 (`.gitignore` 対象、git 管理外＝ライブラリ更新で上書きされない)。詳細は README。
- `local/machines.md`: 全端末の端末名やスペックが記載されたマシン台帳。
- `dotcodex/AGENTS.md`: Codex 版 global rules adapter の配布用原本 (load/save 対象外。配布は README を参照)。
- `dotcodex/skills/*/SKILL.md`: Codex 版 skill の配布用原本 (load/save 対象外。配布は README を参照)。
- `copilot/prompts/*.prompt.md`: Copilot 版 prompt の配布用原本 (load/save 対象外。配布は README を参照)。

### 端末名

現在の端末名は `CLAUDE.local.md`で定義する。
端末名の一覧は `<library_path>/local/machines.md` で定義する。

### 同期 (load / save)

ローカル (`~/.claude/`) と library (`<library_path>/dotclaude/`, `<library_path>/commands/`)
の間で同期する。**load = library → ローカル、save = ローカル → library。**
対象は `CLAUDE.md` と `commands/*.md` のみ。

**cp による一括上書きはしない。** どちらが「正」かは状況によるため、load/save いずれも:

1. **diff**: 対応ファイルを `diff` して差分を提示する。
   ```bash
   diff <library_path>/dotclaude/CLAUDE.md ~/.claude/CLAUDE.md
   diff -ru <library_path>/commands ~/.claude/commands
   ```
2. **状況判断**: 差分の素性を見極める (FREEZONE への端末別追記か / 構造化セクションの
   更新か / 一方が古いだけか)。
3. **方式を提案**: 「全体上書き」か「merge」かを提案。merge なら *どの hunk を
   どちらから採るか (cherry-pick 単位)* まで具体的に挙げて指示を仰ぐ。
4. **実行**: 指示どおり反映する。判断と最終指示は必ずユーザーが行う。

特に `CLAUDE.md` の FREEZONE は端末ごとに追記が積もる領域。上書きは他端末が
save したメモリを消すので、原則 merge + cherry-pick で扱う。構造化セクション
(FREEZONE より上) は人間管理なので、差分があれば内容を確認してから反映する。

注意: PowerShell の `diff` は別物 (`Compare-Object`)。Windows でも Bash ツールで `diff` を使う。
**`CLAUDE.local.md` は load/save 対象外** — 端末ローカル管理でクラウド共有しない
(`dotclaude/CLAUDE.local.md` は新端末セットアップ用のひな型)。

### セットアップ

新しい端末でセットアップする際は、まず `<library_path>/dotclaude/CLAUDE.local.md` を
`~/.claude/CLAUDE.local.md` にコピーし、端末固有の設定 (パス・マシン情報) を記入する。
次に上記の load 手順を実行する (既存ファイルがあれば diff 提示・判断はユーザー)。


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

## 端末固有ルール

`~/.claude/CLAUDE.local.md` を import する (端末ローカル管理、クラウド共有なし)。

@~/.claude/CLAUDE.local.md


## ━━━━━━ FREEZONE BOUNDARY ━━━━━━

ここから下は `#`・`/memory`・Claude の追記用ゾーン (共有メモリ)。
全端末で共有したいメモリをここに追記する (`CLAUDE.md` 全体が load/save 対象なのでクラウド経由で他端末にも反映される)。
境界より上の構造化セクションは触らない。

## 客観文書では絶対呼称

報告書・notes・save-chat 出力など、後で別人 / 別セッションが読む文書では絶対呼称 (Claude / agent / ユーザー / 役割名) を使い、相対呼称 (自分 / あなた / 私) は避ける。chat レスポンスでの相対呼称は OK。

## Dropbox 多端末同期の orphan temp 掃除

Dropbox で多端末共有していると、エディタ (Obsidian 等) の atomic-write (temp 書き → rename) の残骸 `*.tmp.<pid>.<hash>` (拡張子非依存。markdown なら `*.md.tmp.…`、canvas なら `*.canvas.tmp.…`) が sync 競合で取り残され、各 workspace に溜まる。agent はこれを掃除してよい。ただし**必ず安全確認してから**消す (盲目的な自動削除スクリプトは不可 — 内容判断が安全の決め手):

1. 親 `<base>` が存在する (末尾 `.tmp.<pid>.<hash>` を剥がした名前。無ければ削除せず手動確認 — その temp が唯一のコピーかもしれない)。
2. **十分に時間が経過している** (目安: mtime が 24h 以上前)。直近のものは編集中セッションの in-flight write や、まだ rename が他端末へ伝播していない可能性があるので触らない (多端末 Dropbox は他端末の保存・後始末の到達にラグがある)。
3. temp が親の部分集合 (`diff temp base` の `<` 固有行ゼロ) なら削除可 (内容損失ゼロが保証される)。
4. 固有行があれば深掘りし、その内容が親で **superseded / 最終版で意図的除去 / 別形で保持** のいずれかと確認できた場合のみ削除。確認できなければ消さず一覧提示。
5. vault の AI ノートフォルダ内でも対象 — これは「ノート執筆 (save-chat 経由必須)」ではなく temp 残骸の掃除。ノート本体には触れない。

**対象外** (`.tmp.<pid>.<hash>` 構造を持たず base の一意導出が成り立たない別系統): Dropbox の競合コピー `foo (… conflicted copy YYYY-MM-DD).md` (本物の分岐内容を持ちうる) / エディタ系 `.swp` `.bak` `~` `#foo#` 等。これらはこのルールでは扱わない。
