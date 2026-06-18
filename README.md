# claude-code-save-chat

Claude Code / Codex / Copilot の会話保存と複数端末 config 管理を、Obsidian とクラウド同期フォルダに寄せて運用するための個人用ライブラリ。

複数端末で利用する Claude Code (CLI / VS Code 拡張 / Cursor 等) の chat 履歴サマリーを Obsidian vault のノートに保存するためのコマンド `/save-chat` と、端末設定の snapshot / drift 確認 / 安全な apply review を行う `/config-manager`、および Claude Code と Codex の会話履歴をワークスペース単位で横断一覧する読み取り専用コマンド `/chat-list` を実装する。あわせて、Claude Code / Codex / Copilot 向けの agent 設定、save-chat / config-manager workflow、補助スクリプトをクラウドストレージ (Dropbox / iCloud Drive / Google Drive 等) 経由で配布・共有する。Obsidian vault もクラウドストレージ経由で共有すると便利。

## 免責

このライブラリは個人用の設定・運用補助を公開しているもので、無保証で提供される。内容には未確認・実験的な前提を含む場合があり、作者は利用に伴う設定変更、データ損失、環境不整合、その他の損害について責任を負わない。各コマンドやスクリプトは、内容と影響範囲を確認したうえで自己責任で実行する。

This library publishes personal configuration and operations helpers as-is, without warranty. It may include unverified or experimental assumptions. The author assumes no responsibility for configuration changes, data loss, environment inconsistencies, or any other damage caused by use of this library. Review each command or script and its impact before running it, and use it at your own risk.

## 配置場所

このフォルダはクラウド同期される場所であればどこに置いてもよく、フォルダ名も自由。`git clone` すると既定で repo 名の `claude-code-save-chat/` になるが、好きにリネームしてよい。各端末では、このフォルダの実パスを `library_path` として `~/.claude/CLAUDE.md` の「ホスト情報」セクションに記録する。

例:
- `~/Dropbox/claude-code-save-chat/`  (クラウド直下に clone 既定名のまま)
- `~/iCloud/<any>/<folders>/claude-code-save-chat/`  (中間フォルダ階層も自由)
- `~/GoogleDrive/agent-config/`  (任意にリネーム)
- `~/Dropbox/library/claude/`  (作者の実運用例: `library/` 配下に置き `claude` にリネーム)

## 構成

```
<library_path>/
├── README.md                    ← このファイル
├── .claude/CLAUDE.md            ← library repo の保守ルール (Claude Code 用・この repo 編集用、配布しない)
├── AGENTS.md                    ← library repo の保守ルール (Codex 用・.claude/CLAUDE.md を参照する adapter、配布しない)
├── dotclaude/                   ← 各端末の ~/.claude/ へ deploy する Claude Code 原本
│   ├── CLAUDE.md                ← 共有ルール + 端末設定 + メモリを統合した管理ブロック構造 (1 ファイル)
│   └── commands/                ← ~/.claude/commands/ へ deploy する slash commands
│       ├── save-chat.md         ← save-chat core への薄い入口 (Claude Code 皮)
│       ├── config-manager.md    ← config snapshot/update workflow への薄い入口
│       └── chat-list.md         ← chat-list.py への薄い入口 (claude+codex 会話履歴の横断リスト)
├── .gitignore                   ← git 除外パターン
├── dotcodex/                    ← 各端末の ~/.codex/ へ deploy する Codex 原本
│   ├── AGENTS.md                ← Codex global rules adapter
│   ├── skills/save-chat/SKILL.md ← save-chat core への薄い入口 (Codex 皮)
│   ├── skills/config-manager/SKILL.md ← Codex 版 config-manager (薄い入口)
│   └── skills/chat-list/SKILL.md ← chat-list.py への薄い入口 (Codex 皮)
├── copilot/                     ← Copilot 版 prompt の配布用原本 (任意・VS Code + Copilot 端末のみ)
│   └── prompts/save-chat.prompt.md ← save-chat core への薄い入口 (Copilot 皮)
├── scripts/                     ← workflow の正本 + 補助スクリプト集 (非配布。README は目次)
│   ├── README.md                ← scripts の目次
│   ├── save-chat-core.md        ← save-chat の共通仕様 (workflow authority、3 皮が実行時に読む)
│   ├── chat-list.py             ← claude+codex 会話履歴の横断リスト (chat-list 皮が実行時に読む)
│   ├── config-update.md         ← config snapshot/update workflow の正
│   ├── config-apply-recipes.md  ← snapshot-driven config recipes
│   ├── config-apply-patches.md  ← optional local patch recipes の入口
│   ├── config-snapshot-*.py     ← live config snapshot 収集
│   ├── config-log-helper.py     ← snapshot/apply log の閲覧・比較 helper
│   ├── config-jsonc-set-keys.py ← JSONC top-level key 設定 helper
│   └── patch-* / fix-*          ← optional local patch / recovery scripts
├── scratch/                     ← ローカル退避用 (.gitignore 対象、配布対象外)
├── local/                       ← 利用者ローカル領域 (.gitignore 対象)
├── notes/                       ← 開発メモ (.gitignore 対象)
└── log/                         ← config snapshot / apply log (.gitignore 対象)
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

Codex を使う端末でも、save-chat の設定原典は `~/.claude/CLAUDE.md` なので、
最低限 `~/.claude/CLAUDE.md`(「ホスト情報」セクションに `library_path` / `vault_path` 等を
記入)を配置する必要がある。Claude Code 本体を使わない端末でも、このファイルは
Codex / Copilot が参照する設定原典として必要 (save-chat の仕様本体は library 側の
`scripts/save-chat-core.md` を読む)。

そのうえで `dotcodex/` を `~/.codex/` へ展開する。既存の
`~/.codex/AGENTS.md` がある場合は上書きせず、`dotcodex/AGENTS.md` の
マーカー付き adapter block を diff/merge する。

`/chat-list` (claude+codex 会話履歴ブラウザ) を使う端末では、あわせてその皮と PATH コマンドを展開する
→ [「`/chat-list` — 展開 (deploy)」](#展開-deploy) を参照。

## `/save-chat` — 会話を Obsidian vault に保存

現在の会話を markdown ノートとして Obsidian vault に書き出す。

- **保存先**: vault 内の **AI ノートフォルダ** (`claude{YYYY}/` 等)
- **構造**: frontmatter (tags / model / machine / session_id 等) + 本体 + 改訂履歴
- **改訂モード**: 同 slug 既存ファイルがあれば上書き + 改訂履歴に追記
- **テンプレート**: default / qa / worklog / troubleshoot / decision から会話の性質に応じて選択

```
/save-chat                  ← slug 自動生成
/save-chat my-topic-slug    ← slug 指定
save-chatしてください        ← Codex 版 skill の自然文トリガー
```

### save-chat の構成 — core + 薄い皮 3 枚

save-chat は **共通仕様 (core) 1 つ + プラットフォーム別の薄い入口 (皮) 3 枚**で構成する
(config-manager と同じ形態)。仕様の正本は core だけが持ち、各皮は「起動形態 + core の解決 +
platform 固有のメタデータ取得 (binding)」のみを持つ:

| | ファイル | 役割 |
|---|---|---|
| **core (正)** | [`scripts/save-chat-core.md`](scripts/save-chat-core.md) | ノートフォーマット・slug/タグ規則・改訂規則・wikilink 規則の共通仕様。**非配布** (library 単一コピー、3 皮が実行時に読む) |
| **Claude Code 皮** | [`dotclaude/commands/save-chat.md`](dotclaude/commands/save-chat.md) | slash command。`~/.claude/commands/` へ load で配布 |
| **Codex 皮** | [`dotcodex/skills/save-chat/SKILL.md`](dotcodex/skills/save-chat/SKILL.md) | skill (自然文トリガー)。`~/.codex/skills/` へ配布 |
| **Copilot 皮** | [`copilot/prompts/save-chat.prompt.md`](copilot/prompts/save-chat.prompt.md) | user prompt。VS Code User prompts へ配布 |

各皮は core を `<library_path>/scripts/save-chat-core.md` から読む (`library_path` は
`~/.claude/CLAUDE.md` の「ホスト情報」セクションで解決)。frontmatter の `source` / `model` /
`session_id` は皮ごとの binding で取得し、安定取得できなければ省略する。

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
| **Claude Code 版** | [`dotclaude/commands/config-manager.md`](dotclaude/commands/config-manager.md) | `~/.claude/commands/config-manager.md` |
| **Codex 版** | [`dotcodex/skills/config-manager/SKILL.md`](dotcodex/skills/config-manager/SKILL.md) | `~/.codex/skills/config-manager/SKILL.md` |

どちらも薄い入口で、実体の workflow・recipe・local policy の扱いは [`scripts/config-update.md`](scripts/config-update.md) が持つ。設定変更・ロールバック等の apply は `scripts/config-update.md` の apply mode の承認手順に従い、具体的変更への明示承認なしに live config を触らない。人間向けの詳しい入口仕様と例は [`dotclaude/commands/config-manager.md`](dotclaude/commands/config-manager.md) を参照。Claude Code 版の展開は `dotclaude/commands/` の他コマンドと同じ load 手順、Codex 版は下記「展開 (Codex)」に従う。

### config-manager の設計思想

config-manager は「snapshot に出た値を機械的に全適用する同期ツール」ではない。snapshot は端末の live 状態をできるだけ網羅的に観測するための材料であり、apply は agent が review-only で差分・意図・危険度を整理し、ユーザーが承認した具体的変更だけを現在端末へ反映する。

config-manager は `local/` に固定の目標値を維持しない。取り込み元は snapshot、ユーザーが明示した値、private policy、または承認済み recipe の入力として都度選ぶ。`local/` は machine inventory / private policy / private recipes などの軽いローカル知識置き場であり、live 設定が `local/` 内の任意ファイルと違うだけでは drift や apply 対象とは扱わない。

recipe は、よく使う安全な apply 手順の型を固定するためのもの。config recipe は snapshot に状態が出る正規設定を扱い、patch recipe は snapshot に状態が出ない補修・復旧・ローカル patch を扱う。どちらも apply log では `recipe_id` と `recipe_type` で記録する。

snapshot には editor settings のように低リスクで宣言的に再現できる値もあれば、`brew` / `pyenv` / fonts / model list のように provisioning 計画が必要な値、`claude.md` の host-info のように端末固有でコピーしてはいけない値、version/path のような診断値も混在する。したがって、recipe が無い source は即エラーではなく、まず review-only で `low` / `medium` / `high` / `system` / `local-sensitive` / `diagnostic` の性質を分類し、target・old/new・backup・rollback・verification を明示してから承認を求める。反復する ad-hoc 操作だけを public recipe または `local/config-local-recipes.md` へ昇格する。

実装済み recipe には [`scripts/config-apply-recipes.md`](scripts/config-apply-recipes.md) で `risk class` を明示する。未カバー source の一般ルールも同ファイルに置き、流動的な拡張・ツール・環境差を全列挙しない方針にしている。

## `/chat-list` — Claude Code と Codex の会話履歴を横断一覧 (読み取り専用)

Claude Code と Codex の会話履歴を **ワークスペース単位で 1 つに束ねて列挙・閲覧する**読み取り専用ツール。純正 UI が片方ずつ・WS 区別なしでしか見せない履歴を、横断・時系列で一覧できる。要約や引き継ぎ (resume) はせず、列挙と全文の取り出しに徹する。

使い方は 2 通り。**生スクリプトを直接叩くだけで十分実用**で、slash command はその薄い糖衣:

**(1) 生 CLI (人間が端末で直接 — これだけで完結)**

```bash
python3 <library_path>/scripts/chat-list.py                   # 現在 WS の claude+codex 履歴を新しい順で
python3 <library_path>/scripts/chat-list.py --workspaces      # WS 一覧 (各 WS の会話数・期間の census)
python3 <library_path>/scripts/chat-list.py --ws GPU          # WS を部分一致で指定 (rename/正規化分裂も束ねる)
python3 <library_path>/scripts/chat-list.py --grep NFC        # 本文を全文検索 (一致行も表示)
python3 <library_path>/scripts/chat-list.py --dump <id> --open  # 会話の全文をエディタの untitled buffer へ
python3 <library_path>/scripts/chat-list.py --help            # オプションの正本
```

**(2) `/chat-list` slash command (agent 経由)** — agent が自然文を確定セレクタ (WS path / 会話 id) に解決し、`--dump` 等の前に対象を提示して確認を取る。生 CLI に NL 解決と安全確認を足しただけ。

```
/chat-list / /chat-list --workspaces       ← 生 CLI と同じ
このWSのcodexの履歴だけ見せて                ← agent が --tool codex 等に解決
○○ を含む会話を探して                       ← --grep に解決
N番の会話を全部見せて                        ← 番号から id を確定し --dump
```

**2 層構造** (core は実行可能スクリプト。Claude Code 皮 + Codex 皮。Copilot 皮は無し):

| | 実体 (正) | 展開先 |
|---|---|---|
| **core (正)** | [`scripts/chat-list.py`](scripts/chat-list.py) | **非配布** (library 単一コピー、生 CLI または皮が `library_path` 経由で実行) |
| **Claude Code 皮** | [`dotclaude/commands/chat-list.md`](dotclaude/commands/chat-list.md) | slash command。`~/.claude/commands/` へ load で配布 |
| **Codex 皮** | [`dotcodex/skills/chat-list/SKILL.md`](dotcodex/skills/chat-list/SKILL.md) | skill (自然文トリガー)。`~/.codex/skills/` へ配布 |

各行は `#` / 開始時刻 / 由来 (`CC`/`CX` + 起動元、`*`=archived codex) / id / サイズ / タイトル。`--sort time|mtime|size|count|name` (既定は新しい順) と `--reverse` で並べ替え、`--title` / `--grep` で絞り込み、`--dump` で全文 (stdout / `--out` / `--open` でエディタ buffer) を取り出せる。オプションの正本は `--help`。

core は決定的 (LLM 推論ゼロ) なので生 CLI で完結する。claude は `~/.claude/projects/*.jsonl`、codex は `~/.codex/sqlite/state_5.sqlite` の `threads` を読む。開始時刻は会話本体の timestamp が正本 (OS の file mtime は Dropbox 同期で揃うため使わない)、同一セッションの物理重複は `(harness, id)` で排除、codex の subagent / archived は既定で除外。

### 展開 (deploy)

「chat-list を展開して」と言われたら次を行う。core (`scripts/chat-list.py`) は**非配布** — 皮と PATH 設定だけ端末ローカルに用意する。`<library_path>` は `~/.claude/CLAUDE.md` のホスト情報から解決する。

1. **Claude Code 皮** (この端末で `/chat-list` を使うなら):
   `cp <library_path>/dotclaude/commands/chat-list.md ~/.claude/commands/chat-list.md`
   (既存があれば上書き前に `diff`。認識にはセッション再読込が要ることがある。)
2. **Codex 皮** (この端末で Codex を使うなら):
   `mkdir -p ~/.codex/skills/chat-list && cp <library_path>/dotcodex/skills/chat-list/SKILL.md ~/.codex/skills/chat-list/SKILL.md`
   (反映は Codex の新規セッションから。)
3. **PATH コマンド `chat-list`** (任意 — 素のターミナルで使うなら): 下記「`chat-list` を PATH のコマンドにする」。

皮は実行時に `library_path` 経由で core を呼ぶだけなので、**core を更新しても皮の再 deploy は不要** (皮そのものを編集したときだけ再 cp)。Codex の AGENTS 等と違い chat-list 皮は新規ファイルなので managed-block merge は不要、cp でよい。

### `chat-list` を PATH のコマンドにする (任意・端末ローカル)

`python3 <library_path>/scripts/chat-list.py …` と打つ代わりに、PATH 上の `chat-list` で直接呼べる。スクリプトは標準ライブラリのみ・`library_path` 非依存。PATH を通す操作 (どのディレクトリを PATH に足すか) は各端末ローカルで一度だけ行う。Windows 用ラッパー `scripts/chat-list.cmd` は repo 同梱 (mac/Linux の symlink・ラッパーは端末ローカルで作る)。

**macOS / Linux** — PATH 上のディレクトリ (例 `~/.local/bin`) に**小さなラッパー**を置く。ラッパーが `python3 <script>` を呼ぶので、スクリプトの実行ビットに依存せず、**Dropbox 共有 (Windows 端末の編集が往復すると mac 側の `+x` が剥がれる) でも壊れない**:

```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/chat-list <<SH
#!/bin/sh
exec python3 "<library_path>/scripts/chat-list.py" "\$@"
SH
chmod +x ~/.local/bin/chat-list      # このラッパーの +x は端末ローカルで安定
chat-list --help
chat-list --ws hoge
```

(よりシンプルに `ln -sf <library_path>/scripts/chat-list.py ~/.local/bin/chat-list` の symlink でも可。スクリプトは実行ビット付き git mode `100755` で配布されるが、Dropbox 経由で Windows 端末が編集すると mac 側の `+x` が落ちることがある。そのときは `chmod +x <library_path>/scripts/chat-list.py` で復活するか、上のラッパー方式にする。)

**Windows** — リポジトリ同梱の [`scripts/chat-list.cmd`](scripts/chat-list.cmd) が隣の `chat-list.py` を `%~dp0` で呼ぶラッパー。動く Python を順に探すフォールバック連鎖 (① `py` ランチャ → ② アクティブ venv `%VIRTUAL_ENV%` → ③ 実際に実行できる `python`/`python3` → ④ `%USERPROFILE%\.venvs\*` の venv → ⑤ pyenv-win の `versions\*` を直接) なので、**venv 非アクティブでも、フォルダの `.python-version` が未インストール版を指して pyenv-win shim が失敗する状況でも動く**。**`<library_path>\scripts` を PATH に追加するだけ**で `chat-list` コマンドになる:

```powershell
# PowerShell: ユーザー PATH に library の scripts\ を追加 (一度だけ)。User スコープを読んで足す
# ($env:Path を使うと machine 由来の項目まで User PATH に流れ込むので避ける)
$lib = "<library_path>\scripts"
$u = [Environment]::GetEnvironmentVariable("Path","User")
[Environment]::SetEnvironmentVariable("Path", $u.TrimEnd(';') + ";" + $lib, "User")
# 新しい端末/シェルを開いてから (Cursor の統合ターミナルは Cursor 自体を再起動):
chat-list --help
chat-list --ws hoge
```

PATHEXT に `.CMD` があるので拡張子なしの `chat-list` で `chat-list.cmd` が呼ばれる。`chat-list.cmd` / `.gitattributes` は repo 同梱 (CRLF 固定)。

- どちらも `chat-list` は呼び出し時の cwd を現在 WS とみなす (= そのフォルダの claude+codex 履歴)。
- **Windows 動作確認済み** (amada / Windows 11)。Windows 配慮: 全ファイル読みは `encoding="utf-8"` 固定、codex の sqlite は `pathlib.as_uri()` で OS 非依存 URI、cwd の `\\?\` 拡張長プレフィックスとドライブ大小は正規化して claude/codex を 1 WS に統合、`%Z` のローカライズ名 (例「東京 (標準時)」) はオフセット略称化 (→ `JST`)。`chat-list.cmd` は CRLF 必須なので `.gitattributes` (`*.cmd text eol=crlf`) で固定。CJK (日本語) は**対話型ターミナルでは化けない** (Python が UTF-16 でコンソールへ直接出力する)。化けるのは出力を**パイプ/リダイレクト**した時だけで、その場合は `PYTHONIOENCODING=utf-8` を設定すれば解消する (データ処理自体は常に UTF-8 で正しい)。

## Codex 版 global rules / skills (任意)

Codex でも Claude Code 側のルール、save-chat workflow、config 管理 workflow を参照できる。Codex 版 skill は**薄い皮** — 実行時に library 側の正本 (save-chat は `scripts/save-chat-core.md`、config-manager は `scripts/config-update.md`) を読むので、正本の更新に自動追従する (フォークではない)。

> **前提: `~/.claude/CLAUDE.md` が必須。** `CLAUDE.md` の「ホスト情報」セクション (`vault_path` / `library_path` 等) は端末ローカルで library に複製が無く、これが無いと保存先も library の位置 (= core の位置) も解決できない。(移行前の端末で旧 `~/.claude/CLAUDE.local.md` が残っていれば、そこからの解決もフォールバックとして可。)

> **Codex 単体利用時の注意:** Claude Code binary が未導入でもよいが、`~/.claude/CLAUDE.md`(「ホスト情報」セクション記入済み)は必要。save-chat の仕様本体は library 側の `scripts/save-chat-core.md` を直接読むため、`~/.claude/commands/` の配置は不要。

- **global rules**: `dotcodex/AGENTS.md` を `~/.codex/AGENTS.md` へ展開する。既存の `~/.codex/AGENTS.md` があれば上書きせず、マーカー付き adapter block を diff/merge する。
- **save-chat 呼び出し**: slash command ではなく skill の自然文トリガー。例: `save-chatしてください` / `/save-chat` / `save-chat <slug>`
- **config-manager 呼び出し**: config snapshot / drift / apply review 用の薄い入口。例: `config-managerで最近の設定差分を見て` / `<machine> の設定をこの端末に取り込みたい`
- **frontmatter**: `source: codex`。`model` / `session_id` は Codex 自身の local transcript (`$CODEX_HOME/session_index.jsonl` + `sessions/**/*.jsonl` の `turn_context`) から取得し、reasoning effort が同時に取れる場合は `model: gpt-5.5 (medium)` 形式で付記。読めなければ省略 (詳細は SKILL.md の binding)
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

VS Code + GitHub Copilot でも save-chat を使える。Copilot 版は**薄い皮** — 実行時に library 側の正本 (`scripts/save-chat-core.md`) を仕様として読む (フォークではない)。

> **前提: `~/.claude/CLAUDE.md` が必須。** `CLAUDE.md` の「ホスト情報」セクション (`vault_path` / `library_path` 等) は端末ローカルで library に複製が無く、これが無いと保存先も library の位置 (= core の位置) も解決できない。(移行前の端末で旧 `~/.claude/CLAUDE.local.md` が残っていれば、そこからの解決もフォールバックとして可。)

- **呼び出し**: Copilot Chat の `/save-chat` (`/save-chat <slug>` で slug 指定)
- **frontmatter**: `source: github-copilot`。`session_id` は Copilot 自身の debug-logs セッション UUID、`model` は同セッションフォルダの `models.json` 等から既知の場合のみ。読めなければ省略

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

基本的に library 側 (`dotclaude/`, `dotcodex/`, `copilot/`) を編集の正とし、
各端末の `$HOME` 配下や editor user prompts へ展開する。端末側で直接編集した場合は、
差分を確認して library 側へ戻す。

Claude Code の `~/.claude/` への `load`(配布)手順の詳細は
[`dotclaude/CLAUDE.md`](dotclaude/CLAUDE.md) を参照(`save` は廃止)。

## 補助スクリプト — `scripts/`

`scripts/` は **workflow 正本** (save-chat core、config workflow) と**補助ツール**の置き場。非配布 (library 単一コピー) で、各端末の皮・helper が実行時に参照する。Claude Code / Codex / VS Code / Cursor 周辺で見つかった再利用可能な修正・診断スクリプトもここに置く。[`scripts/README.md`](scripts/README.md) は目次とし、軽いスクリプトは 1-2 行の説明だけでよい。使い方・注意点・復旧手順が必要なものは、スクリプト専用の `.md` に詳しく書く。

主な分類:

- Workflow authorities: save-chat の共通仕様 [`scripts/save-chat-core.md`](scripts/save-chat-core.md) と config workflow の正 [`scripts/config-update.md`](scripts/config-update.md)。各皮 (thin entrypoint) が実行時に読む。
- Config workflow and helpers: config snapshot / compare / apply protocol と、JSONC・log 操作用の helper。詳細は [`scripts/README.md`](scripts/README.md) と [`scripts/config-update.md`](scripts/config-update.md)。
- Patch and recovery utilities: VS Code / Cursor / Codex 周辺の optional local patch・復旧 script。詳細は [`scripts/README.md`](scripts/README.md) と [`scripts/config-apply-patches.md`](scripts/config-apply-patches.md)。

`scripts/` の内容は任意利用。新端末セットアップに必須ではなく、必要な端末で必要なものだけ実行する。

## ローカル領域 — `local/` · `notes/` · `scratch/` · `log/`

`.gitignore` 対象のフォルダで、**git 管理外＝バージョン管理されない利用者ローカル領域**。commit も push もされず、`git pull` でライブラリを更新しても**上書きされない**。各自のローカルな内容を安心して置ける (remote が public でも露出しない)。

- `local/` : 端末固有・個人的な設定や事実 (例: マシン台帳、private policy、private recipes)。git に入れたくないがすぐ参照したいもの。
- `notes/` : 長期保存の開発メモ・気付き (日付付き md, `YYYY-MM-DD_topic.md` 推奨)。
- `scratch/` : 作業前バックアップ、退避コピー、実験版、旧実体の保全などの一時・準長期退避先。
- `log/` : config snapshot / apply log などの raw 履歴。

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
- **UTF-8 読み取り**: Windows PowerShell 5.1 でこの library の管理対象テキスト (`.md`, `.json`, `.jsonc`, `.prompt.md`, `SKILL.md`, `AGENTS.md`, `CLAUDE.md`) を `Get-Content` する時は `-Encoding UTF8` を明示する。
- **パスは POSIX 変換**: `D:\Dropbox\library\claude` → `/d/Dropbox/library/claude` に変換して Bash に渡す。`CLAUDE.md` の「ホスト情報」セクションのパス定義は Windows 表記 (`D:\...`) のまま書き、使用時に変換する。
- **端末固有メモはメモリ領域へ**: POSIX パス変換・`hostname` の挙動・projects パスエンコード等の Windows 専用補足は `CLAUDE.md` の管理ブロック外にあるメモリ領域 (M) に置く (管理ブロック内の共有ルール S は master 準拠のまま保つ)。
- **GPU スペック取得**: `Get-WmiObject Win32_VideoController` 等で取得。machines.md の `プロセッサ` 欄にはディスクリート GPU を採用 (統合 GPU は除外)。

## 注意

- 本 library に**個人 secrets を置かない** (`.env`, API キー等は別の場所へ)
- `CLAUDE.md` の「ホスト情報」セクションとメモリ領域は端末ローカル — load で配布・上書きしない

## License

MIT — see [LICENSE](LICENSE).
