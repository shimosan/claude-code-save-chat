---
description: claude-code と codex の会話履歴を横断で列挙・閲覧する (読み取り専用)。既定は現在の WS の統合履歴を時系列で。WS 一覧・各会話の先頭/末尾プレビュー・特定会話の全文 dump も可能。
allowed-tools: ["Bash", "Read"]
argument-hint: "[--ws <名前>] [--workspaces] [--dump <id|番号>] [--title <語>] [--grep <語>] [--head N|--tail N] [--tool claude|codex] [--since <日付>] [--sort count|name] [--open]"
---

# /chat-list — 会話履歴の横断リスト (Claude Code 皮)

library の決定的コア `scripts/chat-list.py` に委譲する thin なエントリポイント。
**仕様 (列挙ロジック・データ源・出力形式) をこのファイルに複製しない。**

claude-code と codex の会話履歴を横断で**列挙・閲覧するだけ** (読み取り専用)。要約・引き継ぎ
(resume) は対象外 (将来レイヤ)。

## 役割分担 (重要)

- **コア (`scripts/chat-list.py`, 決定的)**: セレクタは**確定値のみ**受ける (`--ws` は cwd パス /
  部分一致語、`--dump` は会話 id)。LLM 推論ゼロ・読み取り専用。
- **皮 (この agent)**: ユーザーの**自然言語 → 確定セレクタへの解決**を担う。曖昧な指定は
  `--workspaces` や一覧で候補を出して絞り、**`--dump` の前は対象の title / 開始時刻 / プレビューを
  見せてユーザーの確認を取る** (安全はこの確認で担保)。

## `<library_path>` の解決

`scripts/chat-list.py` を含むなら現在の workspace を使う。無ければ `~/.claude/CLAUDE.md` の
「ホスト情報」セクションの `library_path` から読む (未移行端末では旧 `~/.claude/CLAUDE.local.md`)。
どちらも無ければユーザーに尋ねる。パスを捏造しない。script が読めない場合は中断して報告する。

## 起動

`python3 <library_path>/scripts/chat-list.py [options]` を Bash で実行する。
**出力 (一覧そのもの) を提示する — 散文サマリーに要約し直さない。** 各行 (`#`・時刻・由来・ID・タイトル、
`--grep`/`--head`/`--tail` の一致・プレビュー行) はユーザーが次に叩く手がかり (`--dump <id>`・WS 選択など)
なので、**番号と ID を残したまま見せる**。先頭に 1〜2 行の要約コメントを添えるのは可。件数が多くても行を
散文に潰さず一覧を出す (必要なら「関連分に絞る/上位 N 行に限る」と述べてから絞る)。
オプションの正本は `--help`。主なもの:

- 既定 (引数なし): **現在の cwd の WS の統合履歴**を時系列で。
- `--ws <値>`: 別 WS を対象に。`/` 始まりは絶対パス (厳密)、それ以外は cwd 部分一致。
  曖昧で複数 WS にまたがる時は、まず `--workspaces` を出して候補を確定してから渡す。
- `--all-ws`: WS で絞らず全件。
- `--head N` / `--tail N`: 各会話の先頭/末尾 N 行を併記 (本体を読む)。
- `--workspaces`: WS 一覧 (各 WS のチャット数・期間の 1 行概要)。
- `--dump <id>`: 指定会話の全文。既定 stdout、`--out FILE` でファイル、`--open` でエディタ buffer、`--raw` で生 jsonl。
- フィルタ: `--tool claude|codex` / `--since YYYY-MM-DD`。
  - `--title <語>`: タイトル部分一致 (メタのみ・高速)。
  - `--grep <語>`: **本文 (会話の中身) を全文検索**し一致行も表示 (本文を読むので遅め。`--ws` スコープ内のみ)。
- `--ws` は既定一覧でも `--workspaces` でも効く WS 限定子 (`--workspaces --ws GPU` で census を絞る)。
  **`--all-ws` とは排他** (同時指定はエラー)。
- `--sort last|count|name|first`: `--workspaces` の並び替え (既定 last=最終活動↓)。
- `--open [cursor|code]`: 出力をエディタの untitled バッファで開く (list / workspaces / dump 全モード。下記)。
- `--include-subagents` / `--include-archived`: 既定で除外している codex の subagent / archived を含める
  (archived は codex のみ。`--workspaces` の census は常に `⊘N` で archived を別表示)。
- `--format json`: 機械可読 (番号→WS / id 解決などに使う)。
- 細かい調整: `--limit N` (会話一覧を末尾 N 件に。`--workspaces` には効かない)、`--ws-match exact|basename|substring` (`--ws` のマッチ方式を上書き。既定は厳密 or basename 一致)。

## エディタのバッファで開く

`--open` フラグ、またはパイプで、出力を **Cursor / VSCode の untitled バッファ**(ファイル非紐付け)に開ける。
list / `--workspaces` / `--dump` どのモードでも使える:

```bash
python3 <library_path>/scripts/chat-list.py --dump <id> --open        # = cursor のバッファ
python3 <library_path>/scripts/chat-list.py --workspaces --open code  # VSCode のバッファ
python3 <library_path>/scripts/chat-list.py --dump <id> | cursor -    # パイプでも同じ
```

`--open` は `--out FILE` の兄弟 (出力先の選択)。既定 cursor、`--open code` で VSCode、不在エディタ名はエラー。
長文 dump は chat に貼らず buffer か `--out` に流す。

## 自然言語 → セレクタの解決指針

- 「○○ の WS の履歴」: `--ws ○○` (部分一致)。複数該当なら `--workspaces` で候補提示 → ユーザーに選ばせる。
  複数 WS をまとめて見るなら `--ws a --ws b` / `--ws a,b`。
- 「WS の N 番」: `--workspaces` の行番号 (`#`) で WS を指す指示には、その番号の**行の path を引いて**
  `--ws <path>` に渡す (番号は表示ごとに振り直す不安定キー。確定は path)。`--format json` の `i` で機械的に引ける。
- 「(会話の) N 番を全部見せて」「○○ という会話を出して」: 一覧の番号やタイトルから**会話 id を特定**し、
  `--dump <id>` で出す。**実行前に** 対象 1 件の title・開始時刻・末尾数行 (`--tail` 付き一覧など) を
  見せて確認を取る。Cursor 利用中なら `--dump <id> --open` でバッファに開くのが楽。
- 「○○ を含む会話」(中身で探す): `--grep ○○` (本文全文検索)。タイトルだけなら `--title ○○`。
- 番号 (`#`) は会話一覧・WS 一覧とも**表示ごとに振り直す不安定キー**。確定は必ず id か WS の path。
- 大量・大容量 dump はそのまま貼らず、`--open` / `--out` で開くか、要点だけ抜粋する。

## 補足

- user global command。どの WS からでも起動できる (既定はその cwd の WS)。
- 開始時刻は会話本体の timestamp が正本 (ファイル mtime は Dropbox 同期で揃うため使わない) — コア実装済み。
- codex は `~/.codex/sqlite/state_5.sqlite` の目録、claude は `~/.claude/projects/` の本体を読む (コア実装済み)。
