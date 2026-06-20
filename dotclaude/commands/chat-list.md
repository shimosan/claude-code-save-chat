---
description: claude-code / codex / cursor / copilot の会話履歴を横断で列挙・閲覧する (読み取り専用)。既定は現在の WS の統合履歴を時系列で。WS 一覧・各会話の先頭/末尾プレビュー・特定会話の全文 dump も可能。
allowed-tools: ["Bash", "Read"]
argument-hint: "[--path <名前>] [--all] [--exact] [--workspaces] [--dump <id>] [--title <語>] [--grep <語>] [--preview [N]] [--head N|--tail N] [--tool claude|codex|cursor|copilot] [--long] [--sort start|end|size|total|title|path] [--reverse] [--json] [--open]"
---

# /chat-list — 会話履歴の横断リスト (Claude Code 皮)

library の決定的コア `scripts/chat-list.py` に委譲する thin なエントリポイント。
**仕様 (列挙ロジック・データ源・出力形式) をこのファイルに複製しない。**

**claude-code / codex / cursor (native) / copilot (VS Code 拡張 + CLI)** の会話履歴を横断で
**列挙・閲覧するだけ** (読み取り専用)。要約・引き継ぎ (resume) は対象外 (将来レイヤ)。
由来列は `<WSラベル> CC|CX|CU|CP/<起動元/surface>` (CC=Claude Code, CX=Codex, CU=Cursor, CP=Copilot)。

## 役割分担 (重要)

- **コア (`scripts/chat-list.py`, 決定的)**: セレクタは**確定値のみ**受ける (`--path` は cwd パス /
  部分一致語、`--dump` は会話 id)。LLM 推論ゼロ・読み取り専用。
- **皮 (この agent)**: ユーザーの**自然言語 → 確定セレクタへの解決**を担う。曖昧な指定は
  `--workspaces` や一覧で候補を出して絞り、**`--dump` の前は対象の title / 開始時刻 / プレビューを
  見せてユーザーの確認を取る** (安全はこの確認で担保)。

## `<library_path>` の解決

`scripts/chat-list.py` を含むなら現在の workspace を使う。無ければ `~/.claude/CLAUDE.md` の
「ホスト情報」セクションの `library_path` から読む (未移行端末では旧 `~/.claude/CLAUDE.local.md`)。
どちらも無ければユーザーに尋ねる。パスを捏造しない。script が読めない場合は中断して報告する。

## 起動

`python3 <library_path>/scripts/chat-list.py [options]` を Bash で実行する
(PATH に通してあれば `chat-list [options]` でよい。Windows では `python3` の代わりに `python` / `py`、
または PATH 上の `chat-list`)。
**出力 (一覧そのもの) を提示する — 散文サマリーに要約し直さない。** 各行 (`#`・時刻・由来・ID・サイズ・タイトル、
`--grep`/`--head`/`--tail` の一致・プレビュー行) はユーザーが次に叩く手がかり (`--dump <id>`・WS 選択など)
なので、**番号と ID を残したまま見せる**。先頭に 1〜2 行の要約コメントを添えるのは可。件数が多くても行を
散文に潰さず一覧を出す (必要なら「関連分に絞る/上位 N 行に限る」と述べてから絞る)。
オプションの正本は `--help`。主なもの:

- 既定 (引数なし): **現在の cwd の WS の統合履歴**を時系列で。
- `--path <値>`: 別 WS を対象に。**既定は cwd 部分一致**、`--exact` で完全一致。反復・カンマ区切りで複数可。
  曖昧で複数 WS にまたがる時は、まず `--workspaces` を出して候補を確定してから渡す。
- `--all`: WS で絞らず全件。**`--path` とは排他**。
- `--exact`: `--path` / `--title` を完全一致に (既定は部分一致)。
- `--workspaces`: WS 一覧 (各 WS のチャット数・start/end の census)。
- `--dump <id>`: 指定会話の全文。冒頭に情報ブロック (`# key : value` を `# ────` 罫線で囲む。id/origin/model/messages/events/span/size/cwd/path/title)、各メッセージは前に罫線 + 見出し `### <role> [i/N] <時刻>` (role 先頭で grep しやすい)。既定 stdout(`> file` でファイル)、`--open` でエディタ buffer、`--json` で構造化メッセージ (各要素に `ts`)。
  - メッセージ位置の grep: `grep -nE '^### \w+ +\[[0-9]+/[0-9]+\] '` (全件) / `grep -n '^### user '` (role 絞り)。機械処理は `--json` (境界=配列要素で 100% 確実) が本筋。
- フィルタ (両モード): `--tool claude|codex|cursor|copilot` / `--title <語>`(タイトル絞り) / `--grep <語>`(**本文全文検索**・遅め)。
- `--path` / `--title` / `--grep` / `--tool` は一覧でも `--workspaces` でも効く(`--workspaces --path GPU` で census を絞る)。
- `--sort` / `--reverse`(`-r`): 並び替え。**既定 `start`=開始時刻・新しい順**。列 header 名と一致するキー: 共通 `start` / `end`(最終活動。会話内の最後の timestamp で OS の file mtime ではない) / `size`、一覧専用 `title`、`--workspaces` 専用 `total`(本数) / `path`。start/end/size/total は新しい/大きい順、title/path は昇順。`--reverse` で反転。モード外キーはエラー。
- `--head N` / `--tail N`: **出力の先頭/末尾 N 件**に絞る (両モード・Unix 流)。
- `--preview [N]`: 一覧で各会話の本文プレビュー。`N`=先頭 N 行 / `--preview=-N`=末尾 N 行 / 単体=既定 10 行。各行頭に `[role HH:MM]`。
- 各会話に**サイズ列**(会話本体ファイルのバイト数を `696K`/`2.4M` 風に。`--json` は正確な `bytes` 整数)。
- `--open [cursor|code]`: 出力をエディタの untitled バッファで開く (全モード。下記)。
- `--long` (`-l`): 一覧に**モデル列**を追加 (cursor/copilot は記録値、claude は jsonl・codex は rollout head から取得)。既定は省略。
- **archived/hidden は既定で常に表示** (除外しない・印のみ)。由来末尾に `*`。`--long` では claude のみ
  `*c`(Cursor で hidden) `*v`(VS Code) `*cv`(両方)、codex/cursor/copilot は `*`。`--workspaces` は `arch` 列に `-N`。
- `--include-subagents`: 既定で除外している subagent を含める (codex の subagent スレッド + cursor の subagentComposerIds)。
- `--json`: 機械可読の構造化 JSON (番号→WS / id 解決などに使う。dump はメッセージ配列)。

## エディタのバッファで開く

`--open` フラグ、またはパイプで、出力を **Cursor / VSCode の untitled バッファ**(ファイル非紐付け)に開ける。
list / `--workspaces` / `--dump` どのモードでも使える:

```bash
python3 <library_path>/scripts/chat-list.py --dump <id> --open        # = cursor のバッファ
python3 <library_path>/scripts/chat-list.py --workspaces --open code  # VSCode のバッファ
python3 <library_path>/scripts/chat-list.py --dump <id> | cursor -    # パイプでも同じ
```

`--open` は出力先の選択 (エディタ buffer)。既定 cursor、`--open code` で VSCode、不在エディタ名はエラー。
長文 dump は chat に貼らず buffer か、リダイレクト `> file` に流す。

## 自然言語 → セレクタの解決指針

- 「○○ の WS の履歴」: `--path ○○` (部分一致)。複数該当なら `--workspaces` で候補提示 → ユーザーに選ばせる。
  複数 WS をまとめて見るなら `--path a --path b` / `--path a,b`。完全一致が要るなら `--exact`。
- 「WS の N 番」: `--workspaces` の行番号 (`#`) で WS を指す指示には、その番号の**行の path を引いて**
  `--path <path> --exact` に渡す (番号は表示ごとに振り直す不安定キー。確定は path)。`--json` の `cwd` で機械的に引ける。
- 「(会話の) N 番を全部見せて」「○○ という会話を出して」: 一覧の番号やタイトルから**会話 id を特定**し、
  `--dump <id>` で出す。**実行前に** 対象 1 件の title・開始時刻・本文プレビュー (`--preview` 付き一覧など) を
  見せて確認を取る。Cursor 利用中なら `--dump <id> --open` でバッファに開くのが楽。
- 「○○ を含む会話」(中身で探す): `--grep ○○` (本文全文検索)。タイトルだけなら `--title ○○`。
- 番号 (`#`) は会話一覧・WS 一覧とも**表示ごとに振り直す不安定キー**。確定は必ず id か WS の path。
- 大量・大容量 dump はそのまま貼らず、`--open` / リダイレクトで開くか、要点だけ抜粋する。

## 補足

- user global command。どの WS からでも起動できる (既定はその cwd の WS)。
- 開始時刻は会話本体の timestamp が正本 (ファイル mtime は Dropbox 同期で揃うため使わない) — コア実装済み。
- データ源 (コア実装済み・読み取り専用): claude=`~/.claude/projects/*.jsonl` / codex=`~/.codex/sqlite/state_5.sqlite` /
  cursor=`Cursor/…/globalStorage/state.vscdb` / copilot=`Code/…/workspaceStorage/<hash>/chatSessions/*` + CLI は `~/.copilot/`。
  WAL の sqlite は app の起動/終了どちらでも読めるよう mode=ro→immutable フォールバックで開く。
- archive フラグもローカルから読む (codex=threads.archived / claude=editor の hiddenSessionIds /
  cursor=composerHeaders.isArchived / copilot=agentSessions cache・CLI は data.db workspaces.archived_at)。
