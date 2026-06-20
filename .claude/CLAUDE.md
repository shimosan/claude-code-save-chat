# Claude Code — library repo の保守ルール

この repo は Claude Code / Codex / Copilot 等の設定を複数端末へ配布・同期する library。
ここは配布物そのものではなく、library を保守するための project memory。

## 構造
- `dotclaude/` — 各端末の `~/.claude/` へ deploy する Claude Code 原本。
  - `dotclaude/CLAUDE.md` → `~/.claude/CLAUDE.md`(共有ルール + 端末設定 + メモリを統合した管理ブロック構造。1 ファイル。旧 `CLAUDE.local.md` はこの library の host/folder 情報用途では使わず、本ファイルへ統合)
  - `dotclaude/commands/*.md` → `~/.claude/commands/` へ deploy する slash command。
- `dotcodex/` — 各端末の `~/.codex/` へ deploy する Codex 原本。
  - `dotcodex/AGENTS.md` → `~/.codex/AGENTS.md`(Claude Code 側ルール参照 adapter)
  - `dotcodex/skills/*/SKILL.md` → `~/.codex/skills/*/SKILL.md`
- `copilot/` — VS Code + GitHub Copilot 向け prompt 原本。
- `scripts/` — workflow の正本 (`save-chat-core.md`, `config-update.md` 等) と補助スクリプト。
  **非配布** (library 単一コピー)。各端末の薄い皮が `library_path` 経由で実行時に読む。
- `local/`, `notes/`, `scratch/` — gitignored なローカル領域。

## 編集の正
- 共有ルール・コマンド・skill の編集の正は library 側(`dotclaude/`, `dotcodex/`, `copilot/`)。
  端末側(`~/.claude/`, `~/.codex/`, VS Code User prompts 等)を直接いじったら library へ戻す。
- save-chat / config-manager は「core (正本、`scripts/`) + 薄い皮 (各 deploy フォルダ)」の 2 層。
  仕様・workflow を直すのは core、起動形態や platform binding (source / model / session_id の
  取得法) を直すのは皮。皮に仕様を複製しない。
- load の手順と diff/merge ポリシーは `dotclaude/CLAUDE.md` の「配布 (load)」を参照(save は廃止 — 端末→library の書き戻しはしない)。
- `dotclaude/CLAUDE.md` は subfolder ゆえ自動ロードされない。これは意図的 —
  編集対象(同期マスター)が自身を制御しないようにするため。
- `dotcodex/AGENTS.md` は配布原本。`dotcodex/` 配下で作業する時に Codex が読んでも、
  library repo の保守ルールはこの `.claude/CLAUDE.md` が正。
- 詳細は README.md。

## ローカル領域の使い分け
- `local/` は machine inventory、private policy、private recipes など、継続参照する軽いローカル知識置き場。
  作業前バックアップ、退避コピー、実験版、旧実体の保全は原則 `scratch/` に置く。
- `local/` に backup を置くのは、継続的に参照する端末固有資料として明確な理由がある場合に限る。
  迷う場合は `scratch/` を使う。
- `notes/`(開発メモ・gitignored)の 3 層運用ルール(日付付き note / `ideas.md` / `todo.md`)と
  テーマ別索引は `notes/README.md` を参照する。notes を作成・更新する時はそれに従う。

## 管理ブロックのマーカー検出規約
- `~/.claude/CLAUDE.md`(配布原本は `dotclaude/CLAUDE.md`)の管理ブロックは、行頭が `<!--` で
  `claude-library:begin` / `claude-library:end` を含む **2 行だけ**が実体マーカー。これがゾーン境界
  (S/L と M、ユーザー自由エリア)を画定する。
- **配布原本の本文 (prose) では、このコメント形マーカーを再現しない。** マーカーに言及する時は
  `claude-library:begin` のようにコード span で書く。理由: load/merge や snapshot がマーカーを探す時、
  prose の例示が混じると素朴な検索で誤検出する(過去に prose の言及行を end マーカーと誤認した実績あり)。
- 検出は `grep -n '<!-- claude-library:'`(コメント開き + namespace)で行頭マーカー2行だけを一意に拾う。
  単なる `claude-library:end` の substring 検索は prose もヒットするので使わない。
- load/merge でゾーンを分ける時は、マーカー行か `## ホスト情報` 見出し(行頭一致・ブロック内で一意)を
  境界に使い、行番号のハードコードに依存しない。merge 後は L+M が旧ファイルと byte 一致するか diff で検証する。
- snapshot script (`config-snapshot-{mac,win}.py`) の `has_library_island` は、この実体マーカー有無を
  記録する **歴史的フィールド名**(「island」は旧称「ライブラリ島」の名残。改名すると過去 snapshot と
  drift が出るため据え置き)。

## Windows PowerShell の UTF-8 読み取り
- Windows PowerShell 5.1 では BOM なし UTF-8 を既定 encoding で正しく読めないことがある。
- この library の管理対象テキスト (`.md`, `.json`, `.jsonc`, `.prompt.md`, `SKILL.md`,
  `AGENTS.md`, `CLAUDE.md`) を `Get-Content` で読む時は `-Encoding UTF8` を明示する。
- 任意の外部ファイルには、そのファイルの実 encoding を確認してから使う。

## Codex Git 操作
- Codex sandbox では `.git` が read-only になりうる。`git status` / `git diff` / `git log` など
  read-only 操作は通常実行する。
- `git add` / `git commit` / `git mv` / `git rm` / `git tag` など `.git` に書く操作は、
  ユーザーが明示指示した時だけ行い、実行時は sandbox 内で試さず最初から権限付きで実行する。
- `git push` はユーザーの明示指示がある時だけ行う。
